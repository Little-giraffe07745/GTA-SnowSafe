"""Monthly snowfall from Environment Canada (Station 51459 — Toronto City Centre).

All SnowSafe cities are in the GTA climate zone and reuse this single station.
The fetch is slow (one HTTP request per year) so we cache aggressively.

Usage:
    python3 -m etl.fetch_snowfall --city toronto
    python3 -m etl.fetch_snowfall --city markham   # copies toronto_*.csv → markham_*.csv
"""

from __future__ import annotations

import argparse
import io
import shutil
from pathlib import Path

import pandas as pd
import requests

from .config import load

EC_BULK_URL = "https://climate.weather.gc.ca/climate_data/bulk_data_e.html"
STATION_ID = 51459        # Toronto City Centre — used for all GTA cities
DEFAULT_YEAR_RANGE = range(2014, 2027)

MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def fetch_monthly(years=DEFAULT_YEAR_RANGE) -> pd.DataFrame:
    """Hit Environment Canada once per year, sum snow by month."""
    rows = []
    for year in years:
        params = {
            "format": "csv",
            "stationID": STATION_ID,
            "Year": year,
            "Month": 1,
            "Day": 1,
            "time": "LST",
            "timeframe": 2,  # 2 = daily data
            "submit": "Download Data",
        }
        print(f"  {year}...", end="", flush=True)
        resp = requests.get(EC_BULK_URL, params=params, timeout=60)
        if resp.status_code != 200 or len(resp.text) < 100:
            print(" failed")
            continue

        df = pd.read_csv(io.StringIO(resp.text), encoding="utf-8-sig")

        snow_col = next(
            (c for c in df.columns if "Total Snow" in c and "Flag" not in c),
            None,
        )
        if snow_col is None:
            print(" no snow column")
            continue
        df[snow_col] = pd.to_numeric(df[snow_col], errors="coerce").fillna(0)

        month_col = next(c for c in df.columns if c.strip() == "Month")
        monthly = df.groupby(month_col)[snow_col].sum()
        for m, cm in monthly.items():
            rows.append({"年份": year, "月份": int(m), "降雪量_cm": round(float(cm), 1)})
        print(f" ok ({len(df)} days)")

    out = pd.DataFrame(rows).sort_values(["年份", "月份"]).reset_index(drop=True)
    out["月份名"] = out["月份"].map(MONTH_NAMES)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--years", type=int, nargs="*", default=None,
                        help="override year range, e.g. --years 2020 2021 2022")
    args = parser.parse_args()

    city = load(args.city)
    src_city = city.get("snow_source_city", city["key"])
    src_csv = Path(f"{src_city}_snowfall_monthly.csv")
    dst_csv = Path(f"{city['key']}_snowfall_monthly.csv")

    # Source city fetches from Environment Canada; others just copy.
    if city["key"] == src_city:
        print(f"{city['display_name_en']} Snowfall (Environment Canada Station {STATION_ID})")
        print("=" * 50)
        years = args.years if args.years else DEFAULT_YEAR_RANGE
        df = fetch_monthly(years=years)
        df.to_csv(dst_csv, index=False, encoding="utf-8-sig")
        print(f"\nSaved: {dst_csv} ({len(df)} months)")
    else:
        if not src_csv.exists():
            raise SystemExit(
                f"{src_csv} not found — run `python3 -m etl.fetch_snowfall "
                f"--city {src_city}` first."
            )
        min_year = city.get("collision_min_year")
        df = pd.read_csv(src_csv)
        if min_year:
            df = df[df["年份"] >= min_year]
        df.to_csv(dst_csv, index=False, encoding="utf-8-sig")
        print(f"Copied {src_csv} → {dst_csv} ({len(df)} months)")


if __name__ == "__main__":
    main()
