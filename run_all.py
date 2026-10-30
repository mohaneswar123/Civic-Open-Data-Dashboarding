"""Rebuild everything from the raw CSVs in one command:  python run_all.py

1. pipeline : validate -> clean -> quarantine -> DuckDB (+ lineage & quality reports)
2. ml       : train and evaluate all models (+ metrics reports), then the classification view (ml.classify)
"""
import sys

from pipeline.run import run
from ml import train_all  # noqa: F401  (imported for its modules)
from ml import classify, train_crop, train_diabetes, train_suicides, train_weather

if __name__ == "__main__":
    summary = run()
    if summary["overall"] != "ok":
        print("Pipeline finished in DEGRADED mode - models are trained on the last good data.")
    for mod in (train_crop, train_suicides, train_diabetes, train_weather, classify):
        mod.main()
    sys.exit(0 if summary["overall"] == "ok" else 1)
