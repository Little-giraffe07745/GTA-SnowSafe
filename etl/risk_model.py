"""Snow-collision risk math. Pure functions, importable by tests.

Extracted from snow_risk_generic.py — the actual algorithm is unchanged, just
re-organized so compute_risk_multiplier() and identify_street_hotspots() can be
called without running the full pipeline.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd
from shapely.geometry import Point

# Snow-season definition used to normalize monthly collision counts.
SNOW_MONTHS = 5
NON_SNOW_MONTHS = 7

# Grid size (degrees) for street-level hotspot aggregation.
GRID_SIZE = 0.005

# Number of top hotspots to surface in the app.
TOP_N_HOTSPOTS = 30


def assign_neighbourhood(df: pd.DataFrame, polygons: Dict, centroids: Dict) -> pd.DataFrame:
    """Tag each collision with its neighbourhood name.

    Uses point-in-polygon first; if no polygon contains the point, falls back
    to the nearest centroid across the full centroids dict (centroids may
    cover neighbourhoods missing from the polygons layer).
    """
    poly_items = list(polygons.items())
    cent_names = list(centroids.keys())
    cent_lats = np.array([centroids[n]["lat"] for n in cent_names])
    cent_lngs = np.array([centroids[n]["lng"] for n in cent_names])

    result: List[str] = []
    for _, row in df.iterrows():
        pt = Point(row["LONG_WGS84"], row["LAT_WGS84"])
        assigned = None
        for name, poly in poly_items:
            if poly.contains(pt):
                assigned = name
                break
        if assigned is None and cent_names:
            dists = (row["LAT_WGS84"] - cent_lats) ** 2 + \
                    (row["LONG_WGS84"] - cent_lngs) ** 2
            assigned = cent_names[int(np.argmin(dists))]
        result.append(assigned)

    df = df.copy()
    df["NEIGHBOURHOOD"] = result
    return df


def compute_risk_multiplier(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-neighbourhood snow vs no-snow collision counts and risk multiplier.

    Input df must have: NEIGHBOURHOOD, is_snow_collision (0/1), OCC_YEAR,
    INJURY_COLLISIONS (YES/NO), PEDESTRIAN (YES/NO), LONG_WGS84, LAT_WGS84.
    """
    stats = df.groupby(["NEIGHBOURHOOD", "is_snow_collision"]).agg(
        collisions=("OCC_YEAR", "size"),
        injuries=("INJURY_COLLISIONS", lambda x: (x == "YES").sum()),
        pedestrian=("PEDESTRIAN", lambda x: (x == "YES").sum()),
        avg_lng=("LONG_WGS84", "mean"),
        avg_lat=("LAT_WGS84", "mean"),
    ).reset_index()

    snow = stats[stats["is_snow_collision"] == 1].set_index("NEIGHBOURHOOD")
    no_snow = stats[stats["is_snow_collision"] == 0].set_index("NEIGHBOURHOOD")

    risk = pd.DataFrame(index=snow.index)
    risk["snow_collisions"] = snow["collisions"]
    risk["no_snow_collisions"] = no_snow["collisions"].reindex(risk.index).fillna(0)
    risk["injury_in_snow"] = snow["injuries"]
    risk["pedestrian_in_snow"] = snow["pedestrian"]
    risk["avg_lng"] = snow["avg_lng"]
    risk["avg_lat"] = snow["avg_lat"]

    risk["snow_monthly_avg"] = risk["snow_collisions"] / SNOW_MONTHS
    risk["no_snow_monthly_avg"] = risk["no_snow_collisions"] / NON_SNOW_MONTHS
    # If no_snow_monthly_avg is 0 but snow_monthly_avg > 0, risk is effectively infinite
    risk["risk_multiplier"] = (
        risk["snow_monthly_avg"] / risk["no_snow_monthly_avg"].replace(0, np.inf)
    ).replace([np.inf], [999]).round(2)  # cap at 999 for display

    return risk.sort_values("snow_collisions", ascending=False)


def identify_street_hotspots(df: pd.DataFrame, top_n: int = TOP_N_HOTSPOTS) -> pd.DataFrame:
    """Grid-based top-N hotspots by severity score (collisions + 3*injuries + 5*ped)."""
    snow_df = df[df["is_snow_collision"] == 1].copy()
    snow_df["grid_lat"] = (snow_df["LAT_WGS84"] / GRID_SIZE).round() * GRID_SIZE
    snow_df["grid_lng"] = (snow_df["LONG_WGS84"] / GRID_SIZE).round() * GRID_SIZE

    grid_stats = snow_df.groupby(["grid_lat", "grid_lng"]).agg(
        collisions=("OCC_YEAR", "size"),
        injuries=("INJURY_COLLISIONS", lambda x: (x == "YES").sum()),
        pedestrian=("PEDESTRIAN", lambda x: (x == "YES").sum()),
        neighbourhood=("NEIGHBOURHOOD", lambda x: x.mode().iloc[0]
                       if len(x.mode()) > 0 else "Unknown"),
    ).reset_index()

    grid_stats["severity"] = (
        grid_stats["collisions"]
        + grid_stats["injuries"] * 3
        + grid_stats["pedestrian"] * 5
    )

    return grid_stats.nlargest(top_n, "severity")


def load_neighbourhood_polygons(geojson_path: str) -> Dict:
    """Load a York Region GeoJSON file → {name: shapely polygon}."""
    import json
    from shapely.geometry import shape

    with open(geojson_path, encoding="utf-8") as f:
        geojson = json.load(f)

    return {
        feat["properties"]["name"]: shape(feat["geometry"])
        for feat in geojson["features"]
    }
