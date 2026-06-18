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
