"""Crop yield model (the only module that uses a second dataset: state rainfall).

Target      : log(yield) where yield = production / area  (tonnes per hectare)
Split       : time-separated - train <= 2010, test 2011-2015 (no future leakage)
Baseline    : historical median yield for the same district + crop + season
Candidate   : LightGBM with rainfall features
Ablation    : identical LightGBM WITHOUT rainfall -> does rainfall honestly add value?
Uncertainty : 10th / 90th percentile quantile models, conformally calibrated on the
              last training year (2010) so the 80% interval really covers ~80%
"""
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml import common
from ml.features import CROP_CAT, CROP_RAIN, crop_features

TRAIN_END = 2010


def load():
    df = common.query("""
        SELECT c.state, c.district, c.year, c.season, c.crop, c.area_ha, c.production, c.yield_t_per_ha,
               r.annual, r.jun_sep, r.oct_dec, r.mar_may, r.monsoon_departure_pct
        FROM crop c LEFT JOIN rainfall_state_year r ON r.state = c.state AND r.year = c.year
        WHERE c.unit = 'tonnes' AND c.production > 0 AND NOT c.flag_yield_outlier
    """)
    df["target"] = np.log(df["yield_t_per_ha"])
    return df


def fit_lgb(X, y, objective="regression", alpha=None):
    params = dict(n_estimators=600, learning_rate=0.05, num_leaves=127, min_child_samples=20,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=common.SEED, verbose=-1)
    if objective == "quantile":
        params.update(objective="quantile", alpha=alpha, n_estimators=300)
    m = lgb.LGBMRegressor(**params)
    m.fit(X, y)
    return m


DAMPING = 0.5          # only half of the historical trend is carried forward
MAX_SLOPE = 0.05       # cap: at most ~5% yield change per year from the trend term


def trend_slopes(rows: pd.DataFrame) -> pd.DataFrame:
    """OLS slope of yearly mean log-yield per state/crop/season (>= 6 distinct years), capped."""
    g = rows.groupby(["state", "crop", "season", "year"])["target"].mean().reset_index()
    out = []
    for key, s in g.groupby(["state", "crop", "season"]):
        if s["year"].nunique() >= 6:
            slope = np.polyfit(s["year"], s["target"], 1)[0]
            out.append((*key, float(np.clip(slope, -MAX_SLOPE, MAX_SLOPE))))
    return pd.DataFrame(out, columns=["state", "crop", "season", "slope"])


def main():
    t0 = time.perf_counter()
    df = load()
    train, test = df[df.year <= TRAIN_END], df[df.year > TRAIN_END]

    # ---- baseline: hierarchical historical median (district/crop/season -> state/crop -> crop)
    def baseline_predict(rows):
        pred = pd.Series(np.nan, index=rows.index)
        for keys in (["district", "crop", "season"], ["state", "crop"], ["crop"]):
            med = train.groupby(keys)["target"].median().rename("m")
            fill = rows[keys].merge(med, left_on=keys, right_index=True, how="left")["m"]
            pred = pred.fillna(pd.Series(fill.values, index=rows.index))
        return pred.fillna(train["target"].median())

    base_pred = baseline_predict(test)

    Xtr_raw, Xte_raw = crop_features(train), crop_features(test)
    Xtr, cats = common.to_categories(Xtr_raw, CROP_CAT)
    Xte, _ = common.to_categories(Xte_raw, CROP_CAT, cats)
    model = fit_lgb(Xtr, train["target"])
    pred = model.predict(Xte)

    # ---- ablation: no rainfall
    Xtr_nr, _ = common.to_categories(crop_features(train, use_rain=False), CROP_CAT, cats)
    Xte_nr, _ = common.to_categories(crop_features(test, use_rain=False), CROP_CAT, cats)
    model_nr = fit_lgb(Xtr_nr, train["target"])
    pred_nr = model_nr.predict(Xte_nr)

    # Conformalised quantile regression: fit quantiles on <= 2009, measure how far
    # 2010 actuals fall outside, widen the band by that amount.
    fit_rows, cal_rows = (train.year < TRAIN_END).values, (train.year == TRAIN_END).values
    q10 = fit_lgb(Xtr[fit_rows], train["target"][fit_rows], "quantile", 0.1)
    q90 = fit_lgb(Xtr[fit_rows], train["target"][fit_rows], "quantile", 0.9)
    y_cal = train["target"][cal_rows].values
    scores = np.maximum(q10.predict(Xtr[cal_rows]) - y_cal, y_cal - q90.predict(Xtr[cal_rows]))
    n_cal = len(scores)
    q_hat = float(np.quantile(scores, min(1.0, np.ceil((n_cal + 1) * 0.8) / n_cal)))
    raw_lo, raw_hi = q10.predict(Xte), q90.predict(Xte)
    raw_coverage = float(np.mean((test["target"].values >= raw_lo) & (test["target"].values <= raw_hi)))
    lo, hi = raw_lo - q_hat, raw_hi + q_hat
    coverage = float(np.mean((test["target"].values >= lo) & (test["target"].values <= hi)))

    # ---- Future years. Trees cannot extrapolate time, so a year after the data looks
    # like the last training year. Candidate fix: add each state-crop-season's historical
    # log-yield trend (slope fitted on TRAIN years only, damped, capped). Evaluated on test.
    slopes_train = trend_slopes(train)
    adj = test[["state", "crop", "season"]].merge(slopes_train, on=["state", "crop", "season"], how="left")["slope"].fillna(0).values
    pred_trend = pred + DAMPING * adj * (test["year"].values - TRAIN_END)

    y = test["target"].values
    def summarise(p):
        m = common.regression_metrics(y, p)  # on log scale
        ape = np.abs(np.exp(p) - np.exp(y)) / np.exp(y)
        m["median_ape_pct"] = float(100 * np.median(ape))
        m["r2_ci95"] = common.bootstrap_ci(y, p, lambda a, b: 1 - ((a - b) ** 2).sum() / ((a - a.mean()) ** 2).sum())
        return m

    results = {"baseline_historical_median": summarise(base_pred.values),
               "lightgbm_no_rainfall": summarise(pred_nr),
               "lightgbm_with_rainfall": summarise(pred),
               "lightgbm_with_rainfall_plus_trend": summarise(pred_trend)}
    trend_gain = results["lightgbm_with_rainfall"]["rmse"] - results["lightgbm_with_rainfall_plus_trend"]["rmse"]
    use_trend = trend_gain > 0.002

    # condition-wise (per season and top crops) - a model can be good on average and bad for a group
    test = test.assign(pred=pred, base=base_pred.values)
    by_season = []
    for s, g in test.groupby("season"):
        by_season.append({"group": s, "n": int(len(g)),
                          "model_r2": common.regression_metrics(g["target"], g["pred"])["r2"],
                          "baseline_r2": common.regression_metrics(g["target"], g["base"])["r2"]})
    top_crops = test["crop"].value_counts().head(10).index
    by_crop = []
    for c in top_crops:
        g = test[test.crop == c]
        by_crop.append({"group": c, "n": int(len(g)),
                        "model_mae_log": common.regression_metrics(g["target"], g["pred"])["mae"],
                        "baseline_mae_log": common.regression_metrics(g["target"], g["base"])["mae"]})

    rain_gain = results["lightgbm_no_rainfall"]["rmse"] - results["lightgbm_with_rainfall"]["rmse"]
    rain_names = set(CROP_RAIN)
    imp = common.feature_importance(model, list(Xtr.columns))
    rain_share = sum(f["importance"] for f in imp if f["feature"] in rain_names)

    # Lookups for the prediction form.
    rain = common.query("SELECT * FROM rainfall_state_year WHERE year BETWEEN 1961 AND 2010")
    normals = rain.groupby("state")[["annual", "jun_sep", "oct_dec", "mar_may"]].mean().round(1)
    options = (df.groupby(["state", "district"]).size().reset_index()[["state", "district"]]
               .groupby("state")["district"].apply(sorted).to_dict())
    crop_seasons = df.groupby("crop")["season"].apply(lambda s: sorted(s.unique())).to_dict()

    # ---- Final model for serving: evaluation is done, so refit on ALL years (1997-2015)
    # with the same settings; the conformal width measured above is kept.
    X_all, _ = common.to_categories(crop_features(df), CROP_CAT, cats)
    model = fit_lgb(X_all, df["target"])
    q10 = fit_lgb(X_all, df["target"], "quantile", 0.1)
    q90 = fit_lgb(X_all, df["target"], "quantile", 0.9)
    slopes_all = trend_slopes(df)
    trend_map = {f"{r.state}|{r.crop}|{r.season}": float(r.slope) for r in slopes_all.itertuples()}

    bundle = {"model": model, "q10": q10, "q90": q90, "conformal_q": q_hat, "last_year": int(df.year.max()),
              "use_trend": use_trend, "trend_damping": DAMPING, "trend_slopes": trend_map, "categories": cats, "features": list(Xtr.columns),
              "rain_normals": normals.to_dict(orient="index"), "districts": options, "crop_seasons": crop_seasons,
              "train_median_yield": df.groupby("crop")["yield_t_per_ha"].median().to_dict()}
    report = {
        "title": "Crop yield (t/ha) - LightGBM with state rainfall",
        "task": "regression", "target": "log(yield = production / area)",
        "split": {"type": "time", "train": f"1997-{TRAIN_END}", "test": f"{TRAIN_END + 1}-2015",
                  "train_rows": int(len(train)), "test_rows": int(len(test))},
        "results": results,
        "selected": "lightgbm_with_rainfall_plus_trend" if use_trend else "lightgbm_with_rainfall",
        "future_years": {
            "method": f"damped ({DAMPING}) state-crop-season log-yield trend added beyond the last data year"
                      if use_trend else "no trend adjustment (it did not help on held-out years)",
            "trend_rmse_improvement_log": float(trend_gain), "adopted": bool(use_trend),
            "served_model": "refit on all years 1997-2015 after evaluation",
        },
        "interval": {"type": "conformalised quantile regression (10-90)", "nominal": 0.8,
                     "raw_quantile_coverage": raw_coverage, "empirical_coverage": coverage,
                     "conformal_widening_log": q_hat, "calibration_rows": int(n_cal)},
        "by_condition": {"season": by_season, "top_crops": by_crop},
        "feature_importance": imp,
        "rainfall_contribution": {
            "rmse_improvement_log": float(rain_gain),
            "importance_share": round(float(rain_share), 4),
            "conclusion": ("Rainfall features improve test error" if rain_gain > 0.005 else
                           "Rainfall features give little or no improvement on held-out years - "
                           "yield is driven mostly by crop, location and season"),
        },
        "exclusions": ["non-tonne units (Coconut, fibre crops)", "zero production", "yield outliers (robust z>5)",
                       "aggregate rows (quarantined in pipeline)"],
        "limitations": ["State rainfall is an unweighted mean of IMD sub-divisions",
                        "Rainfall is annual/seasonal - intra-season timing is not captured",
                        "Association only - the model does not establish that rainfall causes yield changes"],
    }
    common.save("crop_yield", bundle, report, t0)
    for k, v in results.items():
        print(f"  {k:28s} R2(log)={v['r2']:.3f}  RMSE(log)={v['rmse']:.3f}  medAPE={v['median_ape_pct']:.1f}%")
    print(f"  trend gain={trend_gain:.4f} adopted={use_trend}")
    print(f"  interval coverage raw={raw_coverage:.3f} calibrated={coverage:.3f}  rainfall gain={rain_gain:.4f}")


if __name__ == "__main__":
    main()
