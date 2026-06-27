"""Tests for etl.export_collisions — locks down cleaning + sampling behaviour."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from etl.export_collisions import (  # noqa: E402
    DEFAULT_CAP,
    MONTH_NAMES,
    clean_collisions,
    stratified_sample,
)


def _snow_lookup() -> pd.DataFrame:
    """3 months across 2 years; month 1 has snow, month 7 does not."""
    return pd.DataFrame({
        "year": [2024, 2024, 2024, 2024, 2025, 2025],
        "month": [1, 6, 7, 12, 1, 6],
        "snow_cm": [40.0, 0.0, 0.0, 25.0, 15.0, 0.0],
    })


def _yrp_df() -> pd.DataFrame:
    return pd.DataFrame({
        "OCC_YEAR": [2024, 2024, 2024, 2024, 2025, 2020, 2024],
        "OCC_MONTH": [1, 7, 1, 1, 6, 1, 1],
        "LAT_WGS84": [43.85, 43.86, 43.85, 43.85, 43.87, 43.85, 43.85],
        "LONG_WGS84": [-79.35, -79.36, -79.35, -79.35, -79.37, -79.35, -79.35],
        "INJURY_COLLISIONS": ["YES", "NO", "NO", "NO", "YES", "NO", "NO"],
        "PEDESTRIAN": ["NO", "NO", "YES", "NO", "NO", "NO", "NO"],
        "InvolveCyclist": [None, "Y", None, None, None, None, None],
    })


def _toronto_df() -> pd.DataFrame:
    """Toronto spells months as names — schema mismatch is the whole point."""
    return pd.DataFrame({
        "OCC_YEAR": [2024, 2024, 2024],
        "OCC_MONTH": ["January", "July", "January"],
        "LAT_WGS84": [43.65, 43.66, 0.0],
        "LONG_WGS84": [-79.38, -79.39, 0.0],
        "INJURY_COLLISIONS": ["YES", "NO", "NO"],
        "PEDESTRIAN": ["NO", "NO", "NO"],
        "BICYCLE": ["YES", "NO", "NO"],
    })


def test_clean_drops_zero_zero_coords():
    df = clean_collisions(_toronto_df(), min_year=2014, snow_lookup=_snow_lookup())
    assert len(df) == 2
    assert (df["lat"].abs() > 0).all()


def test_clean_toronto_month_names():
    df = clean_collisions(_toronto_df(), min_year=2014, snow_lookup=_snow_lookup())
    assert set(df["m"].unique()) == {1, 7}


def test_clean_yrp_dedupes():
    """Rows 1, 3, 4, 7 share (year=2024, month=1, lat, lng) — only one survives."""
    df = clean_collisions(_yrp_df(), min_year=2020, snow_lookup=_snow_lookup())
    jan_2024 = df[(df["y"] == 2024) & (df["m"] == 1)]
    assert len(jan_2024) == 1


def test_clean_respects_min_year():
    """Row 6 is 2020 — min_year=2022 should drop it."""
    df = clean_collisions(_yrp_df(), min_year=2022, snow_lookup=_snow_lookup())
    assert (df["y"] >= 2022).all()


def test_clean_unifies_bools_across_schemas():
    # YRP cyclist uses Y/N — clean should normalize to 1.
    df = clean_collisions(_yrp_df(), min_year=2020, snow_lookup=_snow_lookup())
    july = df[df["m"] == 7].iloc[0]
    assert july["c"] == 1
    # Toronto uses BICYCLE YES/NO.
    df_t = clean_collisions(_toronto_df(), min_year=2014, snow_lookup=_snow_lookup())
    jan = df_t[df_t["m"] == 1].iloc[0]
    assert jan["c"] == 1


def test_clean_snow_flag_from_lookup():
    df = clean_collisions(_yrp_df(), min_year=2020, snow_lookup=_snow_lookup())
    july = df[df["m"] == 7].iloc[0]
    jan = df[df["m"] == 1].iloc[0]
    assert july["s"] == 0
    assert jan["s"] == 1


def test_clean_compact_schema():
    """Output must have exactly the documented compact keys."""
    df = clean_collisions(_yrp_df(), min_year=2020, snow_lookup=_snow_lookup())
    assert set(df.columns) == {"lat", "lng", "y", "m", "s", "i", "p", "c"}


def test_stratified_sample_under_cap_returns_all():
    df = clean_collisions(_yrp_df(), min_year=2020, snow_lookup=_snow_lookup())
    sampled = stratified_sample(df, cap=1000)
    assert len(sampled) == len(df)


def test_stratified_sample_over_cap_caps_total():
    """Synthesize 1000 rows in 4 strata, cap at 100 → sample ≤ 100."""
    big = pd.concat([_yrp_df()] * 200, ignore_index=True)
    df = clean_collisions(big, min_year=2020, snow_lookup=_snow_lookup())
    sampled = stratified_sample(df, cap=100)
    assert len(sampled) <= 100


def test_stratified_sample_preserves_rare_strata():
    """A rare pedestrian row should survive sampling."""
    rows = []
    for _ in range(500):
        rows.append({"OCC_YEAR": 2024, "OCC_MONTH": 7, "LAT_WGS84": 43.85,
                     "LONG_WGS84": -79.35, "INJURY_COLLISIONS": "NO",
                     "PEDESTRIAN": "NO", "InvolveCyclist": None})
    for i in range(3):
        rows.append({"OCC_YEAR": 2024, "OCC_MONTH": 7,
                     "LAT_WGS84": 43.90 + i * 0.001, "LONG_WGS84": -79.35,
                     "INJURY_COLLISIONS": "NO", "PEDESTRIAN": "YES",
                     "InvolveCyclist": None})
    df = clean_collisions(pd.DataFrame(rows), min_year=2020, snow_lookup=_snow_lookup())
    sampled = stratified_sample(df, cap=50)
    # All 3 ped rows should survive since their stratum is small.
    assert sampled["p"].sum() == 3


def test_month_names_dict_complete():
    assert len(MONTH_NAMES) == 12
    assert MONTH_NAMES["january"] == 1
    assert MONTH_NAMES["december"] == 12


def test_default_cap_is_sane():
    assert DEFAULT_CAP >= 1000
    assert DEFAULT_CAP <= 10000
