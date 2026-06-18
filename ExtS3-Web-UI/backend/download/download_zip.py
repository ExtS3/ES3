import os
import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

# chrome 다운로드 함수 임포트
from backend.download.chrome import chrome_download
from backend.download.vscode import vscode_download
from backend.auth.security import require_permission



router = APIRouter()

# Suppressor 서버 정보 (환경변수 활용)
SUPPRESSOR_BASE_URL = f"http://{os.getenv('SUPPRESSOR_PRIVATE_IP')}:{os.getenv('PORT')}"
SUPPRESSOR_HOLDING_URL = f"{SUPPRESSOR_BASE_URL}/api/holding"
SUPPRESSOR_FILE_SCAN_URL = os.getenv("FILE_SCAN_URL") or f"{SUPPRESSOR_BASE_URL}/file_scan"

def send_to_suppressor_task(file_path: str, extID: str, browser:str,version:str,extName:str, suppressor_url: str):
    """
    백그라운드에서 실행될 파일 전송 함수
    """
    try:
        # 1. 파일이 실제로 존재하는지 확인
        if not os.path.exists(file_path):
            print(f"전송 실패: 파일을 찾을 수 없음 ({file_path})")
            return
    

        # 2. 파일 읽어서 Suppressor로 POST 전송
        with open(file_path, "rb") as f:
            if browser == "VSCode":
                send_files = {'file': (f"{extID}-{version}.vsix", f, "application/octet-stream")}
            else:
                send_files = {'file': (f"{extID}.zip", f, "application/zip")}
            data = {"extID": extID ,"browser":browser, "version": version, "extName":extName}
            
            # 스캔 서버 응답을 기다림 (timeout 넉넉히)
            response = requests.post(suppressor_url, files=send_files, data=data, timeout=300)
            response.raise_for_status()
        
        print(f"Suppressor 전송 성공: {extID}")
        
        # 3. (옵션) 전송 완료 후 로컬에 저장된 임시 파일 삭제
        # os.remove(file_path) 
        
    except Exception as e:
        print(f"Suppressor 전송 중 오류 발생: {e}")


@router.post("/api/download_zip")
async def download_extension(
    request: Request,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(require_permission("request_extension")),
):
    try:
        data = await request.json()
        extID = data.get("extension_id")
        browser = data.get("browser")
        extVersion = data.get("extVersion") or data.get("version")
        extName = data.get("extName")
        bypass_holding = bool(data.get("bypass_holding"))

        if not extID or not browser:
            return JSONResponse(status_code=400, content={"message": "필수 파라미터가 누락되었습니다."})

        if bypass_holding and "bypass_holding" not in _user["permissions"]:
            raise HTTPException(status_code=403, detail="[Bypass holding] 권한이 없습니다")

        if browser == "Chrome" or browser == "VSCode":
            # 1. 스토어에서 파일 다운로드 (경로 리턴받음)
            if browser == "Chrome":
                file_path = chrome_download(extID)
            else:
                file_path = vscode_download(extID, extVersion)

            if file_path:
                suppressor_url = SUPPRESSOR_FILE_SCAN_URL if bypass_holding else SUPPRESSOR_HOLDING_URL
                # 2. 다운로드 성공 시, 백그라운드 작업으로 Suppressor 전송 예약
                background_tasks.add_task(
                    send_to_suppressor_task, 
                    file_path, 
                    extID,
                    browser,
                    extVersion,
                    extName,
                    suppressor_url
                    
                    )

                # 3. 사용자에게는 즉시 성공 응답 전달
                mode_message = (
                    "대기 시간을 건너뛰고 보안 검사를 바로 시작했습니다."
                    if bypass_holding
                    else "보안 검사를 시작합니다."
                )
                return {
                    "status": "success",
                    "path": file_path,
                    "message": mode_message,
                    "bypass_holding": bypass_holding
                }
            else:
                return JSONResponse(status_code=500, content={"status": "fail", "message": "파일 다운로드에 실패했습니다."})

        return {"status": "error", "message": "지원하지 않는 브라우저입니다."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"서버 에러: {e}")
        return JSONResponse(status_code=500, content={"message": str(e)})
