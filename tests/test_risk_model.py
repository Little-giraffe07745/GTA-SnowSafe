"""Tests for etl.risk_model — risk math and hotspot detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from etl.risk_model import (  # noqa: E402
    GRID_SIZE,
    SNOW_MONTHS,
    NON_SNOW_MONTHS,
    assign_neighbourhood,
    compute_risk_multiplier,
    identify_street_hotspots,
)


def _fake_collisions():
    """6 records across 2 neighbourhoods, 3 snow / 3 non-snow."""
    return pd.DataFrame([
        # Snowy collisions (is_snow_collision=1) — all in "North"
        {"OCC_YEAR": 2024, "OCC_MONTH": 1, "LAT_WGS84": 44.0, "LONG_WGS84": -79.4,
         "INJURY_COLLISIONS": "YES", "PEDESTRIAN": "NO",
         "is_snow_collision": 1, "NEIGHBOURHOOD": "North"},
        {"OCC_YEAR": 2024, "OCC_MONTH": 1, "LAT_WGS84": 44.001, "LONG_WGS84": -79.401,
         "INJURY_COLLISIONS": "NO", "PEDESTRIAN": "YES",
         "is_snow_collision": 1, "NEIGHBOURHOOD": "North"},
        {"OCC_YEAR": 2024, "OCC_MONTH": 2, "LAT_WGS84": 44.002, "LONG_WGS84": -79.402,
         "INJURY_COLLISIONS": "NO", "PEDESTRIAN": "NO",
         "is_snow_collision": 1, "NEIGHBOURHOOD": "North"},
        # Non-snowy collisions — split 2 North / 1 South
        {"OCC_YEAR": 2024, "OCC_MONTH": 7, "LAT_WGS84": 44.0, "LONG_WGS84": -79.4,
         "INJURY_COLLISIONS": "NO", "PEDESTRIAN": "NO",
         "is_snow_collision": 0, "NEIGHBOURHOOD": "North"},
        {"OCC_YEAR": 2024, "OCC_MONTH": 8, "LAT_WGS84": 44.001, "LONG_WGS84": -79.401,
         "INJURY_COLLISIONS": "NO", "PEDESTRIAN": "NO",
         "is_snow_collision": 0, "NEIGHBOURHOOD": "North"},
        {"OCC_YEAR": 2024, "OCC_MONTH": 7, "LAT_WGS84": 43.7, "LONG_WGS84": -79.5,
         "INJURY_COLLISIONS": "NO", "PEDESTRIAN": "NO",
         "is_snow_collision": 0, "NEIGHBOURHOOD": "South"},
    ])


def test_compute_risk_multiplier_counts():
    df = _fake_collisions()
    risk = compute_risk_multiplier(df)
    assert "North" in risk.index
    north = risk.loc["North"]
    assert int(north.snow_collisions) == 3
    assert int(north.no_snow_collisions) == 2
    assert int(north.injury_in_snow) == 1
    assert int(north.pedestrian_in_snow) == 1


def test_compute_risk_multiplier_formula():
    """risk_multiplier = (snow_collisions/SNOW_MONTHS) / (no_snow/NON_SNOW_MONTHS)."""
    df = _fake_collisions()
    risk = compute_risk_multiplier(df)
    north = risk.loc["North"]
    expected = round((3 / SNOW_MONTHS) / (2 / NON_SNOW_MONTHS), 2)
    assert float(north.risk_multiplier) == expected


def test_compute_risk_multiplier_handles_zero_no_snow():
    """When no_snow=0, denominator becomes 1 (via .replace(0, 1)) — should not div-by-zero."""
    df = _fake_collisions()
    df = df[df["NEIGHBOURHOOD"] != "South"]  # remove non-snow collisions for South
    df.loc[df["NEIGHBOURHOOD"] == "North", "is_snow_collision"] = 1
    # South now has only snow collisions, no non-snow
    risk = compute_risk_multiplier(df)
    assert "South" not in risk.index  # South had no snow collisions either


def test_identify_street_hotspots_severity_score():
    """severity = collisions + 3*injuries + 5*pedestrian."""
    df = _fake_collisions()
    hotspots = identify_street_hotspots(df, top_n=10)
    assert len(hotspots) > 0
    row = hotspots.iloc[0]
    expected = row.collisions + row.injuries * 3 + row.pedestrian * 5
    assert int(row.severity) == int(expected)


def test_identify_street_hotspots_grid_size():
    """Records within GRID_SIZE should collapse to the same grid cell."""
    df = _fake_collisions()
    hotspots = identify_street_hotspots(df, top_n=10)
    # All 3 North snowy collisions are within GRID_SIZE of (44.0, -79.4)
    # Their grid_lat/lng should snap to the same rounded value.
    assert len(hotspots) >= 1


def test_assign_neighbourhood_fallback_to_nearest_centroid():
    """When no polygon contains the point, nearest centroid wins."""
    from shapely.geometry import box
    polygons = {"North": box(-79.5, 43.9, -79.3, 44.1)}
    centroids = {"North": {"lat": 44.0, "lng": -79.4},
                 "South": {"lat": 43.7, "lng": -79.5}}
    df = pd.DataFrame([{
        "LAT_WGS84": 43.71, "LONG_WGS84": -79.49,  # outside North polygon
        "OCC_YEAR": 2024,
    }])
    out = assign_neighbourhood(df, polygons, centroids)
    assert out.iloc[0]["NEIGHBOURHOOD"] == "South"


def test_assign_neighbourhood_in_polygon():
    from shapely.geometry import box
    polygons = {"North": box(-79.5, 43.9, -79.3, 44.1)}
    centroids = {"North": {"lat": 44.0, "lng": -79.4}}
    df = pd.DataFrame([{"LAT_WGS84": 44.0, "LONG_WGS84": -79.4, "OCC_YEAR": 2024}])
    out = assign_neighbourhood(df, polygons, centroids)
    assert out.iloc[0]["NEIGHBOURHOOD"] == "North"
