from fastapi import Depends, FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import requests
from urllib.parse import quote
from dotenv import load_dotenv
import os


app = FastAPI()
load_dotenv()
app.add_middleware(GZipMiddleware, minimum_size=1024)

from backend.auth.bootstrap import initialize_auth_system
from backend.auth.security import (
    AUTH_COOKIE_NAME,
    decode_access_token,
    get_user_by_id,
    get_user_roles,
    require_permission,
)


@app.on_event("startup")
async def startup_auth_system():
    initialize_auth_system()


@app.middleware("http")
async def enforce_initial_credential_change(request: Request, call_next):
    allowed_paths = {
        "/api/auth/login",
        "/api/auth/change-credentials",
        "/api/auth/logout",
        "/api/auth/me",
        "/api/auth/session",
    }
    if request.url.path.startswith("/api/") and request.url.path not in allowed_paths:
        token = request.cookies.get(AUTH_COOKIE_NAME)
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()

        if token:
            try:
                payload = decode_access_token(token)
                user = get_user_by_id(str(payload["sub"]))
                if user and user["must_change_credentials"]:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "Credentials must be changed before using this API.",
                            "redirect": "/change-credentials",
                        },
                    )
            except HTTPException:
                pass

    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        static_cache_seconds = os.getenv("STATIC_CACHE_SECONDS", "3600")
        response.headers.setdefault("Cache-Control", f"public, max-age={static_cache_seconds}")
    return response


def require_admin_page(request: Request):
    token = request.cookies.get(AUTH_COOKIE_NAME)
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        return RedirectResponse("/", status_code=303)

    try:
        payload = decode_access_token(token)
        user = get_user_by_id(str(payload["sub"]))
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    if not user or not user["is_active"]:
        return RedirectResponse("/", status_code=303)
    if user["must_change_credentials"]:
        return RedirectResponse("/change-credentials", status_code=303)
    if "admin" not in get_user_roles(user["id"]):
        return HTMLResponse("Administrator access is required.", status_code=403)

    return None


def require_authenticated_page(request: Request):
    token = request.cookies.get(AUTH_COOKIE_NAME)
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        return RedirectResponse("/", status_code=303)

    try:
        payload = decode_access_token(token)
        user = get_user_by_id(str(payload["sub"]))
    except HTTPException:
        return RedirectResponse("/", status_code=303)

    if not user or not user["is_active"]:
        return RedirectResponse("/", status_code=303)
    if user["must_change_credentials"] and request.url.path != "/change-credentials":
        return RedirectResponse("/change-credentials", status_code=303)

    return None


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants for Nexus
NEXUS_BASE_URL = os.getenv("NEXUS_BASE_URL")
NEXUS_REPOSITORY = os.getenv("NEXUS_REPOSITORY")
NEXUS_USERNAME = os.getenv("NEXUS_USERNAME")
NEXUS_PASSWORD = os.getenv("NEXUS_PASSWORD")

# Jinja2 Templates and Static Files (from upstream)
templates = Jinja2Templates(directory="frontend/templates")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    response = FileResponse("frontend/static/img/logo.png", media_type="image/png")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response

############ 프론트 라우팅 ############
# Upstream Frontend Routes
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})

# 로그인 페이지
@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup(request: Request):
    return templates.TemplateResponse(request, "auth/signup.html", {"request": request})

@app.get("/change-credentials", response_class=HTMLResponse)
async def change_credentials_page(request: Request):
    blocked = require_authenticated_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "auth/change_credentials.html", {"request": request})

### -------------------------------------------------------------- ###
# 앱 탐색 페이지
@app.get("/search", response_class=HTMLResponse)
async def search(request: Request):
    blocked = require_authenticated_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "search/search.html", {"request": request})

# 검색 결과 상세 페이지
@app.get("/detail", response_class=HTMLResponse)
async def detail(request: Request):
    blocked = require_authenticated_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "search/detail/detail.html",{"request": request})
@app.get("/no_result", response_class=HTMLResponse)
async def no_result(request: Request):
    blocked = require_authenticated_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "search/no_result.html", {"request": request})
@app.get('/search_list', response_class=HTMLResponse)
async def search_list(request: Request):
    blocked = require_authenticated_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "search/list.html", {"request": request})
### -------------------------------------------------------------- ###
# 관리자 대시보드
@app.get("/admin", response_class = HTMLResponse)
async def admin_dash(request: Request):
    blocked = require_admin_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "admin/admin_dash.html", {"request": request})
@app.get("/admin/log", response_class=HTMLResponse)
async def admin_log(request: Request):
    blocked = require_admin_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "admin/log.html", {"request": request})
@app.get("/admin/version-diff", response_class=HTMLResponse)
async def admin_version_diff(request: Request):
    blocked = require_admin_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "admin/version_diff.html", {"request": request})
@app.get("/admin/policy", response_class=HTMLResponse)
async def admin_policy(request: Request):
    blocked = require_admin_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "admin/policy.html", {"request": request})
@app.get("/admin/permissions", response_class=HTMLResponse)
async def admin_permissions(request: Request):
    blocked = require_admin_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "admin/permissions.html", {"request": request})
@app.get("/admin/policy-catalog", response_class=HTMLResponse)
async def admin_policy_catalog(request: Request):
    blocked = require_admin_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "admin/policy_catalog.html", {"request": request})
@app.get("/scenario", response_class=HTMLResponse)
async def admin_scenario_id(request: Request):
    blocked = require_admin_page(request)
    if blocked:
        return blocked
    return templates.TemplateResponse(request, "scenario/scenario_id.html", {"request": request})


@app.get("/scenario/{scenario_id}", response_class=HTMLResponse)
async def admin_scenario_detail(request: Request, scenario_id: str):
    blocked = require_admin_page(request)
    if blocked:
        return blocked
    return templates.TemplateResponse(
        request,
        "scenario/scenario_detail.html",
        {"request": request, "scenario_id": scenario_id},
    )


# 라이브러리 페이지
@app.get("/library", response_class=HTMLResponse)
async def library(request: Request):
    blocked = require_authenticated_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "library/library.html", {"request": request})

# 사용자 세팅
@app.get("/user_set", response_class=HTMLResponse)
async def user_set(request: Request):
    blocked = require_authenticated_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "setting/user_setting.html", {"request": request})

# 업로드 후 빌드 설정 페이지
@app.get("/build", response_class=HTMLResponse)
async def build(request: Request):
    blocked = require_authenticated_page(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "upload/build.html", {"request": request})



############# 백엔드 라우팅 #############
# 검색 API 라우팅
from backend.search.search import router as search_router
app.include_router(search_router)

# 관리자 대시보드 pending 파일 조회 라우팅
# from backend.admin.pending import router as admin_pending_router
# app.include_router(admin_pending_router)

# 관리자 로그 조회 라우팅
from backend.admin.log import router as admin_log_router
app.include_router(admin_log_router)
from backend.admin.policy import router as admin_policy_router
app.include_router(admin_policy_router)
from backend.install_helper.policy_catalog_router import router as policy_catalog_router
app.include_router(policy_catalog_router)
from backend.admin.permissions import router as admin_permissions_router
app.include_router(admin_permissions_router)
from backend.scenario.scenario_id import router as scenario_id_router
app.include_router(scenario_id_router)

# 업로드 파일 스캔 서버로 전송-----------------------
from backend.security_scan.file_save import router as file_save_router
app.include_router(file_save_router)

# 반드시 후에 삭제할 것 - 파일을 웹에서 볼 수 있게 하는 용도
# 2. SAVE_DIR 경로 가져오기
from backend.security_scan.file_save import SAVE_DIR
# 3. 정적 파일 마운트 (이게 함수보다 밑에 있어야 /scan_pending 주소를 가로채지 않습니다)
app.mount("/scan_pending", StaticFiles(directory=SAVE_DIR), name="scan_pending")
# ----------------------------------------

# suppressor 전송 라우팅
from backend.security_scan.send_suppressor import router as send_suppressor_router
app.include_router(send_suppressor_router)

# 계정별 확장 업로드 레지스트리 (첫/추가 업로드 + 자동 버전)
from backend.security_scan.upload_registry import router as upload_registry_router
app.include_router(upload_registry_router)

# nexus 리스트 조회
from backend.nexus.nexus_repo import router as nexus_repo
app.include_router(nexus_repo)

# zip파일 다운로드 라우팅
from backend.download.download_zip import router as download_zip
app.include_router(download_zip)

# 설치 도우미 배치 파일 다운로드 라우팅
from backend.install_helper.batch import router as install_helper_batch_router
app.include_router(install_helper_batch_router)

# 스캔 결과 recevive
from backend.recevie_result import router as recevie_result_router
app.include_router(recevie_result_router)

# 로그인 체크 라우팅
from backend.auth.login import router as login_router
app.include_router(login_router)

# 관리자 승인/거절 라우팅
from backend.admin.decision.approve import router as approve_router
app.include_router(approve_router)
from backend.admin.decision.reject import router as reject_router
app.include_router(reject_router)



# Backend API Routes
from urllib.parse import quote, unquote

# 1. 업로드 부분 수정
@app.post("/api/plugins/upload")
async def upload_plugin(
    plugin_name: str = Form(...),
    version: str = Form(...),
    file: UploadFile = File(...),
    _user: dict = Depends(require_permission("upload")),
):
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다.")

        # 한글 파일명 처리: unquote로 혹시 모를 인코딩을 풀고 다시 정리
        filename = unquote(file.filename)
        
        # Nexus에 저장될 논리적 경로 조립 (한글 포함 가능)
        nexus_path = f"{plugin_name}/{version}/{filename}"
        
        # 중요: URL 조립 시 quote를 사용하되, 슬래시(/)는 유지함
        encoded_path = quote(nexus_path, safe='/')
        upload_url = f"{NEXUS_BASE_URL}/repository/{NEXUS_REPOSITORY}/{encoded_path}"

        response = requests.put(
            upload_url,
            data=file_bytes,
            auth=(NEXUS_USERNAME, NEXUS_PASSWORD),
            headers={"Content-Type": "application/octet-stream"},
            timeout=60
        )

        if response.status_code not in [200, 201, 204]:
            # 에러 발생 시 response.text(HTML)가 너무 길면 detail이 깨지므로 요약 처리
            raise HTTPException(
                status_code=500,
                detail=f"Nexus 업로드 실패: {response.status_code}"
            )

        return {
            "success": True,
            "nexus_path": nexus_path, # 프론트에는 인코딩 안 된 깔끔한 이름 전달
            "message": "Nexus 업로드 성공"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. 다운로드 부분 수정
@app.get("/api/plugins/download")
def download_plugin(
    plugin_name: str,
    version: str,
    filename: str,
    _user: dict = Depends(require_permission("install_extension")),
):
    try:
        # 파일명 인코딩 정리
        safe_filename = unquote(filename)
        nexus_path = f"{plugin_name}/{version}/{safe_filename}"
        
        # Nexus 요청용 인코딩 (safe='/')
        encoded_path = quote(nexus_path, safe='/')
        download_url = f"{NEXUS_BASE_URL}/repository/{NEXUS_REPOSITORY}/{encoded_path}"
        
        response = requests.get(
            download_url,
            auth=(NEXUS_USERNAME, NEXUS_PASSWORD),
            stream=True,
            timeout=30
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="파일을 찾을 수 없습니다.")
            
        def iterfile():
            for chunk in response.iter_content(chunk_size=8192):
                yield chunk

        # 브라우저가 한글 파일명을 인식하게 하는 헤더
        encoded_header_filename = quote(safe_filename)
        headers = {
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_header_filename}"
        }
        
        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers=headers
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
