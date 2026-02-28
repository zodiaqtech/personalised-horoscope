"""
Pydantic models for natal (birth chart) profile data.
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime


class NatalProfile(BaseModel):
    """
    Computed natal chart profile for a user.
    Stored once per user; never recomputed unless birth details change.
    """
    user_id: str
    name: str

    # Birth details (normalised)
    dob: str                    # "DD/MM/YYYY"
    tob: str                    # "HH:MM"
    pob: str                    # original city string
    lat: float
    lon: float
    tz: float

    # Lagna (Ascendant)
    lagna_sign: str                   # "Aries"
    lagna_sign_number: int            # 1–12
    lagna_house: int = 1              # always 1

    # Other natal data
    planets: Dict[str, dict] = Field(default_factory=dict)
    houses: Dict[int, dict] = Field(default_factory=dict)

    # House lords: house number → ruling planet name
    house_lords: Dict[str, str] = Field(default_factory=dict)
    # e.g. {"1": "Mars", "2": "Venus", ...}

    # Planet placements: planet name → house number
    planet_houses: Dict[str, int] = Field(default_factory=dict)
    # e.g. {"Sun": 3, "Moon": 7, ...}

    # Planet dignity scores: planet name → score (-3 to 5)
    planet_strengths: Dict[str, float] = Field(default_factory=dict)

    # ── Phase 2: new natal data fields ───────────────────────────────

    # Planet retrograde status (parsed from API is_retrograde flag)
    planet_retrograde: Dict[str, bool] = Field(default_factory=dict)
    # e.g. {"Saturn": True, "Mars": False, ...}

    # Planet sidereal longitudes 0–360° (sign_index * 30 + degree_in_sign)
    planet_longitudes: Dict[str, float] = Field(default_factory=dict)
    # e.g. {"Sun": 312.5, "Moon": 45.3, ...}

    # Combust status: planet within combust threshold of Sun
    planet_combust: Dict[str, bool] = Field(default_factory=dict)
    # e.g. {"Mercury": True, "Venus": False, ...}

    # Active Antardasha (sub-period) lord
    active_anta_dasha_lord: str = ""

    # ─────────────────────────────────────────────────────────────────

    # Active Vimshottari Maha Dasha lord
    active_maha_dasha_lord: str = ""

    # Yoga detection
    rajayoga_present: bool = False
    yoga_planets: List[str] = Field(default_factory=list)

    # Overall natal house strength (used for natal_modifier rules)
    lagna_strength: float = 0.0

    computed_at: datetime = Field(default_factory=datetime.utcnow)


class NatalComputeRequest(BaseModel):
    """Request body for POST /natal/compute"""
    user_id: str
    name: str
    dob: str        # accepts "DD/MM/YYYY" or ISO date "YYYY-MM-DD"
    tob: str        # e.g. "10:03 AM", "10:03:12 AM", "10:03"
    pob: str        # city name, e.g. "Prayagraj (Allahabad)"
