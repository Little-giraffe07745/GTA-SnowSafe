"""City configuration loader. Single source of truth: cities.json at repo root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

_ROOT = Path(__file__).resolve().parent.parent
CITIES_FILE = _ROOT / "cities.json"


def load_all() -> List[dict]:
    """Return the full list of city config dicts."""
    with open(CITIES_FILE, encoding="utf-8") as f:
        return json.load(f)["cities"]


def load(city_key: str) -> dict:
    """Look up one city by its key. Raises KeyError if missing."""
    for city in load_all():
        if city["key"] == city_key:
            return city
    raise KeyError(f"City '{city_key}' not in {CITIES_FILE.name}")


def meta_for_frontend() -> List[dict]:
    """Subset exposed to the in-app city picker (no internal-only fields)."""
    return [
        {
            "key": c["key"],
            "display_name_en": c["display_name_en"],
            "display_name_cn": c["display_name_cn"],
            "lat": c["lat"],
            "lng": c["lng"],
            "default_zoom": c.get("default_zoom", 12),
        }
        for c in load_all()
    ]


if __name__ == "__main__":
    # `python3 -m etl.config` prints the frontend meta JSON.
    print(json.dumps(meta_for_frontend(), ensure_ascii=False, indent=2))
