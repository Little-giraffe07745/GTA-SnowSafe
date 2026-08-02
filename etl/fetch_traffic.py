"""Traffic collision data fetcher.

Two backends:
- `toronto_ckan`: downloads the 175MB Toronto Police CSV once, slices to the
  columns the rest of the pipeline needs, writes `<key>_traffic_raw.csv`.
- `yrp`: paginated query against York Regional Police ArcGIS FeatureServer,
  filtered by `municipality='<city>'` from cities.json. Dedupes by OBJECTID
  across pages so the raw CSV doesn't carry the 20–36% duplicate rows that
  resultOffset pagination produces against this API.

Usage:
    python3 -m etl.fetch_traffic --city markham
"""

from __future__ import annotations

import argparse
import io
import os
import time

import pandas as pd
import requests

from .config import load

# GTA-wide sanity bounds — drop records with bogus coords. The municipality
# filter is what actually scopes records to one city; this is just defensive.
GTA_LAT_MIN, GTA_LAT_MAX = 43.5, 45.0
GTA_LNG_MIN, GTA_LNG_MAX = -80.5, -79.0

YRP_API_URL = (
    "https://services8.arcgis.com/lYI034SQcOoxRCR7/arcgis/rest/services/"
    "Road_Safety_2016_to_2020/FeatureServer/0/query"
)
YRP_PAGE_SIZE = 2000

TORONTO_CKAN_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
    "ec53f7b2-769b-4914-91fe-a37ee27a90b3/resource/"
    "cb890861-ed20-4862-bb75-b1f9ec1e58dd/download/"
    "traffic-collisions-4326.csv"
)


def _in_gta(lat: float, lng: float) -> bool:
    return (GTA_LAT_MIN <= lat <= GTA_LAT_MAX) and (GTA_LNG_MIN <= lng <= GTA_LNG_MAX)


def _parse_yrp_record(feat: dict) -> dict | None:
    attr = feat.get("attributes", {})
    geom = feat.get("geometry", {})
    x, y = geom.get("x"), geom.get("y")
    if x is None or y is None:
        return None

    occ_date = attr.get("occ_date")
    year, month = None, None
    if occ_date:
        try:
            dt = pd.Timestamp(str(occ_date)[:10])
            year, month = dt.year, dt.month
        except Exception:
            pass

    case_type = str(attr.get("case_type") or "").lower()
    injury = "YES" if ("injury" in case_type or "fatal" in case_type) else "NO"

    ped_raw = attr.get("InvolvePed")
    pedestrian = "YES" if (
        ped_raw is True or str(ped_raw).upper() in ("YES", "TRUE", "1", "Y")
    ) else "NO"

    object_id = attr.get("OBJECTID")

    return {
        "OCC_YEAR": year,
        "OCC_MONTH": month,
        "INJURY_COLLISIONS": injury,
        "PEDESTRIAN": pedestrian,
        "LONG_WGS84": x,
        "LAT_WGS84": y,
        "_OBJECTID": object_id,
    }


def fetch_yrp(municipality: str) -> pd.DataFrame:
    """Paginated YRP ArcGIS query for one municipality.

    The API returns overlapping pages when resultOffset-based pagination
    runs against a changing backend snapshot. We dedupe by OBJECTID across
    pages so the raw CSV doesn't carry 20–36% duplicate rows (observed
    rates: Vaughan 36%, Markham 19%, RH 20%, Newmarket 24%).
    """
    # Escape single quotes to prevent SQL injection via municipality name
    safe_municipality = municipality.replace("'", "''")
    where = f"municipality='{safe_municipality}'"
    records: list[dict] = []
    seen_ids: set = set()
    dup_count = 0
    offset = 0

    while True:
        params = {
            "where": where,
            "outFields": "OBJECTID,occ_date,case_type,InvolvePed,municipality",
            "outSR": "4326",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": YRP_PAGE_SIZE,
        }
        print(f"  offset={offset}...", end="", flush=True)
        resp = requests.get(YRP_API_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            print(" no more records")
            break

        kept = 0
        page_dups = 0
        for feat in features:
            rec = _parse_yrp_record(feat)
            if rec is None:
                continue
            if rec["OCC_YEAR"] is None:
                continue
            if not _in_gta(rec["LAT_WGS84"], rec["LONG_WGS84"]):
                continue
            oid = rec.pop("_OBJECTID", None)
            if oid is not None:
                key = (municipality, oid)
                if key in seen_ids:
                    page_dups += 1
                    dup_count += 1
                    continue
                seen_ids.add(key)
            records.append(rec)
            kept += 1
        msg = f" got {len(features)} (kept {kept}"
        if page_dups:
            msg += f", deduped {page_dups}"
        msg += f", total {len(records)})"
        print(msg)

        if not data.get("exceededTransferLimit"):
            break
        offset += YRP_PAGE_SIZE
        time.sleep(0.3)

    if dup_count:
        print(f"  fetch-time dedup removed {dup_count:,} duplicate OBJECTIDs")

    if not records:
        return pd.DataFrame(columns=["OCC_YEAR", "OCC_MONTH", "INJURY_COLLISIONS",
                                     "PEDESTRIAN", "LONG_WGS84", "LAT_WGS84"])

    df = pd.DataFrame(records)
    df["OCC_YEAR"] = df["OCC_YEAR"].astype(int)
    df["OCC_MONTH"] = df["OCC_MONTH"].astype(int)
    return df


def fetch_toronto_ckan(raw_cache_path: str | None = None) -> pd.DataFrame:
    """Download Toronto's 175MB collisions CSV (cached) and slice to canonical columns."""
    raw_path = raw_cache_path or "traffic_collisions_raw.csv"

    if not os.path.exists(raw_path):
        print(f"  downloading Toronto CSV (~175MB)...")
        resp = requests.get(TORONTO_CKAN_URL, stream=True, timeout=120)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(raw_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {downloaded / 1e6:.1f} MB ({pct:.0f}%)", end="", flush=True)
        print()

    df = pd.read_csv(raw_path)
    return df[["OCC_YEAR", "OCC_MONTH", "INJURY_COLLISIONS", "PEDESTRIAN",
               "LONG_WGS84", "LAT_WGS84"]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True, help="city key from cities.json")
    args = parser.parse_args()

    city = load(args.city)
    print(f"{city['display_name_en']} Fetch Traffic Data")
    print("=" * 50)

    if city["data_source"] == "toronto_ckan":
        df = fetch_toronto_ckan()
    elif city["data_source"] == "yrp":
        df = fetch_yrp(city["yrp_municipality"])
    else:
        raise ValueError(f"Unknown data_source: {city['data_source']}")

    min_year = city.get("collision_min_year")
    if min_year:
        df = df[df["OCC_YEAR"] >= min_year]

    output = f"{city['key']}_traffic_raw.csv"
    df.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {output}  ({len(df):,} records)")
    print(f"  Years: {df['OCC_YEAR'].min()} - {df['OCC_YEAR'].max()}")
    print(f"  Injuries: {(df['INJURY_COLLISIONS'] == 'YES').sum():,}")


if __name__ == "__main__":
    main()
