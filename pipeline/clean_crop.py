"""Clean the crop production dataset."""
import numpy as np
import pandas as pd

from . import config
from .quality import Rule, apply_rules, partition_health


def clean(raw: pd.DataFrame) -> dict:
    steps = []
    df = raw.copy()

    # 1. Normalise text columns (source has trailing spaces, e.g. "Kharif     ", "Telangana ").
    for c in ["State_Name", "District_Name", "Season", "Crop"]:
        df[c] = df[c].astype(str).str.strip()
    df["District_Name"] = df["District_Name"].str.title()
    steps.append("Trimmed whitespace in State/District/Season/Crop; District names title-cased")

    df = df.rename(columns={"State_Name": "state", "District_Name": "district", "Crop_Year": "year",
                            "Season": "season", "Crop": "crop", "Area": "area_ha", "Production": "production"})
    df["source_row"] = raw.index + 2  # line number in the CSV (header = line 1) for lineage

    # 2. Units: production is NOT always tonnes.
    df["unit"] = df["crop"].map(config.CROP_NON_TONNE_UNITS).fillna("tonnes")
    steps.append("Tagged production unit per crop (Coconut=nuts, fibre crops=bales, others=tonnes)")

    key = ["state", "district", "year", "season", "crop"]
    rules = [
        Rule("aggregate_row", "Row is a pre-computed total (e.g. 'Total foodgrain') - would double count",
             lambda d: d["crop"].isin(config.CROP_AGGREGATE_ROWS)),
        Rule("missing_production", "Production value is missing", lambda d: d["production"].isna()),
        Rule("non_positive_area", "Area is zero or negative", lambda d: d["area_ha"] <= 0),
        Rule("negative_production", "Production is negative", lambda d: d["production"] < 0),
        Rule("duplicate_key", "Duplicate State/District/Year/Season/Crop row",
             lambda d: d.duplicated(subset=key, keep="first")),
        Rule("zero_production", "Production reported as exactly 0 (crop failure or non-reporting)",
             lambda d: d["production"] == 0, action="flag"),
    ]
    clean_df, quarantine, rule_report = apply_rules(df, rules, partition_col="state")

    # 3. Yield + per-crop robust outlier flag on log-yield (median / MAD).
    clean_df["yield_t_per_ha"] = clean_df["production"] / clean_df["area_ha"]
    pos = clean_df["yield_t_per_ha"] > 0
    logy = np.log(clean_df.loc[pos, "yield_t_per_ha"])
    grp = clean_df.loc[pos, "crop"]
    med = logy.groupby(grp).transform("median")
    mad = (logy - med).abs().groupby(grp).transform("median") * 1.4826
    z = ((logy - med) / mad.replace(0, np.nan)).abs()
    clean_df["flag_yield_outlier"] = False
    clean_df.loc[pos, "flag_yield_outlier"] = (z > config.YIELD_OUTLIER_Z).fillna(False).values
    n_out = int(clean_df["flag_yield_outlier"].sum())
    rule_report.append({"rule": "yield_outlier", "action": "flag", "rows": n_out,
                        "description": f"Per-crop robust z-score of log-yield > {config.YIELD_OUTLIER_Z}"})
    steps.append("Computed yield = production / area; flagged per-crop robust outliers")

    aggregates = quarantine[quarantine["_quarantine_reason"] == "aggregate_row"] if len(quarantine) else quarantine
    partitions = partition_health(clean_df, "state", value_col="production",
                                  flag_cols=["flag_zero_production", "flag_yield_outlier"])
    return {
        "tables": {"crop": clean_df},
        "quarantine": quarantine,
        "rules": rule_report,
        "steps": steps,
        "partitions": partitions,
        "notes": [f"{len(aggregates)} aggregate rows kept out of totals to prevent double counting",
                  "Tonnage totals on the dashboard use unit = 'tonnes' rows only"],
    }
