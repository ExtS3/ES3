import os
import shutil

from fastapi import APIRouter, HTTPException, Form, File, UploadFile

from hm_new import request_holding

router = APIRouter()


@router.post("/api/holding")
async def holding(
    extID:   str = Form(...),
    browser: str = Form(...),
    version: str = Form(...),
    extName: str = Form(...),
    file: UploadFile = File(...),
):
    # extID 는 신뢰 불가 입력이므로 경로 세그먼트로 정규화해 traversal 차단
    # (아래 request_holding 의 pending/{id}.json 저장에도 정규화된 값을 넘긴다)
    safe_ext_id = os.path.basename(str(extID or "").replace("\\", "/").rstrip("/"))
    if safe_ext_id.strip(".") == "" or "\x00" in safe_ext_id:
        raise HTTPException(status_code=400, detail="Invalid extID")
    extID = safe_ext_id

    # 로컬 임시 저장 (optional — 필요 없으면 제거 가능)
    UPLOAD_DIR = "./pending_files"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{extID}.zip")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 파일 포인터를 처음으로 되돌려 바이너리 읽기
    await file.seek(0)
    file_data = await file.read()

    result = request_holding(extID, browser, version, extName, file_data)

    if not result.get("registered"):
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=result.get("reason"))

    return {
        "status": "success",
        "message": "파일 수신 및 홀딩 등록 완료",
        "holding_seconds": result["holding_seconds"],
    }
