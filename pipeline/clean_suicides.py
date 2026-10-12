"""Clean the NCRB suicides dataset.

Important semantics: each Type_code (Causes, Means_adopted, Professional_Profile,
Education_Status, Social_Status) is a *separate breakdown of the same deaths*.
Summing across Type_codes multiplies the true count by ~5. Every aggregate on
the site therefore picks exactly ONE Type_code.
"""
import numpy as np
import pandas as pd

from . import config
from .quality import Rule, apply_rules, partition_health

# Breakdown used for headline totals: it has full gender x age detail and its
# total matches Education/Social status exactly in the source.
HEADLINE_TYPE_CODE = "Means_adopted"


def clean(raw: pd.DataFrame) -> dict:
    steps = []
    df = raw.copy()
    df["source_row"] = raw.index + 2
    for c in ["State", "Type_code", "Type", "Gender", "Age_group"]:
        df[c] = df[c].astype(str).str.strip()
    df["State"] = df["State"].replace(config.SUICIDE_STATE_FIXES)
    df["Type"] = df["Type"].str.replace("Specity", "Specify", regex=False).replace({"Seperated": "Separated"})
    steps.append(f"Standardised state names {config.SUICIDE_STATE_FIXES} and fixed category typos")

    df = df.rename(columns={"State": "state", "Year": "year", "Type_code": "type_code", "Type": "category",
                            "Gender": "gender", "Age_group": "age_group", "Total": "total"})
    key = ["state", "year", "type_code", "category", "gender", "age_group"]

    # The source collapses several distinct "Others" sub-categories of
    # Professional_Profile into one label, so the same key appears more than once
    # with DIFFERENT counts. Dropping them would lose deaths; they are summed.
    dup_mask = df.duplicated(subset=key, keep=False)
    rows_before = len(df)
    merged_sources = df[dup_mask].groupby(key)["source_row"].apply(lambda r: ",".join(map(str, r)))
    df = df.groupby(key, as_index=False, sort=False).agg(total=("total", "sum"), source_row=("source_row", "min"))
    df = df.merge(merged_sources.rename("merged_source_rows"), left_on=key, right_index=True, how="left")
    rows_merged = rows_before - len(df)
    steps.append(f"Summed {int(dup_mask.sum())} rows sharing the same key (collapsed 'Others' sub-categories) "
                 f"into {int(dup_mask.sum()) - rows_merged} rows")

    rules = [
        Rule("negative_total", "Total is negative", lambda d: d["total"] < 0),
        Rule("all_ages_aggregate", "Age group '0-100+' is an all-ages total (no age split)",
             lambda d: d["age_group"] == "0-100+", action="flag"),
    ]
    clean_df, quarantine, rule_report = apply_rules(df, rules, partition_col="state")

    # Reconciliation: for each state-year, the Type_code totals should agree.
    recon = clean_df.groupby(["state", "year", "type_code"])["total"].sum().unstack("type_code")
    recon["max_abs_gap"] = recon.max(axis=1) - recon.min(axis=1)
    recon["gap_pct"] = (100 * recon["max_abs_gap"] / recon[HEADLINE_TYPE_CODE].replace(0, np.nan)).round(2)
    recon = recon.reset_index()
    n_div = int((recon["max_abs_gap"] > 0).sum())
    rule_report.append({"rule": "breakdown_divergence", "action": "reported", "rows": n_div,
                        "description": "State-years where breakdown totals (Causes vs Means vs Profession ...) disagree"})
    steps.append("Reconciled totals across breakdowns per state-year (published as suicides_reconciliation)")

    # Headline table: one breakdown only, gender x age resolution, no double counting.
    headline = (clean_df[clean_df.type_code == HEADLINE_TYPE_CODE]
                .groupby(["state", "year", "gender", "age_group"], as_index=False)["total"].sum())
    steps.append(f"Built suicides_headline from Type_code = {HEADLINE_TYPE_CODE} only")

    partitions = partition_health(clean_df, "state")
    rule_report.insert(0, {"rule": "same_key_summed", "action": "merged", "rows": rows_merged,
                           "description": "Rows with an identical key were summed (source collapsed sub-categories)"})
    return {
        "rows_merged": rows_merged,
        "tables": {"suicides": clean_df, "suicides_headline": headline, "suicides_reconciliation": recon},
        "quarantine": quarantine,
        "rules": rule_report,
        "steps": steps,
        "partitions": partitions,
        "notes": ["Never sum across type_code - each one is a different breakdown of the same deaths",
                  f"Headline totals use type_code = {HEADLINE_TYPE_CODE}"],
    }
