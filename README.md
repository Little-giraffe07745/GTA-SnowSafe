# SnowSafe · GTA Winter Driving Safety

> A winter driving safety web app for the Greater Toronto Area that overlays historical collision hotspots, snowfall-risk correlation, and live weather on a single interactive map.

**SnowSafe** merges ~920k historical traffic collision records across 9 GTA cities (Toronto + 8 York Region municipalities) with monthly snowfall data and live Open-Meteo forecasts, then renders them on a Leaflet map you can drop into your phone's home screen.

![status](https://img.shields.io/badge/status-active-green) ![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3.10+-blue) ![javascript](https://img.shields.io/badge/javascript-vanilla-yellow) ![tests](https://github.com/<user>/<repo>/actions/workflows/ci.yml/badge.svg)

---

## What it does

- **One map, all 9 cities** — Toronto, Markham, Richmond Hill, Vaughan, Aurora, Newmarket, King, Georgina, Whitchurch-Stouffville
- **Collision hotspots** — top-30 high-severity intersections per city, with risk score (collisions + 3×injuries + 5×pedestrian)
- **Snow risk multiplier** — per-neighbourhood ratio of "collisions in snow months" vs "non-snow months" — quantifies how much more dangerous snow makes each area
- **Collisions layer** — 38k+ individual collision points (deduplicated, schema-unified, stratified-sampled), color-coded by severity
- **Live weather** — current conditions + 2-hour forecast from Open-Meteo, refreshed every 10 minutes
- **GPS-aware** — follows your location, pops CAUTION / DANGER banners near known hotspots
- **Route test mode** — simulate a drive to preview risk along the path
- **Pure static** — vanilla JS, no build step, no backend, no API keys

## Quick start

You need a local HTTP server (browsers block `fetch()` on `file://` URLs).

```bash
# Clone
git clone https://github.com/<your-username>/snowsafe.git
cd snowsafe

# Serve the app (any of these works)
python3 -m http.server 8765
#   or
npx serve .
#   or use VS Code's "Live Server" extension
```

Open http://localhost:8765/ in your browser.

> **Mobile testing** — connect your phone to the same WiFi as your computer, then visit `http://<your-computer-LAN-IP>:8765/` from the phone.

## Project structure

```
.
├── index.html                # the app (single-file, ~80KB)
├── data/                     # pre-generated JSON consumed by the app
│   ├── <city>.json           # 9 files — hotspots, neighbourhoods, snowfall
│   └── <city>_collisions.json # 9 files — individual collision records
├── cities.json               # city config (coords, data source, year range)
├── etl/                      # Python pipeline that produces data/*.json
│   ├── verify_collisions.py  # data quality profiler → reports/collision_quality.md
│   ├── export_collisions.py  # clean + dedupe + sample → data/<city>_collisions.json
│   ├── run_pipeline.py       # main pipeline → data/<city>.json
│   ├── risk_model.py         # snow-risk math
│   ├── weather_parser.py     # hazard classification (shared with JS)
│   ├── fetch_traffic.py      # pull raw collisions (YRP ArcGIS / Toronto open data)
│   ├── fetch_snowfall.py
│   └── fetch_neighbourhoods.py
├── tests/                    # 33 pytest tests
├── reports/
│   └── collision_quality.md  # full data quality report
├── SnowSafe_报告与使用指南.md # detailed writeup (in Chinese)
└── requirements.txt
```

## Data sources

| Source | Coverage | Used for |
|--------|----------|----------|
| [Toronto Open Data](https://open.toronto.ca/) — KSI collisions | 2014–2026 | Toronto collision records |
| [York Regional Police](https://geoyrp.yrp.ca/) ArcGIS REST API | 2021–2025 | 8 York Region cities |
| Environment Canada historical climate | Toronto monthly snowfall 2014–2026 | Snow-flag normalization |
| [Open-Meteo](https://open-meteo.com/) | live | Current weather + 2h forecast |
| York Region EDI neighbourhoods | boundaries | Neighbourhood aggregation |

Raw CSVs are **not** in this repo (Toronto's alone is 167MB, exceeding GitHub's file limit). Run `python3 -m etl.fetch_traffic --city <key>` to pull them yourself.

## Re-running the ETL

```bash
pip install -r requirements.txt

# 1. Pull raw data (one command per city; safe to re-run)
python3 -m etl.fetch_traffic --city markham
python3 -m etl.fetch_snowfall --city toronto
python3 -m etl.fetch_neighbourhoods --city markham

# 2. Verify data quality
python3 -m etl.verify_collisions
#   → reports/collision_quality.md

# 3. Build per-city app data + collision exports
python3 -m etl.run_pipeline --city markham
python3 -m etl.export_collisions --city markham
#   or run all 9 cities:
python3 -m etl.run_pipeline --all
python3 -m etl.export_collisions

# 4. Run tests
pytest tests/ -v
```

## Data quality

See [`reports/collision_quality.md`](reports/collision_quality.md) for the full report. Key findings:

- **920k raw records** across 9 cities; after cleaning: ~460k unique events
- **Toronto (0,0) placeholders** — 16% of Toronto records have `(0,0)` for "unknown location"; dropped during export
- **YRP duplicates** — 19–36% of York Region rows are duplicates from API pagination overlap; deduplicated during export
- **Pedestrian field incomplete** — only Markham and Richmond Hill populate `PEDESTRIAN=YES`; the other 6 YRP cities return all-NO (API limitation, not ground truth)
- **Sampling** — Toronto is capped at 5000 records per city via stratified sampling that preserves rare injury/pedestrian strata in full

## Tests

```bash
pytest tests/ -v          # 33 tests across risk model, weather parser, export
```

Tests cover:
- `compute_risk_multiplier` math + edge cases
- `identify_street_hotspots` severity scoring
- `assign_neighbourhood` polygon matching + centroid fallback
- Weather hazard classification thresholds (rain/snow/wind/fog/ice/thunder)
- Collision export: schema unification, dedup, sampling, snow flag

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | vanilla JS + [Leaflet](https://leafletjs.com/) | No build step, easy to deploy as static files |
| Map tiles | OpenStreetMap + CartoDB | Free, no API key |
| Weather | Open-Meteo | Free, keyless, CORS-friendly |
| ETL | Python + pandas + shapely | Standard data tooling |
| Tests | pytest | Standard Python testing |
| Deployment | Cloudflare Pages / GitHub Pages (planned) | Free, automatic HTTPS |

## Roadmap

- [x] PWA (offline support, install to home screen)
- [ ] Environment Canada official weather warnings
- [ ] RainViewer precipitation radar overlay
- [ ] 7-day forecast timeline UI
- [ ] Dark mode toggle
- [x] Unit switcher (°C/°F, km/h/mph)
- [x] EN/中文 language toggle

## Documentation

- [`SnowSafe_报告与使用指南.md`](SnowSafe_报告与使用指南.md) — comprehensive project report and user guide (in Chinese)
- [`reports/collision_quality.md`](reports/collision_quality.md) — data quality audit

## License

[MIT](LICENSE) — free to use, modify, share.

## Disclaimer

This app aggregates publicly available collision data for informational purposes only. It is **not** a substitute for official weather alerts, traffic advisories, or your own judgment. Drive safely.
