"""Authentication (JWT) and role-based access control.

Access is enforced here, on the server. Hiding a menu item in the UI is not a
security control; every protected endpoint depends on `require_role(...)`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from . import settings

bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _load_users() -> dict:
    if not settings.USERS_FILE.exists():
        users = {u["username"]: {"role": u["role"], "name": u["name"],
                                 "password_hash": bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode()}
                 for u in settings.SEED_USERS}
        settings.USERS_FILE.write_text(json.dumps(users, indent=2))
    return json.loads(settings.USERS_FILE.read_text())


USERS = _load_users()


class User(BaseModel):
    username: str
    role: str
    name: str


ANONYMOUS = User(username="anonymous", role="public", name="Public visitor")


def role_rank(role: str) -> int:
    return settings.ROLES.index(role) if role in settings.ROLES else 0


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    """Anonymous visitors are 'public'. An invalid/expired token is an error, not a silent downgrade."""
    if creds is None:
        return ANONYMOUS
    try:
        payload = jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired - please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    u = USERS.get(payload.get("sub"))
    if not u:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return User(username=payload["sub"], role=u["role"], name=u["name"])


def require_role(min_role: str):
    def dep(user: User = Depends(current_user)) -> User:
        if role_rank(user.role) < role_rank(min_role):
            code = status.HTTP_401_UNAUTHORIZED if user.role == "public" else status.HTTP_403_FORBIDDEN
            raise HTTPException(code, f"This resource requires the '{min_role}' role")
        return user
    return dep


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn):
    u = USERS.get(body.username.strip().lower())
    if not u or not bcrypt.checkpw(body.password.encode(), u["password_hash"].encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_TTL_MIN)
    token = jwt.encode({"sub": body.username.strip().lower(), "role": u["role"], "exp": exp},
                       settings.JWT_SECRET, algorithm=settings.JWT_ALGO)
    return {"access_token": token, "token_type": "bearer",
            "user": {"username": body.username.strip().lower(), "role": u["role"], "name": u["name"]}}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user
