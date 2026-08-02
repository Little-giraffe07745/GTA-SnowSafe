# SnowSafe GTA · Winter Driving Safety

> A winter driving safety web app for the Greater Toronto Area. SnowSafe maps historical collision hotspots and snowfall risk across 9 GTA cities, then overlays live weather conditions on a single interactive Leaflet map.

![status](https://img.shields.io/badge/status-active-green) ![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3.10+-blue) ![javascript](https://img.shields.io/badge/javascript-vanilla-yellow)

---

## What it does

- **Collision hotspots** — top-30 highest-severity intersections per city (scored: collisions + 3×injuries + 5×pedestrians)
- **Snow risk multiplier** — per-neighbourhood ratio comparing snow-month vs non-snow-month collision rates
- **Live weather** — current conditions + 2-hour forecast from Open-Meteo, refreshed every 10 minutes
- **9 GTA cities** — Toronto, Markham, Richmond Hill, Vaughan, Aurora, Newmarket, King, Georgina, Whitchurch-Stouffville
- **GPS-aware** — your location triggers CAUTION / DANGER banners near hotspots
- **Route test mode** — simulate a drive and preview risk along the path
- **Pure static** — vanilla JS, no build step, no backend, no API keys

---

## Quick start

```bash
# Clone
git clone https://github.com/Little-giraffe07745/GTA-SnowSafe.git
cd GTA-SnowSafe

# Serve locally (browsers block fetch() on file:// URLs)
python3 -m http.server 8765
```

Open [http://localhost:8765/](http://localhost:8765/) in your browser.

> **Mobile testing** — connect your phone to the same WiFi, then visit `http://YOUR_PC_IP:8765/`

---

## Project structure

```
.
├── index.html                   # the app (~84KB, single-file)
├── data/                        # pre-generated city data (JSON)
│   ├── <city>.json              # 9 files — hotspots, neighbourhoods, snowfall
│   └── <city>_collisions.json   # 9 files — individual collision records
├── cities.json                  # city config (coords, data source, year range)
├── etl/                         # Python pipeline → data/*.json
│   ├── fetch_traffic.py         # YRP ArcGIS / Toronto CKAN fetcher
│   ├── risk_model.py            # risk multiplier + hotspot math
│   ├── export_collisions.py     # clean + dedupe + stratified sample
│   ├── run_pipeline.py          # orchestrates stages 4-5-6
│   ├── weather_parser.py        # hazard classification (shared with JS)
│   └── fetch_snowfall.py
├── tests/                       # 33 pytest tests
├── reports/collision_quality.md # data quality audit
└── SnowSafe_报告与使用指南.md    # project writeup (Chinese)
```

---

## Re-running the ETL pipeline

```bash
pip install -r requirements.txt

# Pull raw collision data per city
python3 -m etl.fetch_traffic --city markham

# Build risk CSVs + app data JSON
python3 -m etl.run_pipeline --city markham

# Export collision JSON (capped at 5000 records/city)
python3 -m etl.export_collisions --city markham

# Run all 9 cities
for city in toronto markham richmond_hill vaughan newmarket aurora king georgina whitchurch_stouffville; do
  python3 -m etl.run_pipeline --city $city
  python3 -m etl.export_collisions --city $city
done
```

---

## Data sources

| Source | Coverage | Used for |
|--------|----------|----------|
| [Toronto Open Data](https://open.toronto.ca/) — KSI collisions | 2014–2026 | Toronto collision records |
| [York Regional Police](https://geoyrp.yrp.ca/) ArcGIS REST API | 2021–2025 | 8 York Region cities |
| Environment Canada historical climate | Toronto 2014–2026 | Monthly snowfall normalization |
| [Open-Meteo](https://open-meteo.com/) | live | Current weather + 2h forecast |
| York Region EDI neighbourhoods | boundaries | Neighbourhood aggregation |

Raw CSVs are not in this repo (Toronto's is ~167MB, exceeding GitHub's file limit). Run `python3 -m etl.fetch_traffic --city <key>` to pull them.

---

## Tests

```bash
pytest tests/ -v
```

33 tests covering risk model math, weather hazard classification, and collision export logic.

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Frontend | vanilla JS + Leaflet |
| Map tiles | OpenStreetMap + CartoDB (free, no API key) |
| Weather | Open-Meteo (free, keyless, CORS-friendly) |
| ETL | Python + pandas + shapely |
| Tests | pytest |

---

## Roadmap

- [ ] Environment Canada official weather warnings
- [ ] RainViewer precipitation radar overlay
- [ ] 7-day forecast timeline UI
- [ ] Dark mode toggle

---

## License

[MIT](LICENSE)

---

## Disclaimer

This app aggregates publicly available collision data for informational purposes only. It is **not** a substitute for official weather alerts, traffic advisories, or your own judgment. Drive safely.
