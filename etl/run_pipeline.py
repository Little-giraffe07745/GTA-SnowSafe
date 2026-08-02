"""Stages 4-5-6 of the SnowSafe pipeline: risk analysis → app data JSON → per-city HTML.

Replaces snow_risk_generic.py with a cities.json-driven version. The HTML build
step (stage 6) is intentionally retained here so the existing per-city URLs keep
working until Phase 2 ships the unified single-HTML app.

Usage:
    python3 -m etl.run_pipeline --city markham
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from .config import load
from .risk_model import (
    assign_neighbourhood,
    compute_risk_multiplier,
    identify_street_hotspots,
    load_neighbourhood_polygons,
)

MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
HTML_TEMPLATE = REPO_ROOT / "drive_safe_app.html"


def _load_inputs(city_key: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    traffic = pd.read_csv(REPO_ROOT / f"{city_key}_traffic_raw.csv")
    snow = pd.read_csv(REPO_ROOT / f"{city_key}_snowfall_monthly.csv")
    snow = snow[["年份", "月份", "降雪量_cm"]].copy()
    traffic = traffic.merge(snow, left_on=["OCC_YEAR", "OCC_MONTH"],
                            right_on=["年份", "月份"], how="left")
    traffic["降雪量_cm"] = traffic["降雪量_cm"].fillna(0)
    traffic["is_snow_collision"] = (traffic["降雪量_cm"] > 0).astype(int)
    return traffic, snow


def _run_risk(city: dict, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    polygons = load_neighbourhood_polygons(str(REPO_ROOT / f"{city['key']}_neighbourhoods.geojson"))
    centroids_df = pd.read_csv(REPO_ROOT / f"{city['key']}_neighbourhoods.csv")
    centroids = {
        row["name"]: {"lat": row["centroid_lat"], "lng": row["centroid_lng"]}
        for _, row in centroids_df.iterrows()
    }
    df = assign_neighbourhood(df, polygons, centroids)
    risk = compute_risk_multiplier(df)
    hotspots = identify_street_hotspots(df)
    return risk, hotspots


def _build_app_data(city: dict, risk: pd.DataFrame, hotspots: pd.DataFrame,
                    snow_monthly: pd.DataFrame) -> dict:
    hotspot_records = [{
        "lat": round(float(row.grid_lat), 5),
        "lng": round(float(row.grid_lng), 5),
        "neighbourhood": str(row.neighbourhood),
        "collisions": int(row.collisions),
        "injuries": int(row.injuries),
        "pedestrian": int(row.pedestrian),
        "severity": int(row.severity),
    } for row in hotspots.itertuples()]

    neighbourhood_records = [{
        "name": str(name),
        "lat": round(float(row.avg_lat), 5),
        "lng": round(float(row.avg_lng), 5),
        "snow_collisions": int(row.snow_collisions),
        "risk_multiplier": float(row.risk_multiplier),
        "injury_in_snow": int(row.injury_in_snow),
        "pedestrian_in_snow": int(row.pedestrian_in_snow),
    } for name, row in risk.iterrows()]

    snowfall_records = [{
        "y": int(row.年份),
        "m": int(row.月份),
        "cm": round(float(row.降雪量_cm), 1),
        "n": MONTH_NAMES.get(int(row.月份), "???"),
    } for row in snow_monthly.itertuples()]

    return {
        "hotspots": hotspot_records,
        "neighbourhoods": neighbourhood_records,
        "alert_radius_m": 300,
        "city_center": {"lat": city["lat"], "lng": city["lng"]},
        "snowfall_monthly": snowfall_records,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
    }


def _build_html(city: dict, app_data_json: str) -> str:
    """String-replace city-specific bits into drive_safe_app.html.

    Phase 2 will replace this with a single dynamic index.html — kept here so
    the legacy per-city URLs keep working until then.
    """
    template = HTML_TEMPLATE.read_text(encoding="utf-8")
    display = city["display_name_en"]
    fly_name = display.replace("-", "").replace(" ", "")

    template = template.replace(
        "<title>Toronto SnowSafe - 冬季驾驶安全助手</title>",
        f"<title>{display} SnowSafe - 冬季驾驶安全助手</title>",
    )
    template = template.replace(
        '<span class="app-title">Toronto SnowSafe</span>',
        f'<span class="app-title">{display} SnowSafe</span>',
    )
    template = template.replace(
        "// Toronto SnowSafe App",
        f"// {display} SnowSafe App",
    )
    template = template.replace("let currentLng = -79.38;",
                                f"let currentLng = {city['lng']};")
    template = template.replace("const lat = currentLat || 43.6532;",
                                f"const lat = currentLat || {city['lat']};")
    template = template.replace("const lng = currentLng || -79.3832;",
                                f"const lng = currentLng || {city['lng']};")
    template = re.sub(
        r'const EMBEDDED_DATA = \{.*?\};',
        f"const EMBEDDED_DATA = {app_data_json.strip()};",
        template, count=1, flags=re.DOTALL,
    )
    template = template.replace(
        "userMarker = L.marker([43.70, -79.38],",
        f"userMarker = L.marker([{city['lat']}, {city['lng']}],",
    )
    template = template.replace(
        '{name: "Toronto", lat: 43.70, lng: -79.38},',
        f'{{name: "{display}", lat: {city["lat"]}, lng: {city["lng"]}}},',
    )
    template = template.replace("function flyToToronto() {",
                                f"function flyTo{fly_name}() {{")
    template = template.replace(
        "map.flyTo([43.70, -79.38], 12, { duration: 1.5 });",
        f"map.flyTo([{city['lat']}, {city['lng']}], 12, {{ duration: 1.5 }});",
    )
    return template


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--skip-html", action="store_true",
                        help="only produce risk CSVs + app_data.json (Phase 2 will use this)")
    args = parser.parse_args()

    city = load(args.city)
    key = city["key"]
    display = city["display_name_en"]

    print(f"\n{display} Pipeline")
    print("=" * 50)

    traffic, snow = _load_inputs(key)
    print(f"  Records: {len(traffic):,}  "
          f"snow: {traffic['is_snow_collision'].sum():,} / "
          f"no-snow: {(traffic['is_snow_collision'] == 0).sum():,}")

    risk, hotspots = _run_risk(city, traffic)
    risk_path = f"{key}_neighbourhood_snow_risk.csv"
    risk.to_csv(risk_path, encoding="utf-8-sig")
    print(f"  Risk → {risk_path}  (range {risk['risk_multiplier'].min():.2f}"
          f"–{risk['risk_multiplier'].max():.2f})")

    hotspot_path = f"{key}_street_hotspots.csv"
    hotspots.to_csv(hotspot_path, index=False, encoding="utf-8-sig")
    print(f"  Hotspots → {hotspot_path} ({len(hotspots)})")

    app_data = _build_app_data(city, risk, hotspots, snow)
    app_data_path = f"{key}_app_data.json"
    app_data_json = json.dumps(app_data, ensure_ascii=False, indent=2)
    Path(app_data_path).write_text(app_data_json, encoding="utf-8")
    print(f"  App data → {app_data_path}")

    if not args.skip_html:
        html = _build_html(city, app_data_json)
        html_path = f"{key}_safe_app.html"
        Path(html_path).write_text(html, encoding="utf-8")
        print(f"  HTML → {html_path} ({len(html):,} chars)")


if __name__ == "__main__":
    main()
