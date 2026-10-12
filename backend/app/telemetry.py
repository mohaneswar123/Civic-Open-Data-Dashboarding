"""Request telemetry: latency and status per route, kept in a bounded in-memory window
and appended to artifacts/reports/api_requests.log for later analysis."""
from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timezone

import numpy as np
from starlette.middleware.base import BaseHTTPMiddleware

from . import settings

WINDOW = deque(maxlen=2000)
STARTED_AT = datetime.now(timezone.utc)


class TelemetryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            if path.startswith("/api"):
                entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "method": request.method,
                         "route": path, "status": status, "ms": round(1000 * (time.perf_counter() - t0), 2)}
                WINDOW.append(entry)
                try:
                    settings.REPORTS.mkdir(parents=True, exist_ok=True)
                    with open(settings.REPORTS / "api_requests.log", "a") as f:
                        f.write(json.dumps(entry) + "\n")
                except OSError:
                    pass


def summary() -> dict:
    by_route: dict[str, list] = {}
    for e in WINDOW:
        by_route.setdefault(f"{e['method']} {e['route']}", []).append(e)
    routes = []
    for k, items in sorted(by_route.items()):
        ms = np.array([i["ms"] for i in items])
        routes.append({"route": k, "count": len(items),
                       "errors": sum(1 for i in items if i["status"] >= 500),
                       "denied": sum(1 for i in items if i["status"] in (401, 403)),
                       "p50_ms": round(float(np.percentile(ms, 50)), 1),
                       "p95_ms": round(float(np.percentile(ms, 95)), 1),
                       "p99_ms": round(float(np.percentile(ms, 99)), 1)})
    return {"started_at": STARTED_AT.isoformat(timespec="seconds"), "window_size": len(WINDOW),
            "routes": routes, "recent": list(WINDOW)[-50:][::-1]}
