"""Tests for etl.weather_parser — keep Python port in sync with the JS in drive_safe_app.html."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from etl.weather_parser import (  # noqa: E402
    FREEZING_PRECIP_CODES,
    WMO_CODES,
    analyze_weather_risk,
    classify_hour,
)


# ---------- classify_hour threshold tests ----------

def test_clear_sky_no_hazards():
    assert classify_hour(code=0) == []


def test_rain_thresholds():
    light = classify_hour(rain_mm=0.6)
    heavy = classify_hour(rain_mm=2.6)
    assert light[0].severity == "moderate"
    assert heavy[0].severity == "high"
    assert all(h.type == "rain" for h in light + heavy)


def test_rain_below_threshold_no_hazard():
    assert classify_hour(rain_mm=0.5) == []   # 0.5 is not > 0.5


def test_snow_thresholds():
    light = classify_hour(snow_cm=0.3)
    heavy = classify_hour(snow_cm=1.1)
    assert light[0].severity == "moderate"
    assert heavy[0].severity == "high"


def test_freezing_precip_codes_all_high():
    for code in FREEZING_PRECIP_CODES:
        hazards = classify_hour(code=code)
        ice = [h for h in hazards if h.type == "ice"]
        assert ice, f"expected ice hazard for code {code}"
        assert ice[0].severity == "high"


def test_wind_thresholds():
    moderate = classify_hour(wind_kmh=45)
    high = classify_hour(wind_kmh=65)
    assert moderate[0].severity == "moderate"
    assert high[0].severity == "high"
    assert all(h.type == "wind" for h in moderate + high)


def test_fog_thresholds():
    moderate = classify_hour(visibility_m=3500)
    high = classify_hour(visibility_m=800)
    assert moderate[0].severity == "moderate"
    assert high[0].severity == "high"
    assert all(h.type == "fog" for h in moderate + high)


def test_thunder_codes_high():
    # codes >= 95 are thunderstorms
    for code in [95, 96, 99]:
        hazards = classify_hour(code=code)
        thunder = [h for h in hazards if h.type == "thunder"]
        assert thunder and thunder[0].severity == "high"


def test_multiple_hazards_one_hour():
    """Heavy rain + high wind should produce 2 distinct hazards."""
    hazards = classify_hour(rain_mm=3, wind_kmh=70)
    types = {h.type for h in hazards}
    assert types == {"rain", "wind"}


# ---------- analyze_weather_risk aggregation tests ----------

def _hourly(values: dict) -> dict:
    """Build an Open-Meteo-style hourly payload from {field: [list]}."""
    return values


def test_analyze_empty_returns_clear():
    risk = analyze_weather_risk({})
    assert risk.level == "clear"
    assert risk.current_hazards == []
    assert risk.upcoming == []


def test_analyze_clear_hours_returns_clear():
    hourly = _hourly({
        "time": ["2026-01-01T00", "2026-01-01T01", "2026-01-01T02"],
        "rain": [0, 0, 0], "snowfall": [0, 0, 0],
        "weathercode": [0, 0, 0], "windspeed_10m": [10, 10, 10],
        "visibility": [24000, 24000, 24000], "temperature_2m": [20, 20, 20],
        "precipitation_probability": [0, 0, 0],
    })
    risk = analyze_weather_risk(hourly)
    assert risk.level == "clear"


def test_analyze_high_severity_in_window_raises_level():
    hourly = _hourly({
        "time": ["2026-01-01T00", "2026-01-01T01", "2026-01-01T02"],
        "rain": [3.0, 0, 0],    # current hour: heavy rain
        "snowfall": [0, 0, 0],
        "weathercode": [0, 0, 0], "windspeed_10m": [10, 10, 10],
        "visibility": [24000, 24000, 24000], "temperature_2m": [20, 20, 20],
        "precipitation_probability": [80, 0, 0],
    })
    risk = analyze_weather_risk(hourly)
    assert risk.level == "severe"
    assert any(h.type == "rain" and h.severity == "high" for h in risk.current_hazards)


def test_analyze_upcoming_moderate_raises_to_moderate():
    hourly = _hourly({
        "time": ["2026-01-01T00", "2026-01-01T01", "2026-01-01T02"],
        "rain": [0, 0.7, 0],    # +1h: moderate rain
        "snowfall": [0, 0, 0],
        "weathercode": [0, 0, 0], "windspeed_10m": [10, 10, 10],
        "visibility": [24000, 24000, 24000], "temperature_2m": [20, 20, 20],
        "precipitation_probability": [0, 60, 0],
    })
    risk = analyze_weather_risk(hourly)
    assert risk.level == "moderate"
    assert len(risk.upcoming) == 1
    assert risk.upcoming[0]["time"] == "In 1 hour"


def test_wmo_codes_lookup():
    assert WMO_CODES[0] == "Clear sky"
    assert WMO_CODES[95] == "Thunderstorm"
    assert WMO_CODES.get(999, "Unknown") == "Unknown"
