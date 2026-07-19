import os
import uuid

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile

from backend.auth.security import require_permission
from backend.extension_registry import check_registry_duplicate, upsert_registry_entry
from backend.security_scan.scan_status import create_scan_job, mark_scan_job_error
from backend.security_scan.upload_registry import commit_upload

router = APIRouter()

SUPPRESSOR_PRIVATE_IP = os.getenv("SUPPRESSOR_PRIVATE_IP")
PORT = os.getenv("PORT")
URL = f"http://{SUPPRESSOR_PRIVATE_IP}:{PORT}/file_scan"


@router.post("/api/send_suppressor")
async def pending(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    plugin_name: str = Form(...),
    browser: str = Form(...),
    version: str = Form(...),
    mode: str = Form("first"),
    _user: dict = Depends(require_permission("request_extension")),
):
    try:
        duplicate = check_registry_duplicate(plugin_name, version)
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"Already registered extension/version. status={duplicate['status']}",
            )

        commit_upload(
            mode=(mode or "first").strip(),
            ext_id=plugin_name,
            ext_name=plugin_name,
            browser=browser,
            version=version,
            uploader_id=_user["id"],
        )
        upsert_registry_entry(
            ext_id=plugin_name,
            ext_name=plugin_name,
            browser=browser,
            version=version,
            status="review",
        )

        file_content = await file.read()
        job_id = uuid.uuid4().hex
        create_scan_job(
            job_id=job_id,
            ext_id=plugin_name,
            ext_name=plugin_name,
            browser=browser,
            version=version,
            filename=file.filename or "",
            requested_by=_user["id"],
        )

        callback_base_url = (
            os.getenv("SCAN_STATUS_CALLBACK_BASE_URL")
            or os.getenv("WEB_SERVER_URL")
            or os.getenv("DASHBOARD_BASE_URL")
            or str(request.base_url).rstrip("/")
        )
        progress_url = f"{callback_base_url.rstrip('/')}/api/internal/scan-status/{job_id}"
        progress_token = os.getenv("SCAN_STATUS_CALLBACK_TOKEN", "")

        background_tasks.add_task(
            send_to_suppressor_task,
            file_content,
            file.filename,
            file.content_type,
            plugin_name,
            browser,
            version,
            plugin_name,
            job_id,
            progress_url,
            progress_token,
        )

        return {
            "status": "processing",
            "job_id": job_id,
            "message": "File received. Security scan has started.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await file.close()


def send_to_suppressor_task(
    file_content,
    filename,
    content_type,
    extID,
    browser,
    version,
    extName,
    job_id,
    progress_url,
    progress_token,
):
    try:
        files = {"file": (filename, file_content, content_type)}
        data = {
            "extID": str(extID),
            "browser": browser,
            "version": version,
            "extName": extName,
            "job_id": job_id,
            "progress_url": progress_url,
            "progress_token": progress_token,
        }

        response = requests.post(URL, files=files, data=data, timeout=300)
        response.raise_for_status()
    except Exception as exc:
        mark_scan_job_error(job_id, str(exc))
        print(f"Suppressor transfer failed: {exc}")
