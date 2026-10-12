"""Clean the diabetes prediction dataset (standalone public-health module)."""
import pandas as pd

from . import config
from .quality import Rule, apply_rules, partition_health

NUMERIC = ["age", "hypertension", "heart_disease", "bmi", "HbA1c_level", "blood_glucose_level", "diabetes"]


def clean(raw: pd.DataFrame) -> dict:
    steps = []
    df = raw.copy()
    df["source_row"] = raw.index + 2
    df["gender"] = df["gender"].astype(str).str.strip()
    df["smoking_history"] = df["smoking_history"].astype(str).str.strip()

    def out_of_range(d):
        bad = pd.Series(False, index=d.index)
        for col, (lo, hi) in config.DIABETES_RANGES.items():
            bad |= (d[col] < lo) | (d[col] > hi)
        return bad

    feature_cols = [c for c in raw.columns]
    rules = [
        Rule("missing_value", "A required field is missing", lambda d: d[NUMERIC].isna().any(axis=1)),
        Rule("out_of_range", f"Outside plausible ranges {config.DIABETES_RANGES}", out_of_range),
        Rule("invalid_binary", "hypertension/heart_disease/diabetes not in {0,1}",
             lambda d: ~d[["hypertension", "heart_disease", "diabetes"]].isin([0, 1]).all(axis=1)),
        # Records have no patient ID, so exact duplicates cannot be told apart from
        # repeated entries. They are removed to avoid train/test leakage.
        Rule("exact_duplicate", "Exact duplicate of an earlier record (would leak between train/test)",
             lambda d: d.duplicated(subset=feature_cols, keep="first")),
        Rule("smoking_unknown", "smoking_history = 'No Info'", lambda d: d["smoking_history"] == "No Info", action="flag"),
        Rule("rare_gender", "gender = 'Other' (too few records for reliable statistics)",
             lambda d: d["gender"] == "Other", action="flag"),
    ]
    clean_df, quarantine, rule_report = apply_rules(df, rules, partition_col="gender")

    clean_df["age_band"] = pd.cut(clean_df["age"], bins=[0, 18, 30, 45, 60, 75, 200], right=False,
                                  labels=["<18", "18-29", "30-44", "45-59", "60-74", "75+"]).astype(str)
    clean_df["bmi_class"] = pd.cut(clean_df["bmi"], bins=[0, 18.5, 25, 30, 200], right=False,
                                   labels=["Underweight", "Normal", "Overweight", "Obese"]).astype(str)
    steps.append("Derived age_band and WHO BMI class")

    partitions = partition_health(clean_df, "age_band", flag_cols=["flag_smoking_unknown"])
    return {
        "tables": {"diabetes": clean_df},
        "quarantine": quarantine,
        "rules": rule_report,
        "steps": steps,
        "partitions": partitions,
        "notes": ["Dataset is not India-specific and has no geography/time - analysed standalone",
                  "Class imbalance: ~8.8% positive after de-duplication"],
    }
