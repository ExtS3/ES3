from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

# DB 연결 함수
from backend.database import get_db_connection

# JSON 에 맞게 인코딩해주는 도구
from fastapi.encoders import jsonable_encoder


router = APIRouter()

@router.post("/api/admin/pending")
async def pending(request: Request):
    db = get_db_connection()
    if db:
        try:
            with db.cursor() as cursor:
                # 2. 쿼리 실행 예시
                sql = "SELECT * FROM pending_files"
                cursor.execute(sql)
                result = cursor.fetchall()
                # 날짜 객체를 JSON으로 변환
                result = jsonable_encoder(result)
                print(result)
                return JSONResponse(content={"success": True, "data":result})
        finally:
            # 3. 사용이 끝나면 반드시 닫기
            db.close()
