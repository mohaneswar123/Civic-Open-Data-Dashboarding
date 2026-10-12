"""Predictions. Everyone can predict; policy makers and admins also receive
uncertainty intervals, scenarios, explanations and baseline comparisons."""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import predictors as P
from ..auth import User, current_user, require_role, role_rank
from ..db import query, records

router = APIRouter(prefix="/api", tags=["predictions"])


def detailed(user: User) -> bool:
    return role_rank(user.role) >= role_rank("policy")


class CropIn(BaseModel):
    state: str
    district: str
    crop: str
    season: str
    area_ha: float = Field(gt=0)
    year: int = Field(2015, ge=1997, le=2030)
    rainfall_change_pct: float = 0.0


class SuicideIn(BaseModel):
    state: str
    gender: str
    age_group: str
    year: int = Field(2013, ge=2003, le=2030)


class DiabetesIn(BaseModel):
    gender: str
    age: float = Field(ge=0, le=120)
    hypertension: int = Field(ge=0, le=1)
    heart_disease: int = Field(ge=0, le=1)
    smoking_history: str
    bmi: float = Field(ge=10, le=100)
    HbA1c_level: float = Field(ge=3, le=20)
    blood_glucose_level: float = Field(ge=40, le=600)


class WeatherIn(BaseModel):
    city: str
    date: date  # the day to predict FOR


@router.get("/predict/options")
def options():
    crop = P.bundle("crop_yield")
    sui = P.bundle("suicides_forecast")
    dia = P.bundle("diabetes_risk")
    wx = query("SELECT city, min(date) first_date, max(date) last_date FROM weather GROUP BY city ORDER BY city")
    return {
        "crop": {"last_data_year": crop.get("last_year", 2015), "districts": crop["districts"], "crop_seasons": crop["crop_seasons"],
                 "crops": crop["categories"]["crop"], "seasons": crop["categories"]["season"]},
        "suicides": {"states": sui["categories"]["state"], "genders": sui["categories"]["gender"],
                     "age_groups": sui["categories"]["age_group"], "years": [2003, P.MAX_SUICIDE_YEAR],
                     "last_data_year": sui["last_year"]},
        "diabetes": {"genders": dia["categories"]["gender"], "smoking": dia["categories"]["smoking_history"]},
        "weather": {"cities": records(wx), "max_date": P.MAX_WEATHER_DATE.isoformat(),
                    "max_ml_horizon": P.bundle("weather_nextday").get("max_ml_horizon", 1)},
    }


@router.post("/predict/crop")
def predict_crop(body: CropIn, user: User = Depends(current_user)):
    return P.predict_crop(**body.model_dump(), detail=detailed(user))


@router.post("/predict/suicides")
def predict_suicides(body: SuicideIn, user: User = Depends(current_user)):
    return P.predict_suicides(**body.model_dump(), detail=detailed(user))


@router.post("/predict/diabetes")
def predict_diabetes(body: DiabetesIn, user: User = Depends(current_user)):
    return P.predict_diabetes(body.model_dump(), detail=detailed(user))


@router.post("/predict/weather")
def predict_weather(body: WeatherIn, user: User = Depends(current_user)):
    return P.predict_weather(body.city, body.date, detail=detailed(user))


MODEL_NAMES = ["crop_yield", "suicides_forecast", "diabetes_risk", "weather_nextday"]


@router.get("/models")
def model_cards():
    """Short, public 'model cards' - what each model does and how good it honestly is."""
    cards = []
    for name in MODEL_NAMES:
        try:
            r = P.report(name)
        except Exception:
            cards.append({"model": name, "available": False})
            continue
        cards.append({"model": name, "available": True, "title": r["title"], "task": r["task"], "target": r["target"],
                      "split": r["split"], "selected": r["selected"], "limitations": r.get("limitations", []),
                      "trained_at": r["trained_at"]})
    return cards


@router.get("/models/{name}", dependencies=[Depends(require_role("policy"))])
def model_report(name: str):
    if name not in MODEL_NAMES:
        from fastapi import HTTPException
        raise HTTPException(404, "Unknown model")
    return P.report(name)
