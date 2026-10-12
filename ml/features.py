"""Feature builders shared by training (ml/train_*.py) and serving (backend).

Keeping them in one place guarantees the API builds features exactly like training.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- crop + rainfall
CROP_CAT = ["state", "district", "crop", "season"]
CROP_RAIN = ["annual", "jun_sep", "oct_dec", "mar_may", "monsoon_departure_pct"]
CROP_NUM = ["year", "log_area"]


def crop_features(df: pd.DataFrame, use_rain: bool = True) -> pd.DataFrame:
    df = df.copy()
    df["log_area"] = np.log1p(df["area_ha"])
    cols = CROP_CAT + CROP_NUM + (CROP_RAIN if use_rain else [])
    return df[cols]


# ---------------------------------------------------------------- suicides
SUI_CAT = ["state", "gender", "age_group"]
SUI_NUM = ["year", "lag1", "lag2", "lag_mean2", "state_lag1"]


def suicide_panel(headline: pd.DataFrame) -> pd.DataFrame:
    """Add previous-year values per (state, gender, age_group) series."""
    df = headline.sort_values(["state", "gender", "age_group", "year"]).copy()
    g = df.groupby(["state", "gender", "age_group"])["total"]
    df["lag1"] = g.shift(1)
    df["lag2"] = g.shift(2)
    df["lag_mean2"] = (df["lag1"] + df["lag2"]) / 2
    state_tot = df.groupby(["state", "year"])["total"].sum().rename("state_total").reset_index()
    state_tot["year"] += 1  # previous year's state total aligned to the current year
    df = df.merge(state_tot.rename(columns={"state_total": "state_lag1"}), on=["state", "year"], how="left")
    return df


# ---------------------------------------------------------------- diabetes
DIA_CAT = ["gender", "smoking_history"]
DIA_NUM = ["age", "hypertension", "heart_disease", "bmi", "HbA1c_level", "blood_glucose_level"]


# ---------------------------------------------------------------- weather
WX_BASE = ["temperature_2m_max", "temperature_2m_min", "apparent_temperature_max", "apparent_temperature_min",
           "precipitation_sum", "weather_code", "wind_speed_10m_max", "wind_gusts_10m_max"]
WX_CAT = ["city"]


def weather_features(df: pd.DataFrame) -> pd.DataFrame:
    """Input: rows for one or more cities sorted by date (needs >= 7 prior days).
    Output: features describing 'today' + recent history, and next-day targets."""
    df = df.sort_values(["city", "date"]).copy()
    g = df.groupby("city")
    for lag in (1, 2):
        df[f"tmax_lag{lag}"] = g["temperature_2m_max"].shift(lag)
        df[f"precip_lag{lag}"] = g["precipitation_sum"].shift(lag)
    df["tmax_roll7"] = g["temperature_2m_max"].transform(lambda s: s.rolling(7, min_periods=7).mean())
    df["precip_roll7"] = g["precipitation_sum"].transform(lambda s: s.rolling(7, min_periods=7).sum())
    df["rainy_days7"] = g["precipitation_sum"].transform(lambda s: (s >= 2.5).rolling(7, min_periods=7).sum())
    df["tmax_delta1"] = df["temperature_2m_max"] - df["tmax_lag1"]
    rad = np.deg2rad(df["wind_direction_10m_dominant"])
    df["wind_dir_sin"], df["wind_dir_cos"] = np.sin(rad), np.cos(rad)
    doy = pd.to_datetime(df["date"]).dt.dayofyear
    df["doy_sin"], df["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    df["month"] = pd.to_datetime(df["date"]).dt.month
    # targets (next day) - NaN on the last day of each city
    df["target_tmax_next"] = g["temperature_2m_max"].shift(-1)
    df["target_rain_next"] = (g["precipitation_sum"].shift(-1) >= 2.5).astype(float)
    df.loc[df["target_tmax_next"].isna(), "target_rain_next"] = np.nan
    return df


WX_FEATURES = WX_CAT + WX_BASE + ["tmax_lag1", "tmax_lag2", "precip_lag1", "precip_lag2", "tmax_roll7",
                                  "precip_roll7", "rainy_days7", "tmax_delta1", "wind_dir_sin", "wind_dir_cos",
                                  "doy_sin", "doy_cos", "month"]
