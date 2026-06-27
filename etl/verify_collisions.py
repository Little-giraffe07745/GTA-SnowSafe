"""Verify collision data quality across all GTA cities.

Handles two schemas:
  - YRP (York Regional Police): *_traffic_raw.csv for 8 cities
  - Toronto open data: traffic_collisions_raw.csv (single mega-file)

Writes a markdown report to reports/collision_quality.md and prints a console
summary. Pure read-only — no side effects on data.

Usage:
    python3 -m etl.verify_collisions
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"

# Approximate GTA bbox for outlier detection (catches swapped lat/lng, bad
# imports, etc.). Generous envelope around the 9 cities we cover.
GTA_BBOX = {"lat_min": 43.4, "lat_max": 44.5, "lng_min": -80.0, "lng_max": -78.9}

# Column name aliases — Toronto and YRP name these differently.
SCHEMA_ALIASES = {
    "year": ["OCC_YEAR"],
    "month": ["OCC_MONTH"],
    "lat": ["LAT_WGS84"],
    "lng": ["LONG_WGS84"],
    "injury": ["INJURY_COLLISIONS", "INJURY_COLLISIONS_YESNO"],
    "pedestrian": ["PEDESTRIAN"],
    "cyclist": ["InvolveCyclist", "BICYCLE"],
    "fatalities": ["FATALITIES"],
    "hour": ["OCC_HOUR"],
    "neighbourhood": ["NEIGHBOURHOOD_158"],
}


def _detect_schema(cols: list[str]) -> str:
    return "toronto" if "OCC_HOUR" in cols or "NEIGHBOURHOOD_158" in cols else "yrp"


def _resolve(df: pd.DataFrame, field: str) -> str | None:
    for c in SCHEMA_ALIASES[field]:
        if c in df.columns:
            return c
    return None


def _yes_count(series: pd.Series) -> int:
    """Count truthy values across a column that may use YES/Y/True/1."""
    if series is None:
        return 0
    s = series.astype(str).str.strip().str.upper()
    return int(
        (s == "YES").sum()
        + (s == "Y").sum()
        + (s == "TRUE").sum()
        + (s == "1").sum()
    )


def profile_file(path: Path, min_year: int) -> dict:
    df = pd.read_csv(path, low_memory=False)
    schema = _detect_schema(list(df.columns))
    n_raw = len(df)

    year_col = _resolve(df, "year")
    month_col = _resolve(df, "month")
    lat_col = _resolve(df, "lat")
    lng_col = _resolve(df, "lng")

    # Filter by min_year (collision_min_year from cities.json).
    df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
    df = df[df[year_col] >= min_year].copy()
    n_after_year = len(df)

    # Coordinate validity. Toronto encodes unknown locations as (0,0)
    # rather than NaN — treat both NaN and (0,0) as missing.
    missing_lat = df[lat_col].isna().sum()
    missing_lng = df[lng_col].isna().sum()
    df["_coords_valid"] = (
        df[lat_col].notna()
        & df[lng_col].notna()
        & (df[lat_col].abs() > 1e-6)
        & (df[lng_col].abs() > 1e-6)
    )
    both_present = df[df["_coords_valid"]].copy()
    n_zero_zero = int((~df["_coords_valid"]).sum())

    # Outliers outside GTA bbox (genuine geographic anomalies).
    in_bbox = (
        (both_present[lat_col] >= GTA_BBOX["lat_min"])
        & (both_present[lat_col] <= GTA_BBOX["lat_max"])
        & (both_present[lng_col] >= GTA_BBOX["lng_min"])
        & (both_present[lng_col] <= GTA_BBOX["lng_max"])
    )
    n_in_bbox = int(in_bbox.sum())
    n_outliers = len(both_present) - n_in_bbox

    # Field completeness.
    injury_col = _resolve(df, "injury")
    ped_col = _resolve(df, "pedestrian")
    cyc_col = _resolve(df, "cyclist")
    fatal_col = _resolve(df, "fatalities")
    hour_col = _resolve(df, "hour")

    n_injury = _yes_count(df[injury_col]) if injury_col else 0
    n_ped = _yes_count(df[ped_col]) if ped_col else 0
    n_cyc = _yes_count(df[cyc_col]) if cyc_col else 0
    n_fatal = _yes_count(df[fatal_col]) if fatal_col else 0

    # Duplicate full rows.
    n_dupes = int(df.duplicated().sum())

    # Duplicate (year, month, lat, lng) — same event re-recorded.
    n_event_dupes = int(
        df.duplicated(subset=[year_col, month_col, lat_col, lng_col]).sum()
    )

    # Year/month coverage.
    year_counts = df[year_col].value_counts().sort_index().to_dict()
    month_counts = (
        df[month_col].value_counts().sort_index().to_dict() if month_col else {}
    )

    # Coordinate span.
    lat_span = (
        (float(both_present[lat_col].min()), float(both_present[lat_col].max()))
        if len(both_present)
        else (None, None)
    )
    lng_span = (
        (float(both_present[lng_col].min()), float(both_present[lng_col].max()))
        if len(both_present)
        else (None, None)
    )

    return {
        "schema": schema,
        "rows_raw": n_raw,
        "rows_after_min_year": n_after_year,
        "min_year": min_year,
        "year_min": int(df[year_col].min()) if len(df) else None,
        "year_max": int(df[year_col].max()) if len(df) else None,
        "missing_lat": int(missing_lat),
        "missing_lng": int(missing_lng),
        "missing_or_zero": n_zero_zero,
        "outliers_bbox": n_outliers,
        "in_bbox": n_in_bbox,
        "injury": n_injury,
        "pedestrian": n_ped,
        "cyclist": n_cyc,
        "fatalities": n_fatal,
        "has_hour": bool(hour_col),
        "has_neighbourhood": bool(_resolve(df, "neighbourhood")),
        "duplicate_full_rows": n_dupes,
        "duplicate_events": n_event_dupes,
        "year_counts": {int(k): int(v) for k, v in year_counts.items()},
        "lat_span": lat_span,
        "lng_span": lng_span,
    }


def load_min_years() -> dict:
    """key -> collision_min_year from cities.json."""
    cities = json.loads((REPO_ROOT / "cities.json").read_text())["cities"]
    return {c["key"]: int(c.get("collision_min_year", 2014)) for c in cities}


def discover_files(min_years: dict) -> list[tuple[str, Path, int]]:
    """(city_key, path, min_year) for all 9 cities."""
    out = []
    for key in min_years:
        candidate = REPO_ROOT / f"{key}_traffic_raw.csv"
        if not candidate.exists() and key == "richmond_hill":
            candidate = REPO_ROOT / "rh_traffic_raw.csv"
        if not candidate.exists() and key == "toronto":
            candidate = REPO_ROOT / "traffic_collisions_raw.csv"
        if candidate.exists():
            out.append((key, candidate, min_years[key]))
    return out


def render_report(results: list[tuple[str, Path, dict]]) -> str:
    lines = []
    lines.append("# SnowSafe — Collision Data Quality Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(tz=None).astimezone().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Per-city profile")
    lines.append("")
    lines.append(
        "| city | schema | rows | year range | missing/zero coords | "
        "outliers (bbox) | injury | ped | cyclist | fatal | dup rows |"
    )
    lines.append(
        "|------|--------|-----:|:----------:|-------------------:|"
        "---------------:|------:|----:|--------:|------:|--------:|"
    )
    totals = {
        "rows": 0, "outliers": 0, "missing": 0,
        "injury": 0, "ped": 0, "cyclist": 0, "fatal": 0, "dupes": 0,
    }
    for key, path, r in results:
        totals["rows"] += r["rows_after_min_year"]
        totals["outliers"] += r["outliers_bbox"]
        totals["missing"] += r["missing_or_zero"]
        totals["injury"] += r["injury"]
        totals["ped"] += r["pedestrian"]
        totals["cyclist"] += r["cyclist"]
        totals["fatal"] += r["fatalities"]
        totals["dupes"] += r["duplicate_full_rows"]
        yr = f"{r['year_min']}–{r['year_max']}" if r["year_min"] else "—"
        lines.append(
            f"| {key} | {r['schema']} | {r['rows_after_min_year']:,} | {yr} | "
            f"{r['missing_or_zero']:,} | {r['outliers_bbox']:,} | {r['injury']:,} | "
            f"{r['pedestrian']:,} | {r['cyclist']:,} | {r['fatalities']:,} | "
            f"{r['duplicate_full_rows']:,} |"
        )
    lines.append(
        f"| **TOTAL** | — | **{totals['rows']:,}** | — | "
        f"**{totals['missing']:,}** | **{totals['outliers']:,}** | "
        f"**{totals['injury']:,}** | **{totals['ped']:,}** | "
        f"**{totals['cyclist']:,}** | **{totals['fatal']:,}** | "
        f"**{totals['dupes']:,}** |"
    )
    lines.append("")
    lines.append("## Anomalies / things to investigate")
    lines.append("")
    # Build anomaly findings programmatically so the report flags real issues.
    findings = []
    for key, path, r in results:
        if r["missing_or_zero"] > 0:
            findings.append(
                f"- **{key}**: {r['missing_or_zero']:,} rows with missing or "
                "(0,0) placeholder coordinates"
            )
        if r["outliers_bbox"] > 0:
            findings.append(
                f"- **{key}**: {r['outliers_bbox']:,} rows outside the GTA bbox "
                f"(lat {GTA_BBOX['lat_min']}–{GTA_BBOX['lat_max']}, "
                f"lng {GTA_BBOX['lng_min']}–{GTA_BBOX['lng_max']})"
            )
        if r["duplicate_full_rows"] > 0:
            findings.append(
                f"- **{key}**: {r['duplicate_full_rows']:,} exact duplicate rows "
                f"({r['duplicate_full_rows'] / r['rows_after_min_year'] * 100:.1f}% "
                "— strip in export)"
            )
        if r["schema"] == "yrp" and r["pedestrian"] == 0:
            findings.append(
                f"- **{key}**: 0 pedestrian collisions — YRP API field not "
                "populated for this municipality (compare to Markham/RH which "
                "do report peds)"
            )
        if r["schema"] == "yrp" and r["cyclist"] == 0:
            findings.append(
                f"- **{key}**: 0 cyclist collisions — InvolveCyclist field "
                "appears unused"
            )
    if findings:
        lines.extend(findings)
    else:
        lines.append("- (none detected)")
    lines.append("")
    lines.append("## Year coverage")
    lines.append("")
    all_years: dict[int, int] = {}
    for _, _, r in results:
        for y, c in r["year_counts"].items():
            all_years[y] = all_years.get(y, 0) + c
    for y in sorted(all_years):
        lines.append(f"- {y}: {all_years[y]:,}")
    lines.append("")
    lines.append("## Schema notes")
    lines.append("")
    lines.append(
        "- **Toronto** (Toronto open data CSV): full date/hour, includes "
        "FATALITIES, AUTOMOBILE, MOTORCYCLE, PASSENGER, BICYCLE, PEDESTRIAN."
    )
    lines.append(
        "- **YRP** (York Regional Police ArcGIS): IntersectionName, case_type, "
        "InvolveCyclist, drug_alcohol. No hour-of-day, no fatality count."
    )
    lines.append(
        "- Cross-schema unification for the app keeps: lat, lng, year, month, "
        "injury (bool), pedestrian (bool), cyclist (bool)."
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    min_years = load_min_years()
    files = discover_files(min_years)
    if not files:
        raise SystemExit("No *_traffic_raw.csv files found — run etl/fetch_traffic.py first")

    print(f"Verifying {len(files)} collision files…\n")
    results = []
    for key, path, min_year in files:
        print(f"  {key:<24} ← {path.name}")
        r = profile_file(path, min_year)
        results.append((key, path, r))

    REPORTS_DIR.mkdir(exist_ok=True)
    report_md = render_report(results)
    out = REPORTS_DIR / "collision_quality.md"
    out.write_text(report_md, encoding="utf-8")
    print(f"\nReport → {out.relative_to(REPO_ROOT.parent)}")

    # Console one-liner summary.
    total_rows = sum(r["rows_after_min_year"] for _, _, r in results)
    total_ped = sum(r["pedestrian"] for _, _, r in results)
    total_outliers = sum(r["outliers_bbox"] for _, _, r in results)
    total_missing = sum(r["missing_or_zero"] for _, _, r in results)
    total_dupes = sum(r["duplicate_full_rows"] for _, _, r in results)
    print(
        f"\nTotals: {total_rows:,} rows across {len(results)} cities | "
        f"pedestrian={total_ped:,} | outliers={total_outliers:,} | "
        f"missing/zero_coords={total_missing:,} | duplicate_rows={total_dupes:,}"
    )


if __name__ == "__main__":
    main()
