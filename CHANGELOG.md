# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-07-21

### Added
- **9 GTA Cities**: Toronto, Markham, Richmond Hill, Vaughan, Newmarket, Aurora, East Gwillimbury, Georgina, King
- **Collision Hotspot Maps**: Grid-based severity scoring (collisions + 3×injuries + 5×pedestrians)
- **Snow Risk Analysis**: Per-neighbourhood risk multiplier comparing snow vs non-snow collision rates
- **Live Weather Forecast**: Open-Meteo API integration with 5-day forecast display
- **Unit Conversion**: Toggle between metric (km/h, cm) and imperial (mph, inches)
- **Language Toggle**: English / 中文 interface switching
- **PWA Support**: Offline-capable with service worker
- **Collision Data Export**: JSON export for all cities (capped at 5,000 records per city)

### ETL Pipeline
- Toronto CKAN CSV fetcher with 175MB download caching
- York Regional Police ArcGIS paginated API with OBJECTID deduplication
- Stratified sampling preserving rare collision types (injury, pedestrian, cyclist)
- GeoJSON neighbourhood polygon loading with point-in-polygon assignment

### Security Fixes
- SQL injection prevention in municipality parameter (YRP API)
- Escaped single quotes in SQL WHERE clause

### Performance Optimizations
- LCG-based seeded random (replaces slow Math.sin)
- 8MB download chunks for Toronto CSV
- Cached snowfall max values for normalization

### Bug Fixes
- Fixed undeclared `currentLat` variable causing silent failures
- Fixed `hoursAhead` calculation using weather code instead of time offset
- Fixed division by zero in risk multiplier (0 → np.inf sentinel)
- Fixed stratified sample early break skipping valid strata
- Fixed stratum key ambiguity (added underscore separator)
