"""
Pydantic models for horoscope API responses.
"""
from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime


class LifeAreaScores(BaseModel):
    career: float = 0
    finance: float = 0
    love: float = 0
    health: float = 0
    mental: float = 0
    spiritual: float = 0


class LifeAreaBands(BaseModel):
    career: str = "neutral"
    finance: str = "neutral"
    love: str = "neutral"
    health: str = "neutral"
    mental: str = "neutral"
    spiritual: str = "neutral"


class HoroscopeText(BaseModel):
    career: str = ""
    finance: str = ""
    love: str = ""
    health: str = ""
    mental: str = ""
    spiritual: str = ""
    overall: str = ""


class HoroscopeResponse(BaseModel):
    user_id: str
    name: str
    date: str                       # "YYYY-MM-DD"
    active_dasha: str               # current Maha Dasha lord   (e.g. "Jupiter")
    active_anta_dasha: str = ""     # current Antara Dasha lord (e.g. "Venus")
    scores: LifeAreaScores
    bands: LifeAreaBands
    horoscope: HoroscopeText
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class TransitResponse(BaseModel):
    date: str
    transit_houses: Dict[str, int]  # planet → house number
    source: str = "redis"           # "redis" or "api"
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
