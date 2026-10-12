"""API tests against the real built artifacts: role-based access control (NT-5),
input validation, and an independent oracle for a published figure (FR-2)."""
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (ROOT / "artifacts" / "civic.duckdb").exists(),
                                reason="run `python run_all.py` first")


@pytest.fixture(scope="module")
def client():
    from backend.app.main import app
    return TestClient(app)


def token(client, user, pw):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def policy(client):
    return token(client, "policy", "policy@123")


@pytest.fixture(scope="module")
def admin(client):
    return token(client, "admin", "admin@123")


@pytest.mark.parametrize("path", ["/api/public/overview", "/api/public/crop", "/api/public/rainfall",
                                  "/api/public/suicides", "/api/public/diabetes", "/api/public/weather",
                                  "/api/models", "/api/predict/options", "/api/health"])
def test_public_endpoints_open(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/api/policy/crop/disparity", "/api/models/crop_yield", "/api/admin/datasets",
                                  "/api/admin/code"])
def test_anonymous_denied(client, path):
    assert client.get(path).status_code == 401


def test_policy_cannot_reach_admin(client, policy):
    assert client.get("/api/policy/crop/disparity", headers=policy).status_code == 200
    for path in ["/api/admin/datasets", "/api/admin/code", "/api/admin/telemetry", "/api/admin/project/pdf"]:
        assert client.get(path, headers=policy).status_code == 403


def test_admin_inherits_policy(client, admin):
    assert client.get("/api/policy/suicides/farmers", headers=admin).status_code == 200
    assert client.get("/api/admin/datasets", headers=admin).status_code == 200


def test_bad_credentials_and_tokens(client):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.get("/api/policy/crop/options", headers={"Authorization": "Bearer forged"}).status_code == 401


@pytest.mark.parametrize("path", ["backend/../users.json", "pipeline/../../backend/users.json",
                                  "pipeline/../../.gitignore", "ml/../pipeline/config.py/../../backend/users.json",
                                  "nope/x.py"])
def test_code_viewer_blocks_traversal(client, admin, path):
    """NT-5: the code viewer must never expose files outside its allow-list (e.g. password hashes)."""
    r = client.get("/api/admin/code/file", params={"path": path}, headers=admin)
    assert r.status_code == 404
    assert "password_hash" not in r.text


def test_detail_only_for_policy(client, policy):
    body = {"state": "Punjab", "district": "Ludhiana", "crop": "Wheat", "season": "Rabi", "area_ha": 100}
    public = client.post("/api/predict/crop", json=body).json()
    detailed = client.post("/api/predict/crop", json=body, headers=policy).json()
    assert "interval_80" not in public and "interval_80" in detailed
    lo, hi = detailed["interval_80"]
    assert lo <= detailed["yield_t_per_ha"] <= hi


@pytest.mark.parametrize("body,expected", [
    ({"state": "Punjab", "district": "Mumbai", "crop": "Wheat", "season": "Rabi", "area_ha": 10}, 422),
    ({"state": "Atlantis", "district": "X", "crop": "Wheat", "season": "Rabi", "area_ha": 10}, 422),
    ({"state": "Punjab", "district": "Ludhiana", "crop": "Wheat", "season": "Rabi", "area_ha": -5}, 422),
])
def test_crop_validation(client, body, expected):
    assert client.post("/api/predict/crop", json=body).status_code == expected


def test_forecast_horizon_enforced(client):
    r = client.post("/api/predict/suicides", json={"state": "Kerala", "gender": "Male", "age_group": "30-44", "year": 2031})
    assert r.status_code == 422
    r = client.post("/api/predict/weather", json={"city": "Delhi", "date": "2031-01-01"})
    assert r.status_code == 422


def test_suicide_future_band_widens(client, policy):
    bands = []
    for year in (2013, 2015, 2020):
        r = client.post("/api/predict/suicides", headers=policy,
                        json={"state": "Kerala", "gender": "Male", "age_group": "30-44", "year": year}).json()
        assert r["actual"] is None and r["years_beyond_data"] == year - 2012
        bands.append(r["band_80"][1] - r["band_80"][0])
    assert bands[0] < bands[1] < bands[2]  # uncertainty must grow with the horizon


@pytest.mark.parametrize("day,mode", [("2024-07-10", "ml_forecast"), ("2025-01-03", "ml_forecast"),
                                      ("2026-10-13", "climate_outlook")])
def test_weather_mode_depends_on_lead_time(client, day, mode):
    r = client.post("/api/predict/weather", json={"city": "Delhi", "date": day})
    assert r.status_code == 200 and r.json()["mode"] == mode
    if day == "2024-07-10":
        assert r.json()["actual"] is not None  # inside the data -> verifiable


def test_diabetes_ranges_enforced(client):
    body = {"gender": "Male", "age": 40, "hypertension": 0, "heart_disease": 0, "smoking_history": "never",
            "bmi": 500, "HbA1c_level": 5.5, "blood_glucose_level": 100}
    assert client.post("/api/predict/diabetes", json=body).status_code == 422


def test_published_crop_totals_match_independent_oracle(client):
    """FR-2 oracle: recompute yearly tonnage straight from the raw CSV with plain pandas
    (independent of the pipeline code) and compare with what the API publishes."""
    raw = pd.read_csv(ROOT / "datasets" / "crop_production.csv")
    raw["Crop"] = raw["Crop"].str.strip()
    ok = (raw["Production"].notna() & (raw["Area"] > 0)
          & ~raw["Crop"].isin(["Total foodgrain", "Oilseeds total", "Pulses total"])
          & ~raw["Crop"].isin(["Coconut", "Cotton(lint)", "Jute", "Mesta", "Jute & mesta"]))
    oracle = raw[ok].groupby("Crop_Year")["Production"].sum()
    published = {r["year"]: r["production_t"] for r in client.get("/api/public/crop").json()["yearly"]}
    for year, value in oracle.items():
        assert published[year] == pytest.approx(value, rel=1e-9), year
