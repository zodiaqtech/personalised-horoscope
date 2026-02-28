"""
Horoscope orchestrator service.

Ties together:
  - Natal profile (static, computed once)
  - Transit data (global, cached per day)
  - Rule engine (deterministic scoring)
  - Template renderer (score → text)

Returns a fully populated HoroscopeResponse.
"""
import logging
from datetime import datetime
from typing import Optional

from app.models.natal_profile import NatalProfile
from app.models.horoscope import HoroscopeResponse, LifeAreaScores, LifeAreaBands, HoroscopeText
from app.services.natal_service import get_or_compute_natal, get_natal_profile
from app.services.transit_service import get_today_transit, get_today_transit_retrograde
from app.services.rule_engine import evaluate_rules, clamp_scores
from templates.horoscope_templates import score_to_band, get_template, get_overall_template

logger = logging.getLogger(__name__)

SCORE_AREAS = ["career", "finance", "love", "health", "mental", "spiritual"]

# ── Score calibration ────────────────────────────────────────────────────────
# Raw scores accumulate across firing rules, each contributing 1-4 points per
# area. With 196 rules (including antardasha + dasha_sub), extreme charts can
# produce totals up to ~55 raw per area; average charts produce ~20-25.
#
# SCORE_SCALE divides raw scores before clamping so the ±5 range is meaningful:
#   Extreme chart  (~50 raw)  → 6.25 → capped 5.0 → very_positive ✓
#   Average chart  (~24 raw)  → 3.0  → favourable                  ✓
#   Neutral chart  (~10 raw)  → 1.25 → neutral                     ✓
#   Weak chart     (~5  raw)  → 0.6  → neutral / caution           ✓
#
# Calibrated for 196-rule set (164 base + 17 antardasha + 15 dasha_sub).
# Tuning guide:  lower → more scores hit the ±5 caps (less differentiation)
#                higher → all scores cluster near 0   (too flat)
# v1: 6.0  (164 rules, max raw ~30–35)
# v2: 8.0  (196 rules, max raw ~45–55 — antardasha/dasha_sub added)
SCORE_SCALE: float = 8.0




def generate_horoscope(
    user_id: str,
    name: str,
    dob: str,
    tob: str,
    pob: str,
    date_override: Optional[str] = None,
) -> HoroscopeResponse:
    """
    Generate a personalised horoscope for the given user.

    Steps:
    1. Load or compute natal profile
    2. Fetch today's global transit (Redis-cached)
    3. Evaluate JSON rules → raw scores
    4. Scale raw scores (÷ SCORE_SCALE) to bring into meaningful [-5, 5] range
    5. Clamp scaled scores to [-5, 5]
    6. Convert scores to bands
    7. Render static templates
    8. Return HoroscopeResponse
    """
    today_str = date_override or datetime.utcnow().strftime("%Y-%m-%d")
    logger.info(f"Generating horoscope for user={user_id}, date={today_str}")

    # ── 1. Natal Profile ────────────────────────────────────────────
    natal: NatalProfile = get_or_compute_natal(user_id, name, dob, tob, pob)


    # 2. Transit Data (sign map + retrograde flags — Phase 3)
    transit_planets = get_today_transit(date_override=today_str)
    transit_retrograde = get_today_transit_retrograde(date_override=today_str)
    logger.debug(f"Transit planets (zodiac signs): {transit_planets}")
    logger.debug(f"Transit retrograde: {[p for p,r in transit_retrograde.items() if r]}")

    # 3. Rule Engine — pass sign map + retrograde map
    raw_scores = evaluate_rules(natal, transit_planets, transit_retrograde)

    # ── 4. Scale + Clamp Scores ─────────────────────────────────────
    # Divide by SCORE_SCALE so that 15-28 simultaneously-firing rules
    # produce meaningful differentiation across the full [-5, +5] range.
    scaled_scores = {a: raw_scores[a] / SCORE_SCALE for a in SCORE_AREAS}
    clamped = clamp_scores(scaled_scores, min_val=-5.0, max_val=5.0)
    logger.debug(
        f"Scores  raw={{{', '.join(f'{a}:{raw_scores[a]:+.1f}' for a in SCORE_AREAS)}}}"
        f"  scaled={{{', '.join(f'{a}:{scaled_scores[a]:+.2f}' for a in SCORE_AREAS)}}}"
    )

    # ── 5. Score → Band ─────────────────────────────────────────────
    bands = {area: score_to_band(clamped[area]) for area in SCORE_AREAS}

    # ── 6. Band → Text ──────────────────────────────────────────────
    texts = {area: get_template(area, bands[area]) for area in SCORE_AREAS}

    # Overall text: based on average score
    avg_score = sum(clamped[a] for a in SCORE_AREAS) / len(SCORE_AREAS)
    overall_text = get_overall_template(avg_score)
    texts["overall"] = overall_text

    # ── 7. Build Response ───────────────────────────────────────────
    return HoroscopeResponse(
        user_id=user_id,
        name=name,
        date=today_str,
        active_dasha=natal.active_maha_dasha_lord,
        active_anta_dasha=natal.active_anta_dasha_lord,
        scores=LifeAreaScores(**{a: round(clamped[a], 2) for a in SCORE_AREAS}),
        bands=LifeAreaBands(**bands),
        horoscope=HoroscopeText(**texts),
    )


def generate_horoscope_for_natal(
    natal: NatalProfile,
    date_override: Optional[str] = None,
) -> HoroscopeResponse:
    """
    Generate horoscope from an already-loaded NatalProfile object.
    Useful for batch processing all users.
    """
    today_str = date_override or datetime.utcnow().strftime("%Y-%m-%d")
    transit_planets = get_today_transit(date_override=today_str)
    transit_retrograde = get_today_transit_retrograde(date_override=today_str)

    raw_scores = evaluate_rules(natal, transit_planets, transit_retrograde)
    scaled_scores = {a: raw_scores[a] / SCORE_SCALE for a in SCORE_AREAS}
    clamped = clamp_scores(scaled_scores)
    bands = {area: score_to_band(clamped[area]) for area in SCORE_AREAS}
    texts = {area: get_template(area, bands[area]) for area in SCORE_AREAS}
    avg_score = sum(clamped[a] for a in SCORE_AREAS) / len(SCORE_AREAS)
    texts["overall"] = get_overall_template(avg_score)

    return HoroscopeResponse(
        user_id=natal.user_id,
        name=natal.name,
        date=today_str,
        active_dasha=natal.active_maha_dasha_lord,
        active_anta_dasha=natal.active_anta_dasha_lord,
        scores=LifeAreaScores(**{a: round(clamped[a], 2) for a in SCORE_AREAS}),
        bands=LifeAreaBands(**bands),
        horoscope=HoroscopeText(**texts),
    )
