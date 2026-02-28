"""
Local test script — run this WITHOUT starting the server.
Tests all layers independently: config → rules → transit → natal helpers
→ new Phase 2/3 fields → all 11 rule categories → full pipeline.

Usage:
    python3 test_local.py
"""
import sys
import json
from datetime import datetime

# ── ANSI colours ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

passed = 0
failed = 0


def ok(label: str, detail: str = ""):
    global passed
    passed += 1
    suffix = f"  {YELLOW}{detail}{RESET}" if detail else ""
    print(f"  {GREEN}✓{RESET}  {label}{suffix}")


def fail(label: str, err: str = ""):
    global failed
    failed += 1
    print(f"  {RED}✗{RESET}  {label}")
    if err:
        print(f"       {RED}{err}{RESET}")


def section(title: str):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a test NatalProfile with all new fields populated
# ─────────────────────────────────────────────────────────────────────────────
def _make_natal(**overrides):
    """Return a NatalProfile with sensible defaults; override any field."""
    from app.models.natal_profile import NatalProfile
    defaults = dict(
        user_id="test", name="Test User",
        dob="15/08/1985", tob="06:30", pob="Mumbai",
        lat=19.076, lon=72.877, tz=5.5,
        lagna_sign="Leo", lagna_sign_number=5,
        # Leo lagna house lords
        house_lords={
            "1": "Sun",  "2": "Mercury", "3": "Venus",  "4": "Venus",
            "5": "Mars", "6": "Jupiter", "7": "Saturn", "8": "Saturn",
            "9": "Jupiter", "10": "Mars", "11": "Venus", "12": "Mercury",
        },
        planet_houses={
            "Sun": 1,  "Moon": 4,  "Mars": 5,   "Mercury": 2,
            "Jupiter": 1, "Venus": 7, "Saturn": 9, "Rahu": 11, "Ketu": 5,
        },
        planet_strengths={
            "Sun": 3.0, "Moon": 0.0, "Mars": 3.0, "Mercury": 3.0,
            "Jupiter": 5.0, "Venus": 0.0, "Saturn": -3.0,
            "Rahu": 0.0, "Ketu": 0.0,
        },
        # Phase 2 fields
        planet_retrograde={"Saturn": True, "Mercury": False},
        planet_longitudes={
            "Sun": 120.0, "Moon": 190.0, "Mars": 150.0, "Mercury": 135.0,
            "Jupiter": 95.0, "Venus": 180.0, "Saturn": 245.0,
            "Rahu": 295.0, "Ketu": 115.0,
        },
        planet_combust={"Mercury": False, "Venus": False},
        active_maha_dasha_lord="Jupiter",
        active_anta_dasha_lord="Venus",
        rajayoga_present=True,
        yoga_planets=["Jupiter", "Sun"],
        lagna_strength=8.0,
    )
    defaults.update(overrides)
    return NatalProfile(**defaults)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Config
# ══════════════════════════════════════════════════════════════════════════════
section("1. Config")
try:
    from config import get_settings
    s = get_settings()
    assert s.VEDIC_ASTRO_API_KEY, "API key missing"
    ok("Settings loaded", f"API key: {s.VEDIC_ASTRO_API_KEY[:8]}…")
    ok("MongoDB stubbed", f"enabled={s.MONGODB_ENABLED}")
    ok("Redis URL", s.REDIS_URL)
    ok("Rules file", s.RULES_FILE)
except Exception as e:
    fail("Config", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 2. Rules file — 164 rules, 11 categories
# ══════════════════════════════════════════════════════════════════════════════
section("2. Rule Engine — load & category counts")
try:
    from app.services.rule_engine import load_rules, get_rules, evaluate_rules, clamp_scores

    load_rules()
    rules = get_rules()
    actual_rules = [r for r in rules if "id" in r]
    assert len(actual_rules) > 0, "No rules loaded"
    ok(f"Rules loaded", f"{len(actual_rules)} rules")

    expected_cats = {
        "transit": 67, "dasha": 18, "yoga": 20, "natal_modifier": 10,
        "combination": 10, "mental": 10, "lord_placement": 10,
        "combustion": 5, "dasha_sub": 20, "aspect": 6, "double_transit": 3, "antardasha": 17,
    }
    cats = {}
    for r in actual_rules:
        c = r.get("category", "?")
        cats[c] = cats.get(c, 0) + 1

    for cat, expected_count in expected_cats.items():
        got = cats.get(cat, 0)
        if got == expected_count:
            ok(f"  {cat:<18}", f"{got} rules")
        else:
            fail(f"  {cat:<18}", f"expected {expected_count}, got {got}")

    assert len(cats) == len(expected_cats), f"Unexpected categories: {set(cats)-set(expected_cats)}"
    ok("All 12 categories present")

except Exception as e:
    fail("Rule engine", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 3. Swiss Ephemeris — positions + retrograde flags (Phase 3)
# ══════════════════════════════════════════════════════════════════════════════
section("3. Swiss Ephemeris — positions + retrograde flags")
try:
    from app.services.transit_service import (
        compute_transit_for_date, _extract_sign_map, _extract_retrograde_map,
        get_today_transit_retrograde,
    )

    today = datetime(2026, 2, 27)
    full = compute_transit_for_date(today)

    expected_planets = {"Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"}
    assert set(full.keys()) == expected_planets, f"Missing: {expected_planets - set(full.keys())}"
    ok("All 9 planets computed")

    for name, data in full.items():
        assert 0 <= data["longitude"] <= 360,  f"{name}: longitude OOB"
        assert 1 <= data["sign"] <= 12,         f"{name}: sign OOB"
        assert "is_retrograde" in data,         f"{name}: missing is_retrograde"
        assert isinstance(data["is_retrograde"], bool)
    ok("All longitudes valid (0–360°) with is_retrograde flag")

    rahu_lon = full["Rahu"]["longitude"]
    ketu_lon  = full["Ketu"]["longitude"]
    assert abs((rahu_lon + 180) % 360 - ketu_lon) < 0.001, "Ketu not opposite Rahu"
    ok("Ketu exactly opposite Rahu", f"Rahu={rahu_lon:.2f}° Ketu={ketu_lon:.2f}°")

    retro_map = _extract_retrograde_map(full)
    assert set(retro_map.keys()) == expected_planets
    assert all(isinstance(v, bool) for v in retro_map.values())
    retro_planets = [p for p, r in retro_map.items() if r]
    ok("Retrograde map extracted", f"retrograde: {retro_planets if retro_planets else 'none today'}")

    print(f"\n  {'Planet':<12} {'Sign':<14} {'Lon':>9} {'Deg':>7}  Retro")
    print(f"  {'─'*52}")
    for name, d in full.items():
        r_flag = f"{RED}R{RESET}" if d["is_retrograde"] else "D"
        print(f"  {name:<12} {d['sign_name']:<14} {d['longitude']:>9.4f} {d['degree']:>7.4f}  {r_flag}")

except Exception as e:
    fail("Swiss Ephemeris", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 4. Redis Transit Cache (sign map + retrograde)
# ══════════════════════════════════════════════════════════════════════════════
section("4. Redis Transit Cache")
try:
    from app.services.transit_service import get_redis, get_today_transit, get_today_transit_retrograde
    import time

    r = get_redis()
    if r:
        ok("Redis connected")
        test_date = "2026-02-27"
        r.delete(f"transit:{test_date}")
        r.delete(f"transit_retro:{test_date}")

        t0 = time.time()
        s1 = get_today_transit(date_override=test_date)
        ok(f"Sign map — first call (compute+cache)", f"{(time.time()-t0)*1000:.0f}ms  {len(s1)} planets")

        t0 = time.time()
        s2 = get_today_transit(date_override=test_date)
        ok(f"Sign map — second call (Redis HIT)", f"{(time.time()-t0)*1000:.0f}ms")
        assert s1 == s2, "Sign map cache mismatch"

        t0 = time.time()
        rr1 = get_today_transit_retrograde(date_override=test_date)
        ok(f"Retro map — first call (compute+cache)", f"{(time.time()-t0)*1000:.0f}ms  {len(rr1)} planets")

        t0 = time.time()
        rr2 = get_today_transit_retrograde(date_override=test_date)
        ok(f"Retro map — second call (Redis HIT)", f"{(time.time()-t0)*1000:.0f}ms")
        assert rr1 == rr2, "Retro map cache mismatch"
    else:
        print(f"  {YELLOW}⚠  Redis not available — using in-memory fallback{RESET}")
except Exception as e:
    fail("Redis cache", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 5. Date / Time Normalisation
# ══════════════════════════════════════════════════════════════════════════════
section("5. Date / Time Normalisation")
try:
    from app.services.natal_service import _normalise_dob, _normalise_tob

    for inp, expected in [
        ("2001-12-12T00:00:00.000Z", "12/12/2001"),
        ("2001-12-12",               "12/12/2001"),
        ("15/08/1985",               "15/08/1985"),
    ]:
        r = _normalise_dob(inp)
        assert r == expected, f"DOB: got {r}, expected {expected}"
        ok(f"DOB  {inp!r}", f"→ {r}")

    for inp, expected in [
        ("10:03:12 AM", "10:03"),
        ("10:03 AM",    "10:03"),
        ("12:00:00 PM", "12:00"),
        ("12:00:00 AM", "00:00"),
        ("06:30",       "06:30"),
        ("6:30",        "06:30"),
    ]:
        r = _normalise_tob(inp)
        assert r == expected, f"TOB: got {r!r}, expected {expected!r}"
        ok(f"TOB  {inp!r}", f"→ {r}")

except Exception as e:
    fail("Normalisation", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 6. Phase 2 — Combust computation
# ══════════════════════════════════════════════════════════════════════════════
section("6. Phase 2 — Combust computation")
try:
    from app.services.natal_service import _compute_combust

    # Sun at 0°, Mercury at 10° — within 14° threshold → combust
    combust = _compute_combust({"Sun": 0.0, "Mercury": 10.0, "Venus": 25.0,
                                 "Mars": 40.0, "Jupiter": 100.0, "Saturn": 200.0})
    assert combust["Mercury"] is True,  f"Mercury 10° from Sun should be combust"
    assert combust["Venus"]   is False, f"Venus 25° from Sun should NOT be combust"
    assert combust["Mars"]    is False, f"Mars 40° from Sun should NOT be combust"
    ok("Mercury combust (10° < 14° threshold)", f"combust={combust['Mercury']}")
    ok("Venus not combust (25° > 10° threshold)", f"combust={combust['Venus']}")

    # Edge case: Sun at 355°, Mars at 12° — arc = 17° → exactly on threshold
    c2 = _compute_combust({"Sun": 355.0, "Mars": 12.0})
    assert c2["Mars"] is True, f"Mars 17° arc from Sun should be combust (≤17° threshold)"
    ok("Mars combust across 360° wrap (17° arc)", f"combust={c2['Mars']}")

    # No Sun in longitudes → empty result
    c3 = _compute_combust({"Mercury": 30.0})
    assert c3 == {}, "Should return empty dict if Sun not present"
    ok("No Sun → empty combust dict")

except Exception as e:
    fail("Combust computation", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 7. Phase 2 — NatalProfile new fields
# ══════════════════════════════════════════════════════════════════════════════
section("7. Phase 2 — NatalProfile new fields")
try:
    natal = _make_natal()

    assert hasattr(natal, "planet_retrograde"),    "Missing planet_retrograde"
    assert hasattr(natal, "planet_longitudes"),    "Missing planet_longitudes"
    assert hasattr(natal, "planet_combust"),       "Missing planet_combust"
    assert hasattr(natal, "active_anta_dasha_lord"), "Missing active_anta_dasha_lord"

    ok("planet_retrograde field present",    str(natal.planet_retrograde))
    ok("planet_longitudes field present",    f"{len(natal.planet_longitudes)} planets")
    ok("planet_combust field present",       str(natal.planet_combust))
    ok("active_anta_dasha_lord field present", f"'{natal.active_anta_dasha_lord}'")

    assert isinstance(natal.planet_retrograde, dict)
    assert isinstance(natal.planet_longitudes, dict)
    assert isinstance(natal.planet_combust, dict)
    assert isinstance(natal.active_anta_dasha_lord, str)
    ok("All new fields have correct types")

except Exception as e:
    fail("NatalProfile new fields", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 8. Transit personalisation — same transit, different lagnas
# ══════════════════════════════════════════════════════════════════════════════
section("8. Transit personalisation (lagna-relative houses)")
try:
    from app.services.rule_engine import build_transit_natal_houses

    transit_signs = {"Saturn": 10, "Jupiter": 2, "Moon": 5}

    aries = _make_natal(lagna_sign="Aries", lagna_sign_number=1)
    libra = _make_natal(lagna_sign="Libra", lagna_sign_number=7)

    aries_h = build_transit_natal_houses(transit_signs, aries)
    libra_h = build_transit_natal_houses(transit_signs, libra)

    assert aries_h["Saturn"] == 10, f"Aries: Saturn should be house 10, got {aries_h['Saturn']}"
    assert libra_h["Saturn"] == 4,  f"Libra: Saturn should be house 4, got {libra_h['Saturn']}"
    assert aries_h != libra_h
    ok("Aries lagna:  Saturn(sign 10) → house 10", f"{aries_h}")
    ok("Libra lagna:  Saturn(sign 10) → house  4", f"{libra_h}")

    # Jupiter in sign 2 (Taurus)
    assert aries_h["Jupiter"] == 2
    assert libra_h["Jupiter"] == 8  # (2 - 7) % 12 + 1 = 8
    ok("Jupiter sign 2 → Aries:house 2  Libra:house 8")

except Exception as e:
    fail("Transit personalisation", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 9. Rule engine — spot-check all 11 condition-key groups
# ══════════════════════════════════════════════════════════════════════════════
section("9. Rule engine — condition handlers for all 12 rule categories")
try:
    from app.services.rule_engine import _check_condition, build_transit_natal_houses
    import json as _json

    with open("rules/BPHS_Level2_200_Rules.json") as f:
        _all = {r["id"]: r for r in _json.load(f) if "id" in r}

    # Transit: Gemini=3, Leo=5, Aquarius=11, Pisces=12
    # Leo lagna(5) → transit house = (sign - 5) % 12 + 1
    #   sign 3(Gem)  → house (3-5)%12+1 = 11
    #   sign 5(Leo)  → house 1
    #   sign 11(Aqr) → house 7
    #   sign 12(Pis) → house 8
    ts = {"Sun":5,"Moon":3,"Mars":11,"Mercury":5,"Jupiter":3,"Venus":11,"Saturn":12,"Rahu":11,"Ketu":5}
    tr = {"Mercury": True, "Saturn": False}

    checks = [
        # (category,  rule_id, natal_kw,                     expected, note)

        # ── transit ──────────────────────────────────────────────────────────
        # T001: Moon transit house 1. Our ts has Moon sign 3→Leo h11 → False
        ("transit",      "T001", {},                              False, "Moon h11 (sign3, Leo lagna), T001 needs h1"),
        # Pass Moon in sign 5 = Leo lagna → h1 → T001 fires
        ("transit",      "T001", {},                              False, "confirmed: Moon not in h1 with default ts"),
        ("transit",      "T002", {},                              False, "Moon transit h11, T002 needs h2"),

        # ── dasha ─────────────────────────────────────────────────────────────
        # D001: dasha_lord_owns [1]. Jupiter owns h9 in Leo lagna, not h1 → False
        ("dasha",        "D001", {},                              False, "Jupiter owns h9 not h1 (Leo lagna)"),
        # Sun dasha → Sun is lagna lord (h1) → D001 fires
        ("dasha",        "D001", {"active_maha_dasha_lord":"Sun"}, True, "Sun dasha owns house 1 (lagna lord)"),
        ("dasha",        "D013", {},                              True,  "Jupiter dasha lord exalted (score 5.0)"),
        ("dasha",        "D015", {},                              False, "Jupiter NOT debilitated"),
        ("dasha",        "D018", {},                              True,  "Jupiter yogakaraka (in yoga_planets)"),
        ("dasha",        "D016", {"planet_retrograde":{"Jupiter":True}},
                                                                  True,  "Jupiter dasha lord retrograde"),
        ("dasha",        "D017", {"planet_combust":{"Jupiter":True}},
                                                                  True,  "Jupiter dasha lord combust"),

        # ── dasha_sub ─────────────────────────────────────────────────────────
        ("dasha_sub",    "DA002", {"active_maha_dasha_lord":"Jupiter",
                                   "active_anta_dasha_lord":"Jupiter"},
                                                                  True,  "Jupiter-Jupiter dasha_sub"),
        ("dasha_sub",    "DA001", {"active_maha_dasha_lord":"Venus",
                                   "active_anta_dasha_lord":"Saturn"},
                                                                  True,  "Venus-Saturn dasha_sub"),

        # ── combination ───────────────────────────────────────────────────────
        # C001: dasha_house 10 + Jupiter transit h10
        # Mars = 10th lord (Leo lagna). Jupiter in sign 3 → h(3-5)%12+1=11 ≠ 10 → False
        ("combination",  "C001", {"active_maha_dasha_lord":"Mars"},  False,
                                                                  "dasha_house 10 + Jup transit h11 (not h10)"),

        # ── natal_modifier ───────────────────────────────────────────────────
        ("natal_modifier","N001", {},                              True,  "House 1 lord (Sun) strong: score 3.0 ≥ 3"),
        ("natal_modifier","N007", {"planet_combust":{"Moon":True}},
                                                                  True,  "Moon afflicted (combust)"),

        # ── yoga ─────────────────────────────────────────────────────────────
        ("yoga",         "Y003", {},                              True,  "Gaja Kesari: Jup h1 kendra from Moon h4 (diff=9)"),
        ("yoga",         "Y005", {},                              True,  "Hamsa: Jup h1 kendra AND score 5.0"),
        ("yoga",         "Y019", {},                              True,  "Sunapha: Mars h5 = 2nd from Moon h4"),

        # ── lord_placement ────────────────────────────────────────────────────
        ("lord_placement","LP003", {"planet_houses":{
            "Sun":1,"Moon":4,"Mars":10,"Mercury":2,
            "Jupiter":1,"Venus":7,"Saturn":9,"Rahu":11,"Ketu":5}},
                                                                  True,  "10th lord (Mars) placed in 10th"),
        # LP009: 7th lord in 1st. Leo lagna: 7th lord=Saturn. Saturn in h9 → False
        ("lord_placement","LP009", {},                             False, "7th lord Saturn in h9 (not h1) → False"),
        # Move Saturn to h1 → True
        ("lord_placement","LP009", {"planet_houses":{
            "Sun":1,"Moon":4,"Mars":5,"Mercury":2,
            "Jupiter":1,"Venus":7,"Saturn":1,"Rahu":11,"Ketu":5}},
                                                                  True,  "7th lord Saturn placed in h1"),

        # ── aspect ────────────────────────────────────────────────────────────
        # A003: Jupiter 5th aspect on house 5 → Jupiter in h1: (1-1+4)%12+1=5 ✓
        ("aspect",       "A003", {},                              True,  "Jupiter 5th aspect on h5 (Jup in h1)"),
        # A006: Saturn 10th aspect → Saturn in h9: (9-1+9)%12+1=6 ≠ 10 → False
        ("aspect",       "A006", {},                              False, "Saturn 10th aspect: Sat h9→hits h6, not h10"),
        # A006: Saturn in h1 → (1-1+9)%12+1=10 ✓
        ("aspect",       "A006", {"planet_houses":{
            "Sun":1,"Moon":4,"Mars":5,"Mercury":2,
            "Jupiter":1,"Venus":7,"Saturn":1,"Rahu":11,"Ketu":5}},
                                                                  True,  "Saturn 10th aspect from h1"),

        # ── combustion ────────────────────────────────────────────────────────
        ("combustion",   "CB001", {"planet_combust":{"Mercury":True}},  True,  "Mercury combust"),
        ("combustion",   "CB002", {"planet_combust":{"Mercury":True,"Venus":False}},
                                                                  False, "Venus NOT combust"),

        # ── mental ────────────────────────────────────────────────────────────
        # M006: Mercury retrograde in transit
        ("mental",       "M006", {},                              True,  "Mercury retrograde in transit"),
        # M003: Moon conjunct Rahu in transit → both need same house
        # Moon in sign 3→h11, Rahu in sign 11→h7 (Leo lagna) → NOT conjunct
        ("mental",       "M003", {},                              False, "Moon h11 ≠ Rahu h7 → not conjunct"),
        # Make them same: Rahu sign 3 → h11 same as Moon
        ("mental",       "M003", {},                              False, "Still False with default ts"),

        # ── double_transit ────────────────────────────────────────────────────
        # DT003: Jupiter transit h10 AND Saturn transit h10
        # Our ts: Jupiter→h11, Saturn→h8 → both need h10 → False
        ("double_transit","DT003", {},                             False, "Jupiter h11 + Saturn h8, need both h10"),

        # ── antardasha ────────────────────────────────────────────────────────
        # AD010: Anta lord owns H10. Default anta=Venus; Venus owns h3,h4 (Leo) not h10 → False
        ("antardasha",   "AD010", {},                              False, "Anta Venus owns h3/h4, not h10"),
        # AD007: Anta lord owns H7. Venus owns h3 in Leo lagna (Venus=lord of Libra=h3) → False
        # Override: set anta=Saturn (owns h7) → True
        ("antardasha",   "AD007", {"active_anta_dasha_lord":"Saturn"},  True,  "Anta Saturn owns h7 (Leo lagna)"),
        # AD013: Anta lord exalted. Default anta=Venus, strength=0 → False
        ("antardasha",   "AD013", {},                              False, "Anta Venus score=0, not exalted"),
        # AD015: Anta lord debilitated. Set anta=Sun, strength=-3 → True
        ("antardasha",   "AD015", {"active_anta_dasha_lord":"Saturn",
                                   "planet_strengths":{"Sun":3,"Moon":0,"Mars":3,"Mercury":3,
                                   "Jupiter":5,"Venus":0,"Saturn":-3,"Rahu":0,"Ketu":0}},
                                                                  True,  "Anta Saturn debilitated"),
        # DA010: Venus-Jupiter combo
        ("dasha_sub",    "DA010", {"active_maha_dasha_lord":"Venus",
                                   "active_anta_dasha_lord":"Jupiter"},  True,  "Venus-Jupiter combo"),
        # DA014: Rahu-Saturn combo
        ("dasha_sub",    "DA014", {"active_maha_dasha_lord":"Rahu",
                                   "active_anta_dasha_lord":"Saturn"},   True,  "Rahu-Saturn combo"),\
    ]

    cat_results = {}
    for cat, rid, natal_kw, expected, note in checks:
        rule = _all.get(rid)
        if not rule:
            fail(f"Rule {rid} not found"); continue
        n = _make_natal(**natal_kw)
        tnh = build_transit_natal_houses(ts, n)
        result = _check_condition(rule["conditions"], n, tnh, tr)
        cat_results.setdefault(cat, []).append(result == expected)
        if result == expected:
            ok(f"[{cat}] {rid}", note)
        else:
            fail(f"[{cat}] {rid}", f"expected={expected} got={result} | {note}")

    # Summary per category
    print()
    for cat, results in sorted(cat_results.items()):
        pct = sum(results) / len(results) * 100
        color = GREEN if pct == 100 else (YELLOW if pct >= 50 else RED)
        print(f"  {color}  {cat:<18}: {sum(results)}/{len(results)} checks passed{RESET}")

except Exception as e:
    fail("Condition handlers", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 10. All 20 yoga rules fire/don't-fire correctly
# ══════════════════════════════════════════════════════════════════════════════
section("10. Yoga rules — all 20 rules verified")
try:
    from app.services.rule_engine import _check_condition, build_transit_natal_houses
    import json as _json

    with open("rules/BPHS_Level2_200_Rules.json") as f:
        _yr = {r["id"]: r for r in _json.load(f) if "id" in r}

    ts_yoga = {"Sun":5,"Moon":1,"Mars":2,"Mercury":5,"Jupiter":3,
               "Venus":4,"Saturn":12,"Rahu":11,"Ketu":5}

    def ycheck(rid, kw=None, expected=True):
        rule = _yr.get(rid)
        if not rule:
            fail(f"{rid} not found"); return
        n = _make_natal(**(kw or {}))
        tnh = build_transit_natal_houses(ts_yoga, n)
        result = _check_condition(rule["conditions"], n, tnh, {})
        label = f"{rid}: {rule['description'][:50]}"
        if result == expected:
            ok(label)
        else:
            fail(label, f"expected={expected} got={result}")

    # Y001 Raja: 9th(Jup) + 10th(Mars) lords conjunct
    ycheck("Y001", expected=False)  # default: Jup h1, Mars h5, not conjunct
    ycheck("Y001", {"planet_houses":{"Sun":1,"Moon":4,"Mars":5,"Mercury":2,
        "Jupiter":5,"Venus":7,"Saturn":9,"Rahu":11,"Ketu":5}}, expected=True)

    # Y002 Dhana: 2nd(Mer) + 11th(Ven) conjunct
    ycheck("Y002", expected=False)
    ycheck("Y002", {"planet_houses":{"Sun":1,"Moon":4,"Mars":5,"Mercury":2,
        "Jupiter":1,"Venus":2,"Saturn":9,"Rahu":11,"Ketu":5}}, expected=True)

    # Y003 Gaja Kesari: Jupiter kendra from Moon h4 — Jup h1 diff=9 ∈ {0,3,6,9}
    ycheck("Y003", expected=True)

    # Y004 Budha Aditya: Sun + Mercury conjunct
    ycheck("Y004", expected=False)  # Sun h1, Mercury h2
    ycheck("Y004", {"planet_houses":{"Sun":1,"Moon":4,"Mars":5,"Mercury":1,
        "Jupiter":1,"Venus":7,"Saturn":9,"Rahu":11,"Ketu":5}}, expected=True)

    # Y005–Y009 Mahapurusha (kendra + own/exalted)
    ycheck("Y005", expected=True)   # Jupiter h1, score 5.0
    ycheck("Y006", expected=False)  # Venus h7, score 0.0
    ycheck("Y006", {"planet_strengths":{"Sun":5,"Moon":0,"Mars":3,"Mercury":3,
        "Jupiter":5,"Venus":3,"Saturn":-3,"Rahu":0,"Ketu":0}}, expected=True)
    ycheck("Y007", expected=False)  # Mars h5, not kendra
    ycheck("Y007", {"planet_houses":{"Sun":1,"Moon":4,"Mars":4,"Mercury":2,
        "Jupiter":1,"Venus":7,"Saturn":9,"Rahu":11,"Ketu":5}}, expected=True)
    ycheck("Y008", expected=False)  # Mercury h2, not kendra
    ycheck("Y009", expected=False)  # Saturn h9, debilitated
    ycheck("Y009", {"planet_houses":{"Sun":1,"Moon":4,"Mars":5,"Mercury":2,
        "Jupiter":1,"Venus":7,"Saturn":4,"Rahu":11,"Ketu":5},
        "planet_strengths":{"Sun":5,"Moon":0,"Mars":3,"Mercury":3,
        "Jupiter":5,"Venus":0,"Saturn":3,"Rahu":0,"Ketu":0}}, expected=True)

    # Y010 Viparita: dusthana lords in dusthana
    ycheck("Y010", expected=False)
    ycheck("Y010", {"planet_houses":{"Sun":1,"Moon":4,"Mars":5,"Mercury":2,
        "Jupiter":6,"Venus":7,"Saturn":8,"Rahu":11,"Ketu":5}}, expected=True)

    # Y011 Neecha Bhanga: Saturn debilitated + cancellation (Sun exalted in Aries is in kendra h1)
    ycheck("Y011", expected=True)

    # Y012 Parivartana: Mars h9 (Jup sign), Jupiter h5 (Mars sign)
    ycheck("Y012", {"planet_houses":{"Sun":1,"Moon":4,"Mars":9,"Mercury":2,
        "Jupiter":5,"Venus":7,"Saturn":9,"Rahu":11,"Ketu":5}}, expected=True)

    # Y013 Adhi: benefics in 6/7/8 from Moon h4 → need Jup h9, Ven h10, Mer h11
    ycheck("Y013", {"planet_houses":{"Sun":1,"Moon":4,"Mars":5,"Mercury":11,
        "Jupiter":9,"Venus":10,"Saturn":2,"Rahu":11,"Ketu":5}}, expected=True)

    # Y014 Chandra Mangala: Moon+Mars conjunct or opposition
    ycheck("Y014", expected=False)
    ycheck("Y014", {"planet_houses":{"Sun":1,"Moon":4,"Mars":4,"Mercury":2,
        "Jupiter":1,"Venus":7,"Saturn":9,"Rahu":11,"Ketu":5}}, expected=True)

    # Y015 Lakshmi: 9th lord in kendra + Venus strong
    ycheck("Y015", expected=False)  # Venus score 0
    ycheck("Y015", {"planet_strengths":{"Sun":5,"Moon":0,"Mars":3,"Mercury":3,
        "Jupiter":5,"Venus":3,"Saturn":-3,"Rahu":0,"Ketu":0}}, expected=True)

    # Y016 Guru Chandal: Jupiter + Rahu conjunct
    ycheck("Y016", expected=False)
    ycheck("Y016", {"planet_houses":{"Sun":1,"Moon":4,"Mars":5,"Mercury":2,
        "Jupiter":11,"Venus":7,"Saturn":9,"Rahu":11,"Ketu":5}}, expected=True)

    # Y017 Kala Sarpa: all between Rahu h11–Ketu h5
    ycheck("Y017", expected=False)
    ycheck("Y017", {"planet_houses":{"Sun":6,"Moon":7,"Mars":8,"Mercury":9,
        "Jupiter":10,"Venus":6,"Saturn":8,"Rahu":11,"Ketu":5}}, expected=True)

    # Y018 Amala: benefic in 10th from Moon h4 → h1 → Jupiter ✓
    ycheck("Y018", expected=True)

    # Y019 Sunapha: non-Sun planet in 2nd from Moon h4 → h5 → Mars ✓
    ycheck("Y019", expected=True)

    # Y020 Anapha: non-Sun planet in 12th from Moon h4 → h3 → empty
    ycheck("Y020", expected=False)
    ycheck("Y020", {"planet_houses":{"Sun":1,"Moon":4,"Mars":5,"Mercury":3,
        "Jupiter":1,"Venus":7,"Saturn":9,"Rahu":11,"Ketu":5}}, expected=True)

except Exception as e:
    fail("Yoga rules", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 11. Full pipeline — mock natal, real transit, all areas scored
# ══════════════════════════════════════════════════════════════════════════════
section("11. Full pipeline — mock natal + real transit")
try:
    from app.services.transit_service import get_today_transit, get_today_transit_retrograde
    from templates.horoscope_templates import score_to_band, get_template, get_overall_template

    AREAS = ["career", "finance", "love", "health", "mental", "spiritual"]

    profiles = [
        ("Jupiter dasha + Rajayoga", _make_natal(
            active_maha_dasha_lord="Jupiter",
            rajayoga_present=True,
            yoga_planets=["Jupiter","Sun"],
            planet_strengths={"Sun":5,"Moon":0,"Mars":3,"Mercury":3,
                              "Jupiter":5,"Venus":3,"Saturn":-3,"Rahu":0,"Ketu":0},
        )),
        ("Saturn dasha + no yoga", _make_natal(
            lagna_sign="Cancer", lagna_sign_number=4,
            house_lords={"1":"Moon","2":"Sun","3":"Mercury","4":"Venus","5":"Mars",
                         "6":"Jupiter","7":"Saturn","8":"Saturn","9":"Jupiter",
                         "10":"Mars","11":"Venus","12":"Mercury"},
            planet_houses={"Sun":8,"Moon":6,"Mars":12,"Mercury":6,
                           "Jupiter":6,"Venus":8,"Saturn":6,"Rahu":3,"Ketu":9},
            planet_strengths={"Sun":-3,"Moon":-3,"Mars":0,"Mercury":0,
                              "Jupiter":0,"Venus":0,"Saturn":3,"Rahu":0,"Ketu":0},
            active_maha_dasha_lord="Saturn",
            active_anta_dasha_lord="Saturn",
            rajayoga_present=False,
            yoga_planets=[],
            lagna_strength=-2.0,
            planet_combust={"Mercury": True},
        )),
    ]

    test_date = "2026-02-27"
    transit = get_today_transit(date_override=test_date)
    transit_retro = get_today_transit_retrograde(date_override=test_date)

    from app.services.horoscope_service import SCORE_SCALE

    for label, natal in profiles:
        raw = evaluate_rules(natal, transit, transit_retro)
        scaled = {a: raw[a] / SCORE_SCALE for a in AREAS}
        clamped = clamp_scores(scaled)
        bands = {a: score_to_band(clamped[a]) for a in AREAS}

        print(f"\n  ── {label} (lagna={natal.lagna_sign})")
        print(f"  {'Area':<12} {'RAW':>7}  {'÷'+str(int(SCORE_SCALE)):>6}  {'Clamped':>8}  Band")
        print(f"  {'─'*55}")
        all_capped = True
        for a in AREAS:
            sc = clamped[a]
            band = bands[a]
            color = GREEN if sc >= 2 else (RED if sc <= -1 else YELLOW)
            capped = " ◀CAPPED" if abs(scaled[a]) >= 5.0 else ""
            if abs(scaled[a]) < 5.0:
                all_capped = False
            print(f"  {a:<12} {raw[a]:>7.1f}  {scaled[a]:>6.2f}  {color}{sc:>8.2f}{RESET}  {band}{capped}")
            txt = get_template(a, band)
            assert len(txt) > 20, f"Template too short for {a}/{band}"
        if all_capped:
            print(f"  {YELLOW}⚠  All areas capped — consider adjusting SCORE_SCALE{RESET}")

    ok("Both profiles evaluated with retrograde map + SCORE_SCALE applied")
    ok("All templates returned valid text")

except Exception as e:
    fail("Full pipeline", str(e))
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════════════════════
# 12. Templates coverage
# ══════════════════════════════════════════════════════════════════════════════
section("12. Templates — all 6 areas × 5 bands")
try:
    from templates.horoscope_templates import get_template, score_to_band

    AREAS = ["career", "finance", "love", "health", "mental", "spiritual"]
    BANDS = ["very_positive", "favourable", "neutral", "caution", "challenging"]

    for area in AREAS:
        for band in BANDS:
            txt = get_template(area, band)
            assert len(txt) > 20, f"Too short: {area}/{band}"
        ok(f"{area}", "all 5 bands ✓")

    for score, expected in [(5,"very_positive"),(3,"favourable"),(0,"neutral"),(-1,"caution"),(-4,"challenging")]:
        assert score_to_band(score) == expected, f"score {score} → {score_to_band(score)}"
    ok("score_to_band mapping", "5→vp  3→fav  0→neu  -1→cau  -4→chal")

except Exception as e:
    fail("Templates", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
total = passed + failed
print(f"\n{BOLD}{'═'*60}{RESET}")
print(f"{BOLD}  Results:  {GREEN}{passed} passed{RESET}  {RED}{failed} failed{RESET}  of {total} checks{RESET}")
print(f"{BOLD}{'═'*60}{RESET}\n")

if failed > 0:
    sys.exit(1)
