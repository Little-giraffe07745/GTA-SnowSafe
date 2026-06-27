"""Weather hazard classification — Python port of analyzeWeatherRisk() from drive_safe_app.html.

Kept in sync with the JS implementation so server-side callers (alerts, CI) and
the in-app client agree on what counts as a hazard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers", 81: "Moderate showers", 82: "Violent showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm + hail", 99: "Thunderstorm + heavy hail",
}

FREEZING_PRECIP_CODES = {56, 57, 66, 67}


@dataclass
class Hazard:
    type: str          # rain | snow | ice | wind | fog | thunder
    severity: str      # moderate | high
    msg: str


@dataclass
class WeatherRisk:
    level: str = "clear"            # clear | moderate | severe
    current_hazards: List[Hazard] = field(default_factory=list)
    upcoming: List[dict] = field(default_factory=list)
    current_code: int = 0
    current_desc: str = "Unknown"


def classify_hour(
    rain_mm: float = 0.0,
    snow_cm: float = 0.0,
    code: int = 0,
    wind_kmh: float = 0.0,
    visibility_m: float = 24000.0,
    temp_c: float = 20.0,
) -> List[Hazard]:
    """Return hazards for one hour. Mirrors the per-hour block of analyzeWeatherRisk()."""
    hazards: List[Hazard] = []

    if rain_mm > 2.5:
        hazards.append(Hazard("rain", "high", f"Heavy rain {rain_mm:.1f} mm/h"))
    elif rain_mm > 0.5:
        hazards.append(Hazard("rain", "moderate", f"Rain {rain_mm:.1f} mm/h"))

    if snow_cm > 1.0:
        hazards.append(Hazard("snow", "high", f"Heavy snow {snow_cm:.1f} cm/h"))
    elif snow_cm > 0.2:
        hazards.append(Hazard("snow", "moderate", f"Snow {snow_cm:.1f} cm/h"))

    if code in FREEZING_PRECIP_CODES:
        hazards.append(Hazard("ice", "high", "Freezing precipitation - BLACK ICE RISK"))

    if wind_kmh > 60:
        hazards.append(Hazard("wind", "high", f"Dangerous wind {round(wind_kmh)} km/h"))
    elif wind_kmh > 40:
        hazards.append(Hazard("wind", "moderate", f"Strong wind {round(wind_kmh)} km/h"))

    if visibility_m < 1000:
        hazards.append(Hazard("fog", "high", f"Very low visibility {round(visibility_m)} m"))
    elif visibility_m < 4000:
        hazards.append(Hazard("fog", "moderate", f"Low visibility {round(visibility_m)} m"))

    if code >= 95:
        hazards.append(Hazard("thunder", "high", "Thunderstorm"))

    return hazards


def analyze_weather_risk(hourly: dict) -> WeatherRisk:
    """Top-level analysis over an Open-Meteo hourly block.

    `hourly` is the Open-Meteo payload: {time: [...], rain: [...], snowfall: [...],
    weathercode: [...], windspeed_10m: [...], visibility: [...], temperature_2m: [...],
    precipitation_probability: [...]}.
    """
    if not hourly:
        return WeatherRisk()

    times = hourly.get("time", [])
    n = len(times)
    if n == 0:
        return WeatherRisk()

    current_idx = 0
    current_hazards: List[Hazard] = []
    upcoming: List[dict] = []

    end = min(current_idx + 7, n)
    for i in range(current_idx, end):
        hour_hazards = classify_hour(
            rain_mm=(hourly.get("rain") or [0] * n)[i],
            snow_cm=(hourly.get("snowfall") or [0] * n)[i],
            code=(hourly.get("weathercode") or [0] * n)[i],
            wind_kmh=(hourly.get("windspeed_10m") or [0] * n)[i],
            visibility_m=(hourly.get("visibility") or [24000] * n)[i],
            temp_c=(hourly.get("temperature_2m") or [20] * n)[i],
        )
        if not hour_hazards:
            continue
        hours_ahead = i - current_idx
        time_label = "Now" if hours_ahead == 0 else (
            "In 1 hour" if hours_ahead == 1 else f"In {hours_ahead} hours"
        )
        if hours_ahead == 0:
            current_hazards.extend(hour_hazards)
        else:
            upcoming.append({
                "time": time_label,
                "timeIdx": i,
                "hazards": [{"type": h.type, "severity": h.severity, "msg": h.msg}
                            for h in hour_hazards],
                "code": (hourly.get("weathercode") or [0] * n)[i],
                "prob": (hourly.get("precipitation_probability") or [0] * n)[i],
            })

    has_high = any(h.severity == "high" for h in current_hazards) or \
        any(h["severity"] == "high" for u in upcoming for h in u["hazards"])
    has_moderate = any(h.severity == "moderate" for h in current_hazards) or \
        any(h["severity"] == "moderate" for u in upcoming for h in u["hazards"])

    level = "severe" if has_high else ("moderate" if has_moderate else "clear")

    current_code = (hourly.get("weathercode") or [0] * n)[current_idx] if n else 0
    return WeatherRisk(
        level=level,
        current_hazards=current_hazards,
        upcoming=upcoming,
        current_code=current_code,
        current_desc=WMO_CODES.get(current_code, "Unknown"),
    )
