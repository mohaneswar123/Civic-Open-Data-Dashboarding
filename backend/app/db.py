"""Read-only DuckDB access with a small result cache.

* A fresh read-only connection per query: the pipeline can atomically swap the
  database file without the API holding a lock on it.
* Cache entries are keyed by the database file's modification time, so a new
  pipeline run invalidates every cached result automatically.
* If the database is missing, endpoints fail with HTTP 503 (degraded mode)
  instead of crashing the whole API.
"""
from __future__ import annotations

import math
import threading
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from fastapi import HTTPException

from . import settings

_cache: dict[tuple, Any] = {}
_lock = threading.Lock()


class DataUnavailable(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=503, detail=detail)


def db_version() -> float | None:
    try:
        return settings.DB_PATH.stat().st_mtime
    except FileNotFoundError:
        return None


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    version = db_version()
    if version is None:
        raise DataUnavailable("Analytics database not built yet - run `python run_all.py`")
    key = (sql, tuple(params or []), version)
    with _lock:
        if key in _cache:
            return _cache[key]
    try:
        with duckdb.connect(str(settings.DB_PATH), read_only=True) as con:
            df = con.execute(sql, params or []).df()
    except duckdb.CatalogException as e:
        raise DataUnavailable(f"Required table missing (dataset may have failed in the pipeline): {e}")
    except duckdb.IOException as e:
        raise DataUnavailable(f"Database temporarily unavailable: {e}")
    with _lock:
        if len(_cache) > 512:
            _cache.clear()
        _cache[key] = df
    return df


def clean_value(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(v) or math.isinf(v) else round(float(v), 4)
    if isinstance(v, (pd.Timestamp,)):
        return v.date().isoformat()
    if v is pd.NA or v is pd.NaT:
        return None
    return v


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of dicts (NaN -> null, numpy -> python)."""
    cols = list(df.columns)
    return [{c: clean_value(v) for c, v in zip(cols, row)} for row in df.itertuples(index=False, name=None)]


def scalar(sql: str, params: list | None = None):
    df = query(sql, params)
    return clean_value(df.iat[0, 0]) if len(df) else None
