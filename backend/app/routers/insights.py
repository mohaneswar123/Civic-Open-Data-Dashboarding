"""Insight pages shared by every role: dataset briefs, exploratory data analysis (EDA), and the
classification view of every model (comparison, confusion matrix, label-only predictions)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ml import classify
from ml import features as F

from .. import predictors as P
from .. import settings
from ..catalog import DATASETS
from ..db import clean_value, db_version, query

# Read-only, aggregated views (no row-level data), so they are open to every role, including anonymous public users.
router = APIRouter(prefix="/api/insights", tags=["insights"])

TASKS = ["crop_yield", "diabetes", "weather_temp", "weather_rain", "suicides"]


def _cls_report(task: str) -> dict:
    path = settings.REPORTS / f"cls_{task}.json"
    if not path.exists():
        raise HTTPException(503, f"Classifier report for '{task}' not built yet - run `python -m ml.classify`")
    return json.loads(path.read_text())


# ------------------------------------------------------------------ brief datasets
@router.get("/brief")
def brief():
    lineage = {}
    try:
        lineage = json.loads((settings.REPORTS / "lineage.json").read_text())
    except Exception:
        pass
    out = []
    for d in DATASETS:
        lin = lineage.get(d["key"], {})
        tasks = []
        for t in TASKS:
            try:
                r = _cls_report(t)
            except HTTPException:
                continue
            if r["dataset"] == d["key"]:
                tasks.append({"task": t, "title": r["title"], "classes": r["class_names"], "selected": r["selected"]})
        out.append({**{k: v for k, v in d.items() if k != "columns"},
                    "columns": [{"name": n, "type": ty, "description": desc} for n, ty, desc in d["columns"]],
                    "rows_raw": lin.get("rows_in"), "rows_clean": lin.get("rows_clean"),
                    "rows_quarantined": lin.get("rows_quarantined"), "tasks": tasks})
    return out


# ------------------------------------------------------------------ EDA
def _summary(s: pd.Series, label: str) -> dict:
    s = s.dropna().astype(float)
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    out = ((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).mean() if iqr > 0 else 0.0
    return {"label": label, "count": int(len(s)), "mean": float(s.mean()), "std": float(s.std()), "min": float(s.min()),
            "q1": float(q1), "median": float(s.median()), "q3": float(q3), "max": float(s.max()), "outlier_pct": float(100 * out)}


def _hist(s: pd.Series, label: str, log: bool = False, bins: int = 24) -> dict:
    v = s.dropna().astype(float)
    if log:
        v = np.log10(v[v > 0])
    counts, edges = np.histogram(v, bins=bins)
    return {"label": label, "log": log, "bins": [{"x0": float(a), "x1": float(b), "count": int(c)}
                                                  for a, b, c in zip(edges[:-1], edges[1:], counts)]}


def _cats(df: pd.DataFrame, col: str, label: str, top: int = 10, weight: str | None = None, weight_label: str = "rows") -> dict:
    agg = (df.groupby(col)[weight].sum() if weight else df[col].value_counts()).sort_values(ascending=False)
    return {"label": label, "measure": weight_label, "distinct": int(df[col].nunique()),
            "top": [{"value": str(k), "count": float(v)} for k, v in agg.head(top).items()]}


def _corr(df: pd.DataFrame, cols: list[tuple[str, str]]) -> dict:
    m = df[[c for c, _ in cols]].astype(float).corr().round(3)
    return {"columns": [lbl for _, lbl in cols], "matrix": [[clean_value(x) for x in row] for row in m.values]}


def _raw_missing(name: str) -> list[dict]:
    from pipeline import config
    raw = pd.read_csv(config.RAW_DIR / config.SOURCES[name]["file"])
    return [{"column": c, "missing_pct": float(100 * raw[c].isna().mean())} for c in raw.columns]


def _targets(name: str) -> list[dict]:
    out = []
    for t in TASKS:
        try:
            r = _cls_report(t)
        except HTTPException:
            continue
        if r["dataset"] == name:
            d = r["class_distribution"]
            out.append({"task": t, "title": r["title"], "rule": r["class_rule"],
                        "classes": [{"name": n, "train": d["train"][i], "validation": d["validation"][i], "test": d["test"][i]}
                                    for i, n in enumerate(r["class_names"])]})
    return out


WMO = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
       61: "Light rain", 63: "Rain", 65: "Heavy rain", 80: "Light showers", 81: "Showers", 82: "Violent showers"}


@lru_cache(maxsize=16)
def _eda(name: str, _version: float | None) -> dict:
    if name == "crop":
        df = query("SELECT state, district, year, season, crop, area_ha, production, yield_t_per_ha FROM crop WHERE unit = 'tonnes'")
        pos = df[(df.production > 0) & (df.area_ha > 0)].assign(
            log_area=lambda d: np.log10(d.area_ha), log_prod=lambda d: np.log10(d.production), log_yield=lambda d: np.log10(d.yield_t_per_ha))
        trend = df.groupby("year").agg(rows=("crop", "size"), states=("state", "nunique")).reset_index()
        return {
            "summary": [_summary(df.area_ha, "Area (ha)"), _summary(df.production, "Production (t)"), _summary(df.yield_t_per_ha, "Yield (t/ha)")],
            "histograms": [_hist(df.area_ha, "Area (ha)", True), _hist(df.production, "Production (t)", True), _hist(df.yield_t_per_ha, "Yield (t/ha)", True)],
            "categories": [_cats(df, "state", "Records by state"), _cats(df, "crop", "Records by crop"), _cats(df, "season", "Records by season")],
            "correlation": _corr(pos, [("year", "Year"), ("log_area", "log Area"), ("log_prod", "log Production"), ("log_yield", "log Yield")]),
            "trend": {"label": "Records per year", "x": "Year", "points": [{"x": int(r.year), "y": int(r.rows)} for r in trend.itertuples()]},
            "notes": ["Area, production and yield are heavily right-skewed, so histograms use a log10 scale",
                      "1997 and 2011-2015 have fewer reporting states; record counts drop for that reason, not because farming fell"],
        }
    if name == "rainfall":
        df = query("SELECT * FROM rainfall")
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        trend = df.groupby("year")["annual"].mean().reset_index()
        return {
            "summary": [_summary(df.annual, "Annual (mm)"), _summary(df.jun_sep, "Monsoon Jun-Sep (mm)"), _summary(df.departure_pct, "Departure from normal (%)")],
            "histograms": [_hist(df.annual, "Annual (mm)"), _hist(df.jun_sep, "Monsoon Jun-Sep (mm)"), _hist(df.departure_pct, "Departure from normal (%)")],
            "categories": [{"label": "Mean annual rainfall by sub-division (top 10)", "measure": "mm", "distinct": int(df.subdivision.nunique()),
                            "top": [{"value": k, "count": float(v)} for k, v in df.groupby("subdivision")["annual"].mean().sort_values(ascending=False).head(10).items()]}],
            "correlation": _corr(df, [(m, m.capitalize()) for m in months] + [("annual", "Annual")]),
            "trend": {"label": "Mean annual rainfall across sub-divisions (mm)", "x": "Year", "points": [{"x": int(r.year), "y": round(float(r.annual), 1)} for r in trend.itertuples()]},
            "notes": ["The monsoon months (Jun-Sep) correlate most with the annual total",
                      "26 rows had an ANNUAL value that did not match the monthly sum; they were recomputed"],
        }
    if name == "suicides":
        head = query("SELECT * FROM suicides_headline")
        panel = F.suicide_panel(head).dropna(subset=["lag1", "lag2"])
        causes = query("SELECT category, sum(total) total FROM suicides WHERE type_code = 'Causes' GROUP BY category")
        trend = head.groupby("year")["total"].sum().reset_index()
        return {
            "summary": [_summary(head.total, "Count per state-gender-age group")],
            "histograms": [_hist(head.total[head.total > 0], "Count per group (log10)", True)],
            "categories": [_cats(head, "state", "Total by state", weight="total", weight_label="suicides"),
                           _cats(head, "age_group", "Total by age group", weight="total", weight_label="suicides"),
                           _cats(head, "gender", "Total by gender", weight="total", weight_label="suicides"),
                           _cats(causes, "category", "Top causes", weight="total", weight_label="suicides")],
            "correlation": _corr(panel, [("total", "This year"), ("lag1", "Last year"), ("lag2", "Two years ago"), ("state_lag1", "State total last year"), ("year", "Year")]),
            "trend": {"label": "Recorded suicides per year", "x": "Year", "points": [{"x": int(r.year), "y": int(r.total)} for r in trend.itertuples()]},
            "notes": ["This year's count is almost perfectly correlated with last year's, which is why simple persistence forecasts work well",
                      "Totals use one breakdown only; summing all five would count each death about five times"],
        }
    if name == "diabetes":
        df = query("SELECT * FROM diabetes")
        prev = df.groupby("age_band")["diabetes"].mean().mul(100)
        order = ["<18", "18-29", "30-44", "45-59", "60-74", "75+"]
        return {
            "summary": [_summary(df.age, "Age (years)"), _summary(df.bmi, "BMI"), _summary(df.HbA1c_level, "HbA1c (%)"), _summary(df.blood_glucose_level, "Glucose (mg/dL)")],
            "histograms": [_hist(df.age, "Age (years)"), _hist(df.bmi, "BMI"), _hist(df.HbA1c_level, "HbA1c (%)", bins=18), _hist(df.blood_glucose_level, "Glucose (mg/dL)", bins=18)],
            "categories": [_cats(df, "gender", "Records by gender"), _cats(df, "smoking_history", "Records by smoking history"),
                           _cats(df, "bmi_class", "Records by BMI class"), _cats(df, "age_band", "Records by age band")],
            "correlation": _corr(df, [("age", "Age"), ("bmi", "BMI"), ("HbA1c_level", "HbA1c"), ("blood_glucose_level", "Glucose"),
                                      ("hypertension", "Hypertension"), ("heart_disease", "Heart disease"), ("diabetes", "Diabetes")]),
            "trend": {"label": "Diabetes prevalence by age band (%)", "x": "Age band", "points": [{"x": a, "y": round(float(prev.get(a, 0)), 2)} for a in order if a in prev]},
            "notes": ["HbA1c and glucose are recorded at a few fixed levels, so their histograms look spiky",
                      "Only 8.8% of records are diabetic: the classes are imbalanced"],
        }
    if name == "weather":
        df = query("SELECT city, date, year, temperature_2m_max, temperature_2m_min, precipitation_sum, wind_speed_10m_max, weather_code, rainy_day FROM weather")
        df["condition"] = df.weather_code.map(WMO).fillna("Other")
        trend = df.groupby("year")["temperature_2m_max"].mean().reset_index()
        return {
            "summary": [_summary(df.temperature_2m_max, "Max temperature (°C)"), _summary(df.temperature_2m_min, "Min temperature (°C)"),
                        _summary(df.precipitation_sum, "Rainfall (mm/day)"), _summary(df.wind_speed_10m_max, "Max wind (km/h)")],
            "histograms": [_hist(df.temperature_2m_max, "Max temperature (°C)"), _hist(df.temperature_2m_min, "Min temperature (°C)"),
                           _hist(df.precipitation_sum[df.precipitation_sum > 0], "Rainfall on wet days (log10 mm)", True), _hist(df.wind_speed_10m_max, "Max wind (km/h)")],
            "categories": [_cats(df, "condition", "Days by weather condition"),
                           _cats(df.assign(rain=df.rainy_day.map({0: "Dry day", 1: "Rainy day (≥ 2.5 mm)"})), "rain", "Dry vs rainy days")],
            "correlation": _corr(df, [("temperature_2m_max", "Max temp"), ("temperature_2m_min", "Min temp"), ("precipitation_sum", "Rainfall"), ("wind_speed_10m_max", "Wind")]),
            "trend": {"label": "Mean daily max temperature, all cities (°C)", "x": "Year", "points": [{"x": int(r.year), "y": round(float(r.temperature_2m_max), 2)} for r in trend.itertuples()]},
            "notes": ["Rainfall is zero on most days, so its histogram shows wet days only, on a log scale",
                      "Every city has a complete daily record with no gaps"],
        }
    raise HTTPException(404, f"Unknown dataset '{name}'")


@router.get("/eda/{name}")
def eda(name: str):
    if name not in {d["key"] for d in DATASETS}:
        raise HTTPException(404, f"Unknown dataset '{name}'")
    out = dict(_eda(name, db_version()))
    rows = query(f'SELECT count(*) n FROM "{name}"').iat[0, 0]
    corr = out["correlation"]
    pairs = [{"pair": f"{a} & {b}", "r": corr["matrix"][i][j]}
             for i, a in enumerate(corr["columns"]) for j, b in enumerate(corr["columns"])
             if j > i and corr["matrix"][i][j] is not None]
    pairs.sort(key=lambda x: -abs(x["r"]))
    return {**out, "dataset": name, "rows": int(rows), "missing": _missing(name, db_version()), "targets": _targets(name),
            "pairs": pairs[:8], "quality": _quality(name, db_version())}


@lru_cache(maxsize=8)
def _missing(name: str, _version: float | None) -> list[dict]:
    return _raw_missing(name)


# Natural key of each raw file: two rows with the same key describe the same thing.
RAW_KEYS = {"crop": ["State_Name", "District_Name", "Crop_Year", "Season", "Crop"], "rainfall": ["SUBDIVISION", "YEAR"],
            "suicides": ["State", "Year", "Type_code", "Type", "Gender", "Age_group"], "weather": ["city", "date"], "diabetes": None}
ACTION_WORDS = {"quarantine": "Removed (kept in quarantine)", "flag": "Kept, marked for exclusion",
                "flag (repaired)": "Repaired", "repaired": "Repaired", "merged": "Merged (summed)", "reported": "Reported"}


@lru_cache(maxsize=8)
def _quality(name: str, _version: float | None) -> dict:
    """Data-quality checks on the RAW file, before any cleaning."""
    from pipeline import config
    raw = pd.read_csv(config.RAW_DIR / config.SOURCES[name]["file"])
    n = len(raw)
    missing = [{"column": c, "missing": int(raw[c].isna().sum()), "pct": float(100 * raw[c].isna().mean())} for c in raw.columns]
    exact = int(raw.duplicated().sum())
    key = RAW_KEYS.get(name)
    key_dups = None
    if key:
        k = raw[key].apply(lambda col: col.astype(str).str.strip())
        key_dups = int(k.duplicated().sum())
    text_issues = []
    for c in raw.select_dtypes(include=["object", "string"]).columns:
        v = raw[c].dropna().astype(str)
        text_issues.append({"column": c, "rows": int((v != v.str.strip()).sum())})
    negatives = [{"column": c, "rows": int((raw[c] < 0).sum())} for c in raw.select_dtypes("number").columns]
    issues = []
    try:
        q = json.loads((settings.REPORTS / "quality.json").read_text()).get(name, {})
        for r in q.get("rules", []):
            if r["rows"]:
                issues.append({"issue": r["rule"].replace("_", " ").capitalize(), "rows": int(r["rows"]),
                               "action": ACTION_WORDS.get(r["action"], r["action"]), "detail": r["description"]})
    except Exception:
        pass
    lin = {}
    try:
        lin = json.loads((settings.REPORTS / "lineage.json").read_text()).get(name, {})
    except Exception:
        pass
    cells = n * raw.shape[1]
    return {
        "raw_rows": n, "raw_columns": int(raw.shape[1]), "missing": missing,
        "missing_cells": int(sum(m["missing"] for m in missing)), "missing_cells_pct": float(100 * sum(m["missing"] for m in missing) / cells) if cells else 0.0,
        "exact_duplicates": exact, "key_duplicates": key_dups, "key_columns": key,
        "text_issues": [t for t in text_issues if t["rows"] > 0], "negatives": [x for x in negatives if x["rows"] > 0],
        "issues": sorted(issues, key=lambda x: -x["rows"]),
        "flow": {"raw": lin.get("rows_in", n), "quarantined": lin.get("rows_quarantined", 0), "merged": lin.get("rows_merged", 0),
                 "clean": lin.get("rows_clean")},
    }


# ------------------------------------------------------------------ classifiers
@router.get("/classifiers")
def classifiers():
    out = []
    for t in TASKS:
        try:
            r = _cls_report(t)
        except HTTPException:
            continue
        sel = next(m for m in r["models"] if m["model"] == r["selected"])
        out.append({"task": t, "dataset": r["dataset"], "title": r["title"], "classes": r["class_names"],
                    "selected": r["selected"], "test_macro_f1": sel["test"]["macro_f1"], "models": len(r["models"])})
    return out


@router.get("/classifiers/{task}")
def classifier_report(task: str):
    if task not in TASKS:
        raise HTTPException(404, "Unknown task")
    return _cls_report(task)


@router.get("/classifiers/{task}/options")
def classifier_options(task: str):
    if task not in TASKS:
        raise HTTPException(404, "Unknown task")
    b = P.bundle(f"cls_{task}")
    out = {"models": list(b["models"].keys()), "selected": b["selected"], "classes": b["class_names"]}
    if task == "crop_yield":
        crop = P.bundle("crop_yield")
        out.update({"districts": crop["districts"], "crop_seasons": crop["crop_seasons"], "crops": b["categories"]["crop"]})
    elif task == "diabetes":
        out.update({"genders": b["categories"]["gender"], "smoking": b["categories"]["smoking_history"]})
    elif task.startswith("weather"):
        rng = query("SELECT min(date) a, max(date) b FROM weather").iloc[0]
        out.update({"cities": b["categories"]["city"], "first_date": (rng.a + timedelta(days=8)).date().isoformat(),
                    "last_date": (rng.b + timedelta(days=1)).date().isoformat()})
    elif task == "suicides":
        last = int(query("SELECT max(year) FROM suicides_headline").iat[0, 0])
        out.update({"states": b["categories"]["state"], "genders": b["categories"]["gender"],
                    "age_groups": b["categories"]["age_group"], "years": [2003, last + 1]})
    return out


class ClassifyIn(BaseModel):
    model: str | None = None
    inputs: dict


def _features(task: str, x: dict) -> pd.DataFrame:
    try:
        if task == "crop_yield":
            crop = P.bundle("crop_yield")
            if x["district"] not in crop["districts"].get(x["state"], []):
                raise HTTPException(422, f"District '{x['district']}' has no crop records in {x['state']}")
            n = crop["rain_normals"].get(x["state"]) or {}
            row = pd.DataFrame([{"state": x["state"], "district": x["district"], "crop": x["crop"], "season": x["season"],
                                 "area_ha": float(x["area_ha"]), "year": int(x["year"]),
                                 "annual": n.get("annual", np.nan), "jun_sep": n.get("jun_sep", np.nan),
                                 "oct_dec": n.get("oct_dec", np.nan), "mar_may": n.get("mar_may", np.nan), "monsoon_departure_pct": 0.0}])
            if row.area_ha[0] <= 0:
                raise HTTPException(422, "Area must be positive")
            return F.crop_features(row)
        if task == "diabetes":
            row = {k: x[k] for k in F.DIA_CAT + F.DIA_NUM}
            for k in F.DIA_NUM:
                row[k] = float(row[k])
            return pd.DataFrame([row])
        if task.startswith("weather"):
            target = date.fromisoformat(x["date"])
            base = target - timedelta(days=1)
            _, today = P._features_on(x["city"], base)
            if today.empty or today["tmax_roll7"].isna().any():
                raise HTTPException(422, "Pick a date inside the observed record (or the day after it)")
            return today[F.WX_FEATURES]
        if task == "suicides":
            year = int(x["year"])
            s = query("SELECT year, total FROM suicides_headline WHERE state=? AND gender=? AND age_group=?",
                      [x["state"], x["gender"], x["age_group"]])
            hist = dict(zip(s["year"].astype(int), s["total"].astype(float)))
            if (year - 1) not in hist or (year - 2) not in hist:
                raise HTTPException(422, "Need the two previous years of data: choose a year from 2003 to the year after the data ends")
            sp = float(query("SELECT sum(total) FROM suicides_headline WHERE state=? AND year=?", [x["state"], year - 1]).iat[0, 0])
            return pd.DataFrame([{"state": x["state"], "gender": x["gender"], "age_group": x["age_group"], "year": year,
                                  "lag1": hist[year - 1], "lag2": hist[year - 2],
                                  "lag_mean2": (hist[year - 1] + hist[year - 2]) / 2, "state_lag1": sp}])
    except KeyError as e:
        raise HTTPException(422, f"Missing input: {e.args[0]}")
    except ValueError as e:
        raise HTTPException(422, f"Invalid input: {e}")
    raise HTTPException(404, "Unknown task")


@router.post("/classifiers/{task}/predict")
def classifier_predict(task: str, body: ClassifyIn):
    """Returns the predicted CLASS only (e.g. 'High'); no numeric value or probability is exposed."""
    if task not in TASKS:
        raise HTTPException(404, "Unknown task")
    b = P.bundle(f"cls_{task}")
    name = body.model or b["selected"]
    if name not in b["models"]:
        raise HTTPException(422, f"Unknown model '{name}'")
    for col in b["cat"]:
        if col in body.inputs and col in b["categories"] and str(body.inputs[col]) not in b["categories"][col]:
            raise HTTPException(422, f"Unknown {col} '{body.inputs[col]}'")
    X = _features(task, body.inputs)
    idx = int(classify.predict_proba(b["models"][name], X, b["categories"], b["cat"]).argmax(axis=1)[0])
    return {"label": b["class_names"][idx], "model": name, "is_selected_model": name == b["selected"], "classes": b["class_names"]}
