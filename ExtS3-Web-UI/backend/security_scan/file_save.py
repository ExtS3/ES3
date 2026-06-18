import os
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse,HTMLResponse

from backend.auth.security import require_permission


router = APIRouter()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = os.path.join(BASE_DIR, "scan_pending")

if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

@router.post("/api/security_scan/file_save")
async def file_save(
    file: UploadFile = File(...),      # FormData의 'file' 키를 자동으로 해석
    plugin_name: str = Form(None),     # 추가 정보가 있다면 받기
    version: str = Form(None),
    _user: dict = Depends(require_permission("request_extension")),
):
    try:
        # 1. 파일 이름 가져오기 (자동으로 메타데이터에서 추출됨)
        filename = file.filename
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(SAVE_DIR, safe_filename)

        # 2. 파일 저장 (파일 내용만 깨끗하게 읽어서 저장)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        print(f"파일 저장 완료: {file_path}, 크기: {len(content)} bytes")

        return {
            "success": True, 
            "size": len(content),
            "save_path": f"/scan_pending/{safe_filename}"
        }

    except Exception as e:
        print(f"저장 중 오류 발생: {e}")
        return JSONResponse(status_code=500, content={"success": False, "detail": str(e)})
    
    

# 반드시 후에 삭제할 것 - 파일을 웹에서 보고, 다운받을 수 있게 하는 용도
@router.get("/scan_pending", response_class=HTMLResponse)
@router.get("/scan_pending/", response_class=HTMLResponse)
async def list_files(request: Request):
    # 1. 폴더 내 파일 목록 가져오기
    files = os.listdir(SAVE_DIR)
    
    # 2. 간단한 HTML 리스트 생성
    file_list_html = "".join([
        f'<li><a href="/scan_pending/{f}" style="text-decoration:none; color:#007bff;">📄 {f}</a></li>' 
        for f in files
    ])
    
    # 3. 전체 페이지 구성
    return f"""
    <html>
        <head><title>Index of /scan_pending</title></head>
        <body style="font-family: sans-serif; padding: 20px;">
            <h2>Index of /scan_pending</h2>
            <hr>
            <ul style="line-height: 2;">
                {file_list_html if files else "<li>파일이 없습니다.</li>"}
            </ul>
            <hr>
        </body>
    </html>
    """
