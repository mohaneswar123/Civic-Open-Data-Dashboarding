"""Classification view of every prediction task:  python -m ml.classify

Numeric targets are turned into ordered classes (e.g. Low / Medium / High), then several
classifiers are trained on the SAME split, compared, and one is selected on the
validation set. The admin "About models" page reads the reports written here, and
predictions made there return only the class label.

Class definitions (thresholds are learned from the TRAINING split only):
  crop_yield       Low / Medium / High  = bottom / middle / top third of yields for that crop
  diabetes         Low risk / High risk = the dataset's own 0/1 diabetes label
  weather_temp     Low / Medium / High  = tomorrow's max temperature vs. the normal third for that city and month
  weather_rain     No rain / Light / Moderate to heavy = IMD categories (< 2.5, 2.5-15.5, >= 15.6 mm)
  suicides         Low / Medium / High  = bottom / middle / top third of yearly counts per group
"""
from __future__ import annotations

import json
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn import metrics as skm
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier
from sklearn.utils.class_weight import compute_sample_weight

from ml import common
from ml.features import (CROP_CAT, DIA_CAT, DIA_NUM, SUI_CAT, SUI_NUM, WX_CAT, WX_FEATURES, crop_features,
                         suicide_panel, weather_features)

SEED = common.SEED
LMH = ["Low", "Medium", "High"]


# ------------------------------------------------------------------ tasks
def tercile(values, q1, q2):
    return np.where(values < q1, 0, np.where(values < q2, 1, 2))


def task_crop():
    from ml.train_crop import load
    df = load()
    q = df[df.year <= 2009].groupby("crop")["target"].quantile([1 / 3, 2 / 3]).unstack()
    q.columns = ["q1", "q2"]
    df = df[df["crop"].isin(q.index)].reset_index(drop=True)  # a crop never seen in training has no thresholds
    df["y"] = tercile(df["target"].values, df["crop"].map(q["q1"]).values, df["crop"].map(q["q2"]).values)
    X = crop_features(df)
    splits = {"train": df.year <= 2009, "validation": df.year == 2010, "test": df.year > 2010}
    return {
        "task": "crop_yield", "dataset": "crop", "title": "Crop yield class",
        "target": "Yield (production / area) of a crop in a district, season and year",
        "class_names": LMH,
        "class_rule": "Low, Medium and High are the bottom, middle and top third of yields for that same crop in the training years, so a class means 'low/high for this crop', not across crops.",
        "split": "time-based: train 1997-2009, validation 2010, test 2011-2015",
        "cat": CROP_CAT, "num": [c for c in X.columns if c not in CROP_CAT], "X": X, "y": df["y"], "splits": splits,
        "note": "District has about 640 values; models that handle categories natively have an advantage.",
    }


def task_diabetes():
    df = common.query("SELECT * FROM diabetes")
    idx_tr, idx_te = train_test_split(df.index, test_size=0.2, stratify=df["diabetes"], random_state=SEED)
    idx_tr, idx_va = train_test_split(idx_tr, test_size=0.2, stratify=df.loc[idx_tr, "diabetes"], random_state=SEED)
    split = pd.Series("train", index=df.index)
    split[idx_va], split[idx_te] = "validation", "test"
    return {
        "task": "diabetes", "dataset": "diabetes", "title": "Diabetes risk class",
        "target": "Whether the person has diabetes (0/1 in the source)",
        "class_names": ["Low risk", "High risk"],
        "class_rule": "High risk = records labelled diabetic in the source; Low risk = all others. Only 8.8% are High risk, so accuracy alone is misleading; macro-F1 is used.",
        "split": "stratified random: 64% train, 16% validation, 20% test",
        "cat": DIA_CAT, "num": DIA_NUM, "X": df[DIA_CAT + DIA_NUM], "y": df["diabetes"].astype(int),
        "splits": {k: split == k for k in ("train", "validation", "test")},
        "note": "Duplicates were removed in the pipeline so no record sits in two splits.",
    }


def _weather_frame():
    raw = common.query("SELECT * FROM weather ORDER BY city, date")
    feats = weather_features(raw)
    feats["precip_next"] = feats.groupby("city")["precipitation_sum"].shift(-1)
    feats = feats.dropna(subset=["tmax_roll7", "target_tmax_next", "precip_next"]).reset_index(drop=True)
    year = pd.to_datetime(feats["date"]).dt.year
    splits = {"train": year <= 2020, "validation": year == 2021, "test": year >= 2022}
    return feats, splits


def task_weather_temp():
    feats, splits = _weather_frame()
    tr = feats[splits["train"]]
    q = tr.groupby(["city", "month"])["target_tmax_next"].quantile([1 / 3, 2 / 3]).unstack()
    q.columns = ["q1", "q2"]
    m = feats[["city", "month"]].merge(q, left_on=["city", "month"], right_index=True, how="left")
    y = pd.Series(tercile(feats["target_tmax_next"].values, m["q1"].values, m["q2"].values), index=feats.index)
    return {
        "task": "weather_temp", "dataset": "weather", "title": "Tomorrow's temperature class",
        "target": "Tomorrow's maximum temperature in the city",
        "class_names": LMH,
        "class_rule": "Low, Medium and High = cooler than usual, normal, or hotter than usual: the bottom, middle and top third of maximum temperatures for that city and month in the training years.",
        "split": "time-based: train 2000-2020, validation 2021, test 2022-2024",
        "cat": WX_CAT, "num": [c for c in WX_FEATURES if c not in WX_CAT], "X": feats[WX_FEATURES], "y": y,
        "splits": splits, "note": "Classes are relative to the season, so 'High' in January and in May mean different temperatures.",
    }


def task_weather_rain():
    feats, splits = _weather_frame()
    p = feats["precip_next"].values
    y = pd.Series(np.where(p < 2.5, 0, np.where(p < 15.6, 1, 2)), index=feats.index)
    return {
        "task": "weather_rain", "dataset": "weather", "title": "Tomorrow's rain class",
        "target": "Tomorrow's rainfall in the city",
        "class_names": ["No rain", "Light", "Moderate to heavy"],
        "class_rule": "India Meteorological Department categories for a 24-hour total: No rain (under 2.5 mm), Light (2.5 to 15.5 mm), Moderate to heavy (15.6 mm or more).",
        "split": "time-based: train 2000-2020, validation 2021, test 2022-2024",
        "cat": WX_CAT, "num": [c for c in WX_FEATURES if c not in WX_CAT], "X": feats[WX_FEATURES], "y": y,
        "splits": splits, "note": "Most days are dry, so the rare heavy-rain class is the hard one.",
    }


def task_suicides():
    panel = suicide_panel(common.query("SELECT * FROM suicides_headline")).dropna(subset=["lag1", "lag2"]).reset_index(drop=True)
    tr = panel.year <= 2008
    q1, q2 = panel.loc[tr, "total"].quantile([1 / 3, 2 / 3])
    y = pd.Series(tercile(panel["total"].values, q1, q2), index=panel.index)
    return {
        "task": "suicides", "dataset": "suicides", "title": "Suicide count class, next year",
        "target": "Recorded suicides next year for a state, gender and age group",
        "class_names": LMH,
        "class_rule": "Low, Medium and High = the bottom, middle and top third of yearly counts across all state-gender-age groups in the training years.",
        "split": "time-based: train 2003-2008, validation 2009, test 2010-2012",
        "cat": SUI_CAT, "num": SUI_NUM, "X": panel[SUI_CAT + SUI_NUM], "y": y,
        "splits": {"train": tr, "validation": panel.year == 2009, "test": panel.year >= 2010},
        "note": "Last year's count already decides the class for most groups, so every model scores high here.",
    }


TASKS = [task_crop, task_diabetes, task_weather_temp, task_weather_rain, task_suicides]


# ------------------------------------------------------------------ models
def linear_pre(cat, num, dense=False):
    return ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=not dense), cat),
                              ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num)])


def tree_pre(cat, num):
    return ColumnTransformer([("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), cat),
                              ("num", SimpleImputer(strategy="median"), num)])


def candidates(t):
    cat, num, k = t["cat"], t["num"], len(t["class_names"])
    big = t["task"] == "crop_yield"
    out = [
        ("Logistic Regression", "linear", "sk", make_pipeline(linear_pre(cat, num), LogisticRegression(max_iter=3000, class_weight="balanced"))),
        ("Decision Tree", "single tree", "sk", make_pipeline(tree_pre(cat, num), DecisionTreeClassifier(
            max_depth=12, min_samples_leaf=20, class_weight="balanced", random_state=SEED))),
        ("Random Forest", "bagging ensemble", "sk", make_pipeline(tree_pre(cat, num), RandomForestClassifier(
            n_estimators=100 if big else 200, max_depth=16 if big else 20, min_samples_leaf=20 if big else 10,
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEED))),
        ("XGBoost", "boosting ensemble", "sk_w", make_pipeline(tree_pre(cat, num), xgb.XGBClassifier(
            n_estimators=400, learning_rate=0.05, max_depth=7, subsample=0.8, colsample_bytree=0.8,
            tree_method="hist", random_state=SEED, n_jobs=-1))),
        ("LightGBM", "boosting ensemble", "lgb", lgb.LGBMClassifier(
            n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=30, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.8, class_weight="balanced", random_state=SEED, verbose=-1)),
    ]
    if not big:  # dense one-hot is too large for ~640 districts
        out.insert(1, ("Naive Bayes", "probabilistic", "sk", make_pipeline(linear_pre(cat, num, dense=True), GaussianNB())))
    return out


def prepare(kind, X, cats, cat_cols):
    if kind == "lgb":
        return common.to_categories(X, cat_cols, cats)[0]
    X = X.copy()
    for c in cat_cols:
        X[c] = X[c].astype(str)
    return X


def predict_proba(entry: dict, X: pd.DataFrame, cats: dict, cat_cols: list) -> np.ndarray:
    """Used by the API: class probabilities from one stored model."""
    return entry["est"].predict_proba(prepare(entry["kind"], X, cats, cat_cols))


# ------------------------------------------------------------------ evaluation
def scores(y, proba, k):
    pred = proba.argmax(axis=1)
    p, r, f, _ = skm.precision_recall_fscore_support(y, pred, labels=list(range(k)), zero_division=0)
    try:
        auc = skm.roc_auc_score(y, proba[:, 1]) if k == 2 else skm.roc_auc_score(y, proba, multi_class="ovr", average="macro", labels=list(range(k)))
    except ValueError:
        auc = None
    return {
        "accuracy": float(skm.accuracy_score(y, pred)), "balanced_accuracy": float(skm.balanced_accuracy_score(y, pred)),
        "macro_precision": float(p.mean()), "macro_recall": float(r.mean()), "macro_f1": float(f.mean()),
        "roc_auc": None if auc is None else float(auc),
        "per_class": [{"precision": float(a), "recall": float(b), "f1": float(c)} for a, b, c in zip(p, r, f)],
        "confusion": skm.confusion_matrix(y, pred, labels=list(range(k))).tolist(),
    }


def reasons(models: list, sel: dict, class_names: list) -> None:
    """Plain-language 'why selected / why not' for every model, from the measured numbers."""
    for m in models:
        why = []
        worst = int(np.argmin([c["recall"] for c in m["test"]["per_class"]]))
        gap = m["train_f1"] - m["validation"]["macro_f1"]
        if m is sel:
            why.append(f"Highest validation macro-F1 ({m['validation']['macro_f1']:.3f}) of all {len(models)} models.")
            why.append(f"On the unseen test set: macro-F1 {m['test']['macro_f1']:.3f}, accuracy {m['test']['accuracy']:.3f}.")
            why.append("Generalises well: training and validation scores are close." if gap < 0.08 else
                       f"Some overfitting (train {m['train_f1']:.3f} vs validation {m['validation']['macro_f1']:.3f}), but it still scores best on unseen data.")
            m["verdict"] = "Selected"
        else:
            d = sel["validation"]["macro_f1"] - m["validation"]["macro_f1"]
            if d < 0.005:
                why.append(f"Practically tied with {sel['model']} on validation (macro-F1 {m['validation']['macro_f1']:.3f} vs {sel['validation']['macro_f1']:.3f}); not chosen only because it scored marginally lower.")
            else:
                why.append(f"Lower validation macro-F1 than {sel['model']} ({m['validation']['macro_f1']:.3f} vs {sel['validation']['macro_f1']:.3f}).")
            if gap > 0.10:
                why.append(f"Overfits: training macro-F1 {m['train_f1']:.3f} but validation only {m['validation']['macro_f1']:.3f}.")
            if sel["train_s"] > 0 and m["train_s"] > 3 * sel["train_s"] and m["train_s"] > 2:
                why.append(f"Slower to train ({m['train_s']:.1f} s vs {sel['train_s']:.1f} s).")
            m["verdict"] = "Not selected"
        why.append(f"Weakest class: '{class_names[worst]}' (recall {m['test']['per_class'][worst]['recall']:.2f}).")
        m["reasons"] = why


def run_task(t: dict) -> None:
    started = time.perf_counter()
    k = len(t["class_names"])
    X, y, sp = t["X"], t["y"].astype(int), t["splits"]
    Xtr, Xva, Xte = X[sp["train"]], X[sp["validation"]], X[sp["test"]]
    ytr, yva, yte = y[sp["train"]].values, y[sp["validation"]].values, y[sp["test"]].values
    cats = common.to_categories(Xtr, t["cat"])[1]
    models, store = [], {}
    for name, family, kind, est in candidates(t):
        Xa = prepare("lgb" if kind == "lgb" else "sk", Xtr, cats, t["cat"])
        t0 = time.perf_counter()
        if kind == "sk_w":
            est.fit(Xa, ytr, xgbclassifier__sample_weight=compute_sample_weight("balanced", ytr))
        else:
            est.fit(Xa, ytr)
        secs = round(time.perf_counter() - t0, 2)
        entry = {"kind": "lgb" if kind == "lgb" else "sk", "est": est}
        store[name] = entry
        pv, pt = (predict_proba(entry, Xs, cats, t["cat"]) for Xs in (Xva, Xte))
        ptr = predict_proba(entry, Xtr, cats, t["cat"])
        models.append({"model": name, "family": family, "train_s": secs,
                       "train_f1": float(skm.f1_score(ytr, ptr.argmax(axis=1), average="macro")),
                       "validation": {k_: v for k_, v in scores(yva, pv, k).items() if k_ not in ("per_class", "confusion")},
                       "test": scores(yte, pt, k)})
        print(f"  [{t['task']}] {name:20s} val F1={models[-1]['validation']['macro_f1']:.4f} test F1={models[-1]['test']['macro_f1']:.4f} acc={models[-1]['test']['accuracy']:.4f} ({secs}s)")
    sel = max(models, key=lambda m: m["validation"]["macro_f1"])
    reasons(models, sel, t["class_names"])
    dist = {s: np.bincount(y[sp[s]].values, minlength=k).tolist() for s in ("train", "validation", "test")}
    report = {
        "task": t["task"], "dataset": t["dataset"], "title": t["title"], "target": t["target"],
        "class_names": t["class_names"], "class_rule": t["class_rule"], "split": t["split"], "note": t["note"],
        "features": {"categorical": t["cat"], "numeric": t["num"]},
        "rows": {s: int(sp[s].sum()) for s in ("train", "validation", "test")}, "class_distribution": dist,
        "selection_rule": "Highest macro-F1 on the validation split (macro-F1 weighs every class equally, so a model cannot win by ignoring a rare class).",
        "selected": sel["model"], "models": models,
    }
    common.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (common.REPORTS_DIR / f"cls_{t['task']}.json").write_text(json.dumps(report, indent=2))
    joblib.dump({"task": t["task"], "class_names": t["class_names"], "cat": t["cat"], "num": t["num"],
                 "categories": cats, "models": store, "selected": sel["model"]},
                common.MODELS_DIR / f"cls_{t['task']}.joblib", compress=3)
    print(f"  [{t['task']}] selected {sel['model']} ({time.perf_counter() - started:.0f}s)")


def main():
    for fn in TASKS:
        print(f"=== {fn.__name__} ===")
        run_task(fn())


if __name__ == "__main__":
    main()
