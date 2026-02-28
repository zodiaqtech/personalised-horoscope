"""
Rule Engine — BPHS enhanced deterministic scorer.

Loads rules once from JSON at startup.
Evaluates rules against natal profile + transit data.
Returns raw life-area scores (float).

KEY DESIGN — Transit house computation:
  transit_planets dict carries global zodiac sign numbers (1=Aries … 12=Pisces).
  BPHS transit rules specify house numbers (1–12) relative to the user's Lagna.
  Before matching, we convert each planet's sign → per-user natal house:

      natal_house = (planet_sign - lagna_sign) mod 12 + 1

  Example: Jupiter in Gemini (sign 3), user Lagna = Taurus (sign 2)
      natal_house = (3 - 2) % 12 + 1 = 2  → Jupiter transiting user's 2nd house

  This is computed ONCE per evaluate_rules() call and cached in
  `transit_natal_houses` dict — used for all transit rule checks.

Phase 1 additions:
  All 46 condition keys from the enhanced ruleset are now handled.
  Unknown keys are skipped with a debug log (fail-open by design so
  forward-compatible rules don't silently break scoring).
"""
import json
import logging
import os
from typing import Dict, List, Any, Optional

from app.models.natal_profile import NatalProfile

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Rule storage (loaded once at startup)
# ─────────────────────────────────────────────

_rules: List[Dict] = []


def load_rules(rules_file: str = "rules/BPHS_Level2_200_Rules.json") -> None:
    global _rules
    if not os.path.exists(rules_file):
        raise FileNotFoundError(f"Rules file not found: {rules_file}")
    with open(rules_file, "r") as f:
        _rules = json.load(f)
    logger.info(f"Loaded {len(_rules)} rules from {rules_file}")


def get_rules() -> List[Dict]:
    return _rules


# ─────────────────────────────────────────────
# Zodiac sign index (1-based)
# ─────────────────────────────────────────────

SIGNS_ORDER = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

SIGN_TO_NUMBER: Dict[str, int] = {s: i + 1 for i, s in enumerate(SIGNS_ORDER)}

SIGN_LORD: Dict[str, str] = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

EXALTATION: Dict[str, str] = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer", "Venus": "Pisces",
    "Saturn": "Libra", "Rahu": "Taurus", "Ketu": "Scorpio",
}

DEBILITATION: Dict[str, str] = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn", "Venus": "Virgo",
    "Saturn": "Aries", "Rahu": "Scorpio", "Ketu": "Taurus",
}

# Natural malefics (used for affliction check)
MALEFICS = {"Saturn", "Mars", "Rahu", "Ketu", "Sun"}

# Natural benefics (used for yoga checks)
NATURAL_BENEFICS = {"Jupiter", "Venus", "Mercury"}

# Special aspect offsets (0-indexed offset from planet's house):
#   offset 0 = same house (1st), offset 6 = 7th house (common to all planets)
# These are the NON-7th special aspects only.
SPECIAL_ASPECT_OFFSETS: Dict[str, List[int]] = {
    "Mars":    [3, 7],   # 4th (offset 3) and 8th (offset 7)
    "Jupiter": [4, 8],   # 5th (offset 4) and 9th (offset 8)
    "Saturn":  [2, 9],   # 3rd (offset 2) and 10th (offset 9)
}

# Condition keys that are consumed/read by another key's handler — skip standalone
_SKIP_KEYS = frozenset({
    "transit_house",          # handled inside transit_planet
    "not_sun",                # handled inside planet_in_2nd/12th_from_moon
    "reference_point",        # handled inside benefics_in
    "between_rahu_ketu",      # handled inside all_planets_hemmed
    "aspect_type",            # handled inside aspects_house (via planet)
    "planet_afflicted",       # handled inside natal_planet
    "planet_strong",          # handled inside natal_planet
    "house_lord_strength",    # handled inside natal_house
    "placed_in_house",        # handled inside house_lord
    "aspects_house",          # handled inside planet (aspect rules)
    "combust",                # handled inside planet (combustion rules)
})


# ─────────────────────────────────────────────
# Dignity scores (used for strength checks)
# ─────────────────────────────────────────────

DIGNITY_SCORE_MAP: Dict[str, float] = {
    "exalted": 5.0,
    "moolatrikona": 4.0,
    "own_sign": 3.0,
    "neutral": 0.0,
    "debilitated": -3.0,
}


# ─────────────────────────────────────────────
# Lagna helpers
# ─────────────────────────────────────────────

def _lagna_sign_number(natal: NatalProfile) -> int:
    return SIGN_TO_NUMBER.get(natal.lagna_sign, 1)


def build_transit_natal_houses(
    transit_sign_map: Dict[str, int],
    natal: NatalProfile,
) -> Dict[str, int]:
    """
    Convert global transit sign numbers → natal house numbers for this user.
    natal_house = (planet_sign - lagna_sign) mod 12 + 1
    """
    lagna_num = _lagna_sign_number(natal)
    natal_houses: Dict[str, int] = {}
    for planet, sign_num in transit_sign_map.items():
        natal_houses[planet] = (sign_num - lagna_num) % 12 + 1
    return natal_houses


# ─────────────────────────────────────────────
# Condition helper functions
# ─────────────────────────────────────────────

def _dasha_lord_owns_houses(cond_houses: List[int], natal: NatalProfile) -> bool:
    dasha_lord = natal.active_maha_dasha_lord
    if not dasha_lord:
        return False
    for h in cond_houses:
        if natal.house_lords.get(str(h), "") == dasha_lord:
            return True
    return False


def _dasha_lord_strength(natal: NatalProfile) -> float:
    dasha_lord = natal.active_maha_dasha_lord
    if not dasha_lord:
        return 0.0
    return natal.planet_strengths.get(dasha_lord, 0.0)


def _anta_lord_owns_houses(cond_houses: List[int], natal: NatalProfile) -> bool:
    """Check if the active Antardasha lord rules any of the given houses."""
    anta_lord = natal.active_anta_dasha_lord
    if not anta_lord:
        return False
    for h in cond_houses:
        if natal.house_lords.get(str(h), "") == anta_lord:
            return True
    return False


def _anta_lord_strength(natal: NatalProfile) -> float:
    anta_lord = natal.active_anta_dasha_lord
    if not anta_lord:
        return 0.0
    return natal.planet_strengths.get(anta_lord, 0.0)


def _transit_planet_in_natal_house(
    transit_planet: str,
    required_house: int,
    transit_natal_houses: Dict[str, int],
) -> bool:
    return transit_natal_houses.get(transit_planet, -1) == required_house


def _is_planet_afflicted(planet: str, natal: NatalProfile) -> bool:
    """
    A planet is considered afflicted if:
    1. It is debilitated (dignity score ≤ -3)
    2. It is conjunct a natural malefic (same natal house)
    3. It is combust (within combust threshold of Sun)
    """
    if natal.planet_strengths.get(planet, 0.0) <= -3.0:
        return True
    planet_house = natal.planet_houses.get(planet, 0)
    if planet_house:
        for malefic in MALEFICS:
            if malefic != planet and natal.planet_houses.get(malefic, 0) == planet_house:
                return True
    if natal.planet_combust.get(planet, False):
        return True
    return False


def _planet_special_aspects_house(
    planet: str,
    planet_house: int,
    target_house: int,
    include_7th: bool = False,
) -> bool:
    """
    Check if planet's special aspect(s) land on target_house.

    Special aspects (non-7th):
      Mars: 4th (offset 3) and 8th (offset 7 from house position)
      Jupiter: 5th (offset 4) and 9th (offset 8)
      Saturn: 3rd (offset 2) and 10th (offset 9)

    include_7th=True also checks the universal 7th aspect (offset 6).
    """
    if not planet_house:
        return False
    offsets = list(SPECIAL_ASPECT_OFFSETS.get(planet, []))
    if include_7th:
        offsets.append(6)
    for offset in offsets:
        aspected = (planet_house - 1 + offset) % 12 + 1
        if aspected == target_house:
            return True
    return False


def _check_planets_conjunct(planets: List[str], natal: NatalProfile) -> bool:
    """All listed planets are in the same natal house."""
    if len(planets) < 2:
        return False
    houses = [natal.planet_houses.get(p, 0) for p in planets]
    valid = [h for h in houses if h > 0]
    return len(valid) == len(planets) and len(set(valid)) == 1


def _resolve_planet_ref(ref: str, natal: NatalProfile) -> str:
    """Resolve a lord reference like '9th_lord' to its planet name."""
    if "_lord" in ref:
        house_num = ref.replace("_lord", "").replace("th", "").replace("nd", "").replace("rd", "").replace("st", "")
        return natal.house_lords.get(house_num, "")
    return ref


def _check_planets_involved_yoga(
    planets: List[str],
    yoga_type: str,
    natal: NatalProfile,
) -> bool:
    """
    Evaluate the `planets_involved` condition for yoga rules that don't have
    a separate `conjunction` or `planet_in_kendra` condition.

    Handles:
      - raja_yoga / dhana_yoga: conjunction of two lords
      - viparita_raja_yoga: dusthana lords in dusthana houses
      - gaja_kesari: Jupiter in kendra from Moon
      - chandra_mangala: Moon-Mars conjunction or mutual aspect
      - Default: all planets conjunct (same house)
    """
    resolved = [_resolve_planet_ref(p, natal) for p in planets]
    if not all(resolved):
        return False

    if yoga_type == "viparita_raja":
        dusthana = {6, 8, 12}
        return any(natal.planet_houses.get(p, 0) in dusthana for p in resolved)

    if yoga_type == "gaja_kesari":
        moon_h = natal.planet_houses.get("Moon", 0)
        jup_h = natal.planet_houses.get("Jupiter", 0)
        if not moon_h or not jup_h:
            return False
        diff = (jup_h - moon_h) % 12
        return diff in {0, 3, 6, 9}  # kendra from Moon (1st, 4th, 7th, 10th)

    if yoga_type == "chandra_mangala":
        moon_h = natal.planet_houses.get("Moon", 0)
        mars_h = natal.planet_houses.get("Mars", 0)
        if not moon_h or not mars_h:
            return False
        diff = (moon_h - mars_h) % 12
        return diff in {0, 6}  # conjunction or opposition (mutual 7th aspect)

    # Default: all resolved planets must be in the same house (conjunction)
    if len(resolved) == 1:
        return True  # single planet is a label; other conditions do the real check
    houses = [natal.planet_houses.get(p, 0) for p in resolved]
    valid = [h for h in houses if h > 0]
    return len(valid) == len(resolved) and len(set(valid)) == 1


def _check_mutual_exchange(natal: NatalProfile) -> bool:
    """
    Parivartana Yoga: two planets are in each other's signs
    (house lords exchanged their placements).
    """
    for p1, h1 in natal.planet_houses.items():
        lord_of_h1 = natal.house_lords.get(str(h1), "")
        if lord_of_h1 and lord_of_h1 != p1:
            p2 = lord_of_h1
            h2 = natal.planet_houses.get(p2, 0)
            if h2 and natal.house_lords.get(str(h2), "") == p1:
                return True
    return False


def _check_kala_sarpa(natal: NatalProfile) -> bool:
    """
    Kala Sarpa Yoga: all seven classical planets are on one side of
    the Rahu–Ketu axis.
    """
    rahu_h = natal.planet_houses.get("Rahu", 0)
    ketu_h = natal.planet_houses.get("Ketu", 0)
    if not rahu_h or not ketu_h:
        return False

    main_planets = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    planet_hs = [natal.planet_houses.get(p, 0) for p in main_planets]
    planet_hs = [h for h in planet_hs if h > 0]
    if not planet_hs:
        return False

    # Collect houses from Rahu going forward until (but not including) Ketu
    fwd_range = set()
    h = rahu_h
    for _ in range(12):
        if h == ketu_h:
            break
        fwd_range.add(h)
        h = h % 12 + 1

    all_fwd = all(h in fwd_range for h in planet_hs)
    all_bwd = all(h not in fwd_range and h != ketu_h for h in planet_hs)
    return all_fwd or all_bwd


def _check_neecha_bhanga_cancellation(natal: NatalProfile) -> bool:
    """
    Neecha Bhanga Raja Yoga cancellation check.
    A debilitated planet's debilitation is cancelled when:
    1. The lord of the debilitation sign is in a kendra (1,4,7,10)
    2. The planet that would be exalted in that sign is in a kendra
    """
    kendra = {1, 4, 7, 10}
    debilitated = [p for p, s in natal.planet_strengths.items() if s <= -3.0]
    if not debilitated:
        return False

    signs_order_local = [
        "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
        "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
    ]

    for planet in debilitated:
        deb_sign = DEBILITATION.get(planet, "")
        if not deb_sign:
            continue
        # Condition 1: lord of debilitation sign in kendra
        deb_lord = SIGN_LORD.get(deb_sign, "")
        if deb_lord and natal.planet_houses.get(deb_lord, 0) in kendra:
            return True
        # Condition 2: exaltation planet of that sign in kendra
        for p, exalt_sign in EXALTATION.items():
            if exalt_sign == deb_sign:
                if natal.planet_houses.get(p, 0) in kendra:
                    return True
    return False


def _check_adhi_yoga(
    benefics_in: List[int],
    reference: str,
    natal: NatalProfile,
) -> bool:
    """
    Adhi Yoga: natural benefics occupy each of the specified houses
    counting from the reference point (Moon or Lagna).

    benefics_in: offsets (e.g. [6,7,8] means 6th, 7th, 8th from ref)
    """
    if reference == "Moon":
        ref_h = natal.planet_houses.get("Moon", 0)
    elif reference == "Lagna":
        ref_h = 1
    else:
        ref_h = natal.planet_houses.get(reference, 0)

    if not ref_h:
        return False

    # All three offsets must have at least one benefic
    for offset in benefics_in:
        target = (ref_h - 1 + offset - 1) % 12 + 1
        if not any(natal.planet_houses.get(b, 0) == target for b in NATURAL_BENEFICS):
            return False
    return True


def _check_planet_from_moon(
    natal: NatalProfile,
    offset: int,
    not_sun: bool = False,
) -> bool:
    """
    Check if any planet (optionally excluding Sun) is `offset` houses
    from Moon's natal house.

    offset=1  → 2nd from Moon (Sunapha yoga)
    offset=-1 → 12th from Moon (Anapha yoga)
    """
    moon_h = natal.planet_houses.get("Moon", 0)
    if not moon_h:
        return False
    target = (moon_h - 1 + offset) % 12 + 1
    for planet, house in natal.planet_houses.items():
        if not_sun and planet == "Sun":
            continue
        if planet == "Moon":
            continue
        if house == target:
            return True
    return False


def _check_benefic_in_10th_from(
    reference_points: List[str],
    natal: NatalProfile,
) -> bool:
    """
    Amala Yoga: a natural benefic occupies the 10th house from Moon or Lagna.
    """
    for ref in reference_points:
        if ref == "Moon":
            ref_h = natal.planet_houses.get("Moon", 0)
        elif ref == "Lagna":
            ref_h = 1
        else:
            ref_h = natal.planet_houses.get(ref, 0)
        if not ref_h:
            continue
        tenth = (ref_h - 1 + 9) % 12 + 1   # 10th from ref (offset 9)
        if any(natal.planet_houses.get(b, 0) == tenth for b in NATURAL_BENEFICS):
            return True
    return False


# ─────────────────────────────────────────────
# Master condition checker
# ─────────────────────────────────────────────

def _check_condition(
    conditions: Dict[str, Any],
    natal: NatalProfile,
    transit_natal_houses: Dict[str, int],
    transit_retrograde: Optional[Dict[str, bool]] = None,
) -> bool:
    """
    Evaluate ALL conditions in a rule (logical AND).

    transit_natal_houses: planet → house number relative to user's lagna.
    transit_retrograde:   planet → is_retrograde_bool  (Phase 3)
    """
    if transit_retrograde is None:
        transit_retrograde = {}

    for key, value in conditions.items():

        # ── Keys consumed by their paired handler — skip ─────────────
        if key in _SKIP_KEYS:
            continue

        # ═══════════════════════════════════════════════════════════════
        # A. DASHA CONDITIONS
        # ═══════════════════════════════════════════════════════════════

        if key == "dasha_lord_owns":
            if not _dasha_lord_owns_houses(value, natal):
                return False

        elif key in ("dasha_relevant_house", "dasha_house"):
            # Both mean: the active maha-dasha lord rules house N
            if not _dasha_lord_owns_houses([int(value)], natal):
                return False

        elif key == "dasha_lord_strength_min":
            if _dasha_lord_strength(natal) < value:
                return False

        elif key == "dasha_lord_exalted":
            score = natal.planet_strengths.get(natal.active_maha_dasha_lord, 0.0)
            if bool(score >= 5.0) != bool(value):
                return False

        elif key == "dasha_lord_own_sign":
            score = natal.planet_strengths.get(natal.active_maha_dasha_lord, 0.0)
            # own_sign = 3.0; exalted = 5.0; moolatrikona = 4.0
            is_own = 3.0 <= score < 5.0
            if bool(is_own) != bool(value):
                return False

        elif key == "dasha_lord_debilitated":
            score = natal.planet_strengths.get(natal.active_maha_dasha_lord, 0.0)
            if bool(score <= -3.0) != bool(value):
                return False

        elif key == "dasha_lord_retrograde":
            is_retro = natal.planet_retrograde.get(natal.active_maha_dasha_lord, False)
            if bool(is_retro) != bool(value):
                return False

        elif key == "dasha_lord_combust":
            is_combust = natal.planet_combust.get(natal.active_maha_dasha_lord, False)
            if bool(is_combust) != bool(value):
                return False

        elif key == "dasha_lord_yogakaraka":
            in_yoga = natal.active_maha_dasha_lord in natal.yoga_planets
            if bool(in_yoga) != bool(value):
                return False

        elif key == "dasha_lord_part_of_yoga":
            if value:
                if natal.active_maha_dasha_lord not in natal.yoga_planets:
                    return False
            else:
                if natal.active_maha_dasha_lord in natal.yoga_planets:
                    return False

        # ═══════════════════════════════════════════════════════════════
        # B. DASHA SUB-PERIOD (Antardasha) CONDITIONS
        # ═══════════════════════════════════════════════════════════════

        elif key == "mahadasha_planet":
            if natal.active_maha_dasha_lord != value:
                return False

        elif key == "antardasha_planet":
            if natal.active_anta_dasha_lord != value:
                return False

        # ═══════════════════════════════════════════════════════════════
        # B2. ANTARDASHA-LORD ATTRIBUTE CONDITIONS
        #     Mirrors the Maha Dasha handlers above but reads
        #     active_anta_dasha_lord instead. Effects in the JSON rules
        #     are ~50 % of the corresponding Maha Dasha rule weights.
        # ═══════════════════════════════════════════════════════════════

        elif key == "antardasha_lord_owns":
            if not _anta_lord_owns_houses(value, natal):
                return False

        elif key == "antardasha_lord_exalted":
            score = natal.planet_strengths.get(natal.active_anta_dasha_lord, 0.0)
            if bool(score >= 5.0) != bool(value):
                return False

        elif key == "antardasha_lord_own_sign":
            score = natal.planet_strengths.get(natal.active_anta_dasha_lord, 0.0)
            is_own = 3.0 <= score < 5.0
            if bool(is_own) != bool(value):
                return False

        elif key == "antardasha_lord_debilitated":
            score = natal.planet_strengths.get(natal.active_anta_dasha_lord, 0.0)
            if bool(score <= -3.0) != bool(value):
                return False

        elif key == "antardasha_lord_retrograde":
            is_retro = natal.planet_retrograde.get(natal.active_anta_dasha_lord, False)
            if bool(is_retro) != bool(value):
                return False

        elif key == "antardasha_lord_combust":
            is_combust = natal.planet_combust.get(natal.active_anta_dasha_lord, False)
            if bool(is_combust) != bool(value):
                return False

        # ═══════════════════════════════════════════════════════════════
        # C. TRANSIT CONDITIONS
        # ═══════════════════════════════════════════════════════════════

        elif key == "transit_planet":
            # Always paired with transit_house in the JSON rules
            t_house = conditions.get("transit_house")
            if t_house is not None:
                if not _transit_planet_in_natal_house(value, int(t_house), transit_natal_houses):
                    return False

        elif key == "transit_retrograde":
            t_planet = conditions.get("transit_planet")
            if t_planet:
                is_retro = transit_retrograde.get(t_planet, False)
                if bool(is_retro) != bool(value):
                    return False

        elif key == "jupiter_transit_house":
            if transit_natal_houses.get("Jupiter", -1) != int(value):
                return False

        elif key == "saturn_transit_house":
            if transit_natal_houses.get("Saturn", -1) != int(value):
                return False

        elif key == "conjunction_with":
            # Transit: the main planet and `value` planet are in the same house
            main = conditions.get("transit_planet")
            if not main:
                return False
            main_h = transit_natal_houses.get(main, -1)
            other_h = transit_natal_houses.get(value, -1)
            if main_h == -1 or main_h != other_h:
                return False

        elif key == "aspect_from":
            # Transit: `value` planet has a special (or 7th) aspect on the
            # transit_house of the rule's main transit planet.
            target_h = conditions.get("transit_house")
            if not target_h:
                return False
            asp_h = transit_natal_houses.get(value, 0)
            if not asp_h:
                return False
            # Include 7th aspect for transit aspect checks
            if not _planet_special_aspects_house(value, asp_h, int(target_h), include_7th=True):
                return False

        # ═══════════════════════════════════════════════════════════════
        # D. NATAL MODIFIER CONDITIONS
        # ═══════════════════════════════════════════════════════════════

        elif key == "natal_house":
            # Paired with house_lord_strength: check if lord of this house is strong/weak
            h_strength = conditions.get("house_lord_strength")
            if h_strength is not None:
                lord = natal.house_lords.get(str(value), "")
                if not lord:
                    return False
                score = natal.planet_strengths.get(lord, 0.0)
                if h_strength == "strong" and score < 3.0:
                    return False
                elif h_strength == "weak" and score >= 0.0:
                    return False

        elif key == "natal_planet":
            planet = value
            p_afflicted = conditions.get("planet_afflicted")
            p_strong = conditions.get("planet_strong")

            if p_afflicted is not None:
                afflicted = _is_planet_afflicted(planet, natal)
                if bool(afflicted) != bool(p_afflicted):
                    return False

            if p_strong is not None:
                strong = natal.planet_strengths.get(planet, 0.0) >= 3.0
                if bool(strong) != bool(p_strong):
                    return False

        elif key == "natal_house_strength_min":
            if natal.lagna_strength < value:
                return False

        elif key == "rajayoga_present":
            if bool(natal.rajayoga_present) != bool(value):
                return False

        # ═══════════════════════════════════════════════════════════════
        # E. LORD PLACEMENT CONDITIONS
        # ═══════════════════════════════════════════════════════════════

        elif key == "house_lord":
            # Paired with placed_in_house: lord of house `value` is in house `placed_in_house`
            placed_in = conditions.get("placed_in_house")
            if placed_in is not None:
                lord = natal.house_lords.get(str(value), "")
                if not lord:
                    return False
                if natal.planet_houses.get(lord, 0) != int(placed_in):
                    return False

        # ═══════════════════════════════════════════════════════════════
        # F. NATAL ASPECT + COMBUSTION CONDITIONS
        # ═══════════════════════════════════════════════════════════════

        elif key == "planet":
            planet = value
            asp_house = conditions.get("aspects_house")
            is_combust = conditions.get("combust")

            if asp_house is not None:
                # Natal special aspect (aspect_type: "special" — no 7th)
                p_house = natal.planet_houses.get(planet, 0)
                if not _planet_special_aspects_house(planet, p_house, int(asp_house), include_7th=False):
                    return False

            if is_combust is not None:
                combust_val = natal.planet_combust.get(planet, False)
                if bool(combust_val) != bool(is_combust):
                    return False

        # ═══════════════════════════════════════════════════════════════
        # G. YOGA CONDITIONS
        # ═══════════════════════════════════════════════════════════════

        elif key == "yoga_type":
            pass  # Label only — other conditions do the real checking

        elif key == "planets_involved":
            # Skip when conjunction or planet_in_kendra handles this
            if "conjunction" in conditions or "planet_in_kendra" in conditions:
                pass
            else:
                yoga_type = conditions.get("yoga_type", "")
                if not _check_planets_involved_yoga(value, yoga_type, natal):
                    return False

        elif key == "planet_in_kendra":
            # The specific planet (from planets_involved) must be in a kendra
            planets = conditions.get("planets_involved", [])
            if not planets:
                return False
            planet = planets[0]
            in_kendra = natal.planet_houses.get(planet, 0) in {1, 4, 7, 10}
            if bool(in_kendra) != bool(value):
                return False

        elif key == "planet_in_own_exaltation":
            # The specific planet (from planets_involved) must be in own sign or exalted
            planets = conditions.get("planets_involved", [])
            if not planets:
                return False
            planet = planets[0]
            score = natal.planet_strengths.get(planet, 0.0)
            qualified = score >= 3.0   # own (3.0), moolatrikona (4.0), or exalted (5.0)
            if bool(qualified) != bool(value):
                return False

        elif key == "conjunction":
            planets = conditions.get("planets_involved", [])
            result = _check_planets_conjunct(planets, natal)
            if bool(result) != bool(value):
                return False

        elif key == "mutual_exchange":
            if bool(_check_mutual_exchange(natal)) != bool(value):
                return False

        elif key == "all_planets_hemmed":
            # Kala Sarpa: checks both all_planets_hemmed AND between_rahu_ketu
            if bool(_check_kala_sarpa(natal)) != bool(value):
                return False

        elif key == "benefics_in":
            ref = conditions.get("reference_point", "Moon")
            if not _check_adhi_yoga(value, ref, natal):
                return False

        elif key == "ninth_lord_in_kendra":
            ninth_lord = natal.house_lords.get("9", "")
            result = bool(ninth_lord) and natal.planet_houses.get(ninth_lord, 0) in {1, 4, 7, 10}
            if bool(result) != bool(value):
                return False

        elif key == "venus_strong":
            result = natal.planet_strengths.get("Venus", 0.0) >= 3.0
            if bool(result) != bool(value):
                return False

        elif key == "planet_in_2nd_from_moon":
            not_sun = conditions.get("not_sun", False)
            result = _check_planet_from_moon(natal, offset=1, not_sun=not_sun)
            if bool(result) != bool(value):
                return False

        elif key == "planet_in_12th_from_moon":
            not_sun = conditions.get("not_sun", False)
            result = _check_planet_from_moon(natal, offset=-1, not_sun=not_sun)
            if bool(result) != bool(value):
                return False

        elif key == "benefic_in_10th_from":
            # value is a list of reference points e.g. ["Moon", "Lagna"]
            refs = value if isinstance(value, list) else [value]
            if not _check_benefic_in_10th_from(refs, natal):
                return False

        elif key == "planet_debilitated":
            result = any(s <= -3.0 for s in natal.planet_strengths.values())
            if bool(result) != bool(value):
                return False

        elif key == "cancellation_condition":
            result = _check_neecha_bhanga_cancellation(natal)
            if bool(result) != bool(value):
                return False

        else:
            logger.debug(f"Unknown condition key: {key!r} — skipping")

    return True


# ─────────────────────────────────────────────
# Main evaluation function
# ─────────────────────────────────────────────

SCORE_AREAS = {"career", "finance", "love", "health", "mental", "spiritual"}


def evaluate_rules(
    natal: NatalProfile,
    transit_sign_map: Dict[str, int],
    transit_retrograde: Optional[Dict[str, bool]] = None,
) -> Dict[str, float]:
    """
    Apply all BPHS rules to the natal profile + today's transit.

    Steps:
      1. Convert global transit sign numbers → per-user natal houses (once)
      2. Iterate all rules; evaluate every condition
      3. Accumulate weighted effects into 6 life-area scores

    Args:
        natal:              user's computed natal profile
        transit_sign_map:   global zodiac sign positions {planet: sign_number}
        transit_retrograde: retrograde flags {planet: bool}  ← Phase 3

    Returns:
        raw (unclamped) scores per life area
    """
    scores: Dict[str, float] = {area: 0.0 for area in SCORE_AREAS}

    if not _rules:
        logger.warning("Rules not loaded — returning zero scores")
        return scores

    # ── Convert transit signs → lagna-relative houses ONCE ──────────
    transit_natal_houses = build_transit_natal_houses(transit_sign_map, natal)
    if transit_retrograde is None:
        transit_retrograde = {}

    logger.debug(
        f"Lagna={natal.lagna_sign}({_lagna_sign_number(natal)}) | "
        f"Transit natal houses: {transit_natal_houses}"
    )

    # ── Evaluate all rules ───────────────────────────────────────────
    matched_count = 0
    for rule in _rules:
        if "id" not in rule:
            continue   # skip comment-only entries
        conditions = rule.get("conditions", {})
        effects    = rule.get("effects", {})
        multiplier = float(rule.get("multiplier", 1.0))

        if _check_condition(conditions, natal, transit_natal_houses, transit_retrograde):
            matched_count += 1
            for area, value in effects.items():
                if area in scores:
                    scores[area] += float(value) * multiplier

    logger.debug(f"Rules matched: {matched_count}/{len(_rules)}")
    return scores


def clamp_scores(
    scores: Dict[str, float],
    min_val: float = -5.0,
    max_val: float = 5.0,
) -> Dict[str, float]:
    """Clamp raw scores to [min_val, max_val]."""
    return {area: max(min_val, min(max_val, val)) for area, val in scores.items()}
