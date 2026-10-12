"""One-command data pipeline:  python -m pipeline.run

raw CSV --(schema check)--> cleaner (rules, quarantine, repairs) --> DuckDB tables
                                                    \--> lineage + quality reports

Design properties
* Idempotent: the database is rebuilt from the raw files into a temp file and
  atomically swapped in, so re-running never duplicates or half-writes data.
* Reconciled: rows_in == rows_clean + rows_quarantined for every dataset; any
  difference is counted as a reconciliation error.
* Degraded mode: if one dataset fails (missing file, schema change, bug), the
  others still publish and the failed one keeps its last good version, marked stale.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from . import clean_crop, clean_diabetes, clean_rainfall, clean_suicides, clean_weather, config

CLEANERS = {
    "crop": clean_crop.clean,
    "rainfall": clean_rainfall.clean,
    "suicides": clean_suicides.clean,
    "diabetes": clean_diabetes.clean,
    "weather": clean_weather.clean,
}

EXPECTED_SCHEMA = {
    "crop": {"State_Name": "str", "District_Name": "str", "Crop_Year": "int", "Season": "str",
             "Crop": "str", "Area": "num", "Production": "num"},
    "rainfall": {"SUBDIVISION": "str", "YEAR": "int", **{m: "num" for m in clean_rainfall.MONTHS},
                 "ANNUAL": "num", "Jan-Feb": "num", "Mar-May": "num", "Jun-Sep": "num", "Oct-Dec": "num"},
    "suicides": {"State": "str", "Year": "int", "Type_code": "str", "Type": "str", "Gender": "str",
                 "Age_group": "str", "Total": "num"},
    "diabetes": {"gender": "str", "age": "num", "hypertension": "int", "heart_disease": "int",
                 "smoking_history": "str", "bmi": "num", "HbA1c_level": "num",
                 "blood_glucose_level": "num", "diabetes": "int"},
    "weather": {"city": "str", "date": "str", "temperature_2m_max": "num", "temperature_2m_min": "num",
                "apparent_temperature_max": "num", "apparent_temperature_min": "num",
                "precipitation_sum": "num", "rain_sum": "num", "weather_code": "int",
                "wind_speed_10m_max": "num", "wind_gusts_10m_max": "num", "wind_direction_10m_dominant": "num"},
}


class SchemaError(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_schema(name: str, df: pd.DataFrame) -> None:
    expected = EXPECTED_SCHEMA[name]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise SchemaError(f"{name}: missing columns {missing}")
    for col, kind in expected.items():
        s = df[col]
        if kind in ("num", "int") and not pd.api.types.is_numeric_dtype(s):
            raise SchemaError(f"{name}.{col}: expected numeric, got {s.dtype}")


def log(msg: str) -> None:
    print(f"[pipeline {datetime.now():%H:%M:%S}] {msg}", flush=True)


def run(raw_dir: Path = config.RAW_DIR, artifacts: Path = config.ARTIFACTS, only: list[str] | None = None) -> dict:
    started = time.perf_counter()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifacts.mkdir(parents=True, exist_ok=True)
    reports_dir = artifacts / "reports"
    quarantine_dir = artifacts / "quarantine"
    reports_dir.mkdir(exist_ok=True)
    quarantine_dir.mkdir(exist_ok=True)

    db_path = artifacts / "civic.duckdb"
    tmp_path = artifacts / f"civic.{run_id}.tmp.duckdb"
    con = duckdb.connect(str(tmp_path))

    lineage, quality, status = {}, {}, {}
    for name, cleaner in CLEANERS.items():
        if only and name not in only:
            continue
        src = config.SOURCES[name]
        path = raw_dir / src["file"]
        t0 = time.perf_counter()
        try:
            if not path.exists():
                raise FileNotFoundError(f"{path.name} not found in {raw_dir}")
            raw = pd.read_csv(path)
            validate_schema(name, raw)
            result = cleaner(raw)

            for tname, tdf in result["tables"].items():
                con.register("_df", tdf)
                con.execute(f'CREATE OR REPLACE TABLE "{tname}" AS SELECT * FROM _df')
                con.unregister("_df")
            q = result["quarantine"]
            if len(q):
                q = q.astype({c: "string" for c in q.columns if q[c].dtype == object})
                con.register("_q", q)
                con.execute(f'CREATE OR REPLACE TABLE "quarantine_{name}" AS SELECT * FROM _q')
                con.unregister("_q")
                q.to_csv(quarantine_dir / f"{name}_quarantine.csv", index=False)

            primary = result["tables"][name]
            rows_in, rows_clean, rows_q = len(raw), len(primary), len(q)
            rows_merged = int(result.get("rows_merged", 0))
            recon_errors = int(rows_in != rows_clean + rows_q + rows_merged)
            lineage[name] = {
                "source": {**src, "sha256": sha256(path), "bytes": path.stat().st_size,
                           "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")},
                "rows_in": rows_in, "rows_clean": rows_clean, "rows_quarantined": rows_q,
                "rows_merged": rows_merged,
                "lineage_coverage_pct": round(100 * (rows_clean + rows_q + rows_merged) / rows_in, 3) if rows_in else 100.0,
                "reconciliation_errors": recon_errors,
                "steps": result["steps"],
                "output_tables": {t: int(len(d)) for t, d in result["tables"].items()},
                "quarantine_table": f"quarantine_{name}" if rows_q else None,
                "notes": result.get("notes", []),
            }
            quality[name] = {"rules": result["rules"], "partitions": result["partitions"], **result.get("extra", {})}
            status[name] = {"status": "ok" if recon_errors == 0 else "reconciliation_error",
                            "seconds": round(time.perf_counter() - t0, 2)}
            log(f"{name:9s} ok  in={rows_in:>7} clean={rows_clean:>7} quarantined={rows_q:>6} "
                f"({status[name]['seconds']}s)")
        except Exception as exc:  # degraded mode: keep going, reuse last good tables
            status[name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                            "seconds": round(time.perf_counter() - t0, 2)}
            log(f"{name:9s} FAILED: {exc}")
            traceback.print_exc(file=sys.stderr)
            if db_path.exists():
                _copy_last_good(con, db_path, name)
                status[name]["status"] = "stale (served from last good version)"

    # Carry over reports for datasets not rebuilt in this run (partial / degraded runs).
    prev_lineage = _read_json(reports_dir / "lineage.json")
    prev_quality = _read_json(reports_dir / "quality.json")
    for name in CLEANERS:
        if name not in lineage and name in prev_lineage:
            lineage[name] = prev_lineage[name]
            quality[name] = prev_quality.get(name, {})
            if only and name not in only and db_path.exists():
                _copy_last_good(con, db_path, name)
    con.close()

    # Atomic swap: readers see either the old or the new database, never a partial one.
    for attempt in range(10):
        try:
            os.replace(tmp_path, db_path)
            break
        except PermissionError:  # Windows: a reader has the file open briefly
            time.sleep(0.5)
    else:
        raise RuntimeError("Could not replace civic.duckdb - is another process holding it open?")

    duration = round(time.perf_counter() - started, 2)
    summary = {
        "run_id": run_id, "pipeline_version": config.PIPELINE_VERSION,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_s": duration, "datasets": status,
        "overall": "ok" if all(s["status"] == "ok" for s in status.values()) else "degraded",
        "reconciliation_errors": sum(v.get("reconciliation_errors", 0) for v in lineage.values()),
    }
    (reports_dir / "lineage.json").write_text(json.dumps(lineage, indent=2, default=str))
    (reports_dir / "quality.json").write_text(json.dumps(quality, indent=2, default=str))
    with open(reports_dir / "pipeline_runs.jsonl", "a") as f:
        f.write(json.dumps(summary, default=str) + "\n")
    log(f"done in {duration}s - overall: {summary['overall']}")
    return summary


def _copy_last_good(con, db_path: Path, name: str) -> None:
    con.execute(f"ATTACH '{db_path.as_posix()}' AS prev (READ_ONLY)")
    try:
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = 'prev'").fetchall()]
        for t in tables:
            if t == name or t.startswith(f"{name}_") or t == f"quarantine_{name}":
                con.execute(f'CREATE OR REPLACE TABLE "{t}" AS SELECT * FROM prev."{t}"')
    finally:
        con.execute("DETACH prev")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


if __name__ == "__main__":
    only = sys.argv[1:] or None
    result = run(only=only)
    sys.exit(0 if result["overall"] == "ok" else 1)
