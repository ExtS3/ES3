from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg2.extras import RealDictCursor

from backend.database import get_db_connection
from backend.auth.security import clear_auth_cache, hash_password, require_admin, require_permission

router = APIRouter(prefix="/api/admin/permissions", dependencies=[Depends(require_admin)])


class CreateUserRequest(BaseModel):
    id: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=10, max_length=256)
    roles: list[str] = []
    permissions: list[str] = []
    must_change_credentials: bool = False


class SetUserPermissionsRequest(BaseModel):
    permissions: list[str]


class SetUserRolesRequest(BaseModel):
    roles: list[str]


class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    description: str | None = None
    permissions: list[str] = []


class DecideSignupRequest(BaseModel):
    permissions: list[str] = []


def _fetch_all(cur, query: str, params: tuple = ()) -> list[dict]:
    cur.execute(query, params)
    return [dict(row) for row in cur.fetchall()]


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


def _validate_permissions(cur, permission_names: list[str]) -> None:
    if not permission_names:
        return
    cur.execute("SELECT name FROM permissions WHERE name = ANY(%s)", (permission_names,))
    found = {row["name"] for row in cur.fetchall()}
    missing = sorted(set(permission_names) - found)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown permissions: {', '.join(missing)}")


def _validate_roles(cur, role_names: list[str]) -> None:
    if not role_names:
        return
    cur.execute("SELECT name FROM roles WHERE name = ANY(%s)", (role_names,))
    found = {row["name"] for row in cur.fetchall()}
    missing = sorted(set(role_names) - found)
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown roles: {', '.join(missing)}")


@router.get("/users")
async def list_users():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            users = _fetch_all(
                cur,
                """
                SELECT id, must_change_credentials, is_active, created_at, updated_at
                FROM users
                ORDER BY created_at DESC
                """,
            )
            for user in users:
                cur.execute(
                    """
                    SELECT r.name
                    FROM user_roles ur
                    JOIN roles r ON r.id = ur.role_id
                    WHERE ur.user_id = %s
                    ORDER BY r.name
                    """,
                    (user["id"],),
                )
                user["roles"] = [row["name"] for row in cur.fetchall()]
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
                    ORDER BY name
                    """,
                    (user["id"], user["id"], user["id"]),
                )
                user["permissions"] = [row["name"] for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT p.name, up.granted
                    FROM user_permissions up
                    JOIN permissions p ON p.id = up.permission_id
                    WHERE up.user_id = %s
                    ORDER BY p.name
                    """,
                    (user["id"],),
                )
                user["permission_overrides"] = {
                    row["name"]: row["granted"] for row in cur.fetchall()
                }
            return {"success": True, "users": users}
    finally:
        conn.close()


@router.post("/users")
async def create_user(
    payload: CreateUserRequest,
    _user: dict = Depends(require_permission("approve_signup")),
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _validate_roles(cur, payload.roles)
            _validate_permissions(cur, payload.permissions)
            if _users_has_column(cur, "username"):
                cur.execute(
                    """
                    INSERT INTO users (id, username, password_hash, must_change_credentials, is_active)
                    VALUES (%s, %s, %s, %s, true)
                    """,
                    (
                        payload.id,
                        payload.id,
                        hash_password(payload.password),
                        payload.must_change_credentials,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO users (id, password_hash, must_change_credentials, is_active)
                    VALUES (%s, %s, %s, true)
                    """,
                    (payload.id, hash_password(payload.password), payload.must_change_credentials),
                )
            if payload.roles:
                cur.execute(
                    """
                    INSERT INTO user_roles (user_id, role_id)
                    SELECT %s, id FROM roles WHERE name = ANY(%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (payload.id, payload.roles),
                )
            if payload.permissions:
                cur.execute(
                    """
                    INSERT INTO user_permissions (user_id, permission_id, granted)
                    SELECT %s, id, true FROM permissions WHERE name = ANY(%s)
                    ON CONFLICT (user_id, permission_id)
                    DO UPDATE SET granted = true
                    """,
                    (payload.id, payload.permissions),
                )
        conn.commit()
        clear_auth_cache(payload.id)
        return {"success": True, "id": payload.id}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    _user: dict = Depends(require_permission("delete_user")),
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="User not found.")
        conn.commit()
        clear_auth_cache(user_id)
        return {"success": True}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("/roles")
async def list_roles():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            roles = _fetch_all(cur, "SELECT id, name, description FROM roles ORDER BY name")
            for role in roles:
                cur.execute(
                    """
                    SELECT p.name
                    FROM role_permissions rp
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE rp.role_id = %s
                    ORDER BY p.name
                    """,
                    (role["id"],),
                )
                role["permissions"] = [row["name"] for row in cur.fetchall()]
            return {"success": True, "roles": roles}
    finally:
        conn.close()


@router.post("/roles")
async def create_role(payload: CreateRoleRequest):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _validate_permissions(cur, payload.permissions)
            cur.execute(
                "INSERT INTO roles (name, description) VALUES (%s, %s) RETURNING id",
                (payload.name, payload.description),
            )
            role_id = cur.fetchone()["id"]
            if payload.permissions:
                cur.execute(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT %s, id FROM permissions WHERE name = ANY(%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (role_id, payload.permissions),
                )
        conn.commit()
        clear_auth_cache()
        return {"success": True, "id": role_id}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.get("")
async def list_permissions():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            permissions = _fetch_all(cur, "SELECT id, name, description FROM permissions ORDER BY name")
            return {"success": True, "permissions": permissions}
    finally:
        conn.close()


@router.get("/signup-requests")
async def list_signup_requests():
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            requests = _fetch_all(
                cur,
                """
                SELECT id, user_id, username, requested_roles, status, requested_at, decided_at, decided_by
                FROM signup_requests
                ORDER BY requested_at DESC
                """,
            )
            return {"success": True, "requests": requests}
    finally:
        conn.close()


@router.post("/signup-requests/{request_id}/approve")
async def approve_signup_request(
    request_id: int,
    payload: DecideSignupRequest,
    admin_user: dict = Depends(require_permission("approve_signup")),
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _validate_permissions(cur, payload.permissions)
            cur.execute(
                """
                SELECT id, user_id, username, password_hash, requested_roles
                FROM signup_requests
                WHERE id = %s AND status = 'pending'
                """,
                (request_id,),
            )
            request_row = cur.fetchone()
            if not request_row:
                raise HTTPException(status_code=404, detail="Pending signup request not found.")
            _validate_roles(cur, request_row["requested_roles"])
            if _users_has_column(cur, "username"):
                cur.execute(
                    """
                    INSERT INTO users (id, username, password_hash, must_change_credentials, is_active)
                    VALUES (%s, %s, %s, false, true)
                    """,
                    (request_row["user_id"], request_row["username"], request_row["password_hash"]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO users (id, password_hash, must_change_credentials, is_active)
                    VALUES (%s, %s, false, true)
                    """,
                    (request_row["user_id"], request_row["password_hash"]),
                )
            cur.execute(
                """
                INSERT INTO user_roles (user_id, role_id)
                SELECT %s, id FROM roles WHERE name = ANY(%s)
                ON CONFLICT DO NOTHING
                """,
                (request_row["user_id"], request_row["requested_roles"]),
            )
            cur.execute("SELECT name FROM permissions")
            all_permissions = [row["name"] for row in cur.fetchall()]
            cur.execute(
                """
                INSERT INTO user_permissions (user_id, permission_id, granted)
                SELECT %s, id, name = ANY(%s)
                FROM permissions
                WHERE name = ANY(%s)
                ON CONFLICT (user_id, permission_id)
                DO UPDATE SET granted = EXCLUDED.granted
                """,
                (request_row["user_id"], payload.permissions, all_permissions),
            )
            cur.execute(
                """
                UPDATE signup_requests
                SET status = 'approved', decided_at = now(), decided_by = %s
                WHERE id = %s
                """,
                (admin_user["id"], request_id),
            )
        conn.commit()
        clear_auth_cache(request_row["user_id"])
        return {"success": True, "user_id": request_row["user_id"]}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.post("/signup-requests/{request_id}/reject")
async def reject_signup_request(
    request_id: int,
    admin_user: dict = Depends(require_permission("approve_signup")),
):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE signup_requests
                SET status = 'rejected', decided_at = now(), decided_by = %s
                WHERE id = %s AND status = 'pending'
                RETURNING user_id
                """,
                (admin_user["id"], request_id),
            )
            request_row = cur.fetchone()
            if not request_row:
                raise HTTPException(status_code=404, detail="Pending signup request not found.")
        conn.commit()
        clear_auth_cache(request_row["user_id"])
        return {"success": True, "user_id": request_row["user_id"]}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.put("/users/{user_id}/permissions")
async def set_user_permissions(user_id: str, payload: SetUserPermissionsRequest):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _validate_permissions(cur, payload.permissions)
            cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="User not found.")
            cur.execute("SELECT name FROM permissions")
            all_permissions = [row["name"] for row in cur.fetchall()]
            enabled = set(payload.permissions)
            cur.execute("DELETE FROM user_permissions WHERE user_id = %s", (user_id,))
            cur.execute(
                """
                INSERT INTO user_permissions (user_id, permission_id, granted)
                SELECT %s, id, name = ANY(%s)
                FROM permissions
                WHERE name = ANY(%s)
                """,
                (user_id, list(enabled), all_permissions),
            )
        conn.commit()
        clear_auth_cache(user_id)
        return {"success": True}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.put("/users/{user_id}/roles")
async def set_user_roles(user_id: str, payload: SetUserRolesRequest):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _validate_roles(cur, payload.roles)
            cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="User not found.")
            cur.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
            if payload.roles:
                cur.execute(
                    """
                    INSERT INTO user_roles (user_id, role_id)
                    SELECT %s, id FROM roles WHERE name = ANY(%s)
                    """,
                    (user_id, payload.roles),
                )
        conn.commit()
        return {"success": True}
    except HTTPException:
        conn.rollback()
        raise
    finally:
        conn.close()
