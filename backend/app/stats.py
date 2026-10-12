"""Small, transparent statistics used by the advanced dashboards.

Every function returns the sample size alongside the estimate so the UI can
show how much evidence sits behind each number.
"""
from __future__ import annotations

import numpy as np
from scipy import stats as st


def trend(x, y) -> dict:
    """OLS slope with p-value and 95% CI. Returns nulls when n < 5."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    if len(x) < 5 or np.ptp(x) == 0:
        return {"slope": None, "p_value": None, "ci95": None, "n": int(len(x)), "significant": False}
    r = st.linregress(x, y)
    t = st.t.ppf(0.975, len(x) - 2)
    return {"slope": float(r.slope), "p_value": float(r.pvalue), "r2": float(r.rvalue ** 2),
            "ci95": [float(r.slope - t * r.stderr), float(r.slope + t * r.stderr)],
            "n": int(len(x)), "significant": bool(r.pvalue < 0.05)}


def spearman(x, y, n_boot: int = 500, seed: int = 42) -> dict:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 8:
        return {"rho": None, "p_value": None, "ci95": None, "n": int(n), "strength": "insufficient data"}
    rho, p = st.spearmanr(x, y)
    # Vectorised bootstrap: rank every resample at once, then a row-wise Pearson on ranks.
    idx = np.random.default_rng(seed).integers(0, n, (n_boot, n))
    rx, ry = st.rankdata(x[idx], axis=1), st.rankdata(y[idx], axis=1)
    rx -= rx.mean(axis=1, keepdims=True)
    ry -= ry.mean(axis=1, keepdims=True)
    denom = np.sqrt((rx ** 2).sum(axis=1) * (ry ** 2).sum(axis=1))
    ok = denom > 0
    boots = (rx * ry).sum(axis=1)[ok] / denom[ok]
    a = abs(rho)
    strength = "negligible" if a < 0.1 else "weak" if a < 0.3 else "moderate" if a < 0.5 else "strong"
    return {"rho": float(rho), "p_value": float(p), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "n": int(n), "strength": strength, "significant": bool(p < 0.05)}


def gini(values) -> float | None:
    v = np.sort(np.asarray([x for x in values if x is not None and not np.isnan(x) and x >= 0], float))
    if len(v) < 2 or v.sum() == 0:
        return None
    n = len(v)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(v) / (n * v.sum()))


def cv(values) -> float | None:
    v = np.asarray(values, float)
    v = v[~np.isnan(v)]
    return float(v.std(ddof=1) / v.mean()) if len(v) > 1 and v.mean() else None


def odds_ratio(a: int, b: int, c: int, d: int) -> dict:
    """2x2 table: exposed (a=cases, b=non-cases), unexposed (c=cases, d=non-cases). Woolf CI, 0.5 correction."""
    if min(a, b, c, d) == 0:
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    orr = (a * d) / (b * c)
    se = np.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return {"odds_ratio": float(orr), "ci95": [float(np.exp(np.log(orr) - 1.96 * se)), float(np.exp(np.log(orr) + 1.96 * se))]}
