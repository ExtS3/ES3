from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor

from backend.database import get_db_connection
from backend.auth.security import (
    clear_auth_cookie,
    clear_auth_cache,
    create_access_token,
    decode_access_token,
    get_current_user,
    get_user_by_id,
    get_user_permissions,
    get_user_roles,
    hash_password,
    set_auth_cookie,
    verify_password,
)

router = APIRouter()


class LoginRequest(BaseModel):
    id: str
    pw: str


class ChangeCredentialsRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=10, max_length=256)


class SignupRequest(BaseModel):
    id: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=10, max_length=256)
    requested_roles: list[str] = ["user"]


def _load_login_user(user_id: str) -> dict | None:
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
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _users_has_column(cur, column_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'admin'
          AND table_name = 'users'
          AND column_name = %s
        """,
        (column_name,),
    )
    return cur.fetchone() is not None


@router.post("/api/auth/signup")
async def signup(payload: SignupRequest):
    requested_roles = payload.requested_roles or ["user"]
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT 1 FROM users WHERE id = %s", (payload.id,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="User already exists.")
            cur.execute(
                "SELECT 1 FROM signup_requests WHERE user_id = %s AND status = 'pending'",
                (payload.id,),
            )
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Signup request already pending.")
            cur.execute("SELECT name FROM roles WHERE name = ANY(%s)", (requested_roles,))
            found_roles = {row["name"] for row in cur.fetchall()}
            missing = sorted(set(requested_roles) - found_roles)
            if missing:
                raise HTTPException(status_code=400, detail=f"Unknown roles: {', '.join(missing)}")
            cur.execute(
                """
                INSERT INTO signup_requests (user_id, username, password_hash, requested_roles)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username,
                    password_hash = EXCLUDED.password_hash,
                    requested_roles = EXCLUDED.requested_roles,
                    status = 'pending',
                    requested_at = now(),
                    decided_at = NULL,
                    decided_by = NULL
                RETURNING id
                """,
                (payload.id, payload.id, hash_password(payload.password), requested_roles),
            )
            request_id = cur.fetchone()["id"]
        conn.commit()
        return {"success": True, "request_id": request_id, "status": "pending"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.post("/api/auth/login")
async def login(request: LoginRequest, response: Response):
    user = _load_login_user(request.id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if not verify_password(request.pw, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    clear_auth_cache(user["id"])
    token = create_access_token(user["id"])
    set_auth_cookie(response, token)

    return {
        "status": "success",
        "message": f"{user['id']} login succeeded.",
        "token": token,
        "must_change_credentials": user["must_change_credentials"],
        "redirect": "/change-credentials" if user["must_change_credentials"] else "/",
    }


@router.post("/api/auth/change-credentials")
async def change_credentials(
    payload: ChangeCredentialsRequest,
    response: Response,
    user: dict = Depends(get_current_user),
):
    new_username = payload.username.strip()
    if not new_username:
        raise HTTPException(status_code=400, detail="Username is required.")

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if new_username != user["id"]:
                cur.execute("SELECT 1 FROM users WHERE id = %s", (new_username,))
                if cur.fetchone():
                    raise HTTPException(status_code=409, detail="Username already exists.")

            if _users_has_column(cur, "username"):
                cur.execute(
                    """
                    UPDATE users
                    SET id = %s,
                        username = %s,
                        password_hash = %s,
                        must_change_credentials = false,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id, must_change_credentials
                    """,
                    (new_username, new_username, hash_password(payload.password), user["id"]),
                )
            else:
                cur.execute(
                    """
                    UPDATE users
                    SET id = %s,
                        password_hash = %s,
                        must_change_credentials = false,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id, must_change_credentials
                    """,
                    (new_username, hash_password(payload.password), user["id"]),
                )
            updated = cur.fetchone()
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        conn.close()

    clear_auth_cache(user["id"])
    clear_auth_cache(updated["id"])
    token = create_access_token(updated["id"])
    set_auth_cookie(response, token)
    return {
        "status": "success",
        "message": "Credentials changed.",
        "token": token,
        "must_change_credentials": updated["must_change_credentials"],
        "redirect": "/",
    }


@router.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {
        "id": user["id"],
        "must_change_credentials": user["must_change_credentials"],
        "permissions": sorted(user["permissions"]),
        "roles": sorted(get_user_roles(user["id"])),
    }


@router.get("/api/auth/session")
async def session(request: Request):
    token = request.cookies.get("exts3_auth")
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        return {"authenticated": False, "id": None, "roles": ["guest"], "role_label": "Guest"}

    try:
        payload = decode_access_token(token)
        user = get_user_by_id(str(payload["sub"]))
    except HTTPException:
        return {"authenticated": False, "id": None, "roles": ["guest"], "role_label": "Guest"}
    if not user or not user["is_active"]:
        return {"authenticated": False, "id": None, "roles": ["guest"], "role_label": "Guest"}

    roles = sorted(get_user_roles(user["id"]))
    if "admin" in roles:
        role_label = "Administrator"
    elif any(role.startswith("department_") for role in roles):
        departments = [
            role.replace("department_", "").replace("_", " ").title()
            for role in roles
            if role.startswith("department_")
        ]
        role_label = f"User ({', '.join(departments)})"
    elif roles:
        role_label = f"User ({', '.join(roles)})"
    else:
        role_label = "User"

    return {
        "authenticated": True,
        "id": user["id"],
        "roles": roles,
        "permissions": sorted(get_user_permissions(user["id"])),
        "role_label": role_label,
        "must_change_credentials": user["must_change_credentials"],
    }


@router.post("/api/auth/logout")
async def logout(response: Response):
    clear_auth_cookie(response)
    return {"status": "success"}
