# SnowSafe — Collision Data Quality Report

Generated: 2026-06-21T10:23:57-04:00

## Per-city profile

| city | schema | rows | year range | missing/zero coords | outliers (bbox) | injury | ped | cyclist | fatal | dup rows |
|------|--------|-----:|:----------:|-------------------:|---------------:|------:|----:|--------:|------:|--------:|
| toronto | toronto | 809,034 | 2014–2026 | 131,978 | 0 | 109,715 | 20,152 | 12,804 | 0 | 0 |
| markham | yrp | 28,511 | 2021–2025 | 0 | 0 | 2,334 | 645 | 355 | 0 | 5,449 |
| richmond_hill | yrp | 17,044 | 2021–2025 | 0 | 0 | 1,368 | 363 | 197 | 0 | 3,397 |
| vaughan | yrp | 41,919 | 2021–2025 | 0 | 0 | 3,196 | 0 | 0 | 0 | 15,070 |
| aurora | yrp | 4,742 | 2021–2025 | 0 | 0 | 374 | 0 | 0 | 0 | 944 |
| newmarket | yrp | 7,304 | 2021–2025 | 0 | 0 | 525 | 0 | 0 | 0 | 1,762 |
| king | yrp | 4,538 | 2021–2025 | 0 | 0 | 414 | 0 | 0 | 0 | 992 |
| georgina | yrp | 3,945 | 2021–2025 | 0 | 0 | 310 | 0 | 0 | 0 | 598 |
| whitchurch_stouffville | yrp | 3,587 | 2021–2024 | 0 | 0 | 323 | 0 | 0 | 0 | 599 |
| **TOTAL** | — | **920,624** | — | **131,978** | **0** | **118,559** | **21,160** | **13,356** | **0** | **28,811** |

## Anomalies / things to investigate

- **toronto**: 131,978 rows with missing or (0,0) placeholder coordinates
- **markham**: 5,449 exact duplicate rows (19.1% — strip in export)
- **richmond_hill**: 3,397 exact duplicate rows (19.9% — strip in export)
- **vaughan**: 15,070 exact duplicate rows (36.0% — strip in export)
- **vaughan**: 0 pedestrian collisions — YRP API field not populated for this municipality (compare to Markham/RH which do report peds)
- **vaughan**: 0 cyclist collisions — InvolveCyclist field appears unused
- **aurora**: 944 exact duplicate rows (19.9% — strip in export)
- **aurora**: 0 pedestrian collisions — YRP API field not populated for this municipality (compare to Markham/RH which do report peds)
- **aurora**: 0 cyclist collisions — InvolveCyclist field appears unused
- **newmarket**: 1,762 exact duplicate rows (24.1% — strip in export)
- **newmarket**: 0 pedestrian collisions — YRP API field not populated for this municipality (compare to Markham/RH which do report peds)
- **newmarket**: 0 cyclist collisions — InvolveCyclist field appears unused
- **king**: 992 exact duplicate rows (21.9% — strip in export)
- **king**: 0 pedestrian collisions — YRP API field not populated for this municipality (compare to Markham/RH which do report peds)
- **king**: 0 cyclist collisions — InvolveCyclist field appears unused
- **georgina**: 598 exact duplicate rows (15.2% — strip in export)
- **georgina**: 0 pedestrian collisions — YRP API field not populated for this municipality (compare to Markham/RH which do report peds)
- **georgina**: 0 cyclist collisions — InvolveCyclist field appears unused
- **whitchurch_stouffville**: 599 exact duplicate rows (16.7% — strip in export)
- **whitchurch_stouffville**: 0 pedestrian collisions — YRP API field not populated for this municipality (compare to Markham/RH which do report peds)
- **whitchurch_stouffville**: 0 cyclist collisions — InvolveCyclist field appears unused

## Year coverage

- 2014: 64,596
- 2015: 67,265
- 2016: 69,669
- 2017: 74,209
- 2018: 79,271
- 2019: 82,832
- 2020: 44,738
- 2021: 65,048
- 2022: 86,052
- 2023: 99,079
- 2024: 102,013
- 2025: 67,581
- 2026: 18,271

## Schema notes

- **Toronto** (Toronto open data CSV): full date/hour, includes FATALITIES, AUTOMOBILE, MOTORCYCLE, PASSENGER, BICYCLE, PEDESTRIAN.
- **YRP** (York Regional Police ArcGIS): IntersectionName, case_type, InvolveCyclist, drug_alcohol. No hour-of-day, no fatality count.
- Cross-schema unification for the app keeps: lat, lng, year, month, injury (bool), pedestrian (bool), cyclist (bool).
