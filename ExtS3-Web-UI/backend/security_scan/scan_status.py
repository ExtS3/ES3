import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.auth.security import get_current_user, require_admin

router = APIRouter()

STORE_DIR = Path(__file__).resolve().parent / "scan_jobs"
STORE_FILE = STORE_DIR / "scan_jobs.json"
_lock = threading.Lock()


class ScanProgressUpdate(BaseModel):
    status: str | None = None
    current_stage: str | None = None
    current_stage_label: str | None = None
    progress: int | None = None
    message: str | None = None
    error: str | None = None
    result_path: str | None = None
    risk_level: str | None = None
    decision: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_store() -> dict[str, Any]:
    if not STORE_FILE.exists():
        return {"jobs": {}}
    try:
        with STORE_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict) and isinstance(data.get("jobs"), dict):
            return data
    except Exception:
        pass
    return {"jobs": {}}


def _write_store(data: dict[str, Any]) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = STORE_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    temp_file.replace(STORE_FILE)


def create_scan_job(
    *,
    job_id: str,
    ext_id: str,
    ext_name: str,
    browser: str,
    version: str,
    filename: str,
    requested_by: str,
    status: str = "queued",
    message: str = "Scan request was queued.",
) -> dict[str, Any]:
    job = {
        "job_id": job_id,
        "ext_id": ext_id,
        "ext_name": ext_name,
        "browser": browser,
        "version": version,
        "filename": filename,
        "requested_by": requested_by,
        "status": status,
        "current_stage": status,
        "current_stage_label": status,
        "progress": 0,
        "message": message,
        "error": None,
        "risk_level": None,
        "decision": None,
        "result_path": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _lock:
        data = _read_store()
        data["jobs"][job_id] = job
        _write_store(data)
    return job


# 검사 후 확정 상태 — suppressor의 generic "success" 콜백이 이걸 덮어쓰면 안 된다.
# (/api/receive가 review/safe/reject를 먼저 기록하고, 그 직후 complete 콜백이 도착함)
_FINAL_STATUSES = {"review", "safe", "reject"}


def update_scan_job(job_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = _read_store()
        job = data["jobs"].get(job_id)
        if not isinstance(job, dict):
            raise KeyError(job_id)
        if updates.get("status") == "success" and job.get("status") in _FINAL_STATUSES:
            updates = {key: value for key, value in updates.items() if key != "status"}
        for key, value in updates.items():
            if value is not None:
                job[key] = value
        if "progress" in job:
            job["progress"] = max(0, min(100, int(job.get("progress") or 0)))
        job["updated_at"] = _now()
        data["jobs"][job_id] = job
        _write_store(data)
        return job


def update_job_by_ext(ext_id: str, version: str, updates: dict[str, Any]) -> None:
    """ext_id+version으로 최신 잡을 찾아 갱신. 잡이 없으면 조용히 무시.

    suppressor 결과 수신(/api/receive)과 관리자 승인/거부처럼 job_id가
    전달되지 않는 라이프사이클 이벤트를 검사 내역에 반영하는 용도.
    """
    with _lock:
        data = _read_store()
        candidates = [
            job
            for job in data["jobs"].values()
            if str(job.get("ext_id")) == str(ext_id) and str(job.get("version")) == str(version)
        ]
        if not candidates:
            return
        job = max(candidates, key=lambda item: str(item.get("updated_at") or ""))
        for key, value in updates.items():
            if value is not None:
                job[key] = value
        job["updated_at"] = _now()
        _write_store(data)


def mark_scan_job_error(job_id: str, message: str) -> None:
    try:
        update_scan_job(
            job_id,
            {
                "status": "error",
                "current_stage": "error",
                "current_stage_label": "error",
                "progress": 100,
                "error": message,
                "message": message,
            },
        )
    except KeyError:
        pass


def _status_counts(jobs: list[dict[str, Any]]) -> dict[str, int]:
    # 카드 5장 기준 버킷: 대기 / 진행 중 / 검토 대기 / 처리 완료(승인·거부) / 실패
    buckets = {
        "queued": "queued",
        "holding": "queued",
        "running": "running",
        "review": "review",
        "safe": "done",
        "reject": "done",
        "success": "done",
        "error": "error",
    }
    counts = {"queued": 0, "running": 0, "review": 0, "done": 0, "error": 0}
    for job in jobs:
        bucket = buckets.get(str(job.get("status") or "queued"))
        if bucket:
            counts[bucket] += 1
    return counts


def _snapshot() -> dict[str, Any]:
    with _lock:
        data = _read_store()
    jobs = list(data.get("jobs", {}).values())
    jobs.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {
        "jobs": jobs,
        "counts": _status_counts(jobs),
    }


def _assert_internal_token(token: str | None) -> None:
    expected = os.getenv("SCAN_STATUS_CALLBACK_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(status_code=403, detail="Invalid scan status callback token.")


@router.get("/api/scan-status")
async def list_scan_status(_user: dict = Depends(get_current_user)):
    return _snapshot()


@router.get("/api/scan-status/stream")
async def stream_scan_status(_user: dict = Depends(get_current_user)):
    async def event_stream():
        previous = None
        while True:
            payload = json.dumps(_snapshot(), ensure_ascii=False)
            if payload != previous:
                yield f"data: {payload}\n\n"
                previous = payload
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/internal/scan-status/{job_id}")
async def update_scan_status(
    job_id: str,
    payload: ScanProgressUpdate,
    x_scan_status_token: str | None = Header(default=None),
):
    _assert_internal_token(x_scan_status_token)
    try:
        job = update_scan_job(job_id, payload.dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Scan job not found.") from exc
    return {"success": True, "job": job}


@router.delete("/api/admin/scan-status/{job_id}")
async def delete_scan_status(job_id: str, _user: dict = Depends(require_admin)):
    with _lock:
        data = _read_store()
        if job_id not in data["jobs"]:
            raise HTTPException(status_code=404, detail="Scan job not found.")
        del data["jobs"][job_id]
        _write_store(data)
    return {"success": True}
