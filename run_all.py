"""Run the full SnowSafe pipeline for every city in cities.json.

Order matters: snowfall fetch is the slowest (one HTTP call per year) and is
shared across all GTA cities via Toronto's station, so we fetch it once and
copy. Everything else is per-city.

Usage:
    python3 run_all.py                  # all cities, all stages
    python3 run_all.py --city markham    # one city only
    python3 run_all.py --skip-fetch      # reuse cached raw CSVs
"""

from __future__ import annotations

import argparse
import sys

from etl import config
from etl.fetch_neighbourhoods import main as fetch_neighbourhoods
from etl.fetch_snowfall import main as fetch_snowfall
from etl.fetch_traffic import main as fetch_traffic
from etl.run_pipeline import main as run_pipeline


def run_city(city: dict, skip_fetch: bool) -> None:
    key = city["key"]
    display = city["display_name_en"]
    print(f"\n{'#' * 60}")
    print(f"# {display} ({key})")
    print(f"{'#' * 60}")

    if not skip_fetch:
        sys.argv = ["fetch_traffic", "--city", key]
        fetch_traffic()
        sys.argv = ["fetch_snowfall", "--city", key]
        fetch_snowfall()
        if city["data_source"] == "yrp":
            sys.argv = ["fetch_neighbourhoods", "--city", key]
            fetch_neighbourhoods()

    sys.argv = ["run_pipeline", "--city", key]
    run_pipeline()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", help="run a single city (default: all)")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="reuse cached *_traffic_raw.csv etc., only run risk + build")
    args = parser.parse_args()

    cities = config.load_all()
    if args.city:
        cities = [c for c in cities if c["key"] == args.city]
        if not cities:
            raise SystemExit(f"Unknown city: {args.city}")

    # Snowfall first — all GTA cities reuse Toronto's station.
    toronto_first = sorted(cities, key=lambda c: c["key"] != "toronto")
    for city in toronto_first:
        run_city(city, skip_fetch=args.skip_fetch)

    print(f"\n{'=' * 60}")
    print(f"Done. {len(cities)} cit{'y' if len(cities) == 1 else 'ies'} processed.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
