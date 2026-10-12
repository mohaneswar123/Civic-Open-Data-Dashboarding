"""Clean the daily city weather dataset (standalone module)."""
import pandas as pd

from . import config
from .quality import Rule, apply_rules, partition_health


def clean(raw: pd.DataFrame) -> dict:
    steps = []
    df = raw.copy()
    df["source_row"] = raw.index + 2
    df["city"] = df["city"].astype(str).str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    steps.append("Parsed date column (invalid dates -> quarantine)")

    def out_of_range(d):
        bad = pd.Series(False, index=d.index)
        for col, (lo, hi) in config.WEATHER_RANGES.items():
            bad |= (d[col] < lo) | (d[col] > hi)
        return bad

    rules = [
        Rule("invalid_date", "Date could not be parsed", lambda d: d["date"].isna()),
        Rule("duplicate_key", "Duplicate city/date row", lambda d: d.duplicated(subset=["city", "date"], keep="first")),
        Rule("out_of_range", f"Outside physical ranges {config.WEATHER_RANGES}", out_of_range),
        Rule("min_above_max", "Daily minimum temperature above maximum",
             lambda d: d["temperature_2m_min"] > d["temperature_2m_max"]),
        Rule("missing_value", "Missing measurement", lambda d: d.drop(columns=["source_row"]).isna().any(axis=1)),
    ]
    clean_df, quarantine, rule_report = apply_rules(df, rules, partition_col="city")

    identical = bool((clean_df["rain_sum"] == clean_df["precipitation_sum"]).all())
    if identical:
        steps.append("rain_sum is identical to precipitation_sum in every row - rain_sum kept, noted as redundant")

    clean_df = clean_df.sort_values(["city", "date"]).reset_index(drop=True)
    clean_df["year"] = clean_df["date"].dt.year
    clean_df["month"] = clean_df["date"].dt.month
    clean_df["rainy_day"] = (clean_df["rain_sum"] >= config.RAINY_DAY_MM).astype(int)
    steps.append(f"Derived rainy_day = rain_sum >= {config.RAINY_DAY_MM} mm (IMD definition)")

    # Gap detection per city (NT-4: a single broken partition must not hide in a global average).
    gaps = []
    for city, g in clean_df.groupby("city"):
        full = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
        missing = full.difference(g["date"])
        gaps.append({"city": city, "first": str(g["date"].min().date()), "last": str(g["date"].max().date()),
                     "expected_days": len(full), "missing_days": len(missing)})
    rule_report.append({"rule": "date_gaps", "action": "reported", "rows": int(sum(x["missing_days"] for x in gaps)),
                        "description": "Calendar days missing inside each city's date range"})

    expected = max(x["expected_days"] for x in gaps)
    partitions = partition_health(clean_df, "city", expected_rows=expected)
    return {
        "tables": {"weather": clean_df},
        "quarantine": quarantine,
        "rules": rule_report,
        "steps": steps,
        "partitions": partitions,
        "notes": ["Covers 10 cities only - not representative of whole states",
                  "Values are ERA5 reanalysis grid estimates, not station observations"],
        "extra": {"date_gaps": gaps, "rain_equals_precipitation": identical},
    }
