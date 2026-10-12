"""Shared helpers for training: data access, categorical handling, metrics, persistence."""
from __future__ import annotations

import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import sklearn
import lightgbm
from sklearn import metrics as skm

from pipeline import config

SEED = 42
MODELS_DIR = config.ARTIFACTS / "models"
REPORTS_DIR = config.ARTIFACTS / "reports"


def query(sql: str) -> pd.DataFrame:
    with duckdb.connect(str(config.DB_PATH), read_only=True) as con:
        return con.execute(sql).df()


def to_categories(df: pd.DataFrame, cat_cols: list[str], categories: dict | None = None):
    """Cast to pandas Categorical with a FIXED category list (saved with the model),
    so inference encodes values exactly like training. Unseen values become NaN."""
    df = df.copy()
    categories = categories or {c: sorted(df[c].dropna().astype(str).unique().tolist()) for c in cat_cols}
    for c in cat_cols:
        df[c] = pd.Categorical(df[c].astype(str), categories=categories[c])
    return df, categories


def regression_metrics(y_true, y_pred) -> dict:
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    err = y_pred - y_true
    denom = np.abs(y_true).sum()
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "r2": float(skm.r2_score(y_true, y_pred)),
        "wape_pct": float(100 * np.abs(err).sum() / denom) if denom else None,
        "bias": float(np.mean(err)),
        "n": int(len(y_true)),
    }


def classification_metrics(y_true, proba, threshold: float) -> dict:
    y_true = np.asarray(y_true).astype(int)
    pred = (np.asarray(proba) >= threshold).astype(int)
    tn, fp, fn, tp = skm.confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "roc_auc": float(skm.roc_auc_score(y_true, proba)) if len(set(y_true)) > 1 else None,
        "pr_auc": float(skm.average_precision_score(y_true, proba)),
        "brier": float(skm.brier_score_loss(y_true, np.clip(proba, 0, 1))),
        "accuracy": float(skm.accuracy_score(y_true, pred)),
        "precision": float(skm.precision_score(y_true, pred, zero_division=0)),
        "recall": float(skm.recall_score(y_true, pred, zero_division=0)),
        "f1": float(skm.f1_score(y_true, pred, zero_division=0)),
        "threshold": float(threshold),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "positive_rate": float(y_true.mean()),
        "n": int(len(y_true)),
    }


def best_f1_threshold(y_true, proba) -> float:
    p, r, t = skm.precision_recall_curve(y_true, proba)
    f1 = 2 * p * r / np.clip(p + r, 1e-9, None)
    return float(t[np.nanargmax(f1[:-1])])


def bootstrap_ci(y_true, y_pred, metric, n: int = 300, seed: int = SEED) -> list[float]:
    """95% bootstrap CI for a metric(y_true, y_pred) - uncertainty for the honesty panel."""
    rng = np.random.default_rng(seed)
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(y_true), len(y_true))
        try:
            vals.append(metric(y_true[idx], y_pred[idx]))
        except ValueError:
            continue
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def feature_importance(model, names: list[str]) -> list[dict]:
    gain = model.booster_.feature_importance(importance_type="gain")
    total = gain.sum() or 1
    out = [{"feature": n, "importance": round(float(g / total), 4)} for n, g in zip(names, gain)]
    return sorted(out, key=lambda x: -x["importance"])


def environment() -> dict:
    return {"python": platform.python_version(), "sklearn": sklearn.__version__,
            "lightgbm": lightgbm.__version__, "pandas": pd.__version__, "seed": SEED}


def data_version() -> dict:
    """Link the model to the exact pipeline output it was trained on (lineage)."""
    lineage = json.loads((REPORTS_DIR / "lineage.json").read_text())
    return {k: v["source"]["sha256"][:12] for k, v in lineage.items()}


def save(name: str, bundle: dict, report: dict, started: float) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = {"model": name, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "train_seconds": round(time.perf_counter() - started, 2), "environment": environment(),
              "data_version": data_version(), **report}
    bundle["report_summary"] = {k: report[k] for k in ("trained_at", "data_version")}
    joblib.dump(bundle, MODELS_DIR / f"{name}.joblib", compress=3)
    (REPORTS_DIR / f"metrics_{name}.json").write_text(json.dumps(report, indent=2, default=float))
    print(f"[train] saved {name} ({report['train_seconds']}s)")
