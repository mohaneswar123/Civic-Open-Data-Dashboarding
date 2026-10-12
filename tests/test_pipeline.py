"""Pipeline acceptance tests: quality rules, lineage, reconciliation, idempotent
replay, degraded mode and per-partition defect detection (NT-1, NT-4, NFR-4)."""
import hashlib
import json

import duckdb
import pandas as pd

from pipeline.run import run


def table_hash(db, table):
    with duckdb.connect(str(db), read_only=True) as con:
        df = con.execute(f'SELECT * FROM "{table}"').df()
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()


def reports(artifacts):
    return (json.loads((artifacts / "reports" / "lineage.json").read_text()),
            json.loads((artifacts / "reports" / "quality.json").read_text()))


def rule_rows(quality, dataset, rule):
    return next(r["rows"] for r in quality[dataset]["rules"] if r["rule"] == rule)


def test_every_row_accounted_for(messy_raw, artifacts):
    """KPI-4 / KPI-5: lineage coverage 100% and zero reconciliation errors."""
    summary = run(raw_dir=messy_raw, artifacts=artifacts)
    lineage, _ = reports(artifacts)
    assert summary["overall"] == "ok"
    for name, lin in lineage.items():
        assert lin["lineage_coverage_pct"] == 100.0, name
        assert lin["reconciliation_errors"] == 0, name
        assert lin["rows_in"] == lin["rows_clean"] + lin["rows_quarantined"] + lin.get("rows_merged", 0)


def test_messy_rows_quarantined_with_reason(messy_raw, artifacts):
    """NT-1: invalid records are detected BEFORE commit and kept with a reason - never silently dropped."""
    run(raw_dir=messy_raw, artifacts=artifacts)
    _, quality = reports(artifacts)
    assert rule_rows(quality, "crop", "missing_production") >= 1
    assert rule_rows(quality, "crop", "aggregate_row") >= 1
    assert rule_rows(quality, "crop", "non_positive_area") >= 1
    assert rule_rows(quality, "crop", "duplicate_key") >= 1
    assert rule_rows(quality, "rainfall", "negative_rainfall") == 1
    assert rule_rows(quality, "diabetes", "out_of_range") == 1
    assert rule_rows(quality, "diabetes", "exact_duplicate") >= 1
    assert rule_rows(quality, "weather", "invalid_date") == 1
    with duckdb.connect(str(artifacts / "civic.duckdb"), read_only=True) as con:
        reasons = {r[0] for r in con.execute("SELECT DISTINCT _quarantine_reason FROM quarantine_crop").fetchall()}
        assert {"missing_production", "aggregate_row", "non_positive_area", "duplicate_key"} <= reasons
        # nothing invalid leaked into the clean table
        assert con.execute("SELECT count(*) FROM crop WHERE production IS NULL OR area_ha <= 0").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM crop WHERE crop = 'Total foodgrain'").fetchone()[0] == 0


def test_rainfall_totals_repaired_from_months(messy_raw, artifacts):
    run(raw_dir=messy_raw, artifacts=artifacts)
    _, quality = reports(artifacts)
    assert rule_rows(quality, "rainfall", "annual_mismatch") >= 1
    with duckdb.connect(str(artifacts / "civic.duckdb"), read_only=True) as con:
        gap = con.execute("""SELECT max(abs(jan+feb+mar+apr+may+jun+jul+aug+sep+oct+nov+"dec" - annual))
                             FROM rainfall""").fetchone()[0]
    assert gap < 0.11  # rounding only


def test_replay_is_idempotent(messy_raw, artifacts):
    """NFR-4: re-running on the same inputs yields byte-identical tables (no duplication)."""
    run(raw_dir=messy_raw, artifacts=artifacts)
    db = artifacts / "civic.duckdb"
    first = {t: table_hash(db, t) for t in ["crop", "rainfall_state_year", "suicides_headline", "diabetes", "weather"]}
    run(raw_dir=messy_raw, artifacts=artifacts)
    second = {t: table_hash(db, t) for t in first}
    assert first == second


def test_schema_break_degrades_safely_and_recovers(messy_raw, artifacts):
    """Degraded mode: one broken source must not take down the others; last good data is served."""
    run(raw_dir=messy_raw, artifacts=artifacts)
    good = table_hash(artifacts / "civic.duckdb", "weather")
    wx_path = messy_raw / "india_2000_2024_daily_weather.csv"
    original = wx_path.read_bytes()
    pd.read_csv(wx_path).drop(columns=["temperature_2m_max"]).to_csv(wx_path, index=False)

    summary = run(raw_dir=messy_raw, artifacts=artifacts)
    assert summary["overall"] == "degraded"
    assert summary["datasets"]["weather"]["status"].startswith("stale")
    assert summary["datasets"]["crop"]["status"] == "ok"
    assert table_hash(artifacts / "civic.duckdb", "weather") == good  # last good version still served

    wx_path.write_bytes(original)  # recovery: fix the source and replay
    assert run(raw_dir=messy_raw, artifacts=artifacts)["overall"] == "ok"
    assert table_hash(artifacts / "civic.duckdb", "weather") == good


def test_defective_partition_is_visible(messy_raw, artifacts):
    """NT-4: a hole in ONE city is reported for that city, not hidden in a global average."""
    run(raw_dir=messy_raw, artifacts=artifacts)
    _, quality = reports(artifacts)
    gaps = {g["city"]: g["missing_days"] for g in quality["weather"]["date_gaps"]}
    assert gaps["Pune"] == 10
    assert all(v == 0 for c, v in gaps.items() if c != "Pune")
    pune = next(p for p in quality["weather"]["partitions"] if p["partition"] == "Pune")
    assert pune["completeness_pct"] < 100


def test_suicide_headline_has_no_double_counting(messy_raw, artifacts):
    """NT-2: summing across breakdowns would multiply deaths ~5x; the headline uses exactly one."""
    run(raw_dir=messy_raw, artifacts=artifacts)
    with duckdb.connect(str(artifacts / "civic.duckdb"), read_only=True) as con:
        headline = con.execute("SELECT sum(total) FROM suicides_headline").fetchone()[0]
        means = con.execute("SELECT sum(total) FROM suicides WHERE type_code = 'Means_adopted'").fetchone()[0]
        everything = con.execute("SELECT sum(total) FROM suicides").fetchone()[0]
    assert headline == means
    assert everything > 2 * headline


def test_missing_file_is_reported_not_crash(messy_raw, artifacts):
    (messy_raw / "diabetes_prediction_dataset.csv").unlink()
    summary = run(raw_dir=messy_raw, artifacts=artifacts)
    assert summary["datasets"]["diabetes"]["status"] == "failed"
    assert summary["datasets"]["crop"]["status"] == "ok"
