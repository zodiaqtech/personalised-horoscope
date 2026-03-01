"""
MongoDB client — Motor async driver.

MONGODB_ENABLED=False → all stubs return None/False (safe for dev).
MONGODB_ENABLED=True  → real reads/writes to myAppDB.

Collections:
  users              — existing user collection (READ-ONLY)
  natal_profiles     — one document per user (WRITE: horoscope engine)
  daily_horoscopes   — one document per user per day (WRITE: batch cron)
"""
import logging
from typing import AsyncIterator, Dict, List, Optional, Any

logger = logging.getLogger(__name__)

_client = None
_db = None


# ─────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────

async def connect_to_mongo(uri: str, db_name: str) -> None:
    global _client, _db
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        _client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        _db = _client[db_name]
        await _client.admin.command("ping")
        logger.info(f"MongoDB connected: {db_name}")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        _client = None
        _db = None


async def disconnect_from_mongo() -> None:
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB disconnected")


def is_connected() -> bool:
    return _db is not None


# ─────────────────────────────────────────────
# Users collection (READ-ONLY)
# ─────────────────────────────────────────────

async def get_user_birth_details(user_id: str) -> Optional[Dict]:
    """
    Fetch a single user's birth details from the users collection.
    Field mapping: name, dob (ISO date), tob (time string), pob (city)
    """
    if not is_connected():
        return None
    try:
        from bson import ObjectId
        query = {"_id": ObjectId(user_id)} if len(str(user_id)) == 24 else {"_id": user_id}
        doc = await _db.users.find_one(query, {"name": 1, "dob": 1, "tob": 1, "pob": 1})
        return doc
    except Exception as e:
        logger.error(f"get_user_birth_details({user_id}): {e}")
        return None


async def get_all_users_with_birth_details() -> List[Dict]:
    """
    Return all users who have dob, tob, and pob filled in.
    Used by the batch cron job to iterate over eligible users.
    """
    if not is_connected():
        logger.warning("MongoDB not connected — cannot fetch users")
        return []
    try:
        cursor = _db.users.find(
            {
                "dob": {"$exists": True, "$ne": None},
                "tob": {"$exists": True, "$ne": None},
                "pob": {"$exists": True, "$ne": None},
            },
            {"_id": 1, "name": 1, "dob": 1, "tob": 1, "pob": 1},
        )
        users = []
        async for doc in cursor:
            doc["user_id"] = str(doc["_id"])
            users.append(doc)
        logger.info(f"Found {len(users)} users with birth details")
        return users
    except Exception as e:
        logger.error(f"get_all_users_with_birth_details: {e}")
        return []


# ─────────────────────────────────────────────
# Natal Profiles collection
# ─────────────────────────────────────────────

async def save_natal_profile(user_id: str, profile_dict: Dict[str, Any]) -> bool:
    if not is_connected():
        logger.debug("MongoDB not connected — natal profile not saved to DB")
        return False
    try:
        # Convert datetime objects to ISO strings for Mongo
        doc = _serialise(profile_dict)
        doc["user_id"] = user_id
        await _db.natal_profiles.replace_one(
            {"user_id": user_id},
            doc,
            upsert=True,
        )
        logger.debug(f"Natal profile saved for {user_id}")
        return True
    except Exception as e:
        logger.error(f"save_natal_profile({user_id}): {e}")
        return False


async def get_natal_profile_from_db(user_id: str) -> Optional[Dict]:
    if not is_connected():
        return None
    try:
        doc = await _db.natal_profiles.find_one({"user_id": user_id}, {"_id": 0})
        return doc
    except Exception as e:
        logger.error(f"get_natal_profile_from_db({user_id}): {e}")
        return None


# ─────────────────────────────────────────────
# Daily Horoscopes collection
# ─────────────────────────────────────────────

async def save_daily_horoscope(user_id: str, date: str, horoscope_dict: Dict) -> bool:
    """
    Upsert today's horoscope for a user.
    Document keyed on (user_id, date) — safe to call multiple times.
    Busts the Redis cache so the next read picks up the fresh document.
    """
    if not is_connected():
        logger.debug("MongoDB not connected — horoscope not saved to DB")
        return False
    try:
        doc = _serialise(horoscope_dict)
        doc.update({"user_id": user_id, "date": date})
        await _db.daily_horoscopes.replace_one(
            {"user_id": user_id, "date": date},
            doc,
            upsert=True,
        )
        # Bust Redis cache so the next read re-populates with the fresh document
        _redis_delete(f"horoscope:{user_id}:{date}")
        return True
    except Exception as e:
        logger.error(f"save_daily_horoscope({user_id}, {date}): {e}")
        return False


async def get_daily_horoscope_from_db(user_id: str, date: str) -> Optional[Dict]:
    """
    Fetch a stored daily horoscope for a user.

    Cache strategy:
      1. Check Redis (key: horoscope:{user_id}:{date}, TTL 86400s)
      2. On miss → query MongoDB → store result in Redis
      3. Returns None if not yet generated for that date.

    This means only the first request of the day hits MongoDB;
    all subsequent calls are served from Redis (~sub-millisecond).
    """
    import json

    cache_key = f"horoscope:{user_id}:{date}"

    # ── 1. Redis cache check ─────────────────────────────────────
    cached = _redis_get(cache_key)
    if cached is not None:
        try:
            return json.loads(cached)
        except Exception:
            pass  # corrupted entry — fall through to MongoDB

    # ── 2. MongoDB read ──────────────────────────────────────────
    if not is_connected():
        return None
    try:
        doc = await _db.daily_horoscopes.find_one(
            {"user_id": user_id, "date": date}, {"_id": 0}
        )
        # ── 3. Populate Redis cache ──────────────────────────────
        if doc:
            _redis_set(cache_key, json.dumps(doc, default=str), ttl=86400)
        return doc
    except Exception as e:
        logger.error(f"get_daily_horoscope_from_db({user_id}, {date}): {e}")
        return None


async def count_horoscopes_for_date(date: str) -> int:
    """Count how many users have a horoscope stored for the given date."""
    if not is_connected():
        return 0
    try:
        return await _db.daily_horoscopes.count_documents({"date": date})
    except Exception as e:
        logger.error(f"count_horoscopes_for_date({date}): {e}")
        return 0


# ─────────────────────────────────────────────
# Batch job state collection (cron status tracking)
# ─────────────────────────────────────────────

async def save_batch_run_status(status_doc: Dict) -> None:
    """Record the result of a batch cron run in the batch_runs collection."""
    if not is_connected():
        return
    try:
        await _db.batch_runs.insert_one(_serialise(status_doc))
    except Exception as e:
        logger.error(f"save_batch_run_status: {e}")


async def get_last_batch_run() -> Optional[Dict]:
    """Return the most recent batch run record."""
    if not is_connected():
        return None
    try:
        doc = await _db.batch_runs.find_one(
            {}, {"_id": 0}, sort=[("started_at", -1)]
        )
        return doc
    except Exception as e:
        logger.error(f"get_last_batch_run: {e}")
        return None


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_redis():
    """Return a live Redis client, or None if unavailable."""
    try:
        from app.services.transit_service import get_redis
        return get_redis()
    except Exception:
        return None


def _redis_get(key: str) -> Optional[str]:
    """Return the Redis value for key, or None on any error."""
    r = _get_redis()
    if not r:
        return None
    try:
        return r.get(key)
    except Exception:
        return None


def _redis_set(key: str, value: str, ttl: int = 86400) -> None:
    """Set a Redis key with TTL, silently ignoring errors."""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, value)
    except Exception:
        pass


def _redis_delete(key: str) -> None:
    """Delete a Redis key, silently ignoring errors."""
    r = _get_redis()
    if not r:
        return
    try:
        r.delete(key)
    except Exception:
        pass


def _serialise(obj):
    """Recursively convert datetime → ISO string, set → list for MongoDB."""
    from datetime import datetime
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(i) for i in obj]
    if isinstance(obj, set):
        return [_serialise(i) for i in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
