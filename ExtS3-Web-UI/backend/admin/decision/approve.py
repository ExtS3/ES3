from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from backend.auth.security import require_permission

from backend.admin.decision.nexus_file import (
    build_review_source_path,
    build_safe_path_from_review_path,
    delete_analysis_result_for_review_path,
    get_extension_payload,
    move_nexus_file,
    resolve_review_source_path,
)

router = APIRouter()

@router.post("/api/decision/approve")
async def approve_extension(
    request: Request,
    _user: dict = Depends(require_permission("approve_extension")),
):
    data = await request.json()
    payload = get_extension_payload(data)

    source_path = resolve_review_source_path(build_review_source_path(payload))
    target_path = build_safe_path_from_review_path(source_path)

    move_nexus_file(source_path, target_path)
    deleted_analysis_path = delete_analysis_result_for_review_path(source_path)

    return JSONResponse({
        "success": True,
        "message": "approved",
        "source_path": source_path,
        "target_path": target_path,
        "deleted_analysis_path": deleted_analysis_path,
    })
