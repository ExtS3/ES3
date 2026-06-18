from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, JSONResponse
from backend.auth.security import require_permission

from backend.admin.decision.nexus_file import (
    append_reject_record,
    build_reject_report_pdf,
    build_review_source_path,
    delete_analysis_result_for_review_path,
    delete_nexus_file,
    get_extension_payload,
    read_reject_records,
    resolve_review_source_path,
)

router = APIRouter()

@router.post("/api/decision/reject")
async def reject_extension(
    request: Request,
    _user: dict = Depends(require_permission("approve_extension")),
):
    data = await request.json()
    payload = get_extension_payload(data)

    source_path = resolve_review_source_path(build_review_source_path(payload))

    append_reject_record({
        **payload,
        "source_path": source_path,
    })
    delete_nexus_file(source_path)
    deleted_analysis_path = delete_analysis_result_for_review_path(source_path)

    return JSONResponse({
        "success": True,
        "message": "rejected",
        "deleted_path": source_path,
        "deleted_analysis_path": deleted_analysis_path,
    })


@router.get("/api/decision/rejects")
async def rejected_extensions(_user: dict = Depends(require_permission("approve_extension"))):
    return JSONResponse({
        "success": True,
        "items": read_reject_records(),
    })


@router.get("/api/decision/rejects/report.pdf")
async def rejected_extensions_report(
    _user: dict = Depends(require_permission("approve_extension")),
):
    pdf = build_reject_report_pdf(read_reject_records())
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="reject_report.pdf"',
        },
    )
