"""Diabetes risk classifier (standalone public-health module).

Target    : diabetes (0/1), ~8.8% positive
Split     : stratified random 80/20 (records have no time or geography); duplicates
            were removed in the pipeline so no record appears in both splits
Baselines : clinical rule (HbA1c >= 6.5 or glucose >= 200, ADA criteria) and logistic regression
Candidate : LightGBM; decision threshold chosen by 5-fold CV on the TRAIN split only
"""
import time

import lightgbm as lgb
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml import common
from ml.features import DIA_CAT, DIA_NUM


def main():
    t0 = time.perf_counter()
    df = common.query("SELECT * FROM diabetes")
    train, test = train_test_split(df, test_size=0.2, stratify=df["diabetes"], random_state=common.SEED)
    ytr, yte = train["diabetes"].values, test["diabetes"].values

    # Baseline 1: clinical rule - no learning at all.
    rule = ((test["HbA1c_level"] >= 6.5) | (test["blood_glucose_level"] >= 200)).astype(float).values

    # Baseline 2: logistic regression.
    logit = make_pipeline(
        ColumnTransformer([("num", StandardScaler(), DIA_NUM),
                           ("cat", OneHotEncoder(handle_unknown="ignore"), DIA_CAT)]),
        LogisticRegression(max_iter=2000, class_weight="balanced"))
    logit.fit(train[DIA_NUM + DIA_CAT], ytr)
    p_logit = logit.predict_proba(test[DIA_NUM + DIA_CAT])[:, 1]

    # Candidate: LightGBM.
    Xtr, cats = common.to_categories(train[DIA_CAT + DIA_NUM], DIA_CAT)
    Xte, _ = common.to_categories(test[DIA_CAT + DIA_NUM], DIA_CAT, cats)
    params = dict(n_estimators=400, learning_rate=0.05, num_leaves=31, min_child_samples=30,
                  random_state=common.SEED, verbose=-1)
    cv = StratifiedKFold(5, shuffle=True, random_state=common.SEED)
    oof = cross_val_predict(lgb.LGBMClassifier(**params), Xtr, ytr, cv=cv, method="predict_proba")[:, 1]
    threshold = common.best_f1_threshold(ytr, oof)
    oof_logit = cross_val_predict(logit, train[DIA_NUM + DIA_CAT], ytr, cv=cv, method="predict_proba")[:, 1]
    threshold_logit = common.best_f1_threshold(ytr, oof_logit)

    model = lgb.LGBMClassifier(**params).fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]

    results = {
        "baseline_clinical_rule": common.classification_metrics(yte, rule, 0.5),
        "baseline_logistic_regression": common.classification_metrics(yte, p_logit, threshold_logit),
        "lightgbm": common.classification_metrics(yte, p, threshold),
    }
    results["lightgbm"]["roc_auc_ci95"] = common.bootstrap_ci(
        yte, p, lambda a, b: __import__("sklearn.metrics").metrics.roc_auc_score(a, b))

    # Condition-wise recall: a model can look great overall and still miss a subgroup.
    test = test.assign(p=p, pred=(p >= threshold).astype(int))
    by_group = []
    for col in ["gender", "age_band", "bmi_class"]:
        for k, g in test.groupby(col):
            pos = g[g.diabetes == 1]
            by_group.append({"dimension": col, "group": k, "n": int(len(g)), "positives": int(len(pos)),
                             "recall": float(pos["pred"].mean()) if len(pos) else None,
                             "precision": float(g.loc[g.pred == 1, "diabetes"].mean()) if g.pred.sum() else None})

    # Calibration curve (10 bins) - are predicted probabilities trustworthy?
    bins = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(p, bins) - 1, 0, 9)
    calib = [{"bin": f"{bins[i]:.1f}-{bins[i + 1]:.1f}", "mean_pred": float(p[idx == i].mean()),
              "observed": float(yte[idx == i].mean()), "n": int((idx == i).sum())}
             for i in range(10) if (idx == i).any()]

    bundle = {"model": model, "categories": cats, "features": DIA_CAT + DIA_NUM, "threshold": threshold,
              "base_rate": float(df["diabetes"].mean())}
    report = {
        "title": "Diabetes risk - LightGBM classifier",
        "task": "binary classification", "target": "diabetes (0/1)",
        "split": {"type": "stratified random 80/20", "train_rows": int(len(train)), "test_rows": int(len(test)),
                  "threshold_selection": "max F1 on 5-fold out-of-fold predictions (train only)"},
        "results": results, "selected": "lightgbm",
        "by_condition": by_group, "calibration": calib,
        "feature_importance": common.feature_importance(model, DIA_CAT + DIA_NUM),
        "limitations": ["Dataset is not India-specific; population and collection method are not documented",
                        "Accuracy is misleading here: predicting 'no diabetes' for everyone is ~91% accurate",
                        "Screening aid for education only - NOT a medical diagnosis"],
    }
    common.save("diabetes_risk", bundle, report, t0)
    for k, v in results.items():
        print(f"  {k:30s} AUC={v['roc_auc']:.4f} F1={v['f1']:.4f} P={v['precision']:.3f} R={v['recall']:.3f}")


if __name__ == "__main__":
    main()
