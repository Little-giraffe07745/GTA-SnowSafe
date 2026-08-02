"""Export cleaned, sample-capped collision records to data/<city>_collisions.json.

Produces a compact per-city JSON file consumable by the frontend as a new
toggle layer. Handles both schemas (Toronto open data + York Regional Police
ArcGIS) and unifies them.

Cleaning steps:
  - drop rows with missing or (0,0) placeholder coordinates
  - dedupe exact duplicate rows (YRP API returns overlapping pages)
  - filter to collision_min_year from cities.json
  - tag each record with is_snow (same month-had-snow rule as run_pipeline.py)
  - stratified sample per city to keep payload bounded

Output schema (compact keys, ~55 bytes/record):
    {"lat":43.88593,"lng":-79.36726,"y":25,"m":1,"s":1,"i":0,"p":0,"c":0}
  Keys: lat, lng, year (y), month (m), snow (s), injury (i), ped (p), cyclist (c).

Usage:
    python3 -m etl.export_collisions                # all cities
    python3 -m etl.export_collisions --city markham # one city
    python3 -m etl.export_collisions --cap 3000     # override sample cap
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .config import load

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

DEFAULT_CAP = 5000  # max records per city after dedup/clean

# Toronto CSV spells months as names; YRP uses 1-12. Normalize before cleaning.
MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _to_bool(series: pd.Series) -> pd.Series:
    """Coerce a YES/Y/TRUE/1 column to 0/1 int."""
    if series is None:
        return pd.Series([], dtype=int)
    s = series.astype(str).str.strip().str.upper()
    return s.isin(["YES", "Y", "TRUE", "1"]).astype(int)


def _load_raw(city_key: str) -> pd.DataFrame:
    """Load the raw collision CSV for a city, handling both filename patterns."""
    candidates = [
        REPO_ROOT / f"{city_key}_traffic_raw.csv",
        REPO_ROOT / "traffic_collisions_raw.csv",  # toronto's megafile
    ]
    if city_key == "richmond_hill":
        candidates.insert(0, REPO_ROOT / "rh_traffic_raw.csv")
    for p in candidates:
        if p.exists():
            return pd.read_csv(p, low_memory=False)
    raise FileNotFoundError(f"No traffic CSV found for {city_key}")


def _load_snow_lookup(city: dict) -> pd.DataFrame:
    """Two-column (year, month) → snow_cm table; truthy cm means snow happened."""
    snow_src = city.get("snow_source_city", city["key"])
    snow_path = REPO_ROOT / f"{snow_src}_snowfall_monthly.csv"
    snow = pd.read_csv(snow_path)
    return snow[["年份", "月份", "降雪量_cm"]].rename(
        columns={"年份": "year", "月份": "month", "降雪量_cm": "snow_cm"}
    )


def clean_collisions(df: pd.DataFrame, min_year: int, snow_lookup: pd.DataFrame) -> pd.DataFrame:
    """Apply uniform cleaning across both schemas and return a compact frame."""
    # Year filter (Toronto has years back to 1985; YRP is 2021+).
    df = df.copy()
    df["OCC_YEAR"] = pd.to_numeric(df["OCC_YEAR"], errors="coerce")
    # Toronto spells months ("January"), YRP uses 1-12 — coerce both to int.
    if not pd.api.types.is_numeric_dtype(df["OCC_MONTH"]):
        lowered = df["OCC_MONTH"].astype(str).str.strip().str.lower()
        df["OCC_MONTH"] = lowered.map(MONTH_NAMES)
        # Anything still missing after name lookup: maybe numeric strings.
        df["OCC_MONTH"] = df["OCC_MONTH"].fillna(
            pd.to_numeric(lowered, errors="coerce")
        )
    else:
        df["OCC_MONTH"] = pd.to_numeric(df["OCC_MONTH"], errors="coerce")
    df = df.dropna(subset=["OCC_YEAR", "OCC_MONTH"])
    df = df[df["OCC_YEAR"] >= min_year]

    # Drop missing or (0,0) placeholder coords.
    df = df.dropna(subset=["LAT_WGS84", "LONG_WGS84"])
    df = df[(df["LAT_WGS84"].abs() > 1e-6) & (df["LONG_WGS84"].abs() > 1e-6)]

    # Dedupe. We dedupe on the full row to keep things simple, then again on
    # (year, month, lat, lng) event key — same call to fetch_traffic may overlap.
    df = df.drop_duplicates()
    df = df.drop_duplicates(subset=["OCC_YEAR", "OCC_MONTH", "LAT_WGS84", "LONG_WGS84"])

    # Unify boolean fields across schemas.
    df["injury"] = _to_bool(df["INJURY_COLLISIONS"]) if "INJURY_COLLISIONS" in df else 0
    df["ped"] = _to_bool(df["PEDESTRIAN"]) if "PEDESTRIAN" in df else 0
    if "InvolveCyclist" in df:
        df["cyc"] = _to_bool(df["InvolveCyclist"])
    elif "BICYCLE" in df:
        df["cyc"] = _to_bool(df["BICYCLE"])
    else:
        df["cyc"] = 0

    # Snow flag (month-had-snow, same as run_pipeline.py).
    df = df.merge(snow_lookup, left_on=["OCC_YEAR", "OCC_MONTH"],
                  right_on=["year", "month"], how="left")
    df["snow_cm"] = df["snow_cm"].fillna(0)
    df["snow"] = (df["snow_cm"] > 0).astype(int)

    # Final schema.
    out = pd.DataFrame({
        "lat": df["LAT_WGS84"].round(5),
        "lng": df["LONG_WGS84"].round(5),
        "y": df["OCC_YEAR"].astype(int),
        "m": df["OCC_MONTH"].astype(int),
        "s": df["snow"].astype(int),
        "i": df["injury"].astype(int),
        "p": df["ped"].astype(int),
        "c": df["cyc"].astype(int),
    })
    return out.reset_index(drop=True)


def stratified_sample(df: pd.DataFrame, cap: int, seed: int = 42) -> pd.DataFrame:
    """Sample ≤cap rows, stratified by year + severity.

    Rare strata (those that would get <1 row under pure proportional
    allocation) are preserved in full so injury/pedestrian events don't get
    sampled out.
    """
    if len(df) <= cap:
        return df
    df = df.copy()
    df["_stratum"] = df["y"].astype(str) + "_" + df["i"].astype(str) + "_" + df["p"].astype(str)
    total = len(df)
    parts = []
    remaining = cap
    counts = df["_stratum"].value_counts()
    for stratum, n in counts.items():
        quota = cap * n / total  # proportional allocation (float)
        if quota < 1.0:
            take = min(n, remaining)  # rare: preserve fully, but never exceed remaining
        else:
            take = min(n, max(1, round(quota)), remaining)
        if remaining <= 0:
            break
        if take <= 0:
            continue  # skip this stratum, try the next one
        parts.append(df[df["_stratum"] == stratum].sample(n=take, random_state=seed))
        remaining -= take
    out = pd.concat(parts, ignore_index=True)
    return out.drop(columns=["_stratum"]).reset_index(drop=True)


def export_city(city: dict, cap: int, skip_existing_snow: bool = False) -> dict:
    key = city["key"]
    min_year = int(city.get("collision_min_year", 2014))
    raw = _load_raw(key)
    snow = _load_snow_lookup(city)
    cleaned = clean_collisions(raw, min_year, snow)
    total_clean = len(cleaned)
    sampled = stratified_sample(cleaned, cap)

    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / f"{key}_collisions.json"
    payload = {
        "city": key,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "total_clean": total_clean,
        "exported": len(sampled),
        "capped": total_clean > cap,
        "fields": ["lat", "lng", "y", "m", "s", "i", "p", "c"],
        "collisions": sampled.to_dict(orient="records"),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    snow_n = int(sampled["s"].sum())
    inj_n = int(sampled["i"].sum())
    ped_n = int(sampled["p"].sum())
    cyc_n = int(sampled["c"].sum())
    return {
        "key": key,
        "out_path": out_path,
        "total_clean": total_clean,
        "exported": len(sampled),
        "snow": snow_n,
        "injury": inj_n,
        "ped": ped_n,
        "cyclist": cyc_n,
        "size_kb": out_path.stat().st_size // 1024,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", help="single city key (default: all)")
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP,
                        help=f"max records per city (default {DEFAULT_CAP})")
    args = parser.parse_args()

    if args.city:
        cities = [load(args.city)]
    else:
        from .config import load_all
        cities = load_all()

    print(f"Exporting collisions for {len(cities)} cities (cap={args.cap}/city)\n")
    totals = {"exported": 0, "snow": 0, "injury": 0, "ped": 0,
              "cyc": 0, "kb": 0}
    for city in cities:
        r = export_city(city, args.cap)
        print(
            f"  {r['key']:<24} {r['exported']:>6} / {r['total_clean']:>7,} "
            f"(snow={r['snow']:>4}, injury={r['injury']:>4}, "
            f"ped={r['ped']:>3}, "
            f"cyc={r['cyclist']:>3}) → {r['out_path'].name} ({r['size_kb']:,} KB)"
        )
        totals["exported"] += r["exported"]
        totals["snow"] += r["snow"]
        totals["injury"] += r["injury"]
        totals["ped"] += r["ped"]
        totals["cyc"] += r["cyclist"]
        totals["kb"] += r["size_kb"]
    print(
        f"\nTotals: {totals['exported']:,} records | "
        f"snow={totals['snow']:,} injury={totals['injury']:,} "
        f"ped={totals['ped']:,} cyc={totals['cyc']:,} | "
        f"~{totals['kb']:,} KB"
    )


if __name__ == "__main__":
    main()
