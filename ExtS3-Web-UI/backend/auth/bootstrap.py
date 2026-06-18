import secrets
from pathlib import Path

from psycopg2.extras import RealDictCursor

from backend.database import get_db_connection
from backend.auth.security import hash_password

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"
INITIAL_ADMIN_USERNAME = "admin"
DEFAULT_USER_ROLES = (
    ("user", "General user"),
    ("department_security", "Security department user"),
    ("department_it", "IT department user"),
    ("department_ops", "Operations department user"),
)
DEFAULT_PERMISSIONS = (
    ("upload", "Upload extension files"),
    ("delete_user", "Delete users"),
    ("manage_extension_policy", "Manage extension review policy"),
    ("request_extension", "Request extension review"),
    ("bypass_holding", "Bypass extension holding period"),
    ("install_extension", "Install approved extensions"),
    ("approve_extension", "Approve or reject reviewed extensions"),
    ("approve_signup", "Approve signup requests"),
)
DEFAULT_USER_PERMISSIONS = ("request_extension", "upload", "install_extension")


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


def run_migrations() -> None:
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed while running migrations.")

    try:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS admin")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS admin.schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = path.name
                cur.execute("SELECT 1 FROM admin.schema_migrations WHERE version = %s", (version,))
                if cur.fetchone():
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute(
                    "INSERT INTO admin.schema_migrations (version) VALUES (%s)",
                    (version,),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_auth_schema_compatibility() -> None:
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed while checking auth schema.")

    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
            cur.execute("UPDATE users SET username = id WHERE username IS NULL")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
            cur.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_credentials BOOLEAN NOT NULL DEFAULT false"
            )
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()")
            cur.execute(
                "ALTER TABLE user_permissions ADD COLUMN IF NOT EXISTS granted BOOLEAN NOT NULL DEFAULT true"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS signup_requests (
                    id BIGSERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    requested_roles TEXT[] NOT NULL DEFAULT ARRAY['user']::TEXT[],
                    status TEXT NOT NULL DEFAULT 'pending',
                    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    decided_at TIMESTAMPTZ,
                    decided_by TEXT
                )
                """
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_extension_uploads_schema() -> None:
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed while ensuring extension_uploads schema.")

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS extension_uploads (
                    ext_id TEXT PRIMARY KEY,
                    ext_name TEXT NOT NULL,
                    browser TEXT NOT NULL DEFAULT '',
                    uploader_id TEXT NOT NULL,
                    latest_version TEXT NOT NULL DEFAULT '1.0.0',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_initial_admin() -> None:
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed while creating initial admin.")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.id
                FROM users u
                JOIN user_roles ur ON ur.user_id = u.id
                JOIN roles r ON r.id = ur.role_id
                WHERE r.name = 'admin'
                LIMIT 1
                """
            )
            existing_admin = cur.fetchone()
            if existing_admin:
                return

            password = secrets.token_urlsafe(18)
            password_hash = hash_password(password)
            if _users_has_column(cur, "username"):
                cur.execute(
                    """
                    INSERT INTO users (id, username, password_hash, must_change_credentials, is_active)
                    VALUES (%s, %s, %s, true, true)
                    ON CONFLICT (id) DO UPDATE
                    SET username = EXCLUDED.username,
                        password_hash = EXCLUDED.password_hash,
                        must_change_credentials = true,
                        is_active = true,
                        updated_at = now()
                    """,
                    (INITIAL_ADMIN_USERNAME, INITIAL_ADMIN_USERNAME, password_hash),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO users (id, password_hash, must_change_credentials, is_active)
                    VALUES (%s, %s, true, true)
                    ON CONFLICT (id) DO UPDATE
                    SET password_hash = EXCLUDED.password_hash,
                        must_change_credentials = true,
                        is_active = true,
                        updated_at = now()
                    """,
                    (INITIAL_ADMIN_USERNAME, password_hash),
                )
            cur.execute(
                """
                INSERT INTO user_roles (user_id, role_id)
                SELECT %s, id
                FROM roles
                WHERE name = 'admin'
                ON CONFLICT DO NOTHING
                """,
                (INITIAL_ADMIN_USERNAME,),
            )
        conn.commit()
        print("=" * 72)
        print("Initial ExtS3 administrator account created.")
        print(f"Username: {INITIAL_ADMIN_USERNAME}")
        print(f"Password: {password}")
        print("This password is shown once. Change the administrator username and password after login.")
        print("=" * 72)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_default_permissions_and_roles() -> None:
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed while creating default permissions and roles.")

    try:
        with conn.cursor() as cur:
            for name, description in DEFAULT_PERMISSIONS:
                cur.execute(
                    """
                    INSERT INTO permissions (name, description)
                    VALUES (%s, %s)
                    ON CONFLICT (name) DO UPDATE
                    SET description = EXCLUDED.description
                    """,
                    (name, description),
                )
            for name, description in DEFAULT_USER_ROLES:
                cur.execute(
                    """
                    INSERT INTO roles (name, description)
                    VALUES (%s, %s)
                    ON CONFLICT (name) DO NOTHING
                    """,
                    (name, description),
                )
            cur.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM roles r
                CROSS JOIN permissions p
                WHERE r.name = 'admin'
                ON CONFLICT DO NOTHING
                """
            )
            cur.execute(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM roles r
                JOIN permissions p ON p.name = ANY(%s)
                WHERE r.name IN ('user', 'department_security', 'department_it', 'department_ops')
                ON CONFLICT DO NOTHING
                """,
                (list(DEFAULT_USER_PERMISSIONS),),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_auth_system() -> None:
    run_migrations()
    ensure_auth_schema_compatibility()
    ensure_extension_uploads_schema()
    ensure_default_permissions_and_roles()
    ensure_initial_admin()
