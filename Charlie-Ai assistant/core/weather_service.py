"""
Real-time Location and Weather Service for CHARLIE AI Assistant.
Provides automatic IP geolocation and live weather telemetry via Open-Meteo API.
Requires zero API keys. Fully offline-tolerant with thread-safe caching.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# WMO Weather code mapping: (Condition name, SVG icon key, Recommended accent color)
_WMO_CODE_MAP = {
    0: ("Clear", "weather_sun", "#f59e0b"),
    1: ("Mainly Clear", "weather_sun_cloud", "#fbbf24"),
    2: ("Partly Cloudy", "weather_sun_cloud", "#fbbf24"),
    3: ("Overcast", "weather_cloud", "#94a3b8"),
    45: ("Foggy", "weather_cloud", "#94a3b8"),
    48: ("Rime Fog", "weather_cloud", "#94a3b8"),
    51: ("Light Drizzle", "weather_rain", "#38bdf8"),
    53: ("Drizzle", "weather_rain", "#38bdf8"),
    55: ("Dense Drizzle", "weather_rain", "#38bdf8"),
    56: ("Freezing Drizzle", "weather_rain", "#67e8f9"),
    57: ("Dense Freezing Drizzle", "weather_rain", "#67e8f9"),
    61: ("Slight Rain", "weather_rain", "#38bdf8"),
    63: ("Moderate Rain", "weather_rain", "#38bdf8"),
    65: ("Heavy Rain", "weather_rain", "#0284c7"),
    66: ("Freezing Rain", "weather_rain", "#67e8f9"),
    67: ("Heavy Freezing Rain", "weather_rain", "#67e8f9"),
    71: ("Slight Snow", "weather_cloud", "#e0e7ff"),
    73: ("Moderate Snow", "weather_cloud", "#e0e7ff"),
    75: ("Heavy Snow", "weather_cloud", "#e0e7ff"),
    77: ("Snow Grains", "weather_cloud", "#e0e7ff"),
    80: ("Rain Showers", "weather_rain", "#38bdf8"),
    81: ("Moderate Showers", "weather_rain", "#38bdf8"),
    82: ("Violent Showers", "weather_rain", "#0284c7"),
    85: ("Snow Showers", "weather_cloud", "#e0e7ff"),
    86: ("Heavy Snow Showers", "weather_cloud", "#e0e7ff"),
    95: ("Thunderstorm", "weather_rain", "#a855f7"),
    96: ("Thunderstorm with Hail", "weather_rain", "#a855f7"),
    99: ("Severe Thunderstorm", "weather_rain", "#a855f7"),
}

_CACHE_LOCK = threading.Lock()
_CACHED_LOCATION: Optional[Dict[str, Any]] = None
_CACHED_WEATHER: Optional[Dict[str, Any]] = None
_LAST_WEATHER_FETCH: float = 0.0
_WEATHER_CACHE_TTL = 900.0  # 15 minutes


def capture_location() -> Dict[str, Any]:
    """Capture current geographic location via public IP geolocation services."""
    global _CACHED_LOCATION
    with _CACHE_LOCK:
        if _CACHED_LOCATION:
            return _CACHED_LOCATION

    # Primary: ip-api.com (fast, no token), fallbacks: ipwhois, freeipapi
    endpoints = [
        ("http://ip-api.com/json/?fields=status,message,country,countryCode,regionName,city,lat,lon", _parse_ip_api),
        ("https://ipwho.is/", _parse_ipwhois),
        ("https://freeipapi.com/api/json", _parse_freeipapi),
    ]

    headers = {"User-Agent": "Charlie-Assistant/2.0 (Desktop AI)"}
    for url, parser in endpoints:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                loc = parser(data)
                if loc and loc.get("city") and loc.get("lat") is not None:
                    with _CACHE_LOCK:
                        _CACHED_LOCATION = loc
                    return loc
        except Exception as e:
            logger.debug("Location provider %s failed: %s", url, e)

    fallback = {
        "city": "Current Location",
        "region": "",
        "country": "",
        "country_code": "",
        "lat": 19.0760,
        "lon": 72.8777,
        "source": "fallback"
    }
    return fallback


def _parse_ip_api(data: dict) -> Optional[Dict[str, Any]]:
    if data.get("status") == "success":
        return {
            "city": data.get("city", "Local"),
            "region": data.get("regionName", ""),
            "country": data.get("country", ""),
            "country_code": data.get("countryCode", ""),
            "lat": float(data.get("lat", 0.0)),
            "lon": float(data.get("lon", 0.0)),
            "source": "ip-api"
        }
    return None


def _parse_ipwhois(data: dict) -> Optional[Dict[str, Any]]:
    if data.get("success"):
        return {
            "city": data.get("city", "Local"),
            "region": data.get("region", ""),
            "country": data.get("country", ""),
            "country_code": data.get("country_code", ""),
            "lat": float(data.get("latitude", 0.0)),
            "lon": float(data.get("longitude", 0.0)),
            "source": "ipwhois"
        }
    return None


def _parse_freeipapi(data: dict) -> Optional[Dict[str, Any]]:
    if data.get("cityName"):
        return {
            "city": data.get("cityName", "Local"),
            "region": data.get("regionName", ""),
            "country": data.get("countryName", ""),
            "country_code": data.get("countryCode", ""),
            "lat": float(data.get("latitude", 0.0)),
            "lon": float(data.get("longitude", 0.0)),
            "source": "freeipapi"
        }
    return None


def get_realtime_weather(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetch live temperature, weather condition, and location."""
    global _CACHED_WEATHER, _LAST_WEATHER_FETCH

    now = time.time()
    with _CACHE_LOCK:
        if not force_refresh and _CACHED_WEATHER and (now - _LAST_WEATHER_FETCH < _WEATHER_CACHE_TTL):
            return _CACHED_WEATHER

    loc = capture_location()
    lat = loc.get("lat", 19.0760)
    lon = loc.get("lon", 72.8777)
    city = loc.get("city", "Current Location")
    country = loc.get("country_code") or loc.get("country", "")

    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,is_day"
    )
    headers = {"User-Agent": "Charlie-Assistant/2.0"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            current = raw.get("current", {})
            temp = float(current.get("temperature_2m", 20.0))
            app_temp = float(current.get("apparent_temperature", temp))
            humidity = int(current.get("relative_humidity_2m", 50))
            wcode = int(current.get("weather_code", 0))
            is_day = bool(current.get("is_day", 1))

            cond_name, icon_key, icon_color = _WMO_CODE_MAP.get(
                wcode, ("Clear", "weather_sun_cloud", "#fbbf24")
            )
            if not is_day and icon_key == "weather_sun":
                cond_name = "Clear Night"
                icon_color = "#93c5fd"

            temp_c_int = round(temp)
            loc_label = f"{city}, {country}".strip(" ,") if country else city

            result = {
                "success": True,
                "city": city,
                "country": country,
                "location_text": loc_label,
                "temp_c": temp_c_int,
                "temp_str": f"{temp_c_int}°C",
                "condition": cond_name,
                "humidity": humidity,
                "apparent_temp_c": round(app_temp),
                "icon_key": icon_key,
                "icon_color": icon_color,
                "display_text": f"{temp_c_int}°C · {cond_name}",
                "timestamp": now,
            }

            with _CACHE_LOCK:
                _CACHED_WEATHER = result
                _LAST_WEATHER_FETCH = now
            return result

    except Exception as e:
        logger.warning("Failed to fetch live weather: %s", e)
        with _CACHE_LOCK:
            if _CACHED_WEATHER:
                return _CACHED_WEATHER

        return {
            "success": False,
            "city": city,
            "country": country,
            "location_text": city,
            "temp_c": 21,
            "temp_str": "--°C",
            "condition": "Offline",
            "humidity": 0,
            "apparent_temp_c": 21,
            "icon_key": "weather_sun_cloud",
            "icon_color": "#94a3b8",
            "display_text": "Live Weather",
            "timestamp": now,
        }
