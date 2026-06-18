import os

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.auth.security import require_admin

router = APIRouter(prefix="/api/admin/scenario", tags=["scenario-admin"])

SUPPRESSOR_BASE = (
    f"http://{os.getenv('SUPPRESSOR_PRIVATE_IP', 'localhost')}:{os.getenv('SUPPRESSOR_PORT', '8001')}"
)


def _suppressor_url(path: str) -> str:
    return f"{SUPPRESSOR_BASE}/api/scenario/{path}"


async def _get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.get(_suppressor_url(path))
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Suppressor 서버에 연결할 수 없습니다.")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


async def _delete(path: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            res = await client.delete(_suppressor_url(path))
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Suppressor 서버에 연결할 수 없습니다.")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ── 목록 조회 ──────────────────────────────────────────────────────────────────
@router.get("/list", dependencies=[Depends(require_admin)])
async def list_scenarios():
    return await _get("list")


# ── 단일 조회 ──────────────────────────────────────────────────────────────────
@router.get("/detail/{scenario_id}", dependencies=[Depends(require_admin)])
async def get_scenario(scenario_id: str):
    return await _get(f"detail/{scenario_id}")


# ── 업로드 ────────────────────────────────────────────────────────────────────
@router.post("/upload", dependencies=[Depends(require_admin)])
async def upload_scenario(
    json_file: UploadFile = File(...),
    md_file: UploadFile = File(None),
):
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            files: dict = {
                "json_file": (json_file.filename, await json_file.read(), "application/json"),
            }
            if md_file and md_file.filename:
                files["md_file"] = (md_file.filename, await md_file.read(), "text/markdown")

            res = await client.post(_suppressor_url("upload"), files=files)
            res.raise_for_status()
            return JSONResponse(status_code=res.status_code, content=res.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Suppressor 서버에 연결할 수 없습니다.")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ── 삭제 ──────────────────────────────────────────────────────────────────────
@router.delete("/delete/{scenario_id}", dependencies=[Depends(require_admin)])
async def delete_scenario(scenario_id: str):
    return await _delete(f"delete/{scenario_id}")


# ── vectorDB 재적재 ────────────────────────────────────────────────────────────
@router.post("/reload", dependencies=[Depends(require_admin)])
async def reload_scenarios():
    async with httpx.AsyncClient(timeout=300) as client:
        try:
            res = await client.post(_suppressor_url("reload"))
            res.raise_for_status()
            return res.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Suppressor 서버에 연결할 수 없습니다.")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


# ── vectorDB 상태 ──────────────────────────────────────────────────────────────
@router.get("/db-status", dependencies=[Depends(require_admin)])
async def db_status():
    return await _get("db-status")