"""
Geo service: resolve city/place of birth to lat, lon, timezone.
Uses VedicAstroAPI geo-search endpoint.
"""
import logging
from typing import Optional
from app.services.astro_api import vedic_api

logger = logging.getLogger(__name__)

# Simple in-process cache to avoid repeated lookups for same city
_geo_cache: dict = {}


def _normalise_city_name(raw_city: str) -> str:
    """
    Strip state/country suffixes stored in the users collection.

    Users often have `pob` values like:
      "Pithoragarh, Uttarakhand, IN"  →  "Pithoragarh"
      "Hyderabad, Telangana, IN"      →  "Hyderabad"
      "Bettiah, Bihar, IN"            →  "Bettiah"
      "Mumbai"                        →  "Mumbai"  (unchanged)

    Strategy: take everything before the first comma, then strip whitespace.
    This is safe because VedicAstroAPI geo-search works best with a bare
    city name — passing state/country confuses the lookup.
    """
    if not raw_city:
        return raw_city
    first_part = raw_city.split(",")[0].strip()
    return first_part if first_part else raw_city.strip()


def resolve_city(city: str) -> Optional[dict]:
    """
    Convert a city name to lat, lon, timezone.

    Automatically normalises compound city strings (e.g. "City, State, IN")
    before querying the geo API so that users with such pob values are not
    silently skipped during the batch job.

    Returns:
        dict with keys: lat (float), lon (float), tz (float), city (str)
        or None if not found.
    """
    city = _normalise_city_name(city)
    city_key = city.strip().lower()
    if city_key in _geo_cache:
        return _geo_cache[city_key]

    try:
        results = vedic_api.fetch_geo_search(city)
        if not results:
            logger.warning(f"Geo-search returned no results for city: {city}")
            return None

        # Take first result — prefer Indian result if available
        if isinstance(results, list):
            indian = [r for r in results if r.get("country") == "IN"]
            first = indian[0] if indian else results[0]
        else:
            first = results

        # API returns coordinates as a 2-element list: ["lat", "lon"]
        coords = first.get("coordinates", [])
        if coords and len(coords) >= 2:
            lat = float(coords[0])
            lon = float(coords[1])
        else:
            lat = float(first.get("latitude", first.get("lat", 0)))
            lon = float(first.get("longitude", first.get("lon", 0)))

        geo = {
            "lat": lat,
            "lon": lon,
            "tz": float(first.get("tz", first.get("timezone", 5.5))),
            "city": first.get("full_name", first.get("name", city)),
        }
        _geo_cache[city_key] = geo
        logger.info(f"Resolved '{city}' → lat={geo['lat']}, lon={geo['lon']}, tz={geo['tz']}")
        return geo

    except Exception as e:
        logger.error(f"Geo-search failed for city '{city}': {e}")
        return None
