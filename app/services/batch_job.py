"""
Batch Cron Job — Daily horoscope generation for all users.

Schedule: 00:05 IST daily (= 18:35 UTC previous day)
Trigger:  APScheduler (runs inside the FastAPI process)

Flow:
  1. Compute today's global transit once (pyswisseph — zero cost)
  2. Fetch all users with birth details from MongoDB
  3. For each user:
       a. Load or compute natal profile (API call once per lifetime)
       b. Run rule engine
       c. Render templates
       d. Upsert result into MongoDB daily_horoscopes
  4. Save batch run status (success/failure counts)

No per-user API call for transit.
API call only for natal (once per user lifetime, cached after that).
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from app.models.natal_profile import NatalProfile
from app.services.transit_service import (
    compute_transit_for_date, _extract_sign_map, _extract_retrograde_map, _ist_today,
)
from app.services.natal_service import (
    get_natal_profile,
    compute_natal_profile,
    _normalise_dob,
    _normalise_tob,
    _detect_active_dasha,
    _detect_active_antardasha,
)
from app.services.horoscope_service import generate_horoscope_for_natal
import app.db.mongodb as db

# Re-detect the active dasha lord if the stored natal profile is older than this
DASHA_REFRESH_DAYS = 30

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# ─────────────────────────────────────────────
# Per-user processing
# ─────────────────────────────────────────────

async def _process_user(
    user: Dict,
    transit_sign_map: Dict[str, int],
    transit_retrograde: Dict[str, bool],
    date_str: str,
) -> Dict:
    """
    Generate and store today's horoscope for a single user.

    Returns a result dict with status and optional error message.
    """
    user_id = user.get("user_id", str(user.get("_id", "")))
    name = user.get("name", "Unknown")

    result = {"user_id": user_id, "name": name, "status": "ok", "error": None}

    try:
        # ── 1. Natal profile ──────────────────────────────────────────
        natal: Optional[NatalProfile] = get_natal_profile(user_id)

        if natal is None:
            # Try MongoDB
            db_doc = await db.get_natal_profile_from_db(user_id)
            if db_doc:
                natal = NatalProfile(**db_doc)

        if natal is None:
            # Compute fresh via VedicAstroAPI (only once per user)
            raw_dob = user.get("dob")
            raw_tob = user.get("tob")
            pob = user.get("pob", "")

            if not raw_dob or not raw_tob or not pob:
                result.update({"status": "skipped", "error": "Missing birth details"})
                return result

            dob = _normalise_dob(str(raw_dob))
            tob = _normalise_tob(str(raw_tob))

            natal = compute_natal_profile(
                user_id=user_id,
                name=name,
                dob=dob,
                tob=tob,
                pob=pob,
            )
            # Persist natal to MongoDB for future runs
            await db.save_natal_profile(user_id, natal.model_dump())
            logger.info(f"[Batch] Natal computed and saved for {user_id} ({name})")

        # ── 1b. Refresh active dasha lord monthly ─────────────────────
        # planet_houses/house_lords never change after birth, but the
        # ACTIVE dasha lord advances every few months/years. Re-detect it
        # from the API if the stored profile is older than DASHA_REFRESH_DAYS.
        try:
            age_days = (datetime.now(IST) - natal.computed_at.replace(tzinfo=IST)).days
            if age_days > DASHA_REFRESH_DAYS:
                from app.services.astro_api import vedic_api
                maha_raw  = vedic_api.fetch_maha_dasha(natal.dob, natal.tob, natal.lat, natal.lon, natal.tz)
                antar_raw = vedic_api.fetch_antara_dasha(natal.dob, natal.tob, natal.lat, natal.lon, natal.tz)
                new_maha  = _detect_active_dasha(maha_raw)
                new_anta  = _detect_active_antardasha(antar_raw, maha_lord=new_maha)
                if new_maha and (new_maha != natal.active_maha_dasha_lord
                                 or new_anta != natal.active_anta_dasha_lord):
                    natal = natal.model_copy(update={
                        "active_maha_dasha_lord": new_maha,
                        "active_anta_dasha_lord": new_anta,
                        "computed_at": datetime.now(IST),
                    })
                    await db.save_natal_profile(user_id, natal.model_dump())
                    logger.info(
                        f"[Batch] Dasha refreshed for {user_id}: "
                        f"{new_maha}/{new_anta}"
                    )
        except Exception as e:
            logger.warning(f"[Batch] Dasha refresh skipped for {user_id}: {e}")

        # ── 2. Horoscope generation ───────────────────────────────────
        # Delegate to the canonical service function so batch output always
        # stays in sync with the live API endpoint (same SCORE_SCALE,
        # same templates, same languages — English + Hindi).
        # Transit was already computed + cached in Redis above, so
        # generate_horoscope_for_natal() gets a cache HIT — no extra I/O.
        horoscope = generate_horoscope_for_natal(natal, date_override=date_str)

        # ── 3. Persist to MongoDB ────────────────────────────────────
        await db.save_daily_horoscope(user_id, date_str, horoscope.model_dump())

    except Exception as e:
        logger.error(f"[Batch] Failed for user {user_id} ({name}): {e}", exc_info=True)
        result.update({"status": "error", "error": str(e)})

    return result


# ─────────────────────────────────────────────
# Main batch function
# ─────────────────────────────────────────────

async def run_daily_batch(date_override: Optional[str] = None) -> Dict:
    """
    Main entry point for the daily batch job.

    Args:
        date_override: YYYY-MM-DD string (default: today in IST)

    Returns:
        Summary dict with counts and timing info.
    """
    started_at = datetime.now(IST)
    date_str = date_override or started_at.strftime("%Y-%m-%d")

    logger.info(f"[Batch] Starting daily batch for {date_str} at {started_at.isoformat()}")

    # ── 1. Compute global transit once (sign map + retrograde) ──────
    transit_date = datetime.strptime(date_str, "%Y-%m-%d")
    full_transit = compute_transit_for_date(transit_date)
    transit_sign_map  = _extract_sign_map(full_transit)
    transit_retrograde = _extract_retrograde_map(full_transit)
    retro_list = [p for p, r in transit_retrograde.items() if r]
    logger.info(f"[Batch] Transit computed: {transit_sign_map}")
    logger.info(f"[Batch] Retrograde today: {retro_list if retro_list else 'none'}")

    # Also cache in Redis so the API endpoint can read it
    from app.services.transit_service import get_redis
    import json
    from config import get_settings
    settings = get_settings()
    r = get_redis()
    if r:
        try:
            r.setex(f"transit:{date_str}", settings.REDIS_TRANSIT_TTL, json.dumps(transit_sign_map))
            r.setex(f"transit_full:{date_str}", settings.REDIS_TRANSIT_TTL, json.dumps(full_transit))
            logger.info("[Batch] Transit cached in Redis")
        except Exception as e:
            logger.warning(f"[Batch] Redis write error: {e}")

    # ── 2. Load all eligible users ───────────────────────────────────
    users = await db.get_all_users_with_birth_details()

    if not users:
        logger.warning("[Batch] No users with birth details found in MongoDB")
        summary = {
            "date": date_str,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(IST).isoformat(),
            "total_users": 0,
            "success": 0,
            "skipped": 0,
            "errors": 0,
            "source": "batch_cron",
        }
        await db.save_batch_run_status(summary)
        return summary

    total = len(users)
    logger.info(f"[Batch] Processing {total} users")

    # ── 3. Process users concurrently (in batches to avoid overload) ─
    results = await _process_users_in_batches(
        users, transit_sign_map, transit_retrograde, date_str, batch_size=20,
    )

    # ── 4. Tally results ─────────────────────────────────────────────
    success = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")

    finished_at = datetime.now(IST)
    duration_secs = (finished_at - started_at).total_seconds()

    summary = {
        "date": date_str,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration_secs, 1),
        "total_users": total,
        "success": success,
        "skipped": skipped,
        "errors": errors,
        "source": "batch_cron",
        "error_details": [
            {"user_id": r["user_id"], "name": r["name"], "error": r["error"]}
            for r in results if r["status"] == "error"
        ],
    }

    logger.info(
        f"[Batch] Finished {date_str}: {success} ok, {skipped} skipped, {errors} errors "
        f"({duration_secs:.1f}s for {total} users)"
    )

    # Persist batch run record
    await db.save_batch_run_status(summary)

    return summary


async def _process_users_in_batches(
    users: List[Dict],
    transit_sign_map: Dict[str, int],
    transit_retrograde: Dict[str, bool],
    date_str: str,
    batch_size: int = 20,
) -> List[Dict]:
    """Process users in concurrent batches to avoid overwhelming the API."""
    all_results = []
    for i in range(0, len(users), batch_size):
        batch = users[i: i + batch_size]
        tasks = [_process_user(u, transit_sign_map, transit_retrograde, date_str) for u in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=False)
        all_results.extend(batch_results)
        logger.info(
            f"[Batch] Processed {min(i + batch_size, len(users))}/{len(users)} users"
        )
    return all_results
