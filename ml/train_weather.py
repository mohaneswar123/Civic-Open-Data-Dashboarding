"""Weather forecasting (standalone): rain and maximum temperature, 1-7 days ahead.

Strategy  : DIRECT multi-horizon - one model per lead time h = 1..7 days, each using
            only what is known on the forecast day (no recursive error feedback)
Split     : time-separated - train 2000-2020, validation 2021 (early stopping +
            rain threshold), test 2022-2024 (never seen during development)
Rain      : rainy day = precipitation >= 2.5 mm (IMD); classification
Temp      : daily maximum temperature; regression
Baselines : persistence (same as the forecast day) and climatology (typical value
            for that city and calendar day)
Beyond 7d : day-to-day weather is not predictable from past values alone, so the
            service switches to a CLIMATE OUTLOOK: smoothed climatology for that
            calendar day + the city's observed warming trend
"""
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml import common
from ml.features import WX_CAT, WX_FEATURES, weather_features

TRAIN_END, VALID_YEAR = 2020, 2021
HORIZONS = range(1, 8)
PARAMS = dict(n_estimators=1500, learning_rate=0.04, num_leaves=63, min_child_samples=40,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=common.SEED, verbose=-1)


def climatology(raw: pd.DataFrame) -> dict:
    """Per city: smoothed day-of-year mean/std of tmax and rainy-day frequency (2000-2024),
    plus the linear trend of annual mean tmax (deg C per year)."""
    raw = raw.assign(doy=pd.to_datetime(raw["date"]).dt.dayofyear.clip(upper=365),
                     year=pd.to_datetime(raw["date"]).dt.year,
                     rainy=(raw["precipitation_sum"] >= 2.5).astype(float))
    out = {}
    for city, g in raw.groupby("city"):
        daily = g.groupby("doy").agg(tmax=("temperature_2m_max", "mean"), tmax_sd=("temperature_2m_max", "std"),
                                     rain=("rainy", "mean")).reindex(range(1, 366)).interpolate()
        # circular 15-day smoothing so Dec 31 and Jan 1 are neighbours
        wrap = pd.concat([daily.iloc[-7:], daily, daily.iloc[:7]])
        smooth = wrap.rolling(15, center=True).mean().iloc[7:-7]
        yearly = g.groupby("year")["temperature_2m_max"].mean()
        slope = float(np.polyfit(yearly.index, yearly.values, 1)[0])
        out[city] = {"tmax": smooth["tmax"].round(2).tolist(), "tmax_sd": smooth["tmax_sd"].round(2).tolist(),
                     "rain_prob": smooth["rain"].round(3).tolist(), "trend_per_year": slope,
                     "ref_year": float(yearly.index.to_series().mean())}
    return out


def main():
    t0 = time.perf_counter()
    raw = common.query("SELECT * FROM weather ORDER BY city, date")
    feats = weather_features(raw).dropna(subset=["tmax_roll7"])
    g = feats.groupby("city")
    year = pd.to_datetime(feats["date"]).dt.year
    clim = climatology(raw[pd.to_datetime(raw["date"]).dt.year <= TRAIN_END])  # baseline uses train years only
    stop = [lgb.early_stopping(50, verbose=False)]

    horizons, summary, results_h1, by_city = {}, [], None, []
    for h in HORIZONS:
        y_t = g["temperature_2m_max"].shift(-h)
        y_r = (g["precipitation_sum"].shift(-h) >= 2.5).astype(float).where(y_t.notna())
        ok = y_t.notna()
        tr, va, te = ok & (year <= TRAIN_END), ok & (year == VALID_YEAR), ok & (year > VALID_YEAR)
        Xtr, cats = common.to_categories(feats.loc[tr, WX_FEATURES], WX_CAT)
        Xva, _ = common.to_categories(feats.loc[va, WX_FEATURES], WX_CAT, cats)
        Xte, _ = common.to_categories(feats.loc[te, WX_FEATURES], WX_CAT, cats)

        temp = lgb.LGBMRegressor(**PARAMS).fit(Xtr, y_t[tr], eval_set=[(Xva, y_t[va])], callbacks=stop)
        rain = lgb.LGBMClassifier(**PARAMS).fit(Xtr, y_r[tr], eval_set=[(Xva, y_r[va])], callbacks=stop)
        thr = common.best_f1_threshold(y_r[va], rain.predict_proba(Xva)[:, 1])
        err_p80 = float(np.quantile(np.abs(temp.predict(Xva) - y_t[va]), 0.8))

        # climatology baseline for the TARGET day
        target_doy = (pd.to_datetime(feats.loc[te, "date"]) + pd.Timedelta(days=h)).dt.dayofyear.clip(upper=365).values - 1
        cities = feats.loc[te, "city"].values
        clim_t = np.array([clim[c]["tmax"][d] for c, d in zip(cities, target_doy)])
        clim_r = np.array([clim[c]["rain_prob"][d] for c, d in zip(cities, target_doy)])

        pt, pr = temp.predict(Xte), rain.predict_proba(Xte)[:, 1]
        yt, yr = y_t[te].values, y_r[te].values.astype(int)
        temp_res = {"baseline_persistence": common.regression_metrics(yt, feats.loc[te, "temperature_2m_max"]),
                    "baseline_climatology": common.regression_metrics(yt, clim_t),
                    "lightgbm": common.regression_metrics(yt, pt)}
        rain_res = {"baseline_persistence": common.classification_metrics(yr, (feats.loc[te, "precipitation_sum"] >= 2.5).astype(float), 0.5),
                    "baseline_climatology": common.classification_metrics(yr, clim_r, 0.5),
                    "lightgbm": common.classification_metrics(yr, pr, thr)}
        if h == 1:
            temp_res["lightgbm"]["mae_ci95"] = common.bootstrap_ci(yt, pt, lambda a, b: np.mean(np.abs(a - b)))
            results_h1 = {"temperature": temp_res, "rain": rain_res}
            fi = {"temperature": common.feature_importance(temp, WX_FEATURES), "rain": common.feature_importance(rain, WX_FEATURES)}
            sub = feats.loc[te].assign(pt=pt, pr=pr, yt=yt, yr=yr)
            for c, s in sub.groupby("city"):
                r = common.classification_metrics(s["yr"], s["pr"], thr)
                by_city.append({"city": c, "n": int(len(s)), "temp_mae": float(np.mean(np.abs(s["pt"] - s["yt"]))),
                                "temp_persistence_mae": float(np.mean(np.abs(s["temperature_2m_max"] - s["yt"]))),
                                "rain_f1": r["f1"], "rain_recall": r["recall"], "rain_rate": r["positive_rate"]})
        skill = 1 - temp_res["lightgbm"]["mae"] / temp_res["baseline_climatology"]["mae"]
        summary.append({"horizon_days": h, "temp_mae": temp_res["lightgbm"]["mae"],
                        "temp_mae_climatology": temp_res["baseline_climatology"]["mae"],
                        "temp_mae_persistence": temp_res["baseline_persistence"]["mae"],
                        "temp_skill_vs_climatology": float(skill),
                        "rain_auc": rain_res["lightgbm"]["roc_auc"], "rain_auc_climatology": rain_res["baseline_climatology"]["roc_auc"],
                        "rain_f1": rain_res["lightgbm"]["f1"], "rain_f1_climatology": rain_res["baseline_climatology"]["f1"]})
        horizons[h] = {"temp": temp, "rain": rain, "rain_threshold": thr, "temp_error_p80": err_p80}
        print(f"  h={h}: temp MAE {temp_res['lightgbm']['mae']:.2f} (clim {temp_res['baseline_climatology']['mae']:.2f}, "
              f"persist {temp_res['baseline_persistence']['mae']:.2f})  rain AUC {rain_res['lightgbm']['roc_auc']:.3f} "
              f"(clim {rain_res['baseline_climatology']['roc_auc']:.3f})")

    clim_all = climatology(raw)  # served outlook uses every year
    clim_sd_err = {c: float(np.nanmean(v["tmax_sd"])) for c, v in clim_all.items()}
    h1 = horizons[1]
    bundle = {"horizons": horizons, "temp_model": h1["temp"], "rain_model": h1["rain"], "rain_threshold": h1["rain_threshold"],
              "temp_error_p80": h1["temp_error_p80"], "categories": cats, "features": WX_FEATURES,
              "climatology": clim_all, "max_ml_horizon": max(HORIZONS)}
    report = {
        "title": "Weather forecast - rain & max temperature, 1-7 days ahead (+ climate outlook beyond)",
        "task": "classification + regression (direct multi-horizon)",
        "target": "rain(t+h) = precipitation >= 2.5 mm ; tmax(t+h), h = 1..7 days",
        "split": {"type": "time", "train": f"2000-{TRAIN_END}", "validation": str(VALID_YEAR),
                  "test": f"{VALID_YEAR + 1}-2024", "train_rows": int((year <= TRAIN_END).sum()), "test_rows": int((year > VALID_YEAR).sum())},
        "results": results_h1, "selected": "lightgbm", "by_horizon": summary,
        "rain_threshold": h1["rain_threshold"], "temp_error_p80": h1["temp_error_p80"], "by_condition": by_city,
        "feature_importance": fi, "climate_outlook_typical_sd": clim_sd_err,
        "limitations": ["Uses only past values at the same city - no satellite, radar or numerical weather model inputs",
                        "Skill falls with lead time; by ~7 days it is close to climatology",
                        "Beyond 7 days only a climate outlook (typical conditions + warming trend) is given",
                        "Reanalysis data (ERA5) is smoother than station observations; 10 cities only"],
    }
    common.save("weather_nextday", bundle, report, t0)


if __name__ == "__main__":
    main()
