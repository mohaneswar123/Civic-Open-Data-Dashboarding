"""Advanced dashboards - policy makers and admins only.

These endpoints add disparity indices, trends with confidence intervals and the
crop <-> rainfall relationship analysis. Every estimate carries its sample size,
uncertainty and caveats so it is hard to over-read.
"""
from functools import lru_cache

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query

from .. import stats
from ..auth import require_role
from ..db import db_version, query, records

router = APIRouter(prefix="/api/policy", tags=["advanced dashboards"], dependencies=[Depends(require_role("policy"))])

CROP_YIELD_SQL = """
    SELECT state, year, sum(production) / sum(area_ha) AS yield_t_ha, sum(production) AS production_t,
           sum(area_ha) AS area_ha, count(DISTINCT district) AS districts
    FROM crop WHERE crop = ? AND unit = 'tonnes' AND production > 0 AND NOT flag_yield_outlier {extra}
    GROUP BY state, year"""


@router.get("/crop/options")
def crop_options():
    crops = query("""SELECT crop, count(*) n FROM crop WHERE unit='tonnes' GROUP BY crop HAVING count(*) > 500
                     ORDER BY n DESC""")
    states = query("SELECT DISTINCT state FROM crop ORDER BY state")
    return {"crops": [r["crop"] for r in records(crops)], "states": [r["state"] for r in records(states)]}


@router.get("/crop/disparity")
def crop_disparity(crop: str = Query("Rice")):
    sy = query(CROP_YIELD_SQL.format(extra=""), [crop])
    if sy.empty:
        raise HTTPException(404, f"No usable data for crop '{crop}'")
    rows = []
    for state, g in sy.groupby("state"):
        t = stats.trend(g["year"], g["yield_t_ha"])
        rows.append({"state": state, "median_yield": float(g["yield_t_ha"].median()), "years": int(len(g)),
                     "trend_per_year": t["slope"], "trend_p": t["p_value"], "trend_significant": t["significant"],
                     "avg_area_ha": float(g["area_ha"].mean())})
    rows.sort(key=lambda r: -r["median_yield"])
    # Years where few states reported would show fake crashes/jumps - they are excluded from
    # the national series and the inequality index (and the exclusion is disclosed).
    per_year = sy.groupby("year").agg(states=("state", "nunique"), production_t=("production_t", "sum"),
                                      area_ha=("area_ha", "sum"))
    min_states = int(np.ceil(0.6 * per_year["states"].max()))
    good_years = per_year[per_year["states"] >= min_states].index
    excluded = [int(y) for y in per_year.index if y not in good_years]
    gini_by_year = [{"year": int(y), "gini": stats.gini(g["yield_t_ha"]), "states": int(len(g))}
                    for y, g in sy[sy.year.isin(good_years)].groupby("year")]
    nat = per_year.loc[good_years]
    reliable = [r for r in rows if r["years"] >= 5]
    best, worst = (reliable[0], reliable[-1]) if reliable else (None, None)
    return {"crop": crop, "states": rows, "gini_by_year": gini_by_year,
            "national_yield": [{"year": int(y), "yield_t_ha": float(r.production_t / r.area_ha), "states": int(r.states)}
                               for y, r in nat.iterrows()],
            "excluded_years": excluded, "min_states": min_states,
            "gap_ratio": (best["median_yield"] / worst["median_yield"]) if best and worst["median_yield"] else None,
            "notes": [f"Years with fewer than {min_states} reporting states are left out of the national and Gini series"
                      + (f" (excluded: {', '.join(map(str, excluded))})" if excluded else ""),
                      "Gap ratio uses only states with at least 5 reporting years",
                      "Yield = total production / total area of reporting districts (tonnes per hectare)",
                      "Gini: 0 = all states equal, 1 = maximal inequality (computed across states per year)",
                      "Trend is an OLS slope; 'significant' means p < 0.05 - not proof of a cause",
                      "States with few reporting years have unreliable trends - check the 'years' column"]}


@router.get("/crop/districts")
def crop_districts(state: str, crop: str = Query("Rice")):
    df = query("""SELECT district, year, sum(production)/sum(area_ha) AS yield_t_ha, sum(area_ha) area_ha
                  FROM crop WHERE state = ? AND crop = ? AND unit='tonnes' AND production > 0 AND NOT flag_yield_outlier
                  GROUP BY district, year""", [state, crop])
    out = []
    for d, g in df.groupby("district"):
        t = stats.trend(g["year"], g["yield_t_ha"])
        out.append({"district": d, "median_yield": float(g["yield_t_ha"].median()), "years": int(len(g)),
                    "latest_year": int(g["year"].max()), "avg_area_ha": float(g["area_ha"].mean()),
                    "trend_per_year": t["slope"], "trend_significant": t["significant"]})
    out.sort(key=lambda r: -r["median_yield"])
    return {"state": state, "crop": crop, "districts": out, "cv": stats.cv([r["median_yield"] for r in out]),
            "gini": stats.gini([r["median_yield"] for r in out])}


@router.get("/crop/rainfall")
def crop_rainfall(crop: str = Query("Rice"), state: str = Query("All")):
    # Bootstrap CIs are the expensive part; cache per database version (a new
    # pipeline run changes db_version and so invalidates the cache).
    return _crop_rainfall(crop, state, db_version())


@lru_cache(maxsize=128)
def _crop_rainfall(crop: str, state: str, _version: float | None):
    """Relationship analysis: does a wetter/drier monsoon go with higher/lower yield?
    Yield anomaly = % deviation from the state's own median yield for this crop (removes
    'Punjab is always high' effects). Compared with monsoon departure from normal."""
    sy = query(CROP_YIELD_SQL.format(extra=""), [crop])
    rain = query("SELECT state, year, monsoon_departure_pct, jun_sep FROM rainfall_state_year")
    df = sy.merge(rain, on=["state", "year"], how="inner")
    if df.empty:
        raise HTTPException(404, "No overlapping crop/rainfall data")
    df["yield_anomaly_pct"] = 100 * (df["yield_t_ha"] / df.groupby("state")["yield_t_ha"].transform("median") - 1)
    # Remove each state's linear technology trend so a time trend is not mistaken for a rainfall effect.
    df["yield_anomaly_detrended"] = np.nan
    for _, idx in df.groupby("state").groups.items():
        g = df.loc[idx]
        if len(g) >= 5:
            b = np.polyfit(g["year"], g["yield_anomaly_pct"], 1)
            df.loc[idx, "yield_anomaly_detrended"] = g["yield_anomaly_pct"] - np.polyval(b, g["year"])
    per_state = []
    for s, g in df.groupby("state"):
        r = stats.spearman(g["monsoon_departure_pct"], g["yield_anomaly_detrended"])
        per_state.append({"state": s, **r})
    per_state.sort(key=lambda r: (r["rho"] is None, -(r["rho"] or 0)))
    sel = df if state == "All" else df[df.state == state]
    pooled = stats.spearman(sel["monsoon_departure_pct"], sel["yield_anomaly_detrended"])
    n_tests = sum(1 for r in per_state if r["rho"] is not None)
    n_sig = sum(1 for r in per_state if r.get("significant"))
    # Model ablation from training (does rainfall help prediction on held-out years?)
    try:
        import json
        from .. import settings
        rep = json.loads((settings.REPORTS / "metrics_crop_yield.json").read_text())
        ablation = rep.get("rainfall_contribution")
    except Exception:
        ablation = None
    return {"crop": crop, "state": state, "pooled": pooled, "per_state": per_state,
            "points": records(sel[["state", "year", "monsoon_departure_pct", "yield_anomaly_detrended", "yield_t_ha"]]),
            "multiple_testing": {"tests": n_tests, "significant": n_sig,
                                 "expected_false_positives": round(0.05 * n_tests, 1)},
            "model_ablation": ablation,
            "notes": ["Association, not causation: irrigation, prices, seeds and policy also change yields",
                      "Yield anomalies are detrended per state to remove long-run technology gains",
                      f"With {n_tests} state-level tests at p<0.05, about {round(0.05 * n_tests, 1)} 'significant' results are expected by chance alone",
                      "State rainfall is the mean of IMD sub-divisions; irrigated states may show little rainfall sensitivity"]}


# ------------------------------------------------------------------ rainfall
@router.get("/rainfall/disparity")
def rainfall_disparity():
    df = query("SELECT subdivision, year, annual, jun_sep, departure_pct FROM rainfall")
    out = []
    for sd, g in df.groupby("subdivision"):
        t = stats.trend(g["year"], g["annual"])
        recent, early = g[g.year >= 1986]["annual"].mean(), g[g.year < 1986]["annual"].mean()
        out.append({"subdivision": sd, "mean_annual_mm": float(g["annual"].mean()), "cv": stats.cv(g["annual"]),
                    "trend_mm_per_decade": None if t["slope"] is None else 10 * t["slope"],
                    "trend_p": t["p_value"], "trend_significant": t["significant"],
                    "deficient_years_pct": float(100 * (g["departure_pct"] <= -20).mean()),
                    "excess_years_pct": float(100 * (g["departure_pct"] >= 20).mean()),
                    "recent_vs_early_pct": float(100 * (recent / early - 1)) if early else None,
                    "years": int(len(g))})
    out.sort(key=lambda r: -(r["cv"] or 0))
    return {"subdivisions": out,
            "notes": ["CV (coefficient of variation) = year-to-year variability; higher = less reliable rainfall",
                      "Deficient / excess: annual rainfall at least 20% below / above the 1961-2010 normal (IMD categories)",
                      "Recent vs early compares 1986-2015 with 1901-1985"]}


@router.get("/rainfall/subdivision")
def rainfall_subdivision(name: str):
    df = query("""SELECT year, annual, jun_sep, oct_dec, mar_may, jan_feb, departure_pct, flag_annual_repaired
                  FROM rainfall WHERE subdivision = ? ORDER BY year""", [name])
    if df.empty:
        raise HTTPException(404, f"Unknown sub-division '{name}'")
    df["rolling10"] = df["annual"].rolling(10, min_periods=5).mean()
    return {"subdivision": name, "years": records(df), "trend": stats.trend(df["year"], df["annual"]),
            "monsoon_trend": stats.trend(df["year"], df["jun_sep"])}


# ------------------------------------------------------------------ suicides
@router.get("/suicides/breakdown")
def suicides_breakdown(type_code: str = Query("Causes"), state: str = Query("All"), year: str = Query("All")):
    params = [type_code]
    sql = "SELECT category, gender, sum(total) total FROM suicides WHERE type_code = ?"
    if state != "All":
        sql += " AND state = ?"; params.append(state)
    if year != "All":
        sql += " AND year = ?"; params.append(int(year))
    df = query(sql + " GROUP BY category, gender", params)
    pivot = df.pivot_table(index="category", columns="gender", values="total", aggfunc="sum", fill_value=0).reset_index()
    pivot["total"] = pivot.drop(columns="category").sum(axis=1)
    pivot = pivot.sort_values("total", ascending=False)
    grand = float(pivot["total"].sum()) or 1
    pivot["share_pct"] = 100 * pivot["total"] / grand
    states = [r["state"] for r in records(query("SELECT DISTINCT state FROM suicides ORDER BY state"))]
    return {"type_code": type_code, "state": state, "year": year, "categories": records(pivot), "states": states,
            "type_codes": ["Causes", "Means_adopted", "Professional_Profile", "Education_Status", "Social_Status"]}


@router.get("/suicides/farmers")
def suicides_farmers():
    nat = query("""SELECT year, sum(total) FILTER (WHERE category = 'Farming/Agriculture Activity') farmers,
                          sum(total) all_professions
                   FROM suicides WHERE type_code = 'Professional_Profile' GROUP BY year ORDER BY year""")
    nat["share_pct"] = 100 * nat["farmers"] / nat["all_professions"]
    st_ = query("""SELECT state, year, sum(total) farmers FROM suicides
                   WHERE type_code = 'Professional_Profile' AND category = 'Farming/Agriculture Activity'
                   GROUP BY state, year""")
    by_state = []
    for s, g in st_.groupby("state"):
        t = stats.trend(g["year"], g["farmers"])
        by_state.append({"state": s, "total_2001_2012": int(g["farmers"].sum()),
                         "trend_per_year": t["slope"], "trend_significant": t["significant"]})
    by_state.sort(key=lambda r: -r["total_2001_2012"])
    return {"national": records(nat), "by_state": by_state[:15],
            "trend": stats.trend(nat["year"], nat["farmers"]),
            "notes": ["Professional_Profile breakdown, category 'Farming/Agriculture Activity'",
                      "NCRB classification changed after 2013 (not in this data); do not splice with later series",
                      "Counts not rates - cultivator population is not in this dataset"]}


@router.get("/suicides/state-trends")
def suicides_state_trends():
    df = query("SELECT state, year, sum(total) total FROM suicides_headline GROUP BY state, year")
    out = []
    for s, g in df.groupby("state"):
        g = g.sort_values("year")
        t = stats.trend(g["year"], g["total"])
        first, last = g["total"].iloc[0], g["total"].iloc[-1]
        out.append({"state": s, "total_2001": int(first), "total_2012": int(last),
                    "change_pct": float(100 * (last / first - 1)) if first else None,
                    "trend_per_year": t["slope"], "trend_p": t["p_value"], "trend_significant": t["significant"]})
    out.sort(key=lambda r: -r["total_2012"])
    return {"states": out}


@router.get("/suicides/reconciliation")
def suicides_reconciliation():
    df = query("SELECT * FROM suicides_reconciliation WHERE max_abs_gap > 0 ORDER BY gap_pct DESC NULLS LAST LIMIT 50")
    summary = query("""SELECT count(*) n, count(*) FILTER (WHERE max_abs_gap > 0) diverging, avg(gap_pct) mean_gap
                       FROM suicides_reconciliation""").iloc[0]
    return {"rows": records(df), "state_years": int(summary.n), "diverging": int(summary.diverging),
            "mean_gap_pct": float(summary.mean_gap or 0),
            "notes": ["Each breakdown should add up to the same deaths; gaps show inconsistencies in the source",
                      "Large gap percentages usually come from small UTs where a few records differ"]}


# ------------------------------------------------------------------ diabetes
@router.get("/diabetes/risk-factors")
def diabetes_risk_factors():
    exposures = {
        "Hypertension": ("hypertension = 1", "hypertension = 0"),
        "Heart disease": ("heart_disease = 1", "heart_disease = 0"),
        "Obese (BMI 30+) vs normal": ("bmi_class = 'Obese'", "bmi_class = 'Normal'"),
        "Overweight vs normal": ("bmi_class = 'Overweight'", "bmi_class = 'Normal'"),
        "Age 60+ vs under 45": ("age >= 60", "age < 45"),
        "Current smoker vs never": ("smoking_history = 'current'", "smoking_history = 'never'"),
        "Former smoker vs never": ("smoking_history = 'former'", "smoking_history = 'never'"),
        "Male vs female": ("gender = 'Male'", "gender = 'Female'"),
    }
    out = []
    for label, (exp, ref) in exposures.items():
        r = query(f"""SELECT
            count(*) FILTER (WHERE {exp} AND diabetes = 1) a, count(*) FILTER (WHERE {exp} AND diabetes = 0) b,
            count(*) FILTER (WHERE {ref} AND diabetes = 1) c, count(*) FILTER (WHERE {ref} AND diabetes = 0) d
            FROM diabetes""").iloc[0]
        o = stats.odds_ratio(int(r.a), int(r.b), int(r.c), int(r.d))
        out.append({"factor": label, **o, "exposed_n": int(r.a + r.b), "exposed_prev_pct": 100 * r.a / max(r.a + r.b, 1),
                    "reference_prev_pct": 100 * r.c / max(r.c + r.d, 1)})
    out.sort(key=lambda x: -x["odds_ratio"])
    heat = query("""SELECT age_band, bmi_class, count(*) n, avg(diabetes) * 100 prevalence_pct
                    FROM diabetes GROUP BY age_band, bmi_class""")
    return {"odds_ratios": out, "age_bmi": records(heat),
            "notes": ["Unadjusted odds ratios: each factor is compared alone; factors overlap (e.g. older people have more hypertension)",
                      "Odds ratio 1 = no association; the 95% CI shows the plausible range",
                      "Cross-sectional data - associations do not show what came first"]}


# ------------------------------------------------------------------ weather
@router.get("/weather/extremes")
def weather_extremes():
    df = query("""SELECT city, year,
                         count(*) FILTER (WHERE temperature_2m_max >= 40) heat_days,
                         count(*) FILTER (WHERE precipitation_sum >= 64.5) heavy_rain_days,
                         sum(precipitation_sum) annual_rain_mm, avg(temperature_2m_max) mean_tmax
                  FROM weather GROUP BY city, year ORDER BY city, year""")
    summary = []
    for c, g in df.groupby("city"):
        t_heat, t_tmax = stats.trend(g["year"], g["heat_days"]), stats.trend(g["year"], g["mean_tmax"])
        t_rain = stats.trend(g["year"], g["annual_rain_mm"])
        summary.append({"city": c, "avg_heat_days": float(g["heat_days"].mean()),
                        "avg_heavy_rain_days": float(g["heavy_rain_days"].mean()),
                        "heat_days_trend_per_decade": None if t_heat["slope"] is None else 10 * t_heat["slope"],
                        "heat_trend_significant": t_heat["significant"],
                        "tmax_trend_c_per_decade": None if t_tmax["slope"] is None else 10 * t_tmax["slope"],
                        "tmax_trend_significant": t_tmax["significant"],
                        "rain_trend_mm_per_decade": None if t_rain["slope"] is None else 10 * t_rain["slope"],
                        "rain_trend_significant": t_rain["significant"]})
    return {"yearly": records(df), "summary": summary,
            "notes": ["Heat day: maximum temperature 40 C or more. Heavy rain day: 64.5 mm or more (IMD 'heavy rainfall')",
                      "25 years is short for climate trends - treat slopes as indicative, check significance"]}
