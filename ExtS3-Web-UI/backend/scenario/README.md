# backend/scenario

suppressor의 벡터 DB 시나리오를 관리하는 API 프록시 모듈입니다.
실제 시나리오 데이터는 suppressor 서버가 보유하고, 이 모듈은 관리자 UI와 suppressor 사이의 브릿지 역할만 합니다.

---

## 파일 구성

### scenario_id.py

`/api/admin/scenario/*` 엔드포인트를 정의합니다.
모든 엔드포인트는 `admin` 롤이 필요합니다.

| 메서드   | 경로                              | suppressor 전달 경로               | 설명                                  |
| -------- | --------------------------------- | ---------------------------------- | ------------------------------------- |
| `GET`    | `/api/admin/scenario/list`        | `GET /api/scenario/list`           | 전체 시나리오 목록 조회               |
| `GET`    | `/api/admin/scenario/detail/{id}` | `GET /api/scenario/detail/{id}`    | 시나리오 상세 조회                    |
| `POST`   | `/api/admin/scenario/upload`      | `POST /api/scenario/upload`        | 시나리오 업로드 (JSON 필수 + MD 선택) |
| `DELETE` | `/api/admin/scenario/delete/{id}` | `DELETE /api/scenario/delete/{id}` | 시나리오 삭제                         |
| `POST`   | `/api/admin/scenario/reload`      | `POST /api/scenario/reload`        | 벡터 DB 전체 재적재 (timeout 300초)   |
| `GET`    | `/api/admin/scenario/db-status`   | `GET /api/scenario/db-status`      | 벡터 DB 상태 조회                     |

**suppressor 연결 환경변수**

| 변수명                  | 기본값      | 설명                 |
| ----------------------- | ----------- | -------------------- |
| `SUPPRESSOR_PRIVATE_IP` | `localhost` | suppressor 서버 IP   |
| `SUPPRESSOR_PORT`       | `8001`      | suppressor 서버 포트 |

suppressor 연결 실패 시 503, suppressor 오류 시 suppressor 상태코드 그대로 반환합니다.

---

## 시나리오 업로드 형식

`/api/admin/scenario/upload`는 `multipart/form-data`로 전송합니다.

| 필드        | 타입    | 필수 | 설명                          |
| ----------- | ------- | ---- | ----------------------------- |
| `json_file` | `.json` | ✅   | 시나리오 데이터 (벡터화 대상) |
| `md_file`   | `.md`   | ❌   | 시나리오 문서 (LLM 참조용)    |

샘플 형식은 suppressor의 `embedding/scenario_docs/` 내 `.md` 파일과 `embedding/base/` 내 `.json` 파일을 참고하세요.

---

## 의존 관계

```
main.py
  └── scenario/scenario_id.router

scenario_id.py  →  suppressor /api/scenario/*  →  embedding/scenario_router.py
```
