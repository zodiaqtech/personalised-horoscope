"""
API routes for the Personalised Horoscope Engine.

Endpoint groups:

  /health               — Service health
  /natal/*              — Natal profile compute + read
  /horoscope/{user_id}  — Read pre-generated daily horoscope from MongoDB
  /transit/today        — Inspect today's transit (pyswisseph, Redis-cached)
  /batch/*              — Batch job status + manual trigger
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from app.models.natal_profile import NatalComputeRequest
from app.models.horoscope import HoroscopeResponse, TransitResponse
from app.services.natal_service import compute_natal_profile, get_natal_profile
from app.services.transit_service import get_today_transit, get_today_transit_full, get_redis
import app.db.mongodb as db

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
router = APIRouter()


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@router.get("/health")
async def health_check():
    redis_ok = False
    try:
        r = get_redis()
        if r:
            r.ping()
            redis_ok = True
    except Exception:
        pass

    return {
        "status": "ok",
        "timestamp": datetime.now(IST).isoformat(),
        "redis": "connected" if redis_ok else "unavailable",
        "mongodb": "connected" if db.is_connected() else "disabled",
        "transit_source": "pyswisseph (local)",
    }


# ─────────────────────────────────────────────
# Natal Profile
# ─────────────────────────────────────────────

@router.post("/natal/compute")
async def compute_natal(request: NatalComputeRequest):
    """
    Compute and store a natal profile for a user.

    Called once when a user registers or updates birth details.
    Result is persisted to MongoDB (when enabled) and in-memory cache.
    """
    try:
        profile = compute_natal_profile(
            user_id=request.user_id,
            name=request.name,
            dob=request.dob,
            tob=request.tob,
            pob=request.pob,
        )
        # Persist to MongoDB
        await db.save_natal_profile(request.user_id, profile.model_dump())

        return {
            "status": "success",
            "user_id": profile.user_id,
            "lagna_sign": profile.lagna_sign,
            "active_dasha": profile.active_maha_dasha_lord,
            "rajayoga": profile.rajayoga_present,
            "yoga_planets": profile.yoga_planets,
            "planet_houses": profile.planet_houses,
            "house_lords": profile.house_lords,
            "planet_strengths": profile.planet_strengths,
            "lagna_strength": profile.lagna_strength,
            "computed_at": profile.computed_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Natal compute failed for {request.user_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/natal/{user_id}")
async def get_natal(user_id: str):
    """Retrieve a previously computed natal profile (memory → MongoDB fallback)."""
    profile = get_natal_profile(user_id)
    if profile:
        return profile.model_dump()

    # Try MongoDB
    doc = await db.get_natal_profile_from_db(user_id)
    if doc:
        return doc

    raise HTTPException(
        status_code=404,
        detail=f"Natal profile not found for user_id={user_id}. Call POST /natal/compute first.",
    )


# ─────────────────────────────────────────────
# Horoscope — READ from MongoDB (batch pre-generated)
# ─────────────────────────────────────────────

@router.get("/horoscope/{user_id}", response_model=HoroscopeResponse)
async def get_horoscope(
    user_id: str,
    date: Optional[str] = Query(None, description="Date YYYY-MM-DD (default: today IST)"),
):
    """
    Read the pre-generated daily horoscope for a user from MongoDB.

    Horoscopes are generated in bulk at 00:05 IST by the daily cron job.
    This endpoint is a pure DB read — no computation on request.

    Returns 404 if the batch hasn't run yet for today.
    """
    today_str = date or datetime.now(IST).strftime("%Y-%m-%d")

    doc = await db.get_daily_horoscope_from_db(user_id, today_str)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No horoscope found for user_id={user_id} on {today_str}. "
                "The daily batch runs at 00:05 IST. "
                "Call POST /batch/trigger to generate immediately."
            ),
        )
    return doc


# ─────────────────────────────────────────────
# Transit — pyswisseph (local, zero cost)
# ─────────────────────────────────────────────

@router.get("/transit/today")
async def get_transit_today(
    date: Optional[str] = Query(None, description="Date YYYY-MM-DD (default: today IST)"),
    full: bool = Query(False, description="Return full detail (longitude, degree) per planet"),
):
    """
    Get today's global transit planet positions.

    Computed locally using Swiss Ephemeris (Lahiri sidereal, TRUE_NODE for Rahu).
    Cached in Redis for 24 hours — zero API cost.

    full=false (default): {planet: sign_number}
    full=true: {planet: {longitude, sign, sign_name, degree}}
    """
    try:
        today_str = date or datetime.now(IST).strftime("%Y-%m-%d")

        if full:
            data = get_today_transit_full(date_override=today_str)
            source = "pyswisseph+redis" if _is_redis_cached(f"transit_full:{today_str}") else "pyswisseph"
            return {
                "date": today_str,
                "ayanamsa": "Lahiri",
                "node_type": "TRUE_NODE",
                "positions": data,
                "source": source,
            }
        else:
            sign_map = get_today_transit(date_override=today_str)
            source = "pyswisseph+redis" if _is_redis_cached(f"transit:{today_str}") else "pyswisseph"
            return TransitResponse(
                date=today_str,
                transit_houses=sign_map,
                source=source,
            )
    except Exception as e:
        logger.exception("Transit fetch failed")
        raise HTTPException(status_code=500, detail=str(e))


def _is_redis_cached(key: str) -> bool:
    r = get_redis()
    if r:
        try:
            return bool(r.exists(key))
        except Exception:
            pass
    return False


# ─────────────────────────────────────────────
# Batch — status and manual trigger
# ─────────────────────────────────────────────

@router.get("/batch/status")
async def get_batch_status(
    date: Optional[str] = Query(None, description="Date YYYY-MM-DD (default: today IST)"),
):
    """
    Check the status of the daily batch job.

    Returns:
      - Last batch run metadata (from MongoDB batch_runs collection)
      - Count of horoscopes generated for today
    """
    today_str = date or datetime.now(IST).strftime("%Y-%m-%d")
    last_run = await db.get_last_batch_run()
    count = await db.count_horoscopes_for_date(today_str)

    return {
        "today": today_str,
        "horoscopes_generated_today": count,
        "last_batch_run": last_run,
        "next_scheduled": "00:05 IST daily",
    }


@router.post("/batch/trigger")
async def trigger_batch(
    background_tasks: BackgroundTasks,
    date: Optional[str] = Query(None, description="Date YYYY-MM-DD (default: today IST)"),
):
    """
    Manually trigger the daily batch job.

    Runs asynchronously in the background — returns immediately.
    Use GET /batch/status to monitor progress.
    """
    today_str = date or datetime.now(IST).strftime("%Y-%m-%d")

    async def _run():
        from app.services.batch_job import run_daily_batch
        await run_daily_batch(date_override=today_str)

    background_tasks.add_task(_run)

    return {
        "status": "triggered",
        "date": today_str,
        "message": "Batch job started in background. Check /api/v1/batch/status for progress.",
    }
