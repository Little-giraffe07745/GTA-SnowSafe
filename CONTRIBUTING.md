# Contributing to SnowSafe GTA

Thank you for your interest in contributing to SnowSafe!

## How to Report Bugs

- Open an [issue on GitHub](../../issues/new)
- Include the city name, browser/OS version, and steps to reproduce
- For data discrepancies, specify the CSV file and date range

## How to Submit PRs

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Commit with a clear message
6. Open a pull request

## Coding Standards

### JavaScript
- ES6+ syntax (const/let, arrow functions, template literals)
- 2-space indentation
- Use strict equality (`===`)
- Document functions with JSDoc for public APIs

### Python
- Type hints for function signatures
- PEP 8 style guide
- docstrings for public functions and classes
- 4-space indentation

## Testing Requirements

All 33 tests must pass before merging:
```bash
pytest tests/ -v
```

New features require corresponding tests. Bug fixes require a test that would have caught the bug.

## Project Structure

```
ontario_weather_app/
├── index.html          # Main single-page application
├── etl/                # Data pipeline
│   ├── fetch_traffic.py    # Traffic data fetcher
│   ├── risk_model.py       # Risk calculation
│   ├── export_collisions.py # Collision data export
│   └── run_pipeline.py     # Pipeline orchestrator
├── data/               # City collision JSON files
├── tests/              # pytest test suite
└── *.geojson, *.csv    # City-specific data files
```

## Data Sources

- **Toronto**: Toronto Police Service Open Data (CKAN)
- **York Region**: York Regional Police ArcGIS FeatureServer
- **Weather**: Open-Meteo API (no API key required)
