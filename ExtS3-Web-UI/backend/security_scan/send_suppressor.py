import requests
import os
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from backend.auth.security import require_permission
from backend.security_scan.upload_registry import commit_upload

router = APIRouter()

SUPPRESSOR_PRIVATE_IP = os.getenv("SUPPRESSOR_PRIVATE_IP")
PORT = os.getenv("PORT")
URL = f"http://{SUPPRESSOR_PRIVATE_IP}:{PORT}/file_scan"

# 실제 전송을 담당하는 별도의 함수
# send_suppressor.py 수정본

@router.post("/api/send_suppressor")
async def pending(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    plugin_name: str = Form(...),  # JS의 'plugin_name'을 받음 (확장 이름 = ext_id)
    browser: str = Form(...),
    version: str = Form(...),
    mode: str = Form("first"),  # 'first' (첫 업로드) | 'update' (추가 업로드)
    _user: dict = Depends(require_permission("request_extension")),
    # 필수는 아니지만 프론트에서 보낼 수도 있으므로 유연하게 대처하거나
    # 내부적으로 plugin_name을 활용해 채워줍니다.
):
    try:
        # 계정별 확장 소유/버전 레지스트리에 먼저 확정 기록 (이름 중복/소유권 검증 포함)
        commit_upload(
            mode=(mode or "first").strip(),
            ext_id=plugin_name,
            ext_name=plugin_name,
            browser=browser,
            version=version,
            uploader_id=_user["id"],
        )

        file_content = await file.read()
        print("전송 URL;qwqw", URL)
        # 백그라운드 작업 예약
        background_tasks.add_task(
            send_to_suppressor_task, 
            file_content, 
            file.filename, 
            file.content_type,
            plugin_name, # 이걸 extID로 쓸 것임
            browser, 
            version,
            plugin_name  # 이걸 extName으로 쓸 것임
        )

        return {
            "status": "processing",
            "message": "파일 수신 완료. 보안 스캔을 시작합니다."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await file.close()

# 전송 함수도 인자 개수를 맞춥니다.
def send_to_suppressor_task(file_content, filename, content_type, extID, browser, version, extName):
    try:
        files = {'file': (filename, file_content, content_type)}
        
        # filescan/main.py 의 scan 함수가 요구하는 5개 인자를 정확히 매칭
        data = {
            "extID": str(extID),
            "browser": browser,
            "version": version,
            "extName": extName
        }
        print("전송 URL;", URL)
        
        response = requests.post(URL, files=files, data=data, timeout=300)
        response.raise_for_status()
        print(f"✅ Suppressor 전송 성공: {extName}")
    except Exception as e:
        print(f"❌ 전송 실패: {e}")
