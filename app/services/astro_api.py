"""
Vedic Astro API client — adapted from AI-predigest project.
Only sync methods used here (keeps implementation simple).
"""
import requests
from typing import Dict, Optional
from datetime import datetime
from cachetools import TTLCache

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import get_settings

settings = get_settings()

# Transit cache: TTL 1 hour, max 1000 entries
TRANSIT_CACHE: TTLCache = TTLCache(maxsize=1000, ttl=3600)


class VedicAstroAPI:
    """Vedic Astro API client (sync only)"""

    BASE_URL = "https://api.vedicastroapi.com/v3-json"

    def __init__(self):
        self.api_key = settings.VEDIC_ASTRO_API_KEY

    def _make_params(self, dob: str, tob: str, lat: float, lon: float, tz: float = 5.5) -> Dict:
        return {
            "api_key": self.api_key,
            "dob": dob,
            "tob": tob,
            "lat": str(lat),
            "lon": str(lon),
            "tz": tz,
            "lang": "en",
        }

    def _fetch(self, endpoint: str, params: Dict) -> Dict:
        url = f"{self.BASE_URL}/{endpoint}"
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def fetch_geo_search(self, city: str) -> Dict:
        """Resolve city name to lat/lon/tz via geo-search API."""
        params = {"api_key": self.api_key, "city": city}
        result = self._fetch("utilities/geo-search", params)
        return result.get("response", [])

    def fetch_planet_details(
        self, dob: str, tob: str, lat: float, lon: float, tz: float = 5.5
    ) -> Dict:
        """Fetch natal planet positions and house placements."""
        params = self._make_params(dob, tob, lat, lon, tz=tz)
        result = self._fetch("horoscope/planet-details", params)
        return result.get("response", {})

    def fetch_maha_dasha(
        self, dob: str, tob: str, lat: float, lon: float, tz: float = 5.5
    ) -> Dict:
        """Fetch Vimshottari Maha Dasha periods."""
        params = self._make_params(dob, tob, lat, lon, tz=tz)
        result = self._fetch("dashas/maha-dasha", params)
        return result.get("response", {})

    def fetch_antara_dasha(
        self, dob: str, tob: str, lat: float, lon: float, tz: float = 5.5
    ) -> Dict:
        """Fetch Antara Dasha periods."""
        params = self._make_params(dob, tob, lat, lon, tz=tz)
        result = self._fetch("dashas/antar-dasha", params)
        data = result.get("response", {})
        return {
            "antardashas": data.get("antardashas", []),
            "antardasha_order": data.get("antardasha_order", []),
        }

    def fetch_transit_chart(
        self,
        dob: str,
        tob: str,
        lat: float,
        lon: float,
        transit_date: str,
        tz: float = 5.5,
    ) -> Dict:
        """Fetch transit chart for a specific date. Results cached for 1 hour."""
        cache_key = f"{dob}_{tob}_{lat}_{lon}_{transit_date}"
        if cache_key in TRANSIT_CACHE:
            return TRANSIT_CACHE[cache_key]

        params = self._make_params(dob, tob, lat, lon, tz=tz)
        params["div"] = "transit"
        params["transit_date"] = transit_date
        params["response_type"] = "planet_object"

        result = self._fetch("horoscope/divisional-charts", params)
        data = result.get("response", {})
        TRANSIT_CACHE[cache_key] = data
        return data

    def fetch_transit_for_today(
        self,
        dob: str,
        tob: str,
        lat: float,
        lon: float,
        tz: float = 5.5,
    ) -> Dict:
        """Fetch today's transit chart."""
        today_str = datetime.now().strftime("%d/%m/%Y")
        return self.fetch_transit_chart(dob, tob, lat, lon, today_str, tz=tz)


# Singleton
vedic_api = VedicAstroAPI()
