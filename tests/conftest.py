"""Shared fixtures: small, versioned samples of the real raw files with deliberately
injected defects, so negative tests run in seconds and are fully reproducible."""
import shutil
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "datasets"


@pytest.fixture()
def messy_raw(tmp_path: Path) -> Path:
    """A raw directory built from real samples plus known-bad rows (NT-1 fixture)."""
    raw = tmp_path / "raw"
    raw.mkdir()

    crop = pd.read_csv(RAW / "crop_production.csv", nrows=2000)
    bad = crop.iloc[[0, 1, 2]].copy()
    bad.loc[bad.index[0], "Production"] = None                      # missing_production
    bad.loc[bad.index[1], "Crop"] = "Total foodgrain"                # aggregate_row
    bad.loc[bad.index[2], "Area"] = 0                                # non_positive_area
    dup = crop.iloc[[10]]                                            # duplicate_key
    pd.concat([crop, bad, dup], ignore_index=True).to_csv(raw / "crop_production.csv", index=False)

    rain = pd.read_csv(RAW / "rainfall_india_cleaned.csv")
    rain.loc[5, "ANNUAL"] = rain.loc[5, "ANNUAL"] + 500             # annual_mismatch (repaired)
    neg = rain.iloc[[6]].copy()
    neg["YEAR"] = 1800
    neg["JAN"] = -5                                                  # negative_rainfall
    pd.concat([rain, neg], ignore_index=True).to_csv(raw / "rainfall_india_cleaned.csv", index=False)

    sui = pd.read_csv(RAW / "cleaned_suicides.csv", nrows=20000)
    sui.to_csv(raw / "cleaned_suicides.csv", index=False)

    dia = pd.read_csv(RAW / "diabetes_prediction_dataset.csv", nrows=3000)
    weird = dia.iloc[[0]].copy()
    weird["bmi"] = 250                                               # out_of_range
    pd.concat([dia, weird, dia.iloc[[1]]], ignore_index=True).to_csv(raw / "diabetes_prediction_dataset.csv", index=False)

    wx = pd.read_csv(RAW / "india_2000_2024_daily_weather.csv")
    wx = wx[wx["date"] < "2001-01-01"]
    # NT-4: one city has a hole in its record while every other city is complete.
    wx = wx[~((wx["city"] == "Pune") & wx["date"].between("2000-03-01", "2000-03-10"))]
    flip = wx.iloc[[0]].copy()
    flip["date"] = "2000-12-31x"                                     # invalid_date
    pd.concat([wx, flip], ignore_index=True).to_csv(raw / "india_2000_2024_daily_weather.csv", index=False)
    return raw


@pytest.fixture()
def artifacts(tmp_path: Path) -> Path:
    out = tmp_path / "artifacts"
    out.mkdir()
    return out


def copy_raw(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst
