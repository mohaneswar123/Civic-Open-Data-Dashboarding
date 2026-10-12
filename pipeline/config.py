"""Central configuration for the data pipeline.

Every path, threshold and source description lives here so that a run is fully
described by (raw file hashes + this file + code version).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "datasets"
ARTIFACTS = ROOT / "artifacts"
DB_PATH = ARTIFACTS / "civic.duckdb"
QUARANTINE_DIR = ARTIFACTS / "quarantine"
REPORTS_DIR = ARTIFACTS / "reports"
MODELS_DIR = ARTIFACTS / "models"

PIPELINE_VERSION = "1.0.0"

# Source manifest: one entry per raw file. Used for lineage and the admin "Datasets" page.
SOURCES = {
    "crop": {
        "file": "crop_production.csv",
        "title": "District-wise, season-wise crop production statistics",
        "publisher": "Ministry of Agriculture & Farmers Welfare (via data.gov.in)",
        "url": "https://data.gov.in/",
        "licence": "Government Open Data License - India (GODL)",
        "grain": "one row per State x District x Year x Season x Crop",
        "units": {"Area": "hectares", "Production": "tonnes (Coconut: nuts; Cotton/Jute/Mesta: bales)"},
    },
    "rainfall": {
        "file": "rainfall_india_cleaned.csv",
        "title": "Sub-division-wise monthly rainfall of India, 1901-2015",
        "publisher": "India Meteorological Department (via data.gov.in)",
        "url": "https://data.gov.in/",
        "licence": "Government Open Data License - India (GODL)",
        "grain": "one row per IMD meteorological sub-division x Year",
        "units": {"JAN..DEC, ANNUAL, seasons": "millimetres"},
    },
    "suicides": {
        "file": "cleaned_suicides.csv",
        "title": "Accidental Deaths & Suicides in India (ADSI), 2001-2012",
        "publisher": "National Crime Records Bureau (via data.gov.in)",
        "url": "https://data.gov.in/",
        "licence": "Government Open Data License - India (GODL)",
        "grain": "one row per State x Year x Breakdown(Type_code) x Category(Type) x Gender x Age group",
        "units": {"Total": "count of persons"},
    },
    "diabetes": {
        "file": "diabetes_prediction_dataset.csv",
        "title": "Diabetes prediction dataset (patient-level health indicators)",
        "publisher": "Public research dataset (Kaggle mirror of EHR-derived data)",
        "url": "https://www.kaggle.com/datasets/iammustafatz/diabetes-prediction-dataset",
        "licence": "As published by the dataset author",
        "grain": "one row per (anonymous) patient record",
        "units": {"bmi": "kg/m^2", "HbA1c_level": "%", "blood_glucose_level": "mg/dL", "age": "years"},
    },
    "weather": {
        "file": "india_2000_2024_daily_weather.csv",
        "title": "Daily weather for 10 Indian cities, 2000-2024",
        "publisher": "Open-Meteo historical weather API (ERA5 reanalysis)",
        "url": "https://open-meteo.com/",
        "licence": "CC BY 4.0",
        "grain": "one row per City x Day",
        "units": {"temperature": "deg C", "precipitation/rain": "mm", "wind": "km/h", "direction": "degrees"},
    },
}

# ---- Domain rules ----------------------------------------------------------
# Rows that are sums of other rows; including them double-counts production.
CROP_AGGREGATE_ROWS = {"Total foodgrain", "Oilseeds total", "Pulses total"}
# Crops whose Production is not reported in tonnes.
CROP_NON_TONNE_UNITS = {
    "Coconut": "nuts",
    "Cotton(lint)": "bales",
    "Jute": "bales",
    "Mesta": "bales",
    "Jute & mesta": "bales",
}
# Robust z-score threshold on log-yield (per crop) above which a row is flagged.
YIELD_OUTLIER_Z = 5.0

# Rainfall: tolerance (mm) when reconciling monthly values against ANNUAL.
RAIN_SUM_TOLERANCE_MM = 1.0
RAIN_SUBDIVISION_FIXES = {"MATATHWADA": "MARATHWADA"}

# IMD sub-division -> state(s). A state with several sub-divisions gets the
# simple mean of them (area weights are not published in the dataset).
SUBDIVISION_TO_STATES = {
    "ANDAMAN & NICOBAR ISLANDS": ["Andaman and Nicobar Islands"],
    "ARUNACHAL PRADESH": ["Arunachal Pradesh"],
    "ASSAM & MEGHALAYA": ["Assam", "Meghalaya"],
    "NAGA MANI MIZO TRIPURA": ["Nagaland", "Manipur", "Mizoram", "Tripura"],
    "SUB HIMALAYAN WEST BENGAL & SIKKIM": ["West Bengal", "Sikkim"],
    "GANGETIC WEST BENGAL": ["West Bengal"],
    "ORISSA": ["Odisha"],
    "JHARKHAND": ["Jharkhand"],
    "BIHAR": ["Bihar"],
    "EAST UTTAR PRADESH": ["Uttar Pradesh"],
    "WEST UTTAR PRADESH": ["Uttar Pradesh"],
    "UTTARAKHAND": ["Uttarakhand"],
    "HARYANA DELHI & CHANDIGARH": ["Haryana", "Chandigarh"],
    "PUNJAB": ["Punjab"],
    "HIMACHAL PRADESH": ["Himachal Pradesh"],
    "JAMMU & KASHMIR": ["Jammu and Kashmir"],
    "WEST RAJASTHAN": ["Rajasthan"],
    "EAST RAJASTHAN": ["Rajasthan"],
    "WEST MADHYA PRADESH": ["Madhya Pradesh"],
    "EAST MADHYA PRADESH": ["Madhya Pradesh"],
    "GUJARAT REGION": ["Gujarat", "Dadra and Nagar Haveli"],
    "SAURASHTRA & KUTCH": ["Gujarat"],
    "KONKAN & GOA": ["Maharashtra", "Goa"],
    "MADHYA MAHARASHTRA": ["Maharashtra"],
    "MARATHWADA": ["Maharashtra"],
    "VIDARBHA": ["Maharashtra"],
    "CHHATTISGARH": ["Chhattisgarh"],
    "COASTAL ANDHRA PRADESH": ["Andhra Pradesh"],
    "RAYALSEEMA": ["Andhra Pradesh"],
    "TELANGANA": ["Telangana"],
    "TAMIL NADU": ["Tamil Nadu", "Puducherry"],
    "COASTAL KARNATAKA": ["Karnataka"],
    "NORTH INTERIOR KARNATAKA": ["Karnataka"],
    "SOUTH INTERIOR KARNATAKA": ["Karnataka"],
    "KERALA": ["Kerala"],
    "LAKSHADWEEP": ["Lakshadweep"],
}

# Suicides: unify spellings to the same state names used elsewhere on the site.
SUICIDE_STATE_FIXES = {
    "A & N Islands": "Andaman and Nicobar Islands",
    "D & N Haveli": "Dadra and Nagar Haveli",
    "Delhi (Ut)": "Delhi",
    "Jammu & Kashmir": "Jammu and Kashmir",
}

# Diabetes: physiologically plausible ranges; values outside are quarantined.
DIABETES_RANGES = {
    "age": (0, 120),
    "bmi": (10, 100),
    "HbA1c_level": (3, 20),
    "blood_glucose_level": (40, 600),
}

# Weather: a "rainy day" per IMD convention is >= 2.5 mm in 24 h.
RAINY_DAY_MM = 2.5
WEATHER_RANGES = {
    "temperature_2m_max": (-30, 55),
    "temperature_2m_min": (-40, 45),
    "precipitation_sum": (0, 1000),
    "wind_speed_10m_max": (0, 250),
    "wind_direction_10m_dominant": (0, 360),
}
