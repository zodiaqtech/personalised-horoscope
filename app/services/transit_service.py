"""
Transit service — zero-cost local ephemeris using pyswisseph.

Replaces the VedicAstroAPI transit call with a local Swiss Ephemeris
computation (Lahiri ayanamsa, sidereal Vedic) — no external API call,
no per-user cost, fully deterministic.

Daily transit result is cached in Redis (key: transit:{YYYY-MM-DD})
with a 24-hour TTL, and also kept in an in-memory dict as fallback.

All users share the same single daily transit record.

Phase 3 additions:
- `is_retrograde` flag added to each planet's position dict
- `get_today_transit_retrograde()` returns {planet: is_retrograde_bool}
  cached under key `transit_retro:{YYYY-MM-DD}`
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

import redis
import swisseph as swe

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─────────────────────────────────────────────
# Swiss Ephemeris — one-time setup
# ─────────────────────────────────────────────

swe.set_sid_mode(swe.SIDM_LAHIRI)

_SWE_PLANETS = {
    "Sun":     swe.SUN,
    "Moon":    swe.MOON,
    "Mars":    swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus":   swe.VENUS,
    "Saturn":  swe.SATURN,
    "Rahu":    swe.TRUE_NODE,
}

SIGNS_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


# ─────────────────────────────────────────────
# Redis client (lazy-init)
# ─────────────────────────────────────────────

_redis_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            _redis_client.ping()
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning(f"Redis not available: {e}. Transit will use in-memory cache only.")
            _redis_client = None
    return _redis_client


# ─────────────────────────────────────────────
# In-memory fallback
# ─────────────────────────────────────────────

_memory_transit_cache: Dict[str, Dict] = {}
_memory_retro_cache: Dict[str, Dict[str, bool]] = {}   # Phase 3


# ─────────────────────────────────────────────
# Swiss Ephemeris computation
# ─────────────────────────────────────────────

def _get_julian_day(year: int, month: int, day: int, hour: float = 0.0) -> float:
    return swe.julday(year, month, day, hour)


def _compute_planet_position(jd: float, planet_code: int) -> dict:
    """
    Compute sidereal longitude for a single planet.

    Returns dict with:
      longitude      – 0–360 (sidereal)
      sign           – 1–12
      sign_name      – e.g. "Gemini"
      degree         – degree within sign (0–29.99)
      is_retrograde  – True if longitudinal speed < 0  ← Phase 3
    """
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
    result = swe.calc_ut(jd, planet_code, flags)

    longitude = result[0][0]               # degrees 0–360
    long_speed = result[0][3]              # longitudinal speed (°/day); < 0 → retrograde
    sign_idx = int(longitude / 30)         # 0-based
    degree_in_sign = longitude % 30

    return {
        "longitude":     round(longitude, 4),
        "sign":          sign_idx + 1,
        "sign_name":     SIGNS_ORDER[sign_idx],
        "degree":        round(degree_in_sign, 4),
        "is_retrograde": long_speed < 0,   # Phase 3
    }


def compute_transit_for_date(date: datetime) -> Dict[str, dict]:
    """
    Compute full daily transit positions using Swiss Ephemeris (Lahiri sidereal).

    Returns:
        Dict mapping planet name → {longitude, sign, sign_name, degree, is_retrograde}
    """
    jd = _get_julian_day(date.year, date.month, date.day, hour=0.0)
    transit_data: Dict[str, dict] = {}

    for name, code in _SWE_PLANETS.items():
        try:
            transit_data[name] = _compute_planet_position(jd, code)
        except Exception as e:
            logger.error(f"Failed to compute position for {name}: {e}")

    # Ketu = exact opposite of Rahu; shares Rahu's retrograde status
    if "Rahu" in transit_data:
        rahu = transit_data["Rahu"]
        ketu_long = (rahu["longitude"] + 180.0) % 360.0
        ketu_sign_idx = int(ketu_long / 30)
        transit_data["Ketu"] = {
            "longitude":     round(ketu_long, 4),
            "sign":          ketu_sign_idx + 1,
            "sign_name":     SIGNS_ORDER[ketu_sign_idx],
            "degree":        round(ketu_long % 30, 4),
            "is_retrograde": rahu.get("is_retrograde", True),  # nodes are retrograde by default
        }

    return transit_data


def _extract_sign_map(transit_data: Dict[str, dict]) -> Dict[str, int]:
    """Convert full transit data → {planet: sign_number} for the rule engine."""
    return {planet: info["sign"] for planet, info in transit_data.items()}


def _extract_retrograde_map(transit_data: Dict[str, dict]) -> Dict[str, bool]:
    """Phase 3: Convert full transit data → {planet: is_retrograde} for the rule engine."""
    return {planet: info.get("is_retrograde", False) for planet, info in transit_data.items()}


# ─────────────────────────────────────────────
# IST helpers
# ─────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


def _ist_today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def get_today_transit(date_override: Optional[str] = None) -> Dict[str, int]:
    """
    Get today's global transit planet sign positions (planet → sign 1-12).

    Source: local pyswisseph (zero API cost).
    Cache: Redis with 86400s TTL, in-memory fallback.
    """
    today_str = date_override or _ist_today()
    redis_key = f"transit:{today_str}"

    r = get_redis()
    if r:
        try:
            cached = r.get(redis_key)
            if cached:
                logger.debug(f"Transit cache HIT (Redis) for {today_str}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis read error: {e}")

    if today_str in _memory_transit_cache:
        logger.debug(f"Transit cache HIT (memory) for {today_str}")
        return _memory_transit_cache[today_str]

    logger.info(f"Computing transit via Swiss Ephemeris for {today_str}")
    date_obj = datetime.strptime(today_str, "%Y-%m-%d")
    full_transit = compute_transit_for_date(date_obj)
    sign_map = _extract_sign_map(full_transit)

    logger.info(f"Transit computed for {today_str}: {sign_map}")

    if r:
        try:
            r.setex(redis_key, settings.REDIS_TRANSIT_TTL, json.dumps(sign_map))
            logger.info(f"Transit cached in Redis: {redis_key}")
        except Exception as e:
            logger.warning(f"Redis write error: {e}")

    _memory_transit_cache[today_str] = sign_map
    return sign_map


def get_today_transit_retrograde(date_override: Optional[str] = None) -> Dict[str, bool]:
    """
    Phase 3: Get retrograde status of all transiting planets for today.

    Returns: {planet_name: is_retrograde_bool}
    Cache: Redis key `transit_retro:{YYYY-MM-DD}` with 86400s TTL.
    """
    today_str = date_override or _ist_today()
    redis_key = f"transit_retro:{today_str}"

    r = get_redis()
    if r:
        try:
            cached = r.get(redis_key)
            if cached:
                logger.debug(f"Transit retrograde cache HIT (Redis) for {today_str}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis read error (retrograde): {e}")

    if today_str in _memory_retro_cache:
        logger.debug(f"Transit retrograde cache HIT (memory) for {today_str}")
        return _memory_retro_cache[today_str]

    # Compute (reuses the same ephemeris call result)
    logger.info(f"Computing transit retrograde for {today_str}")
    date_obj = datetime.strptime(today_str, "%Y-%m-%d")
    full_transit = compute_transit_for_date(date_obj)
    retro_map = _extract_retrograde_map(full_transit)

    if r:
        try:
            r.setex(redis_key, settings.REDIS_TRANSIT_TTL, json.dumps(retro_map))
        except Exception as e:
            logger.warning(f"Redis write error (retrograde): {e}")

    _memory_retro_cache[today_str] = retro_map
    return retro_map


def get_today_transit_full(date_override: Optional[str] = None) -> Dict[str, dict]:
    """
    Same as get_today_transit but returns full detail per planet
    (longitude, sign, sign_name, degree, is_retrograde) — used by the transit API endpoint.
    """
    today_str = date_override or _ist_today()
    full_redis_key = f"transit_full:{today_str}"

    r = get_redis()
    if r:
        try:
            cached = r.get(full_redis_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    date_obj = datetime.strptime(today_str, "%Y-%m-%d")
    full_transit = compute_transit_for_date(date_obj)

    if r:
        try:
            r.setex(full_redis_key, settings.REDIS_TRANSIT_TTL, json.dumps(full_transit))
        except Exception:
            pass

    return full_transit
