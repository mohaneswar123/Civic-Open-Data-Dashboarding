"""Model loading + inference. Features are built with the SAME code used in training (ml.features)."""
from __future__ import annotations

import json
import threading
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
from fastapi import HTTPException

from ml import features as F
from ml.common import to_categories

from . import settings
from .db import query

_models: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def bundle(name: str) -> dict:
    path = settings.MODELS / f"{name}.joblib"
    if not path.exists():
        raise HTTPException(503, f"Model '{name}' is not trained yet - run `python run_all.py` (other models still work)")
    mtime = path.stat().st_mtime
    with _lock:
        if name not in _models or _models[name][0] != mtime:  # reload after retraining
            _models[name] = (mtime, joblib.load(path))
        return _models[name][1]


def report(name: str) -> dict:
    path = settings.REPORTS / f"metrics_{name}.json"
    if not path.exists():
        raise HTTPException(503, f"No evaluation report for '{name}'")
    return json.loads(path.read_text())


def _require(value, allowed, field):
    if value not in allowed:
        raise HTTPException(422, f"Unknown {field} '{value}'")


# ------------------------------------------------------------------ crop
def predict_crop(state, district, crop, season, area_ha, year, rainfall_change_pct, detail: bool):
    b = bundle("crop_yield")
    cats = b["categories"]
    _require(state, cats["state"], "state")
    _require(crop, cats["crop"], "crop")
    _require(season, cats["season"], "season")
    if district not in b["districts"].get(state, []):
        raise HTTPException(422, f"District '{district}' has no crop records in {state}")
    if not (0 < area_ha <= 2_000_000):
        raise HTTPException(422, "Area must be between 0 and 2,000,000 hectares")
    if not (-80 <= rainfall_change_pct <= 100):
        raise HTTPException(422, "Rainfall change must be between -80% and +100%")

    normals = b["rain_normals"].get(state)

    def frame(change):
        factor = 1 + change / 100
        rain = {k: (normals[k] * factor if normals else np.nan) for k in ["annual", "jun_sep", "oct_dec", "mar_may"]}
        row = pd.DataFrame([{"state": state, "district": district, "crop": crop, "season": season,
                             "area_ha": area_ha, "year": year, **rain, "monsoon_departure_pct": change}])
        X, _ = to_categories(F.crop_features(row), F.CROP_CAT, cats)
        return X

    last = b.get("last_year", 2015)
    ahead = max(0, year - last)
    damping = b.get("trend_damping", 0.5)
    slope = b.get("trend_slopes", {}).get(f"{state}|{crop}|{season}", 0.0) if b.get("use_trend") else 0.0
    trend_adj = damping * slope * ahead  # trees cannot extrapolate time, so the trend is added explicitly

    X = frame(rainfall_change_pct)
    log_y = float(b["model"].predict(X)[0]) + trend_adj
    y = float(np.exp(log_y))
    out = {"yield_t_per_ha": y, "production_t": y * area_ha,
           "rainfall_used": {"normal_monsoon_mm": normals["jun_sep"] if normals else None,
                             "scenario_monsoon_mm": normals["jun_sep"] * (1 + rainfall_change_pct / 100) if normals else None},
           "warnings": []}
    if crop not in [c for c, s in b["crop_seasons"].items() if season in s]:
        out["warnings"].append(f"{crop} was never recorded in the {season} season - prediction is an extrapolation")
    out["forecast"] = {"years_beyond_data": ahead, "last_data_year": last,
                       "trend_applied_pct_per_year": round(100 * damping * slope, 2) if ahead else 0.0}
    if ahead:
        trend_txt = (f"The historical yield trend for this state/crop/season ({100 * damping * slope:+.1f}% per year, damped) is carried forward."
                     if slope else
                     "Carrying past trends forward did not improve accuracy on held-out years, so yield is held at recent levels."
                     if not b.get("use_trend") else "No reliable trend for this combination, so yield is held at recent levels.")
        out["warnings"].append(f"{year} is {ahead} year(s) beyond the data (last year {last}). {trend_txt}")
    if ahead > 5:
        out["warnings"].append("More than 5 years ahead: treat this as a rough scenario, not a forecast")
    if not normals:
        out["warnings"].append("No rainfall data for this state - rainfall features left empty")
    if detail:
        q = b["conformal_q"] + 0.02 * ahead  # heuristic widening per year beyond the data (disclosed in UI)
        lo = float(np.exp(b["q10"].predict(X)[0] + trend_adj - q))
        hi = float(np.exp(b["q90"].predict(X)[0] + trend_adj + q))
        hist = query("""SELECT year, production / area_ha AS yield FROM crop
                        WHERE state=? AND district=? AND crop=? AND season=? AND production > 0 ORDER BY year""",
                     [state, district, crop, season])
        scenarios = []
        for ch in range(-40, 45, 10):
            scenarios.append({"rainfall_change_pct": ch, "yield_t_per_ha": float(np.exp(b["model"].predict(frame(ch))[0] + trend_adj))})
        rep = report("crop_yield")
        out.update({"interval_80": [lo, hi], "production_interval_80": [lo * area_ha, hi * area_ha],
                    "interval_coverage_on_test": rep["interval"]["empirical_coverage"],
                    "history": [{"year": int(r.year), "yield": float(r.yield_)} for r in hist.rename(columns={"yield": "yield_"}).itertuples()],
                    "scenarios": scenarios, "top_features": rep["feature_importance"][:8],
                    "rainfall_finding": rep["rainfall_contribution"]})
    return out


# ------------------------------------------------------------------ suicides
MAX_SUICIDE_YEAR = 2030


def predict_suicides(state, gender, age_group, year, detail: bool):
    b = bundle("suicides_forecast")
    cats = b["categories"]
    _require(state, cats["state"], "state")
    _require(gender, cats["gender"], "gender")
    _require(age_group, cats["age_group"], "age group")
    last = b["last_year"]
    if not (2003 <= year <= MAX_SUICIDE_YEAR):
        raise HTTPException(422, f"Choose a year between 2003 and {MAX_SUICIDE_YEAR}")
    series = query("""SELECT year, total FROM suicides_headline WHERE state=? AND gender=? AND age_group=? ORDER BY year""",
                   [state, gender, age_group])
    hist = dict(zip(series["year"].astype(int), series["total"].astype(float)))
    if len(hist) < 5:
        raise HTTPException(422, "Not enough history for this group")
    history = [{"year": int(k), "total": int(v)} for k, v in hist.items()]
    preds, path = None, []

    if year <= last + 1:  # one year ahead: the validated one-step model with real lags
        if (year - 1) not in hist or (year - 2) not in hist:
            raise HTTPException(422, "Need the two previous years of data for this group")
        state_prev = float(query("SELECT sum(total) FROM suicides_headline WHERE state=? AND year=?", [state, year - 1]).iat[0, 0])
        row = pd.DataFrame([{"state": state, "gender": gender, "age_group": age_group, "year": year,
                             "lag1": hist[year - 1], "lag2": hist[year - 2],
                             "lag_mean2": (hist[year - 1] + hist[year - 2]) / 2, "state_lag1": state_prev}])
        preds = {"persistence": float(row.lag1[0]),
                 "weighted_persistence": float(b["w"] * row.lag1[0] + (1 - b["w"]) * row.lag2[0])}
        X, _ = to_categories(row[F.SUI_CAT + F.SUI_NUM], F.SUI_CAT, cats)
        preds["lightgbm_delta"] = float(max(0.0, row.lag1[0] + b["gbm"].predict(X)[0]))
        value, method = preds[b["selected"]], b["selected"]
        bucket = "small (<50)" if row.lag1[0] < 50 else "medium (50-500)" if row.lag1[0] < 500 else "large (500+)"
        band = b["error_bands_p80"].get(bucket, 0)
        band_80 = [max(0.0, value - band), value + band]
    else:  # several years ahead of the last data year
        from ml.train_suicides import multi_step
        vals = np.array([hist[y] for y in sorted(hist)])
        max_bt = max(b["multi_year"])

        def step(hh):
            sel = b["multi_year"][min(hh, max_bt)]
            rel = sel["rel_p80"] * (np.sqrt(hh / max_bt) if hh > max_bt else 1.0)  # extrapolated beyond backtest
            v = multi_step(vals, hh, sel["method"], b["w"])
            spread = rel * max(vals[-1], 10)
            return v, sel["method"], [max(0.0, v - spread), v + spread]

        for y in range(last + 1, year + 1):
            v, _, bd = step(y - last)
            path.append({"year": y, "forecast": round(v, 1), "low": round(bd[0], 1), "high": round(bd[1], 1)})
        value, m, band_80 = step(year - last)
        method = f"{m} ({year - last}-year horizon)"

    warnings = []
    if year > last:
        warnings.append(f"{year} is {year - last} year(s) beyond the data (last year {last}); no actual value to compare")
    if year - last > 5:
        warnings.append("More than 5 years ahead: the backtest covers only up to 5 years, so the band is extrapolated")
    out = {"forecast": round(value, 1), "method": method, "actual": hist.get(year), "warnings": warnings,
           "years_beyond_data": max(0, year - last), "last_data_year": last}
    if detail:
        out.update({"band_80": band_80, "all_methods": preds, "history": history, "path": path,
                    "conclusion": report("suicides_forecast")["conclusion"]})
    return out


# ------------------------------------------------------------------ diabetes
def predict_diabetes(inp: dict, detail: bool):
    b = bundle("diabetes_risk")
    cats = b["categories"]
    _require(inp["gender"], cats["gender"], "gender")
    _require(inp["smoking_history"], cats["smoking_history"], "smoking history")
    row = pd.DataFrame([inp])
    X, _ = to_categories(row[F.DIA_CAT + F.DIA_NUM], F.DIA_CAT, cats)
    p = float(b["model"].predict_proba(X)[0, 1])
    t = b["threshold"]
    band = "High" if p >= t else "Moderate" if p >= max(0.1, t / 3) else "Low"
    out = {"probability": p, "risk_band": band,
           "disclaimer": "Educational estimate from a statistical model - not a diagnosis. Consult a doctor."}
    if detail:
        contrib = b["model"].predict(X, pred_contrib=True)[0]  # SHAP values in log-odds
        names = F.DIA_CAT + F.DIA_NUM
        parts = sorted([{"feature": n, "value": inp[n], "contribution": float(c)} for n, c in zip(names, contrib[:-1])],
                       key=lambda d: -abs(d["contribution"]))
        out.update({"threshold": t, "base_rate": b["base_rate"], "contributions": parts,
                    "baseline_logodds": float(contrib[-1])})
    return out


# ------------------------------------------------------------------ weather
MAX_WEATHER_DATE = date(2030, 12, 31)


def _features_on(city: str, day: date):
    df = query("""SELECT * FROM weather WHERE city = ? AND date BETWEEN ? AND ? ORDER BY date""",
               [city, day - timedelta(days=10), day + timedelta(days=1)])
    feats = F.weather_features(df)
    return feats, feats[pd.to_datetime(feats["date"]).dt.date == day]


def predict_weather(city: str, target: date, detail: bool):
    """Predict the weather FOR `target`:
    * inside the data             -> 1-day-ahead model from the previous day (actual shown for checking)
    * up to 7 days after the data -> direct h-day-ahead model from the last observed day
    * further ahead               -> climate outlook (typical for that date + observed warming trend)"""
    b = bundle("weather_nextday")
    _require(city, b["categories"]["city"], "city")
    rng = query("SELECT min(date) a, max(date) b FROM weather WHERE city = ?", [city]).iloc[0]
    first, last = (rng.a + timedelta(days=7)).date(), rng.b.date()
    if target <= first or target > MAX_WEATHER_DATE:
        raise HTTPException(422, f"Pick a date between {first + timedelta(days=1)} and {MAX_WEATHER_DATE}")

    clim = b["climatology"][city]
    doy = min(target.timetuple().tm_yday, 365) - 1
    horizon = (target - last).days
    max_h = b.get("max_ml_horizon", 1)
    out = {"city": city, "for_date": target.isoformat(), "last_data_date": last.isoformat(),
           "days_beyond_data": max(0, horizon)}

    if horizon <= max_h:
        base = target - timedelta(days=1) if horizon <= 0 else last
        h = 1 if horizon <= 0 else horizon
        hz = b["horizons"][h]
        feats, today = _features_on(city, base)
        X, _ = to_categories(today[F.WX_FEATURES], F.WX_CAT, b["categories"])
        tmax, p_rain = float(hz["temp"].predict(X)[0]), float(hz["rain"].predict_proba(X)[0, 1])
        actual = None
        if horizon <= 0:
            nxt = feats[pd.to_datetime(feats["date"]).dt.date == target]
            if len(nxt):
                actual = {"tmax": float(nxt["temperature_2m_max"].iloc[0]),
                          "rain": bool(nxt["precipitation_sum"].iloc[0] >= 2.5)}
        t = today.iloc[0]
        out.update({"mode": "ml_forecast", "lead_days": h, "based_on": base.isoformat(),
                    "tmax": tmax, "rain_probability": p_rain, "rain_expected": p_rain >= hz["rain_threshold"],
                    "observed_on_base_day": {"tmax": float(t["temperature_2m_max"]), "tmin": float(t["temperature_2m_min"]),
                                             "precip_mm": float(t["precipitation_sum"])},
                    "actual": actual})
        if detail:
            e = hz["temp_error_p80"]
            out.update({"tmax_band_80": [tmax - e, tmax + e], "rain_threshold": hz["rain_threshold"],
                        "climatology": {"tmax": clim["tmax"][doy], "rain_probability": clim["rain_prob"][doy]},
                        "recent": [{"date": d.date().isoformat(), "tmax": float(a), "precip": float(r)}
                                   for d, a, r in zip(pd.to_datetime(feats["date"]), feats["temperature_2m_max"],
                                                      feats["precipitation_sum"]) if d.date() <= base]})
            if horizon > 0:  # the whole 1-7 day path from the last observed day
                out["path"] = [{"date": (last + timedelta(days=hh)).isoformat(), "lead_days": hh,
                                "tmax": float(m["temp"].predict(X)[0]),
                                "rain_probability": float(m["rain"].predict_proba(X)[0, 1])}
                               for hh, m in b["horizons"].items()]
    else:
        warming = clim["trend_per_year"] * (target.year - clim["ref_year"])
        tmax = clim["tmax"][doy] + warming
        sd = clim["tmax_sd"][doy]
        out.update({"mode": "climate_outlook", "lead_days": horizon, "tmax": tmax,
                    "rain_probability": clim["rain_prob"][doy], "rain_expected": clim["rain_prob"][doy] >= 0.5,
                    "actual": None, "warming_adjustment_c": warming})
        if detail:
            out.update({"tmax_band_80": [tmax - 1.28 * sd, tmax + 1.28 * sd],
                        "trend_c_per_decade": 10 * clim["trend_per_year"],
                        "outlook_window": [{"date": (target + timedelta(days=k)).isoformat(),
                                            "tmax": clim["tmax"][(doy + k) % 365] + warming,
                                            "rain_probability": clim["rain_prob"][(doy + k) % 365]} for k in range(-15, 16)]})
    out["explanation"] = (
        "Checked against the real record: the model only saw data up to the previous day." if horizon <= 0 else
        f"Forecast {horizon} day(s) after the last observation ({last}) using the {horizon}-day-ahead model."
        if horizon <= max_h else
        f"{target} is {horizon} days after the last observation ({last}). Day-to-day weather cannot be forecast that far "
        "ahead from past values, so this is a climate outlook: the typical value for this city and calendar date "
        "(2000-2024), adjusted for the city's observed warming trend.")
    return out
