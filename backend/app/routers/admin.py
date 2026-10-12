"""Admin-only endpoints: datasets & lineage, quality, pipeline runs, source code (read-only),
project specification and API telemetry."""
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from .. import settings, telemetry
from ..auth import require_role
from ..db import query, records

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])

TABLE_NAME = re.compile(r"^[a-z_]+$")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


@router.get("/datasets")
def datasets():
    lineage = _read_json(settings.REPORTS / "lineage.json", {})
    quality = _read_json(settings.REPORTS / "quality.json", {})
    out = []
    for name, lin in lineage.items():
        schema = {}
        for t in lin.get("output_tables", {}):
            try:
                schema[t] = records(query(f'DESCRIBE "{t}"')[["column_name", "column_type"]])
            except HTTPException:
                schema[t] = []
        out.append({"name": name, **lin, "quality": quality.get(name, {}), "schema": schema})
    return out


@router.get("/datasets/{table}/sample")
def table_sample(table: str, limit: int = Query(20, ge=1, le=200)):
    if not TABLE_NAME.match(table):
        raise HTTPException(400, "Invalid table name")
    return records(query(f'SELECT * FROM "{table}" LIMIT {int(limit)}'))


@router.get("/quarantine/{name}")
def quarantine(name: str, limit: int = Query(100, ge=1, le=1000)):
    if not TABLE_NAME.match(name):
        raise HTTPException(400, "Invalid dataset name")
    try:
        df = query(f'SELECT * FROM "quarantine_{name}" LIMIT {int(limit)}')
        counts = query(f'SELECT _quarantine_reason reason, count(*) n FROM "quarantine_{name}" GROUP BY 1 ORDER BY 2 DESC')
    except HTTPException:
        return {"rows": [], "reasons": [], "message": "No rows were quarantined for this dataset"}
    return {"rows": records(df), "reasons": records(counts)}


@router.get("/pipeline/runs")
def pipeline_runs():
    path = settings.REPORTS / "pipeline_runs.jsonl"
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    return [json.loads(l) for l in lines[-50:]][::-1]


@router.get("/models")
def models():
    out = {}
    for p in sorted(settings.REPORTS.glob("metrics_*.json")):
        out[p.stem.removeprefix("metrics_")] = _read_json(p, {})
    return out


@router.get("/telemetry")
def get_telemetry():
    return telemetry.summary()


# ------------------------------------------------------------------ source code viewer (read-only)
@router.get("/code")
def code_tree():
    tree = []
    for group, base in settings.CODE_DIRS.items():
        if not base.exists():
            continue
        files = sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
        tree.append({"group": group, "files": [{"path": f"{group}/{p.relative_to(base).as_posix()}",
                                                 "lines": sum(1 for _ in p.open(encoding="utf-8"))} for p in files]})
    return tree


@router.get("/code/file")
def code_file(path: str):
    """Serve a .py file from an allow-listed folder. Resolves the real path and checks it
    is inside the allowed folder, so '../' tricks cannot read other files (e.g. users.json)."""
    group, _, rel = path.partition("/")
    base = settings.CODE_DIRS.get(group)
    if not base or not rel.endswith(".py"):
        raise HTTPException(404, "File not available")
    target = (base / rel).resolve()
    if not target.is_relative_to(base.resolve()) or not target.is_file():
        raise HTTPException(404, "File not available")
    return {"path": path, "content": target.read_text(encoding="utf-8")}


# ------------------------------------------------------------------ project info
@router.get("/project/pdf")
def project_pdf():
    if not settings.PROJECT_PDF or not settings.PROJECT_PDF.exists():
        raise HTTPException(404, "Project specification PDF not found")
    return FileResponse(settings.PROJECT_PDF, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{settings.PROJECT_PDF.name}"'})
