# tests/test_transit_personalisation.py

from app.services.rule_engine import build_transit_natal_houses
from app.models.natal_profile import NatalProfile


def create_fake_natal(lagna_sign, lagna_num):
    return NatalProfile(
        user_id="test",
        name="Test",
        dob="01/01/1990",
        tob="10:00",
        pob="Test",
        lat=0,
        lon=0,
        tz=5.5,
        lagna_sign=lagna_sign,
        lagna_sign_number=lagna_num,
        house_lords={},
        planet_houses={},
        planet_strengths={},
        active_maha_dasha_lord="Jupiter",
        rajayoga_present=False,
        yoga_planets=[],
        lagna_strength=1.0,
    )


def test_same_transit_different_users():
    transit_signs = {"Saturn": 10}

    aries = create_fake_natal("Aries", 1)
    libra = create_fake_natal("Libra", 7)

    aries_houses = build_transit_natal_houses(transit_signs, aries)
    libra_houses = build_transit_natal_houses(transit_signs, libra)

    assert aries_houses["Saturn"] == 10
    assert libra_houses["Saturn"] == 4
    assert aries_houses != libra_houses