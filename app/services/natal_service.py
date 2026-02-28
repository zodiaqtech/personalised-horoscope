"""
Natal profile service.

Responsibilities:
- Parse raw VedicAstroAPI planet-details response
- Extract lagna, house lords, planet placements, planet strengths
- Parse planet retrograde status and sidereal longitudes (Phase 2)
- Compute combust status from longitudes (Phase 2)
- Detect active Maha Dasha + Antara Dasha lords (Phase 2)
- Detect Rajayoga
- Cache natal profiles in-memory (MongoDB integration later)
"""
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.models.natal_profile import NatalProfile
from app.services.astro_api import vedic_api
from app.services.geo_service import resolve_city

logger = logging.getLogger(__name__)

# In-memory natal profile cache: user_id → NatalProfile
_natal_cache: Dict[str, NatalProfile] = {}

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

SIGN_TO_NUMBER = {
    "Aries": 1, "Taurus": 2, "Gemini": 3, "Cancer": 4,
    "Leo": 5, "Virgo": 6, "Libra": 7, "Scorpio": 8,
    "Sagittarius": 9, "Capricorn": 10, "Aquarius": 11, "Pisces": 12,
}

SIGN_LORD: Dict[str, str] = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

SIGNS_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

EXALTATION: Dict[str, str] = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces",
    "Saturn": "Libra", "Rahu": "Taurus", "Ketu": "Scorpio",
}

OWN_SIGNS: Dict[str, List[str]] = {
    "Sun": ["Leo"], "Moon": ["Cancer"], "Mars": ["Aries", "Scorpio"],
    "Mercury": ["Gemini", "Virgo"], "Jupiter": ["Sagittarius", "Pisces"],
    "Venus": ["Taurus", "Libra"], "Saturn": ["Capricorn", "Aquarius"],
    "Rahu": ["Aquarius"], "Ketu": ["Scorpio"],
}

DEBILITATION: Dict[str, str] = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn", "Venus": "Virgo",
    "Saturn": "Aries", "Rahu": "Scorpio", "Ketu": "Taurus",
}

DIGNITY_SCORE: Dict[str, float] = {
    "exalted": 5.0, "moolatrikona": 4.0, "own_sign": 3.0,
    "neutral": 0.0, "debilitated": -3.0,
}

# Trikona + Kendra lords form Rajayoga
RAJAYOGA_HOUSES = {1, 4, 5, 9, 10}

# ── Phase 2: Combust thresholds (degrees from Sun) ───────────────────────────
# A planet is combust when within this many degrees of the Sun (sidereal arc).
COMBUST_THRESHOLDS: Dict[str, float] = {
    "Moon":    12.0,
    "Mars":    17.0,
    "Mercury": 14.0,
    "Jupiter": 11.0,
    "Venus":   10.0,
    "Saturn":  15.0,
    # Rahu/Ketu and Sun itself are excluded intentionally
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _normalise_dob(dob: str) -> str:
    """Convert various date formats to DD/MM/YYYY."""
    dob = dob.strip()
    iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", dob)
    if iso_match:
        y, m, d = iso_match.groups()
        return f"{d}/{m}/{y}"
    if re.match(r"^\d{2}/\d{2}/\d{4}$", dob):
        return dob
    raise ValueError(f"Cannot parse dob: {dob}")


def _normalise_tob(tob: str) -> str:
    """Convert various time formats to HH:MM (24h)."""
    tob = tob.strip()
    match_12h = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)$", tob, re.IGNORECASE)
    if match_12h:
        h, m, meridiem = match_12h.groups()
        h = int(h)
        if meridiem.upper() == "PM" and h != 12:
            h += 12
        elif meridiem.upper() == "AM" and h == 12:
            h = 0
        return f"{h:02d}:{m}"
    match_24h = re.match(r"^(\d{1,2}):(\d{2})", tob)
    if match_24h:
        h, m = match_24h.groups()
        return f"{int(h):02d}:{m}"
    raise ValueError(f"Cannot parse tob: {tob}")


def _get_planet_dignity(planet: str, sign: str) -> str:
    if EXALTATION.get(planet) == sign:
        return "exalted"
    if DEBILITATION.get(planet) == sign:
        return "debilitated"
    if sign in OWN_SIGNS.get(planet, []):
        return "own_sign"
    return "neutral"


def _sign_to_house(lagna_sign: str, planet_sign: str) -> int:
    """Compute house number of planet given lagna sign."""
    try:
        lagna_idx = SIGNS_ORDER.index(lagna_sign)
        planet_idx = SIGNS_ORDER.index(planet_sign)
        return ((planet_idx - lagna_idx) % 12) + 1
    except ValueError:
        return 0


def _parse_planet_details(
    raw: Dict,
    lagna_sign: str,
) -> Tuple[
    Dict[str, int],    # planet_houses
    Dict[str, float],  # planet_strengths
    str,               # lagna_sign (resolved)
    Dict[str, bool],   # planet_retrograde  ← Phase 2
    Dict[str, float],  # planet_longitudes  ← Phase 2
]:
    """
    Parse planet-details API response.

    VedicAstroAPI returns planets as a dict keyed 0..N, each with:
      name      → abbreviation: "Su", "Mo", "Ma", "Me", "Ju", "Ve", "Sa", "Ra", "Ke", "As"
      full_name → "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"
      zodiac    → sign name: "Taurus", "Scorpio" …
      house     → 1-12
      degree    → degree within sign (0–29.99)          ← used for longitude
      is_retrograde / retrograde → bool / "R"/"D"       ← Phase 2

    Returns:
        planet_houses, planet_strengths, lagna_sign, planet_retrograde, planet_longitudes
    """
    planet_houses: Dict[str, int] = {}
    planet_strengths: Dict[str, float] = {}
    planet_retrograde: Dict[str, bool] = {}
    planet_longitudes: Dict[str, float] = {}

    planets_raw = raw.get("planets", raw)
    if isinstance(planets_raw, dict):
        planets_raw = list(planets_raw.values())

    resolved_lagna = lagna_sign

    for p in planets_raw:
        if not isinstance(p, dict):
            continue

        name = p.get("full_name", p.get("name", "")).strip()
        sign = p.get("zodiac", p.get("rasi", p.get("sign", ""))).strip().title()

        if not name or not sign:
            continue

        # Ascendant → sets lagna, not stored as a planet
        if name.lower() in ("ascendant", "lagna", "asc") or p.get("name") == "As":
            resolved_lagna = sign
            continue

        house_num = int(p.get("house", 0))
        if not house_num and resolved_lagna:
            house_num = _sign_to_house(resolved_lagna, sign)

        dignity = _get_planet_dignity(name, sign)
        score = DIGNITY_SCORE.get(dignity, 0.0)

        planet_houses[name] = house_num
        planet_strengths[name] = score

        # ── Phase 2: retrograde ───────────────────────────────────────
        retro_raw = p.get("is_retrograde", p.get("retrograde", p.get("retro", None)))
        if retro_raw is not None:
            if isinstance(retro_raw, bool):
                planet_retrograde[name] = retro_raw
            elif isinstance(retro_raw, str):
                planet_retrograde[name] = retro_raw.strip().upper() in ("R", "TRUE", "YES", "1")
            else:
                planet_retrograde[name] = bool(retro_raw)

        # ── Phase 2: full sidereal longitude ─────────────────────────
        sign_idx = SIGNS_ORDER.index(sign) if sign in SIGNS_ORDER else 0
        degree_in_sign = float(p.get("degree", p.get("degree_in_sign", 0.0)) or 0.0)
        planet_longitudes[name] = round(sign_idx * 30.0 + degree_in_sign, 4)

    return planet_houses, planet_strengths, resolved_lagna, planet_retrograde, planet_longitudes


def _extract_lagna(raw: Dict) -> str:
    """Extract lagna sign from planet-details API response."""
    planets_raw = raw.get("planets", raw)
    if isinstance(planets_raw, dict):
        planets_raw = list(planets_raw.values())
    for p in planets_raw:
        if not isinstance(p, dict):
            continue
        name = p.get("name", "")
        full_name = p.get("full_name", "")
        is_lagna = (
            name == "As"
            or full_name.lower() in ("ascendant", "lagna")
            or name.lower() in ("ascendant", "lagna", "asc")
        )
        if is_lagna:
            sign = p.get("zodiac", p.get("rasi", p.get("sign", "")))
            if sign:
                return str(sign).strip().title()
    lagna = raw.get("lagna", raw.get("ascendant", ""))
    return str(lagna).title() if lagna else ""


def _build_house_lords(lagna_sign: str) -> Dict[str, str]:
    """
    Build house lord mapping based on lagna sign.
    House N is ruled by the lord of the sign occupying that house.
    """
    try:
        lagna_idx = SIGNS_ORDER.index(lagna_sign)
    except ValueError:
        return {}
    house_lords = {}
    for i in range(12):
        sign_for_house = SIGNS_ORDER[(lagna_idx + i) % 12]
        house_lords[str(i + 1)] = SIGN_LORD.get(sign_for_house, "")
    return house_lords


def _detect_active_dasha(maha_dasha_raw: Dict) -> str:
    """
    Detect currently active Maha Dasha lord from API response.
    Looks for the period that contains today's date.
    """
    today = datetime.utcnow()

    DATE_FORMATS = ["%a %b %d %Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y"]

    def parse_date(s):
        if not s:
            return None
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(s.strip(), fmt)
            except ValueError:
                pass
        return None

    mahadasha = maha_dasha_raw.get("mahadasha", [])
    mahadasha_order = maha_dasha_raw.get("mahadasha_order", [])

    if not mahadasha or not mahadasha_order:
        return ""

    active_lord = mahadasha[0] if mahadasha else ""
    for name, date_str in zip(mahadasha, mahadasha_order):
        start_dt = parse_date(date_str)
        if start_dt and start_dt <= today:
            active_lord = name
        elif start_dt and start_dt > today:
            break

    return active_lord


# ── Phase 2: Antardasha detection ────────────────────────────────────────────

def _detect_active_antardasha(antar_raw: Dict, maha_lord: str = "") -> str:
    """
    Detect the currently active Antara Dasha (sub-period) lord.

    The VedicAstroAPI antar-dasha endpoint returns a list of 9 groups
    (one per maha dasha), each group containing 9 "Maha/Anta" strings.

    Actual response shape:
      antardashas: [
        ["Moon/Moon", "Moon/Mars", ...],    # group 0 — Moon maha dasha periods
        ["Mars/Mars", "Mars/Rahu", ...],    # group 1 — Mars maha dasha periods
        ["Rahu/Rahu", "Rahu/Jupiter", ...], # group 2 — Rahu maha dasha periods
        ...                                 # groups 3–8 for remaining lords
      ]
      antardasha_order: [
        ["Sun Oct 07 1984", "Wed May 08 1985", ...],  # start dates for group 0
        ...                                           # one sub-list per group
      ]

    Strategy:
      1. If maha_lord is supplied, find the group whose entries start with
         "{maha_lord}/" — this narrows directly to the current maha period.
      2. Walk that group to find the latest period whose start date <= today.
      3. Fallback (no maha_lord match): scan ALL groups and return the most
         recently started period across the entire 120-year cycle.
    """
    today = datetime.utcnow()

    DATE_FORMATS = ["%a %b %d %Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y"]

    def parse_date(s):
        if not s:
            return None
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(str(s).strip(), fmt)
            except ValueError:
                pass
        return None

    def extract_anta(period_str: str) -> str:
        """'Rahu/Jupiter' → 'Jupiter';  'Jupiter' → 'Jupiter'"""
        parts = str(period_str).split("/")
        return parts[-1].strip() if len(parts) > 1 else str(period_str).strip()

    all_groups = antar_raw.get("antardashas", [])
    all_dates  = antar_raw.get("antardasha_order", [])

    if not all_groups or not all_dates:
        return ""

    # ── Step 1: locate the sub-group for the current maha dasha lord ──────
    target_group: list = []
    target_dates: list = []

    if maha_lord:
        prefix = f"{maha_lord}/"
        for i, group in enumerate(all_groups):
            if isinstance(group, list) and group and str(group[0]).startswith(prefix):
                target_group = group
                target_dates = all_dates[i] if i < len(all_dates) else []
                break

    # ── Step 2a: found the right group — scan for active period ───────────
    if target_group:
        active_lord = ""
        for period_str, date_str in zip(target_group, target_dates):
            d = parse_date(date_str)
            if d and d <= today:
                active_lord = extract_anta(period_str)
            elif d and d > today:
                break
        return active_lord

    # ── Step 2b: fallback — find most recently started period globally ─────
    best_lord = ""
    best_date = None
    for group, dates in zip(all_groups, all_dates):
        if not isinstance(group, list):
            continue
        for period_str, date_str in zip(group, dates):
            d = parse_date(date_str)
            if d and d <= today:
                if best_date is None or d > best_date:
                    best_date = d
                    best_lord = extract_anta(period_str)
    return best_lord


# ── Phase 2: Combust computation ─────────────────────────────────────────────

def _compute_combust(planet_longitudes: Dict[str, float]) -> Dict[str, bool]:
    """
    Determine which planets are combust (too close to the Sun).

    A planet is combust when its angular distance from the Sun is within
    the COMBUST_THRESHOLDS value (in degrees of sidereal arc).

    Sun itself and shadow planets (Rahu, Ketu) are excluded.

    Returns: {planet_name: is_combust_bool}
    """
    sun_lon = planet_longitudes.get("Sun")
    if sun_lon is None:
        return {}

    result: Dict[str, bool] = {}
    for planet, threshold in COMBUST_THRESHOLDS.items():
        p_lon = planet_longitudes.get(planet)
        if p_lon is None:
            continue
        # Shortest arc distance on the 360° circle
        diff = abs(sun_lon - p_lon) % 360.0
        if diff > 180.0:
            diff = 360.0 - diff
        result[planet] = diff <= threshold

    return result


def _detect_rajayoga(
    planet_houses: Dict[str, int],
    house_lords: Dict[str, str],
) -> Tuple[bool, List[str]]:
    """
    Detect Rajayoga: a planet that lords over both a Kendra (1,4,7,10) AND
    a Trikona (1,5,9) is a yoga karaka.
    """
    kendra_lords: set = set()
    trikona_lords: set = set()

    for h, lord in house_lords.items():
        h_num = int(h)
        if h_num in {1, 4, 7, 10}:
            kendra_lords.add(lord)
        if h_num in {1, 5, 9}:
            trikona_lords.add(lord)

    yoga_planets = list(kendra_lords & trikona_lords)
    return bool(yoga_planets), yoga_planets


def _compute_lagna_strength(
    lagna_sign: str,
    planet_houses: Dict[str, int],
    planet_strengths: Dict[str, float],
) -> float:
    """
    Lagna strength: sum of dignity scores of planets in house 1,
    plus lagna lord's dignity bonus.
    """
    strength = sum(
        planet_strengths.get(p, 0)
        for p, h in planet_houses.items()
        if h == 1
    )
    lagna_lord = SIGN_LORD.get(lagna_sign, "")
    if lagna_lord:
        strength += planet_strengths.get(lagna_lord, 0)
    return strength


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def compute_natal_profile(
    user_id: str,
    name: str,
    dob: str,
    tob: str,
    pob: str,
) -> NatalProfile:
    """
    Compute a full natal profile by calling the VedicAstroAPI.
    Expensive — should only be called once per user.
    """
    logger.info(f"Computing natal profile for user_id={user_id}, pob={pob}")

    # 1. Resolve city to lat/lon/tz
    geo = resolve_city(pob)
    if not geo:
        raise ValueError(f"Could not resolve city: {pob}")

    lat, lon, tz = geo["lat"], geo["lon"], geo["tz"]

    # 2. Normalise birth details
    dob_norm = _normalise_dob(dob)
    tob_norm = _normalise_tob(tob)

    # 3. Fetch planet details
    planet_raw = vedic_api.fetch_planet_details(dob_norm, tob_norm, lat, lon, tz)

    # 4. Extract lagna
    lagna_sign = _extract_lagna(planet_raw)
    if not lagna_sign:
        logger.warning(f"Could not extract lagna for user {user_id}; defaulting to Aries")
        lagna_sign = "Aries"

    lagna_sign_number = SIGN_TO_NUMBER.get(lagna_sign, 1)

    # 5. Parse planet placements, strengths, retrograde, longitudes  ← Phase 2
    planet_houses, planet_strengths, lagna_sign, planet_retrograde, planet_longitudes = (
        _parse_planet_details(planet_raw, lagna_sign)
    )

    # 6. Build house lords from lagna
    house_lords = _build_house_lords(lagna_sign)

    # 7. Compute combust status from longitudes  ← Phase 2
    planet_combust = _compute_combust(planet_longitudes)

    # 8. Fetch & parse Maha Dasha
    active_lord = ""
    try:
        maha_raw = vedic_api.fetch_maha_dasha(dob_norm, tob_norm, lat, lon, tz)
        active_lord = _detect_active_dasha(maha_raw)
    except Exception as e:
        logger.warning(f"Failed to fetch maha dasha for {user_id}: {e}")

    # 9. Fetch & parse Antara Dasha  ← Phase 2
    active_anta_lord = ""
    try:
        antar_raw = vedic_api.fetch_antara_dasha(dob_norm, tob_norm, lat, lon, tz)
        active_anta_lord = _detect_active_antardasha(antar_raw, maha_lord=active_lord)
    except Exception as e:
        logger.warning(f"Failed to fetch antara dasha for {user_id}: {e}")

    # 10. Detect Rajayoga
    rajayoga, yoga_planets = _detect_rajayoga(planet_houses, house_lords)

    # 11. Lagna strength
    lagna_strength = _compute_lagna_strength(lagna_sign, planet_houses, planet_strengths)

    profile = NatalProfile(
        user_id=user_id,
        name=name,
        dob=dob_norm,
        tob=tob_norm,
        pob=pob,
        lat=lat,
        lon=lon,
        tz=tz,
        lagna_sign=lagna_sign,
        lagna_sign_number=lagna_sign_number,
        house_lords=house_lords,
        planet_houses=planet_houses,
        planet_strengths=planet_strengths,
        planet_retrograde=planet_retrograde,       # Phase 2
        planet_longitudes=planet_longitudes,       # Phase 2
        planet_combust=planet_combust,             # Phase 2
        active_maha_dasha_lord=active_lord,
        active_anta_dasha_lord=active_anta_lord,   # Phase 2
        rajayoga_present=rajayoga,
        yoga_planets=yoga_planets,
        lagna_strength=lagna_strength,
    )

    _natal_cache[user_id] = profile
    logger.info(
        f"Natal profile computed: lagna={lagna_sign}, dasha={active_lord}, "
        f"anta_dasha={active_anta_lord}, rajayoga={rajayoga}, "
        f"combust={[p for p,v in planet_combust.items() if v]}, "
        f"retrograde={[p for p,v in planet_retrograde.items() if v]}"
    )
    return profile


def get_natal_profile(user_id: str) -> Optional[NatalProfile]:
    """Retrieve natal profile from in-memory cache (MongoDB read stubbed)."""
    return _natal_cache.get(user_id)


def get_or_compute_natal(
    user_id: str,
    name: str,
    dob: str,
    tob: str,
    pob: str,
) -> NatalProfile:
    """
    Return cached natal profile if available; otherwise compute and cache it.
    MongoDB lookup is stubbed — will be enabled later.
    """
    cached = _natal_cache.get(user_id)
    if cached:
        return cached

    # MongoDB lookup (stubbed)
    # from app.db.mongodb import get_natal_from_db
    # db_profile = await get_natal_from_db(user_id)
    # if db_profile: return db_profile

    return compute_natal_profile(user_id, name, dob, tob, pob)
