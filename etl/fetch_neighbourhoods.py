"""York Region EDI neighbourhood boundary fetcher.

Pulls one neighbourhood polygon per OBJECTID via the public York Region
ArcGIS MapServer, writes both CSV (centroids) and GeoJSON (boundaries).

Usage:
    python3 -m etl.fetch_neighbourhoods --city markham
"""

from __future__ import annotations

import argparse
import json
import time

import pandas as pd
import requests

from .config import load

API_URL = (
    "https://ww8.yorkmaps.ca/arcgis/rest/services/"
    "OpenData/Boundary/MapServer/0/query"
)


def _centroid(rings: list) -> tuple[float, float]:
    """Average-vertex centroid. Fine for snow-zone-sized polygons."""
    all_x, all_y = [], []
    for ring in rings:
        for pt in ring:
            all_x.append(pt[0])
            all_y.append(pt[1])
    if not all_x:
        return 0.0, 0.0
    return sum(all_y) / len(all_y), sum(all_x) / len(all_x)


def fetch_one(oid: int) -> dict | None:
    params = {
        "where": f"OBJECTID={oid}",
        "outSR": "4326",
        "f": "json",
        "outFields": "OBJECTID,NBHDNAME,NBHDCODE",
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f" ERROR: {e}")
        return None

    feats = data.get("features", [])
    if not feats:
        return None
    feat = feats[0]
    attr = feat["attributes"]
    rings = feat.get("geometry", {}).get("rings", [])
    lat, lng = _centroid(rings)
    return {
        "oid": oid,
        "name": attr["NBHDNAME"],
        "code": attr["NBHDCODE"],
        "lat": lat,
        "lng": lng,
        "rings": rings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    args = parser.parse_args()

    city = load(args.city)
    if city["data_source"] != "yrp":
        print(f"Skipping {city['key']}: data_source={city['data_source']} has no YRP neighbourhoods.")
        return

    oids = city["neighbourhood_oids"]
    print(f"{city['display_name_en']} Neighbourhood Boundary Fetcher ({len(oids)} OIDs)")
    print("=" * 50)

    rows = []
    geojson_features = []
    for oid in oids:
        print(f"  OBJECTID {oid}...", end="", flush=True)
        result = fetch_one(oid)
        if result is None:
            print(" not found")
            continue
        print(f" {result['name']}  ({result['lat']:.4f}, {result['lng']:.4f})")
        rows.append({
            "OBJECTID": result["oid"],
            "name": result["name"],
            "code": result["code"],
            "centroid_lat": round(result["lat"], 5),
            "centroid_lng": round(result["lng"], 5),
        })
        geojson_features.append({
            "type": "Feature",
            "properties": {"name": result["name"], "code": result["code"]},
            "geometry": {"type": "Polygon", "coordinates": result["rings"]},
        })
        time.sleep(0.2)

    df = pd.DataFrame(rows)
    csv_path = f"{city['key']}_neighbourhoods.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved {len(df)} neighbourhoods to {csv_path}")

    geojson = {"type": "FeatureCollection", "features": geojson_features}
    gj_path = f"{city['key']}_neighbourhoods.geojson"
    with open(gj_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=1)
    print(f"Saved GeoJSON to {gj_path}")


if __name__ == "__main__":
    main()
