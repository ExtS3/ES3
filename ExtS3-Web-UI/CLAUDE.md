# CLAUDE.md — ExtS3-Web-UI 작업 네비게이션

이 문서는 Claude Code가 **ExtS3-Web-UI** 레포에서 코드 수정 또는 기능 추가 작업을 받았을 때, 레포 전체를 처음부터 훑지 않고 **작업 대상 위치를 즉시 파악**하기 위한 네비게이션 문서다.

> **사용 원칙**: 아래 "작업 유형별 진입 위치" 표에서 작업에 맞는 진입 위치를 찾고, **해당 폴더의 README.md를 먼저 읽은 뒤** 작업에 착수한다. 전체 레포를 순차적으로 훑지 않는다. 상세 동작은 이 문서가 아니라 각 폴더의 README.md에 있다.

---

## 레포 기본 정보

- **레포명**: ExtS3-Web-UI
- **역할**: 크롬/VSCode 확장 프로그램 보안 심사 플랫폼의 웹 UI + 백엔드 API
- **프레임워크**: FastAPI (백엔드) + Jinja2 + Vanilla JS (프론트엔드)
- **진입점**: `main.py` (루트) — FastAPI 앱 인스턴스, 모든 라우트 등록, 미들웨어 설정
- **연관 레포**: `suppressor` (보안 분석 서버, 별도 레포 `../suppressor/`. 향후 이 레포와 합쳐질 예정)

---

## 전체 디렉토리 구조

```
ExtS3-Web-UI/
├── main.py                         # FastAPI 진입점, 전체 라우트 등록
├── CLAUDE.md                       # ← 지금 작성하는 파일
│
├── backend/                        # 백엔드 로직 전체
│   ├── database.py                 # PostgreSQL 연결 풀
│   ├── recevie_result.py           # suppressor 분석 결과 수신
│   ├── admin/                      # 관리자 기능
│   │   └── decision/               # 승인·거절 처리
│   ├── ai_judgment/                # LLM 기반 AI 2차 판단
│   ├── auth/                       # 인증·인가
│   ├── db/migrations/              # SQL 마이그레이션
│   ├── download/                   # 웹스토어 확장 다운로드
│   ├── install_helper/             # Windows 정책 배치 파일 생성
│   ├── nexus/                      # Nexus 파일 저장소 연동
│   ├── scenario/                   # RAG 시나리오 관리
│   ├── search/                     # 확장 검색 (Chrome / VSCode)
│   │   └── browser/                # 브라우저별 검색 구현
│   └── security_scan/              # 파일 저장 및 suppressor 전송
│
├── frontend/
│   ├── templates/                  # Jinja2 HTML 템플릿
│   │   ├── admin/                  # 관리자 페이지
│   │   ├── auth/                   # 인증 페이지
│   │   ├── library/                # 라이브러리 페이지
│   │   ├── scenario/               # 시나리오 관리 페이지
│   │   ├── search/                 # 검색 페이지
│   │   │   └── detail/             # 확장 상세 페이지
│   │   ├── setting/                # 사용자 설정 페이지
│   │   └── upload/                 # 파일 업로드 페이지
│   └── static/
│       ├── js/                     # 페이지별 JavaScript
│       │   ├── admin/              # 관리자 페이지 JS
│       │   ├── auth/               # 인증 페이지 JS
│       │   ├── library/            # 라이브러리 페이지 JS
│       │   ├── search/             # 검색 페이지 JS
│       │   ├── upload/             # 업로드 페이지 JS
│       │   ├── common.js           # 전체 공통 — 세션·네비게이션
│       │   ├── index.js            # 메인 대시보드
│       │   └── upload.js           # Upload 버튼 핸들러
│       ├── css/                    # 스타일시트
│       └── vendor/                 # 서드파티 라이브러리 (html2canvas, jsPDF 등)
│
├── docker/                         # Docker 설정
│   ├── db/                         # PostgreSQL 초기화 SQL
│   └── nexus/                      # Nexus 저장소 초기화 스크립트
│
├── scripts/                        # CI 자동화 스크립트
│   ├── check_rules.py              # PR 규칙 검사
│   ├── create_pr.py                # PR 자동 생성
│   └── review_pr.py                # 코드 리뷰 자동화
│
└── tests/                          # 단위 테스트
    ├── browser/                    # VSCode 검색·다운로드 모듈 테스트
    └── install_helper/             # 정책 모델·배치 렌더러 테스트
```

---

## 작업 유형별 진입 위치

> 각 작업의 **진입 위치**로 이동하기 전에, 표의 **README** 열에 명시된 README.md를 반드시 먼저 읽는다.

### 백엔드 API 수정·추가

| 작업 | 진입 위치 | README |
|------|-----------|--------|
| 확장 검색 API (Chrome/VSCode) | `backend/search/` + `backend/search/browser/` | `backend/search/README.md`, `backend/search/browser/README.md` |
| 관리자 승인·거절 처리 | `backend/admin/decision/` | `backend/admin/decision/README.md` |
| 관리자 로그·정책·권한 | `backend/admin/` | `backend/admin/README.md` |
| 인증·인가·세션 | `backend/auth/` | `backend/auth/README.md` |
| AI 2차 판단 (LLM/Slack) | `backend/ai_judgment/` | `backend/ai_judgment/README.md` |
| Nexus 파일 저장소 연동 | `backend/nexus/nexus_repo.py` | `backend/nexus/README.md` |
| 확장 다운로드 (Chrome/VSCode) | `backend/download/` | `backend/download/README.md` |
| 파일 업로드·suppressor 전송 | `backend/security_scan/` | `backend/security_scan/README.md` |
| Windows 정책 배치 파일 생성 | `backend/install_helper/` | `backend/install_helper/README.md` |
| RAG 시나리오 관리 | `backend/scenario/scenario_id.py` | `backend/scenario/README.md` |
| suppressor 결과 수신 | `backend/recevie_result.py` | `backend/README.md` |
| DB 연결·쿼리 | `backend/database.py` | `backend/README.md` |
| DB 스키마·마이그레이션 | `backend/db/migrations/` | `backend/db/migrations/README.md` |
| 전체 라우트 등록·미들웨어 | `main.py` | `backend/README.md` |

### 프론트엔드 수정·추가

| 작업 | 진입 위치 | README |
|------|-----------|--------|
| 관리자 페이지 UI/JS | `frontend/templates/admin/` + `frontend/static/js/admin/` | `frontend/templates/admin/README.md`, `frontend/static/js/admin/README.md` |
| 인증 페이지 UI/JS | `frontend/templates/auth/` + `frontend/static/js/auth/` | `frontend/templates/auth/README.md`, `frontend/static/js/auth/README.md` |
| 검색 페이지 UI/JS | `frontend/templates/search/` + `frontend/static/js/search/` | `frontend/templates/search/README.md`, `frontend/static/js/search/README.md` |
| 라이브러리 페이지 UI/JS | `frontend/templates/library/` + `frontend/static/js/library/` | `frontend/templates/library/README.md`, `frontend/static/js/library/README.md` |
| 업로드 페이지 UI/JS | `frontend/templates/upload/` + `frontend/static/js/upload/` | `frontend/templates/upload/README.md`, `frontend/static/js/upload/README.md` |
| 시나리오 관리 페이지 | `frontend/templates/scenario/` | `frontend/templates/scenario/README.md` |
| 사용자 설정 페이지 | `frontend/templates/setting/` | `frontend/templates/setting/README.md` |
| 전체 공통 세션·네비게이션 | `frontend/static/js/common.js` | `frontend/static/js/README.md` |
| 메인 대시보드 | `frontend/templates/index.html` + `frontend/static/js/index.js` | `frontend/templates/README.md` |
| CSS 스타일 | `frontend/static/css/` | `frontend/static/css/README.md` |
| 서드파티 라이브러리 | `frontend/static/vendor/` | `frontend/static/vendor/README.md` |

### 인프라·배포·CI

| 작업 | 진입 위치 | README |
|------|-----------|--------|
| Docker Compose 전체 구성 | `docker-compose.yml` | `docker/README.md` |
| DB 초기화 SQL | `docker/db/init.sql` | `docker/db/README.md` |
| Nexus 저장소 초기화 | `docker/nexus/init-repository.sh` | `docker/nexus/README.md` |
| 자동 PR 파이프라인 | `scripts/check_rules.py`, `scripts/create_pr.py` | `scripts/README.md` |
| 자동 코드 리뷰 | `scripts/review_pr.py` | `scripts/README.md` |
| GitHub Actions workflow | `.github/workflows/` | `scripts/README.md` |
| PR 규칙 정의 | `.github/pipeline-rules.yml` | `scripts/README.md` |

### 테스트

| 작업 | 진입 위치 | README |
|------|-----------|--------|
| VSCode 검색·다운로드 테스트 | `tests/browser/test_vscode.py` | `tests/browser/README.md` |
| 정책 모델·배치 렌더러 테스트 | `tests/install_helper/test_policy_catalog.py` | `tests/install_helper/README.md` |
| 전체 테스트 실행 | `python -m unittest discover -s tests -p "test_*.py"` | `tests/README.md` |

---

## 작업 전 필수 규칙

1. **작업 전 해당 위치의 README.md를 반드시 먼저 읽는다.** 위 표에서 진입 위치를 찾고, 해당 README.md를 읽은 뒤 작업한다. 전체 레포를 순차적으로 훑지 않는다.

2. **새 API 엔드포인트를 추가할 때**는 `backend/` 하위 해당 모듈에 라우터를 작성하고, `main.py`에 `app.include_router()`로 등록한다. `main.py`에 직접 비즈니스 로직을 작성하지 않는다.

3. **프론트엔드 수정 시** HTML 템플릿은 `frontend/templates/`, JS는 `frontend/static/js/` 하위 동일한 폴더 구조에 위치한다. 페이지별 JS 파일과 템플릿이 1:1로 대응한다. 대응 관계는 각 폴더의 README.md에 명시되어 있다.

4. **DB 접근**은 반드시 `backend/database.py`의 `get_db_connection()` 또는 `execute_query()`를 사용한다. 직접 psycopg2를 import하지 않는다.

5. **인증이 필요한 새 페이지 라우트**는 `main.py`의 `require_authenticated_page()` 또는 `require_admin_page()`를 사용한다. 인증 로직을 직접 구현하지 않는다.

6. **suppressor와의 연동** (분석 결과 수신, 파일 전송)은 `backend/recevie_result.py`와 `backend/security_scan/send_suppressor.py`를 참고한다. suppressor는 현재 별도 레포(`../suppressor/`)에 있으며 향후 이 레포에 합쳐질 예정이다.

7. **테스트를 추가할 때**는 `tests/` 하위에 대상 모듈의 경로 구조와 동일하게 배치한다. 파일명은 `test_*.py` 형식을 따른다.

8. **이 파일(CLAUDE.md)과 각 폴더의 README.md는 코드 변경과 함께 업데이트한다.** 새 파일을 추가하거나 구조를 변경하면 해당 위치의 README.md와 이 파일의 구조도를 반영한다.
