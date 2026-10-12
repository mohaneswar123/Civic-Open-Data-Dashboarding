"""Clean the IMD sub-division rainfall dataset and derive state-level rainfall.

The state-level table is used ONLY by the crop module (crop <-> rainfall is the
single cross-dataset relationship in this project).
"""
import pandas as pd

from . import config
from .quality import Rule, apply_rules, partition_health

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
SEASONS = {"Jan-Feb": ["JAN", "FEB"], "Mar-May": ["MAR", "APR", "MAY"],
           "Jun-Sep": ["JUN", "JUL", "AUG", "SEP"], "Oct-Dec": ["OCT", "NOV", "DEC"]}


def clean(raw: pd.DataFrame) -> dict:
    steps = []
    df = raw.copy()
    df["source_row"] = raw.index + 2
    df["SUBDIVISION"] = df["SUBDIVISION"].str.strip().replace(config.RAIN_SUBDIVISION_FIXES)
    steps.append(f"Fixed sub-division spelling: {config.RAIN_SUBDIVISION_FIXES}")

    rules = [
        Rule("negative_rainfall", "A monthly rainfall value is negative", lambda d: (d[MONTHS] < 0).any(axis=1)),
        Rule("duplicate_key", "Duplicate sub-division/year row",
             lambda d: d.duplicated(subset=["SUBDIVISION", "YEAR"], keep="first")),
        Rule("unmapped_subdivision", "Sub-division has no state mapping",
             lambda d: ~d["SUBDIVISION"].isin(config.SUBDIVISION_TO_STATES)),
    ]
    clean_df, quarantine, rule_report = apply_rules(df, rules, partition_col="SUBDIVISION")

    # Reconcile ANNUAL and seasonal totals against the 12 monthly values. Monthly
    # values are the primary observation, so totals are recomputed when they disagree.
    month_sum = clean_df[MONTHS].sum(axis=1)
    mismatch = (month_sum - clean_df["ANNUAL"]).abs() > config.RAIN_SUM_TOLERANCE_MM
    clean_df["flag_annual_repaired"] = mismatch
    clean_df["annual_as_published"] = clean_df["ANNUAL"]
    clean_df["ANNUAL"] = month_sum.round(1)
    season_fix = 0
    for s, cols in SEASONS.items():
        ssum = clean_df[cols].sum(axis=1).round(1)
        season_fix += int(((ssum - clean_df[s]).abs() > config.RAIN_SUM_TOLERANCE_MM).sum())
        clean_df[s] = ssum
    rule_report.append({"rule": "annual_mismatch", "action": "flag (repaired)", "rows": int(mismatch.sum()),
                        "description": f"|sum(JAN..DEC) - ANNUAL| > {config.RAIN_SUM_TOLERANCE_MM} mm; ANNUAL recomputed"})
    rule_report.append({"rule": "season_mismatch", "action": "repaired", "rows": season_fix,
                        "description": "Seasonal totals disagree with months; recomputed"})
    steps.append("Recomputed ANNUAL and seasonal totals from monthly values where they disagreed")

    clean_df = clean_df.rename(columns={"SUBDIVISION": "subdivision", "YEAR": "year", "ANNUAL": "annual",
                                        "Jan-Feb": "jan_feb", "Mar-May": "mar_may", "Jun-Sep": "jun_sep",
                                        "Oct-Dec": "oct_dec"})
    clean_df.columns = [c.lower() if c in MONTHS else c for c in clean_df.columns]

    # Long-period average (LPA) & departure, the standard IMD way to describe a year.
    lpa = clean_df[(clean_df.year >= 1961) & (clean_df.year <= 2010)].groupby("subdivision")[["annual", "jun_sep"]].mean()
    clean_df = clean_df.merge(lpa.rename(columns={"annual": "lpa_annual", "jun_sep": "lpa_jun_sep"}),
                              left_on="subdivision", right_index=True, how="left")
    clean_df["departure_pct"] = 100 * (clean_df["annual"] - clean_df["lpa_annual"]) / clean_df["lpa_annual"]
    clean_df["monsoon_departure_pct"] = 100 * (clean_df["jun_sep"] - clean_df["lpa_jun_sep"]) / clean_df["lpa_jun_sep"]
    steps.append("Computed Long-Period Average (1961-2010) and % departure per sub-division")

    # State-level view (used by crop module only).
    mapping = pd.DataFrame([(sd, st) for sd, sts in config.SUBDIVISION_TO_STATES.items() for st in sts],
                           columns=["subdivision", "state"])
    val_cols = ["annual", "jun_sep", "oct_dec", "mar_may", "jan_feb", "monsoon_departure_pct", "departure_pct"]
    state_year = (clean_df.merge(mapping, on="subdivision")
                  .groupby(["state", "year"])
                  .agg(**{c: (c, "mean") for c in val_cols}, n_subdivisions=("subdivision", "nunique"))
                  .reset_index().round(2))
    steps.append("Mapped sub-divisions to states (simple mean where a state spans several sub-divisions)")

    partitions = partition_health(clean_df, "subdivision", expected_rows=115, flag_cols=["flag_annual_repaired"])
    return {
        "tables": {"rainfall": clean_df, "rainfall_state_year": state_year, "rainfall_state_map": mapping},
        "quarantine": quarantine,
        "rules": rule_report,
        "steps": steps,
        "partitions": partitions,
        "notes": ["State rainfall is an unweighted mean of IMD sub-divisions (area weights not available)",
                  "Some sub-divisions start after 1901, so completeness < 100% is expected for them"],
    }
