"""Reusable data-quality engine.

A Rule is a named predicate that marks *invalid* rows. Rules have an action:
  - "quarantine": the row is removed from the clean table and written to the
    quarantine table together with the reason (never silently dropped).
  - "flag": the row stays, but a boolean flag column is added so downstream
    charts / models can exclude or annotate it.

Every run returns a report with counts per rule and per partition, so a
defect that is small globally but large in one state/city is still visible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass
class Rule:
    name: str
    description: str
    check: Callable[[pd.DataFrame], pd.Series]  # True where the row is INVALID
    action: str = "quarantine"  # or "flag"


def apply_rules(df: pd.DataFrame, rules: list[Rule], partition_col: str | None = None):
    """Apply rules in order. Returns (clean_df, quarantine_df, rule_report)."""
    df = df.copy()
    quarantined = []
    report = []
    for rule in rules:
        mask = rule.check(df).fillna(False).astype(bool)
        n = int(mask.sum())
        entry = {"rule": rule.name, "description": rule.description, "action": rule.action, "rows": n}
        if partition_col and n:
            by_part = df.loc[mask, partition_col].value_counts().head(10)
            entry["top_partitions"] = {str(k): int(v) for k, v in by_part.items()}
        report.append(entry)
        if rule.action == "quarantine":
            if n:
                q = df[mask].copy()
                q["_quarantine_reason"] = rule.name
                quarantined.append(q)
            df = df[~mask]
        else:
            df[f"flag_{rule.name}"] = mask
    quarantine_df = pd.concat(quarantined, ignore_index=True) if quarantined else pd.DataFrame()
    return df.reset_index(drop=True), quarantine_df, report


def partition_health(df: pd.DataFrame, partition_col: str, expected_rows: int | None = None,
                     value_col: str | None = None, flag_cols: list[str] | None = None) -> list[dict]:
    """Per-partition quality indicators (guards against 'globally fine, locally broken')."""
    out = []
    flag_cols = flag_cols or []
    for key, g in df.groupby(partition_col):
        row = {"partition": str(key), "rows": int(len(g))}
        if expected_rows:
            row["completeness_pct"] = round(100 * len(g) / expected_rows, 2)
        if value_col:
            row["null_pct"] = round(100 * g[value_col].isna().mean(), 2)
        for c in flag_cols:
            row[f"{c}_pct"] = round(100 * g[c].mean(), 2)
        out.append(row)
    return out
