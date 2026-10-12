"""Model comparison for the literature survey:  python -m ml.compare_models

Every candidate model is trained and tested on EXACTLY the same split as the
production model of that task, with the same features, so the numbers are
directly comparable. Results -> artifacts/reports/model_comparison.json
"""
from __future__ import annotations

import json
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from ml import common
from ml.features import (CROP_CAT, DIA_CAT, DIA_NUM, SUI_CAT, SUI_NUM, WX_CAT, WX_FEATURES,
                         crop_features, suicide_panel, weather_features)

SEED = common.SEED


def linear_pre(cat, num):
    return ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), cat), ("num", StandardScaler(), num)])


def tree_pre(cat, num):
    return ColumnTransformer([("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), cat),
                              ("num", "passthrough", num)])


def timed_fit(model, X, y):
    t = time.perf_counter()
    model.fit(X, y)
    return model, round(time.perf_counter() - t, 2)


def run_regression(name, candidates, Xtr, ytr, Xte, yte, extra=None):
    rows = []
    for label, model, kind in candidates:
        fitted, secs = timed_fit(model, Xtr, ytr)
        t = time.perf_counter()
        p = fitted.predict(Xte)
        pred_ms = 1000 * (time.perf_counter() - t) / len(Xte)
        m = common.regression_metrics(yte, p)
        if extra:
            m.update(extra(yte, p))
        rows.append({"model": label, "family": kind, **m, "train_s": secs, "predict_ms_per_1k": round(pred_ms * 1000, 3)})
        print(f"  [{name}] {label:28s} R2={m['r2']:.4f} MAE={m['mae']:.4f} RMSE={m['rmse']:.4f} ({secs}s)")
    return rows


PREDS: dict[str, dict[str, tuple[np.ndarray, float]]] = {}


def paired_bootstrap(task: str, y, selected: str, n: int = 1000):
    """95% CI of (other - selected) for ROC-AUC and F1 on the SAME test rows.
    If the interval contains 0 the difference is not distinguishable from noise."""
    from sklearn.metrics import f1_score, roc_auc_score
    y = np.asarray(y).astype(int)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(y), (n, len(y)))
    ps, ts = PREDS[task][selected]
    out = []
    for label, (po, to) in PREDS[task].items():
        if label == selected:
            continue
        d_auc, d_f1 = [], []
        for i in idx:
            yy = y[i]
            d_auc.append(roc_auc_score(yy, po[i]) - roc_auc_score(yy, ps[i]))
            d_f1.append(f1_score(yy, po[i] >= to) - f1_score(yy, ps[i] >= ts))
        ci = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]  # noqa: E731
        a, f = ci(d_auc), ci(d_f1)
        out.append({"model": label, "auc_diff_ci95": a, "f1_diff_ci95": f,
                    "auc_significant": not (a[0] <= 0 <= a[1]), "f1_significant": not (f[0] <= 0 <= f[1])})
    return out


def run_classification(name, candidates, Xtr, ytr, Xva, yva, Xte, yte):
    rows = []
    for label, model, kind in candidates:
        fitted, secs = timed_fit(model, Xtr, ytr)
        thr = common.best_f1_threshold(yva, fitted.predict_proba(Xva)[:, 1])
        p = fitted.predict_proba(Xte)[:, 1]
        m = common.classification_metrics(yte, p, thr)
        m.pop("confusion")
        PREDS.setdefault(name, {})[label] = (p, thr)
        rows.append({"model": label, "family": kind, **m, "train_s": secs})
        print(f"  [{name}] {label:28s} AUC={m['roc_auc']:.4f} F1={m['f1']:.4f} P={m['precision']:.3f} R={m['recall']:.3f} ({secs}s)")
    return rows


# ------------------------------------------------------------------ 1. crop yield
def crop():
    from ml.train_crop import TRAIN_END, load
    df = load()
    tr, te = df[df.year <= TRAIN_END], df[df.year > TRAIN_END]
    Xtr, Xte = crop_features(tr), crop_features(te)
    num = [c for c in Xtr.columns if c not in CROP_CAT]
    # rainfall features have a few NaNs for unmapped state-years; linear/RF need them filled
    fill = Xtr[num].median()
    Xtr_f, Xte_f = Xtr.fillna(fill), Xte.fillna(fill)
    Xtr_c, cats = common.to_categories(Xtr, CROP_CAT)
    Xte_c, _ = common.to_categories(Xte, CROP_CAT, cats)

    def ape(y, p):
        return {"median_ape_pct": float(100 * np.median(np.abs(np.exp(p) - np.exp(y)) / np.exp(y)))}

    lgb_params = dict(n_estimators=600, learning_rate=0.05, num_leaves=127, min_child_samples=20, subsample=0.8,
                      subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1)
    cands = [
        ("Linear Regression (Ridge)", make_pipeline(linear_pre(CROP_CAT, num), Ridge(alpha=1.0)), "linear"),
        ("Decision Tree", make_pipeline(tree_pre(CROP_CAT, num), DecisionTreeRegressor(min_samples_leaf=5, random_state=SEED)), "single tree"),
        ("Random Forest", make_pipeline(tree_pre(CROP_CAT, num), RandomForestRegressor(
            n_estimators=200, min_samples_leaf=2, max_features=0.5, n_jobs=-1, random_state=SEED)), "bagging ensemble"),
        ("XGBoost", make_pipeline(tree_pre(CROP_CAT, num), xgb.XGBRegressor(
            n_estimators=600, learning_rate=0.05, max_depth=10, subsample=0.8, colsample_bytree=0.8,
            tree_method="hist", random_state=SEED, n_jobs=-1)), "boosting ensemble"),
    ]
    rows = run_regression("crop", cands, Xtr_f, tr["target"], Xte_f, te["target"], ape)
    rows += run_regression("crop", [("LightGBM (selected)", lgb.LGBMRegressor(**lgb_params), "boosting ensemble")],
                           Xtr_c, tr["target"], Xte_c, te["target"], ape)
    # historical-median baseline for reference
    base = pd.Series(np.nan, index=te.index)
    for keys in (["district", "crop", "season"], ["state", "crop"], ["crop"]):
        med = tr.groupby(keys)["target"].median().rename("m")
        base = base.fillna(pd.Series(te[keys].merge(med, left_on=keys, right_index=True, how="left")["m"].values, index=te.index))
    m = common.regression_metrics(te["target"], base.fillna(tr["target"].median()))
    m.update(ape(te["target"].values, base.fillna(tr["target"].median()).values))
    rows.insert(0, {"model": "Historical median (baseline)", "family": "baseline", **m, "train_s": 0.0, "predict_ms_per_1k": 0.0})
    return {"task": "Crop yield regression", "target": "log(yield t/ha)", "split": f"train 1997-{TRAIN_END}, test {TRAIN_END + 1}-2015",
            "n_train": len(tr), "n_test": len(te), "primary_metric": "rmse", "rows": rows}


# ------------------------------------------------------------------ 2. diabetes
def diabetes():
    df = common.query("SELECT * FROM diabetes")
    train, test = train_test_split(df, test_size=0.2, stratify=df["diabetes"], random_state=SEED)
    inner, val = train_test_split(train, test_size=0.2, stratify=train["diabetes"], random_state=SEED)
    cols = DIA_CAT + DIA_NUM
    Xi, Xv, Xt = inner[cols], val[cols], test[cols]
    Xi_c, cats = common.to_categories(Xi, DIA_CAT)
    Xv_c, _ = common.to_categories(Xv, DIA_CAT, cats)
    Xt_c, _ = common.to_categories(Xt, DIA_CAT, cats)
    lin = lambda: linear_pre(DIA_CAT, DIA_NUM)  # noqa: E731
    tre = lambda: tree_pre(DIA_CAT, DIA_NUM)  # noqa: E731
    cands = [
        ("Logistic Regression", make_pipeline(lin(), LogisticRegression(max_iter=2000, class_weight="balanced")), "linear"),
        ("Gaussian Naive Bayes", make_pipeline(ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), DIA_CAT),
                                                                  ("num", StandardScaler(), DIA_NUM)]), GaussianNB()), "probabilistic"),
        ("K-Nearest Neighbours (k=25)", make_pipeline(lin(), KNeighborsClassifier(n_neighbors=25, n_jobs=-1)), "instance-based"),
        ("Decision Tree", make_pipeline(tre(), DecisionTreeClassifier(max_depth=8, random_state=SEED)), "single tree"),
        ("Random Forest", make_pipeline(tre(), RandomForestClassifier(n_estimators=300, min_samples_leaf=2, n_jobs=-1, random_state=SEED)), "bagging ensemble"),
        ("XGBoost", make_pipeline(tre(), xgb.XGBClassifier(n_estimators=400, learning_rate=0.05, max_depth=6,
                                                            tree_method="hist", random_state=SEED, n_jobs=-1)), "boosting ensemble"),
    ]
    rows = run_classification("diabetes", cands, Xi, inner["diabetes"], Xv, val["diabetes"], Xt, test["diabetes"])
    rows += run_classification("diabetes", [("LightGBM (selected)", lgb.LGBMClassifier(
        n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=30, random_state=SEED, verbose=-1), "boosting ensemble")],
        Xi_c, inner["diabetes"], Xv_c, val["diabetes"], Xt_c, test["diabetes"])
    rule = ((test["HbA1c_level"] >= 6.5) | (test["blood_glucose_level"] >= 200)).astype(float).values
    m = common.classification_metrics(test["diabetes"], rule, 0.5)
    m.pop("confusion")
    rows.insert(0, {"model": "Clinical rule (ADA, baseline)", "family": "baseline", **m, "train_s": 0.0})
    sig = paired_bootstrap("diabetes", test["diabetes"], "LightGBM (selected)", n=500)
    return {"significance_vs_selected": sig, "task": "Diabetes risk classification", "target": "diabetes (0/1), 8.8% positive",
            "split": "stratified 64/16/20 (train / threshold-validation / test)", "n_train": len(inner), "n_test": len(test),
            "primary_metric": "f1", "rows": rows}


# ------------------------------------------------------------------ 3. weather (1 day ahead)
def weather():
    raw = common.query("SELECT * FROM weather ORDER BY city, date")
    df = weather_features(raw).dropna(subset=["tmax_roll7", "target_tmax_next"])
    year = pd.to_datetime(df["date"]).dt.year
    tr, va, te = df[year <= 2020], df[year == 2021], df[year >= 2022]
    num = [c for c in WX_FEATURES if c not in WX_CAT]
    Xtr, Xva, Xte = tr[WX_FEATURES], va[WX_FEATURES], te[WX_FEATURES]
    Xtr_c, cats = common.to_categories(Xtr, WX_CAT)
    Xva_c, _ = common.to_categories(Xva, WX_CAT, cats)
    Xte_c, _ = common.to_categories(Xte, WX_CAT, cats)
    lgb_p = dict(n_estimators=600, learning_rate=0.04, num_leaves=63, min_child_samples=40, subsample=0.8,
                 subsample_freq=1, colsample_bytree=0.8, random_state=SEED, verbose=-1)

    # temperature regression
    tcands = [
        ("Linear Regression", make_pipeline(linear_pre(WX_CAT, num), LinearRegression()), "linear"),
        ("Decision Tree", make_pipeline(tree_pre(WX_CAT, num), DecisionTreeRegressor(min_samples_leaf=20, random_state=SEED)), "single tree"),
        ("Random Forest", make_pipeline(tree_pre(WX_CAT, num), RandomForestRegressor(
            n_estimators=200, min_samples_leaf=5, max_features=0.5, n_jobs=-1, random_state=SEED)), "bagging ensemble"),
        ("XGBoost", make_pipeline(tree_pre(WX_CAT, num), xgb.XGBRegressor(
            n_estimators=600, learning_rate=0.04, max_depth=7, subsample=0.8, colsample_bytree=0.8,
            tree_method="hist", random_state=SEED, n_jobs=-1)), "boosting ensemble"),
    ]
    trows = run_regression("weather-temp", tcands, Xtr, tr["target_tmax_next"], Xte, te["target_tmax_next"])
    trows += run_regression("weather-temp", [("LightGBM (selected)", lgb.LGBMRegressor(**lgb_p), "boosting ensemble")],
                            Xtr_c, tr["target_tmax_next"], Xte_c, te["target_tmax_next"])
    m = common.regression_metrics(te["target_tmax_next"], te["temperature_2m_max"])
    trows.insert(0, {"model": "Persistence: tomorrow = today (baseline)", "family": "baseline", **m, "train_s": 0.0, "predict_ms_per_1k": 0.0})

    # rain classification
    rcands = [
        ("Logistic Regression", make_pipeline(linear_pre(WX_CAT, num), LogisticRegression(max_iter=3000)), "linear"),
        ("Decision Tree", make_pipeline(tree_pre(WX_CAT, num), DecisionTreeClassifier(max_depth=10, min_samples_leaf=20, random_state=SEED)), "single tree"),
        ("Random Forest", make_pipeline(tree_pre(WX_CAT, num), RandomForestClassifier(
            n_estimators=300, min_samples_leaf=5, n_jobs=-1, random_state=SEED)), "bagging ensemble"),
        ("XGBoost", make_pipeline(tree_pre(WX_CAT, num), xgb.XGBClassifier(
            n_estimators=600, learning_rate=0.04, max_depth=7, subsample=0.8, colsample_bytree=0.8,
            tree_method="hist", random_state=SEED, n_jobs=-1)), "boosting ensemble"),
    ]
    rrows = run_classification("weather-rain", rcands, Xtr, tr["target_rain_next"], Xva, va["target_rain_next"],
                               Xte, te["target_rain_next"].astype(int))
    rrows += run_classification("weather-rain", [("LightGBM (selected)", lgb.LGBMClassifier(**lgb_p), "boosting ensemble")],
                                Xtr_c, tr["target_rain_next"], Xva_c, va["target_rain_next"], Xte_c, te["target_rain_next"].astype(int))
    m = common.classification_metrics(te["target_rain_next"].astype(int), (te["precipitation_sum"] >= 2.5).astype(float), 0.5)
    m.pop("confusion")
    rrows.insert(0, {"model": "Persistence: rain if it rained today (baseline)", "family": "baseline", **m, "train_s": 0.0})
    split = "train 2000-2020, validation 2021, test 2022-2024"
    return [{"task": "Weather: max temperature tomorrow", "target": "temperature_2m_max (t+1), deg C", "split": split,
             "n_train": len(tr), "n_test": len(te), "primary_metric": "mae", "rows": trows},
            {"significance_vs_selected": paired_bootstrap("weather-rain", te["target_rain_next"], "LightGBM (selected)", n=300),
             "task": "Weather: rain tomorrow", "target": "precipitation(t+1) >= 2.5 mm, 22% positive", "split": split,
             "n_train": len(tr), "n_test": len(te), "primary_metric": "f1", "rows": rrows}]


# ------------------------------------------------------------------ 4. suicides
def suicides():
    panel = suicide_panel(common.query("SELECT * FROM suicides_headline")).dropna(subset=["lag1", "lag2"])
    tr, te = panel[panel.year <= 2009], panel[panel.year > 2009]
    Xtr, Xte = tr[SUI_CAT + SUI_NUM], te[SUI_CAT + SUI_NUM]
    Xtr_c, cats = common.to_categories(Xtr, SUI_CAT)
    Xte_c, _ = common.to_categories(Xte, SUI_CAT, cats)
    dtr = tr["total"] - tr["lag1"]  # models learn the year-on-year change

    def delta(model, X, Xt):
        model.fit(X, dtr)
        return np.clip(te["lag1"].values + model.predict(Xt), 0, None)

    y = te["total"].values
    rows = []

    def add(label, kind, pred, secs=0.0):
        m = common.regression_metrics(y, pred)
        rows.append({"model": label, "family": kind, **m, "train_s": secs})
        print(f"  [suicides] {label:34s} MAE={m['mae']:.2f} RMSE={m['rmse']:.2f} WAPE={m['wape_pct']:.2f}%")

    add("Persistence: same as last year (baseline)", "baseline", te["lag1"].values)
    grid = np.linspace(0, 1, 21)
    w = float(grid[np.argmin([np.abs(g * tr.lag1 + (1 - g) * tr.lag2 - tr.total).mean() for g in grid])])
    add(f"Weighted persistence, w={w:.2f} (selected)", "statistical", (w * te.lag1 + (1 - w) * te.lag2).values)
    for label, kind, model, X, Xt in [
        ("Linear Regression (on lags)", "linear", make_pipeline(linear_pre(SUI_CAT, SUI_NUM), Ridge(alpha=1.0)), Xtr, Xte),
        ("Decision Tree (change)", "single tree", make_pipeline(tree_pre(SUI_CAT, SUI_NUM), DecisionTreeRegressor(min_samples_leaf=20, random_state=SEED)), Xtr, Xte),
        ("Random Forest (change)", "bagging ensemble", make_pipeline(tree_pre(SUI_CAT, SUI_NUM), RandomForestRegressor(
            n_estimators=300, min_samples_leaf=5, n_jobs=-1, random_state=SEED)), Xtr, Xte),
        ("XGBoost (change)", "boosting ensemble", make_pipeline(tree_pre(SUI_CAT, SUI_NUM), xgb.XGBRegressor(
            n_estimators=300, learning_rate=0.03, max_depth=4, objective="reg:absoluteerror", random_state=SEED)), Xtr, Xte),
        ("LightGBM (change)", "boosting ensemble", lgb.LGBMRegressor(objective="l1", n_estimators=300, learning_rate=0.03,
                                                                    num_leaves=15, min_child_samples=20, random_state=SEED, verbose=-1), Xtr_c, Xte_c),
    ]:
        t = time.perf_counter()
        if label.startswith("Linear"):
            model.fit(X, tr["total"])
            pred = np.clip(model.predict(Xt), 0, None)
        else:
            pred = delta(model, X, Xt)
        add(label, kind, pred, round(time.perf_counter() - t, 2))
    return {"task": "Suicide counts, one year ahead", "target": "total per State x Gender x Age group",
            "split": "train 2003-2009, test 2010-2012", "n_train": len(tr), "n_test": len(te), "primary_metric": "mae", "rows": rows}


def main():
    t0 = time.perf_counter()
    results = []
    for fn in (crop, diabetes, weather, suicides):
        print(f"=== {fn.__name__} ===")
        r = fn()
        results.extend(r if isinstance(r, list) else [r])
    out = {"generated_seconds": round(time.perf_counter() - t0, 1), "environment": {**common.environment(), "xgboost": xgb.__version__},
           "tasks": results}
    (common.REPORTS_DIR / "model_comparison.json").write_text(json.dumps(out, indent=2, default=float))
    print(f"saved model_comparison.json ({out['generated_seconds']}s)")


if __name__ == "__main__":
    main()
