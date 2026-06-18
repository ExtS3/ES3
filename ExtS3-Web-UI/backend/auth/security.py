import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg2.extras import RealDictCursor

from backend.database import get_db_connection

AUTH_COOKIE_NAME = "exts3_auth"
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))
PASSWORD_HASH_ITERATIONS = 260000
PERMISSION_LABELS = {
    "upload": "Upload",
    "delete_user": "Delete users",
    "manage_extension_policy": "Manage policy",
    "request_extension": "Request extension",
    "bypass_holding": "Bypass holding",
    "install_extension": "Install extension",
    "approve_extension": "Approve/reject extension",
    "approve_signup": "Approve signup",
}
_bearer = HTTPBearer(auto_error=False)
_runtime_secret = secrets.token_urlsafe(48)
AUTH_CACHE_TTL_SECONDS = float(os.getenv("AUTH_CACHE_TTL_SECONDS", "5"))
_user_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_roles_cache: dict[str, tuple[float, set[str]]] = {}
_permissions_cache: dict[str, tuple[float, set[str]]] = {}


def clear_auth_cache(user_id: str | None = None) -> None:
    if user_id is None:
        _user_cache.clear()
        _roles_cache.clear()
        _permissions_cache.clear()
        return
    _user_cache.pop(user_id, None)
    _roles_cache.pop(user_id, None)
    _permissions_cache.pop(user_id, None)


def _cache_get(cache: dict, key: str):
    cached = cache.get(key)
    if not cached:
        return None
    expires_at, value = cached
    if expires_at < time.time():
        cache.pop(key, None)
        return None
    return value


def _cache_set(cache: dict, key: str, value):
    cache[key] = (time.time() + AUTH_CACHE_TTL_SECONDS, value)
    return value


def _auth_secret() -> bytes:
    return os.getenv("AUTH_SECRET", _runtime_secret).encode("utf-8")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_HASH_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _b64_json(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64_json(value: str) -> dict[str, Any]:
    padding = "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode((value + padding).encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def create_access_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + AUTH_TOKEN_TTL_SECONDS}
    body = _b64_json(payload)
    signature = hmac.new(_auth_secret(), body.encode("ascii"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{body}.{sig}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(_auth_secret(), body.encode("ascii"), hashlib.sha256).digest()
        padding = "=" * (-len(sig) % 4)
        actual = base64.urlsafe_b64decode((sig + padding).encode("ascii"))
        if not hmac.compare_digest(actual, expected):
            raise ValueError("bad signature")
        payload = _unb64_json(body)
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.") from exc


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=AUTH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME)


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        return token
    raise HTTPException(status_code=401, detail="Authentication is required.")


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    cached = _cache_get(_user_cache, user_id)
    if cached is not None or user_id in _user_cache:
        return dict(cached) if cached else None

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, password_hash, must_change_credentials, is_active
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            user = cur.fetchone()
            return _cache_set(_user_cache, user_id, dict(user) if user else None)
    finally:
        conn.close()


def get_user_permissions(user_id: str) -> set[str]:
    cached = _cache_get(_permissions_cache, user_id)
    if cached is not None:
        return set(cached)

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.name
                FROM user_roles ur
                JOIN role_permissions rp ON rp.role_id = ur.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE ur.user_id = %s
                UNION
                SELECT p.name
                FROM user_permissions up
                JOIN permissions p ON p.id = up.permission_id
                WHERE up.user_id = %s AND up.granted = true
                EXCEPT
                SELECT p.name
                FROM user_permissions up
                JOIN permissions p ON p.id = up.permission_id
                WHERE up.user_id = %s AND up.granted = false
                """,
                (user_id, user_id, user_id),
            )
            return _cache_set(_permissions_cache, user_id, {row[0] for row in cur.fetchall()})
    finally:
        conn.close()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    token = _extract_token(request, credentials)
    payload = decode_access_token(token)
    user = get_user_by_id(str(payload["sub"]))
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User is inactive or does not exist.")
    user["permissions"] = get_user_permissions(user["id"])
    return user


def require_credentials_ready(user: dict[str, Any]) -> None:
    if user["must_change_credentials"]:
        raise HTTPException(
            status_code=403,
            detail="Credentials must be changed before using this API.",
        )


def require_permission(permission: str):
    async def dependency(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        require_credentials_ready(user)
        if permission not in user["permissions"]:
            permission_label = PERMISSION_LABELS.get(permission, permission)
            raise HTTPException(status_code=403, detail=f"[{permission_label}] 권한이 없습니다")
        return user

    return dependency


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    require_credentials_ready(user)
    if "admin" not in get_user_roles(user["id"]):
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return user


def get_user_roles(user_id: str) -> set[str]:
    cached = _cache_get(_roles_cache, user_id)
    if cached is not None:
        return set(cached)

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.name
                FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = %s
                """,
                (user_id,),
            )
            return _cache_set(_roles_cache, user_id, {row[0] for row in cur.fetchall()})
    finally:
        conn.close()
