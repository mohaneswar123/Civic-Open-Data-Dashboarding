"""Suicide count forecasting (standalone - no other dataset is used).

Target     : total suicides for a State x Gender x Age-group in a year
             (from the single 'Means_adopted' breakdown, so there is no double counting)
Split      : time-separated - development 2003-2009, test 2010-2012
Selection  : candidates are fitted on 2003-2008 and compared on 2009 (validation);
             the winner is refitted on 2003-2009 and evaluated ONCE on the test years
Candidates : persistence (same as last year), weighted persistence (w*lag1 + (1-w)*lag2),
             LightGBM predicting the year-on-year change (L1 loss)
Multi-year : for 2+ years ahead, a rolling-origin backtest (origins 2005-2011, horizons
             1-5 years) compares flat, weighted-flat and damped-trend forecasts per
             horizon; the winner per horizon and its error spread are stored
"""
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml import common
from ml.features import SUI_CAT, SUI_NUM, suicide_panel

TRAIN_END, VALID_YEAR = 2009, 2009
LGB_PARAMS = dict(objective="l1", n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=20,
                  random_state=common.SEED, verbose=-1)


def fit_candidates(train):
    """Return dict name -> predict(df) fitted on `train`."""
    Xtr, cats = common.to_categories(train[SUI_CAT + SUI_NUM], SUI_CAT)
    gbm = lgb.LGBMRegressor(**LGB_PARAMS).fit(Xtr, train["total"] - train["lag1"])
    # weight w chosen by least absolute error on the training rows only
    grid = np.linspace(0, 1, 21)
    w = float(grid[np.argmin([np.abs(g * train.lag1 + (1 - g) * train.lag2 - train.total).mean() for g in grid])])
    return {
        "persistence": lambda d: d["lag1"].values,
        "weighted_persistence": lambda d: (w * d["lag1"] + (1 - w) * d["lag2"]).values,
        "lightgbm_delta": lambda d: np.clip(
            d["lag1"].values + gbm.predict(common.to_categories(d[SUI_CAT + SUI_NUM], SUI_CAT, cats)[0]), 0, None),
    }, {"gbm": gbm, "categories": cats, "w": w}


PHI = 0.8          # trend damping per year
MAX_BACKTEST_H = 5


def multi_step(hist: np.ndarray, h: int, method: str, w: float) -> float:
    """Forecast h years past the last value of `hist` (chronological, >= 5 values)."""
    last, prev = hist[-1], hist[-2]
    if method == "flat":
        return float(last)
    if method == "weighted_flat":
        return float(w * last + (1 - w) * prev)
    window = hist[-5:]
    slope = np.polyfit(np.arange(len(window)), window, 1)[0]
    return float(max(0.0, last + slope * sum(PHI ** i for i in range(1, h + 1))))


def horizon_backtest(headline, w):
    wide = headline.pivot_table(index=["state", "gender", "age_group"], columns="year", values="total").dropna()
    years = list(wide.columns)
    rows = []
    for origin in range(2005, 2012):
        past = wide[[y for y in years if y <= origin]].values
        for h in range(1, MAX_BACKTEST_H + 1):
            if origin + h > years[-1]:
                break
            actual = wide[origin + h].values
            for m in ("flat", "weighted_flat", "damped_trend"):
                pred = np.array([multi_step(r, h, m, w) for r in past])
                scale = np.maximum(past[:, -1], 10)
                for a, p_, sc in zip(actual, pred, scale):
                    rows.append((h, m, abs(p_ - a), abs(p_ - a) / sc))
    bt = pd.DataFrame(rows, columns=["h", "method", "abs_err", "rel_err"])
    table = bt.groupby(["h", "method"]).agg(mae=("abs_err", "mean"), rel_p80=("rel_err", lambda x: x.quantile(0.8)),
                                             n=("abs_err", "size")).reset_index()
    best = table.loc[table.groupby("h")["mae"].idxmin()].set_index("h")
    return table, {int(h): {"method": r.method, "rel_p80": float(r.rel_p80)} for h, r in best.iterrows()}


def main():
    t0 = time.perf_counter()
    headline = common.query("SELECT * FROM suicides_headline")
    panel = suicide_panel(headline).dropna(subset=["lag1", "lag2"])

    # ---- model selection on validation year (test years untouched)
    dev_tr, dev_va = panel[panel.year < VALID_YEAR], panel[panel.year == VALID_YEAR]
    cands, _ = fit_candidates(dev_tr)
    validation = {k: common.regression_metrics(dev_va["total"], f(dev_va)) for k, f in cands.items()}
    selected = min(validation, key=lambda k: validation[k]["mae"])

    # ---- refit on all development years, evaluate once on test
    train, test = panel[panel.year <= TRAIN_END], panel[panel.year > TRAIN_END]
    cands, fitted = fit_candidates(train)
    y = test["total"].values
    results, preds = {}, {}
    for k, f in cands.items():
        preds[k] = f(test)
        results[k] = common.regression_metrics(y, preds[k])
        results[k]["mae_ci95"] = common.bootstrap_ci(y, preds[k], lambda a, b: np.mean(np.abs(a - b)))
    pred = preds[selected]

    # Residual spread per size bucket -> honest +/- band shown with each forecast.
    test = test.assign(pred=pred, abs_err=np.abs(pred - y))
    test["bucket"] = np.select([test.lag1 < 50, test.lag1 < 500], ["small (<50)", "medium (50-500)"], "large (500+)")
    bands = test.groupby("bucket")["abs_err"].quantile(0.8).round(1).to_dict()
    by_group = []
    for col in ["gender", "age_group", "bucket"]:
        for k, g in test.groupby(col):
            by_group.append({"dimension": col, "group": k, "n": int(len(g)),
                             "selected_mae": float(g["abs_err"].mean()),
                             "persistence_mae": float(np.abs(g["lag1"] - g["total"]).mean())})

    gain = results["persistence"]["mae"] - results[selected]["mae"]
    bt_table, by_h = horizon_backtest(headline, fitted["w"])
    bundle = {**fitted, "selected": selected, "multi_year": by_h, "phi": PHI, "features": SUI_CAT + SUI_NUM, "error_bands_p80": bands,
              "last_year": int(headline.year.max())}
    report = {
        "title": "Suicide counts - one-year-ahead forecast",
        "task": "regression (count)", "target": "total (State x Gender x Age group, Means_adopted breakdown)",
        "split": {"type": "time", "train": f"2003-{TRAIN_END}", "validation": f"{VALID_YEAR} (model selection)",
                  "test": f"{TRAIN_END + 1}-2012", "train_rows": int(len(train)), "test_rows": int(len(test))},
        "validation": validation, "results": results, "selected": selected,
        "weighted_persistence_w": fitted["w"],
        "conclusion": (f"Selected '{selected}' on the validation year. On held-out years it is "
                       f"{abs(gain):.1f} deaths/series {'better' if gain > 0 else 'worse'} in MAE than simple persistence. "
                       "With only 12 annual observations per series, last year's value already explains almost all "
                       "variation; machine learning adds little. This is reported as a negative/neutral finding."),
        "error_bands_p80": bands, "by_condition": by_group,
        "by_horizon": bt_table.round(4).to_dict(orient="records"),
        "multi_year_selection": by_h,
        "feature_importance": common.feature_importance(fitted["gbm"], SUI_CAT + SUI_NUM),
        "limitations": ["Only 12 years of data: multi-year forecasts beyond ~5 years are extrapolations with wide bands",
                        "Multi-year backtest origins overlap the 2010-2012 test years (reported separately)",
                        "Reported counts reflect recording practice as well as true incidence",
                        "Not for individual risk assessment; aggregate planning use only"],
    }
    common.save("suicides_forecast", bundle, report, t0)
    print(f"  selected on validation: {selected}")
    for h, v in by_h.items():
        print(f"  horizon {h}y: {v['method']}  p80 rel err {v['rel_p80']:.3f}")
    for k, v in results.items():
        print(f"  {k:22s} MAE={v['mae']:.2f} RMSE={v['rmse']:.2f} R2={v['r2']:.4f} WAPE={v['wape_pct']:.2f}%")


if __name__ == "__main__":
    main()
