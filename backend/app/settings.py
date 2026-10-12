import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
DB_PATH = ARTIFACTS / "civic.duckdb"
REPORTS = ARTIFACTS / "reports"
MODELS = ARTIFACTS / "models"
PROJECT_PDF = next((ROOT / "project_info").glob("*.pdf"), None) if (ROOT / "project_info").exists() else None
USERS_FILE = Path(__file__).resolve().parents[1] / "users.json"

JWT_SECRET = os.environ.get("CIVIC_JWT_SECRET", "dev-only-change-me-" + "x" * 16)
JWT_ALGO = "HS256"
JWT_TTL_MIN = int(os.environ.get("CIVIC_JWT_TTL_MIN", "480"))

CORS_ORIGINS = os.environ.get("CIVIC_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")

# Roles, lowest to highest. A higher role can access everything a lower one can.
ROLES = ["public", "policy", "admin"]

# Demo accounts seeded on first start (passwords are stored only as bcrypt hashes).
SEED_USERS = [
    {"username": "policy", "password": os.environ.get("CIVIC_POLICY_PASSWORD", "policy@123"),
     "role": "policy", "name": "Policy Maker (demo)"},
    {"username": "admin", "password": os.environ.get("CIVIC_ADMIN_PASSWORD", "admin@123"),
     "role": "admin", "name": "Administrator (demo)"},
]

# Folders whose source code admins may view (read-only). Anything else is refused.
CODE_DIRS = {"pipeline": ROOT / "pipeline", "ml": ROOT / "ml", "backend": ROOT / "backend" / "app",
             "tests": ROOT / "tests"}
