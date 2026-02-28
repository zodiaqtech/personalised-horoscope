"""
One-time fix script: patch active_anta_dasha_lord for all existing natal profiles.

Why needed:
  The original _detect_active_antardasha() misread the API response shape
  (expected a flat list, but API returns 9 nested lists of "Maha/Anta" pairs).
  All existing natal_profiles have active_anta_dasha_lord = "".

What this does:
  For each natal_profile in MongoDB:
    1. Calls VedicAstroAPI antar-dasha endpoint (1 call per user)
    2. Extracts the correct antardasha lord using the fixed function
    3. Patches only active_anta_dasha_lord in MongoDB (does not recompute natal)

Run:  python3 fix_antardasha.py
Safe to re-run — skips users already having a non-empty active_anta_dasha_lord.
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("fix_antardasha")


async def main():
    # ── 1. Load config & connect MongoDB ────────────────────────────────────
    from config import get_settings
    settings = get_settings()

    if not settings.MONGODB_ENABLED:
        logger.error("MONGODB_ENABLED=False — set it to True in .env and retry.")
        sys.exit(1)

    from app.db.mongodb import connect_to_mongo
    await connect_to_mongo(settings.MONGODB_URI, settings.MONGODB_DB_NAME)

    import app.db.mongodb as db
    if not db.is_connected():
        logger.error("MongoDB connection failed — check MONGODB_URI in .env")
        sys.exit(1)

    # ── 2. Load all natal profiles ───────────────────────────────────────────
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    mdb = client[settings.MONGODB_DB_NAME]

    cursor = mdb.natal_profiles.find(
        {},
        {"user_id": 1, "dob": 1, "tob": 1, "lat": 1, "lon": 1, "tz": 1,
         "active_maha_dasha_lord": 1, "active_anta_dasha_lord": 1}
    )
    profiles = []
    async for doc in cursor:
        profiles.append(doc)

    total = len(profiles)
    logger.info(f"Found {total} natal profiles to check")

    # ── 3. Patch each one ────────────────────────────────────────────────────
    from app.services.astro_api import vedic_api
    from app.services.natal_service import _detect_active_antardasha

    fixed = 0
    skipped = 0
    errors = 0

    for i, doc in enumerate(profiles, 1):
        user_id   = doc.get("user_id", "")
        dob       = doc.get("dob", "")
        tob       = doc.get("tob", "")
        lat       = doc.get("lat", 0.0)
        lon       = doc.get("lon", 0.0)
        tz        = doc.get("tz", 5.5)
        maha_lord = doc.get("active_maha_dasha_lord", "")
        anta_lord = doc.get("active_anta_dasha_lord", "")

        # Skip if already patched
        if anta_lord:
            logger.info(f"[{i}/{total}] {user_id} — already has anta={anta_lord}, skipping")
            skipped += 1
            continue

        try:
            antar_raw  = vedic_api.fetch_antara_dasha(dob, tob, lat, lon, tz)
            new_anta   = _detect_active_antardasha(antar_raw, maha_lord=maha_lord)

            if not new_anta:
                logger.warning(f"[{i}/{total}] {user_id} — antardasha still empty after fix")
                errors += 1
                continue

            await mdb.natal_profiles.update_one(
                {"user_id": user_id},
                {"$set": {"active_anta_dasha_lord": new_anta}},
            )
            logger.info(f"[{i}/{total}] {user_id} — patched: maha={maha_lord}, anta={new_anta}")
            fixed += 1

        except Exception as e:
            logger.error(f"[{i}/{total}] {user_id} — ERROR: {e}")
            errors += 1

    # ── 4. Summary ───────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info(f"Done. fixed={fixed}  skipped={skipped}  errors={errors}  total={total}")
    logger.info("=" * 60)
    logger.info("Now re-trigger the batch to regenerate horoscopes:")
    logger.info("  curl -s -X POST http://localhost:8001/api/v1/batch/trigger")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
