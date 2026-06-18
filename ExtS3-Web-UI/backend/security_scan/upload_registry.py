from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

from backend.auth.security import get_current_user, require_permission
from backend.database import get_db_connection

router = APIRouter()


def bump_patch(version: str) -> str:
    """Increment the patch (last) segment of a dotted version. '1.0.1' -> '1.0.2'."""
    parts = str(version or "").strip().split(".")
    if not parts or not parts[-1].isdigit():
        return "1.0.0"
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def _fetch_extension(cur, ext_id: str):
    cur.execute(
        """
        SELECT ext_id, ext_name, browser, uploader_id, latest_version
        FROM extension_uploads
        WHERE ext_id = %s
        """,
        (ext_id,),
    )
    return cur.fetchone()


def commit_upload(mode: str, ext_id: str, ext_name: str, browser: str, version: str, uploader_id: str) -> None:
    """Authoritatively record an upload. Raises HTTPException on name conflict or ownership mismatch."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB 연결에 실패했습니다.")
    try:
        with conn.cursor() as cur:
            if mode == "first":
                cur.execute(
                    """
                    INSERT INTO extension_uploads (ext_id, ext_name, browser, uploader_id, latest_version)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (ext_id) DO NOTHING
                    """,
                    (ext_id, ext_name, browser, uploader_id, version),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise HTTPException(status_code=409, detail="이미 존재하는 확장 이름입니다.")
            else:
                cur.execute(
                    """
                    UPDATE extension_uploads
                    SET latest_version = %s, browser = %s, updated_at = now()
                    WHERE ext_id = %s AND uploader_id = %s
                    """,
                    (version, browser, ext_id, uploader_id),
                )
                if cur.rowcount == 0:
                    conn.rollback()
                    raise HTTPException(status_code=403, detail="본인이 업로드한 확장만 업데이트할 수 있습니다.")
        conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/api/uploads/mine")
async def list_my_uploads(_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB 연결에 실패했습니다.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT ext_id, ext_name, browser, latest_version
                FROM extension_uploads
                WHERE uploader_id = %s
                ORDER BY updated_at DESC
                """,
                (_user["id"],),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    extensions = [
        {
            "ext_id": r["ext_id"],
            "ext_name": r["ext_name"],
            "browser": r["browser"],
            "latest_version": r["latest_version"],
            "next_version": bump_patch(r["latest_version"]),
        }
        for r in rows
    ]
    return {"success": True, "extensions": extensions}


class ResolveRequest(BaseModel):
    mode: str
    ext_id: str | None = None
    ext_name: str | None = None
    browser: str | None = ""


@router.post("/api/uploads/resolve")
async def resolve_upload(
    body: ResolveRequest,
    _user: dict = Depends(require_permission("upload")),
):
    mode = (body.mode or "").strip()

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB 연결에 실패했습니다.")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if mode == "first":
                ext_name = (body.ext_name or "").strip()
                if not ext_name:
                    raise HTTPException(status_code=400, detail="확장 이름을 입력해주세요.")
                existing = _fetch_extension(cur, ext_name)
                if existing is not None:
                    raise HTTPException(status_code=409, detail="이미 존재하는 확장 이름입니다.")
                return {
                    "success": True,
                    "ext_id": ext_name,
                    "ext_name": ext_name,
                    "browser": (body.browser or "").strip(),
                    "version": "1.0.0",
                }

            if mode == "update":
                ext_id = (body.ext_id or "").strip()
                if not ext_id:
                    raise HTTPException(status_code=400, detail="업데이트할 확장을 선택해주세요.")
                existing = _fetch_extension(cur, ext_id)
                if existing is None:
                    raise HTTPException(status_code=404, detail="존재하지 않는 확장입니다.")
                if existing["uploader_id"] != _user["id"]:
                    raise HTTPException(status_code=403, detail="본인이 업로드한 확장만 업데이트할 수 있습니다.")
                return {
                    "success": True,
                    "ext_id": existing["ext_id"],
                    "ext_name": existing["ext_name"],
                    "browser": existing["browser"],
                    "version": bump_patch(existing["latest_version"]),
                }

            raise HTTPException(status_code=400, detail="알 수 없는 업로드 모드입니다.")
    finally:
        conn.close()
