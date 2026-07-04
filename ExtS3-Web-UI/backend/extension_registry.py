from datetime import datetime, timezone
from typing import Any

from backend.database import execute_query

DECIDED_STATUSES = {"safe", "reject"}


def check_registry_duplicate(ext_id: str, version: str) -> dict[str, Any] | None:
    """id+version이 이미 레지스트리에 있으면 그 행을 반환한다. 버전이 다르면 별개 확장이라 None."""
    rows = execute_query(
        """
        SELECT ext_id, ext_name, browser, version, status, decided_at
        FROM extension_registry
        WHERE ext_id = %s AND version = %s
        """,
        (ext_id, version),
    )
    return rows[0] if rows else None


def upsert_registry_entry(
    ext_id: str,
    ext_name: str,
    browser: str,
    version: str,
    status: str = "review",
) -> None:
    """레포(Nexus) 현황을 미러링한다. status가 safe/reject면 검사결과일(decided_at)도 기록."""
    decided_at = datetime.now(timezone.utc) if status in DECIDED_STATUSES else None
    execute_query(
        """
        INSERT INTO extension_registry (ext_id, version, ext_name, browser, status, decided_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (ext_id, version) DO UPDATE SET
            ext_name = EXCLUDED.ext_name,
            browser = EXCLUDED.browser,
            status = EXCLUDED.status,
            decided_at = COALESCE(EXCLUDED.decided_at, extension_registry.decided_at),
            updated_at = now()
        """,
        (ext_id, version, ext_name, browser, status, decided_at),
    )
