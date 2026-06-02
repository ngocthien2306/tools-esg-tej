# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ESG Lab** is a self-contained web tool for panel regression analysis on ESG/financial datasets. Users upload Excel/CSV files, explore data visually, configure and run panel regression models (FE, DID, winsorization, lags), and export Excel reports.

Primary data source: TEJ (Taiwan Economic Journal) ESG datasets.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py        # runs at http://127.0.0.1:8765 with auto-reload
```

Alternative port/host:
```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Reset all data (uploads, runs, DB):
```bash
rm -rf uploads/* runs/* tool.db
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATA_DIR` | project root | Override storage path (uploads/, runs/, tool.db) |
| `APP_USER` | `admin` | HTTP Basic auth username |
| `APP_PASSWORD` | _(unset = open)_ | Set to enable HTTP Basic auth |
| `PORT` | `10000` | Server listen port |

No `.env` file is required for local development.

## Architecture

### Module Responsibilities

| Module | Role |
|---|---|
| `app.py` | All FastAPI routes (HTML pages + JSON API), auth middleware |
| `db.py` | SQLite CRUD for datasets & runs metadata |
| `paths.py` | Central path config; respects `DATA_DIR` override |
| `core/config.py` | Pydantic models: `AnalysisConfig`, `ModelSpec` |
| `core/loader.py` | Read/write Excel/CSV; `dataset_path()` helper |
| `core/profiler.py` | Exploratory analytics: distributions, correlation, panel balance, outliers, quintiles, lead-lag |
| `core/pipeline.py` | Core regression workflow: preprocessing, lag/FE/DID construction, model fitting loop |
| `core/runner.py` | Thin wrapper around `linearmodels.panel.PanelOLS` |
| `core/merger.py` | Two-dataset join with column filtering |
| `core/reporter.py` | Styled Excel workbook generation |

### Data Storage

- **Metadata**: SQLite (`tool.db`) — datasets and runs tables (configs stored as JSON columns)
- **Raw files**: `uploads/` — original `.xlsx`/`.xls`/`.csv` per dataset
- **Run outputs**: `runs/{run_id}/result.json` — full result dict; `.xlsx` reports generated on demand

### Request Flow

HTML pages are Jinja2-rendered by FastAPI. Each page uses **Alpine.js** to call JSON API endpoints on load and user action. **Plotly** renders charts client-side from API responses. No frontend build step — all assets load from CDN.

### Regression Pipeline (`core/pipeline.py`)

```
AnalysisConfig (Pydantic)
 → load dataset (loader)
 → year filter, log transforms, winsorization
 → DID variable creation (High_Treat × Post)
 → lag construction per model spec
 → industry dummies (optional)
 → per-model PanelOLS fit (runner)
 → result.json (coefs, p-values, R², summary stats)
```

`AnalysisConfig` drives everything: target variable, base features, revenue vars with per-variable lags, FE spec (entity/time/industry), clustering strategy, DID setup, sample filter mode, and named model specs.

### API Organization (`app.py`)

**Page routes** (HTML): `/`, `/datasets/{id}`, `/merge`, `/train`, `/runs`, `/runs/{id}`

**Dataset API** (`/api/datasets/...`): upload, profile, correlation, preview, distribution, panel balance, variance, scatter, group stats, quintile, DID trajectories, lead-lag, outliers, ridge plot, first differences, bubble chart, pivot, merge, aliases, delete

**Run API** (`/api/runs/...`): submit config + execute pipeline, export Excel, delete

## Frontend Stack

No build tools. All loaded via CDN:
- **Tailwind CSS** — utility styling
- **Alpine.js** — client-side reactivity
- **Plotly** — interactive charts
- `templates/base.html` — shared nav, toast notifications, layout

## Deployment

**Docker**:
```bash
docker build -t esg-lab .
docker run -e DATA_DIR=/var/data -p 10000:10000 esg-lab
```

**Render**: configured in `render.yaml` with a persistent disk mounted at `/var/data`. `DATA_DIR` is set automatically.

## Key Constraints

- **No tests** — the project has no test suite; validate changes manually via the UI or direct API calls.
- **No linter config** — no ruff/flake8/mypy setup currently.
- **linearmodels, not statsmodels OLS** — regression uses `PanelOLS` from `linearmodels`; the API differs from `statsmodels`.
- **Pydantic v2** — `AnalysisConfig` uses v2 syntax; avoid v1 patterns.
- **SQLite only** — no migrations framework; schema changes require manual `ALTER TABLE` or DB reset.
