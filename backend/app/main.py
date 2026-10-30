"""FastAPI entry point:  uvicorn backend.app.main:app --reload --port 8000  (run from the project root)"""
import json
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import settings

# Make the shared `ml` / `pipeline` packages importable (features are shared with training).
if str(settings.ROOT) not in sys.path:
    sys.path.insert(0, str(settings.ROOT))

from . import auth, db, telemetry  # noqa: E402
from .routers import admin, insights, policy, predict, public  # noqa: E402

app = FastAPI(title="Civic Open-Data Dashboard API", version="1.0.0",
              description="Public accountability dashboard - crop, rainfall, suicides, diabetes and weather data.")
app.add_middleware(telemetry.TelemetryMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, public.router, policy.router, predict.router, admin.router, insights.router):
    app.include_router(r)


@app.get("/api/health", tags=["ops"])
def health():
    """Liveness + data/model status. 'degraded' means the API is up but something is missing or stale."""
    db_ok = db.db_version() is not None
    models = {p.stem: True for p in settings.MODELS.glob("*.joblib")} if settings.MODELS.exists() else {}
    last_run = None
    runs = settings.REPORTS / "pipeline_runs.jsonl"
    if runs.exists():
        lines = runs.read_text().strip().splitlines()
        last_run = json.loads(lines[-1]) if lines else None
    expected = ["crop_yield", "suicides_forecast", "diabetes_risk", "weather_nextday"]
    missing = [m for m in expected if m not in models]
    status = "ok"
    if not db_ok or missing or (last_run and last_run.get("overall") != "ok"):
        status = "degraded"
    return {"status": status, "database": db_ok, "models_missing": missing,
            "last_pipeline_run": last_run and {k: last_run[k] for k in ("run_id", "finished_at", "overall", "datasets")}}
