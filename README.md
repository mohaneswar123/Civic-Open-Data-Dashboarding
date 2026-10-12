# Civic Open-Data Dashboard for Public Accountability (DSCI-20)

A public accountability dashboard that turns messy government open data into honest, transparent,
decision-useful insight. It covers five datasets (crop production, IMD rainfall, NCRB suicides,
diabetes indicators and city weather), three user roles and machine-learning forecasts. Every number
on the site traces back to a line in a raw file.

## Quick start (Windows, local)

```powershell
# 1. Python environment (Python 3.13)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. Rebuild data + models from the raw CSVs (about 2 minutes)
.venv\Scripts\python run_all.py

# 3. API (terminal 1)
.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000

# 4. Website (terminal 2)
cd frontend
npm install
npm run dev          # open http://localhost:5173
```

Demo accounts (seeded on first API start; the passwords can be changed with the `CIVIC_POLICY_PASSWORD`
and `CIVIC_ADMIN_PASSWORD` environment variables):

| Role | Username | Password | Sees |
|---|---|---|---|
| Public | (no login) | | General dashboards, predictions, model transparency |
| Policy maker | `policy` | `policy@123` | Everything Public sees, plus advanced analytics, uncertainty intervals, scenarios, explanations and full model reports |
| Admin | `admin` | `admin@123` | Everything above, plus system architecture, datasets and lineage, project spec, Python code (read-only) and operations |

Set `CIVIC_JWT_SECRET` to a long random value for anything beyond a local demo.

## Run the tests

```powershell
.venv\Scripts\python -m pytest tests -q
```

The 40 tests cover the following:
- Quality rules and quarantine on deliberately messy fixtures (NT-1).
- Idempotent replay.
- Degraded mode and recovery after a schema break.
- Per-partition defect detection (NT-4).
- No double counting.
- An independent oracle for published totals.
- Role-based access control and path-traversal protection (NT-5).
- Input validation and forecast-horizon behaviour.

## Project layout

```
datasets/          raw CSVs (never modified)
project_info/      capstone specification (PDF)
pipeline/          validation -> cleaning -> quarantine -> DuckDB, plus lineage & quality reports
ml/                features shared with the API, and training/evaluation scripts
backend/app/       FastAPI: auth (JWT + roles), public/policy/admin/predict routers, telemetry
frontend/          React + TypeScript + Vite + Tailwind + Recharts
tests/             pytest acceptance tests
artifacts/         generated (git-ignored): civic.duckdb, models, reports, quarantine CSVs
run_all.py         one-command rebuild
```

## Key design decisions

- **Datasets are independent.** The only cross-dataset link is crop production ↔ rainfall, joined by
  state and year through an explicit IMD sub-division → state mapping.
- **Nothing is silently dropped.** Every raw row ends up clean, quarantined with a reason, or merged
  (summed). Lineage coverage is 100% and there are 0 reconciliation errors.
- **Misreading is designed out.** Specific safeguards:
  - Aggregate rows such as "Total foodgrain" are excluded, and non-tonne units are separated.
  - Suicide totals use a single breakdown, so deaths are not counted about 5 times.
  - Years with low reporting coverage are faded or hidden.
  - Counts are labelled as counts, not rates.
- **Honest models.** Every model has the following:
  - A time-separated test set and is compared with simple baselines.
  - Condition-wise errors and calibrated uncertainty.
  - Negative findings stated, for example: rainfall adds little to state-level yield prediction, and
    ML barely beats "same as last year" for suicide counts.

## Forecasting into the future

| Model | How far ahead | Method |
|---|---|---|
| Weather (10 cities) | 1–7 days after the last observation | Direct per-horizon LightGBM models; error grows with lead time and is shown per horizon |
| Weather | Beyond 7 days (to 2030) | Climate outlook: typical value for that city and date, plus the observed warming trend (clearly labelled) |
| Suicide counts | To 2030 | 1 year: validated one-step model. 2+ years: method chosen by rolling-origin back-test; 80% band widens each year |
| Crop yield | To 2030 | Model refit on 1997–2015. Trend extrapolation was tested and **not adopted** because it did not improve held-out accuracy; the interval widens per year ahead |
