# backend

ExtS3-Web-UI의 서버 사이드 전체를 담당하는 패키지입니다.
인증, 확장 프로그램 검색·다운로드·업로드, 보안 분석 연동, 관리자 기능, Nexus 연동까지
앱의 모든 비즈니스 로직이 이 폴더 하위에 위치합니다.

---

## 전체 디렉토리 구조

```
backend/
├── recevie_result.py          # suppressor 분석 결과 수신 · 자동 정책 적용 · 저장
├── database.py                # PostgreSQL 연결 풀 관리
│
├── admin/                     # 관리자 기능 전체
│   ├── decision/              # 확장 승인·거절 → Nexus 파일 이동·삭제
│   ├── log.py                 # 분석 결과 조회 + PDF 리포트
│   ├── permissions.py         # 유저·롤·권한 CRUD + 회원가입 승인
│   ├── policy.py              # 자동 정책 설정 관리
│   └── policy_settings.json   # 정책 설정값 (런타임 파일)
│
├── ai_judgment/               # LLM 2차 판단 (Ollama 기반)
│   ├── judge.py               # LLM 호출 + 응답 파싱
│   ├── extractor.py           # 분석 결과에서 LLM 입력 추출
│   ├── prompts.py             # 시스템·유저 프롬프트
│   └── slack.py               # AI 판단 결과 Slack 전송
│
├── auth/                      # 인증·인가 시스템
│   ├── security.py            # 토큰 발급·검증, 권한 의존성 함수
│   ├── login.py               # 로그인·로그아웃·회원가입·비밀번호 변경 API
│   └── bootstrap.py           # 앱 시작 시 DB 마이그레이션 + 초기 admin 계정 생성
│
├── db/
│   └── migrations/            # SQL 마이그레이션 파일 (앱 시작 시 자동 실행)
│       └── 001_auth_permissions.sql
│
├── download/                  # 웹 스토어에서 확장 다운로드 후 suppressor 전송
│   ├── download_zip.py        # API 엔드포인트 + suppressor 전송 오케스트레이터
│   ├── chrome.py              # Google CRX API 다운로드
│   └── vscode.py              # Open VSX API 다운로드
│
├── install_helper/            # Windows 레지스트리 기반 설치·제거 배치 파일 생성
│   ├── batch.py               # 단일 확장 설치·제거 .bat 생성 API
│   ├── policy_catalog.py      # Chrome 그룹 정책 5종 Pydantic 모델 + 배치 렌더러
│   └── policy_catalog_router.py # 정책 카탈로그 API
│
├── nexus/
│   └── nexus_repo.py          # Nexus 에셋 조회·존재 확인·다운로드·대시보드 API
│
├── scenario/
│   └── scenario_id.py         # suppressor 벡터 DB 시나리오 관리 API 프록시
│
├── search/                    # 확장 프로그램 검색
│   ├── search.py              # 검색 API + 결과 스코어링·캐싱 오케스트레이터
│   └── browser/               # 스토어별 크롤러
│       ├── chrome_id.py       # Chrome 웹스토어 ID 상세 조회
│       ├── chrome_name.py     # Chrome 웹스토어 이름 검색
│       ├── vscode_id.py       # Open VSX ID 상세 조회
│       └── vscode_name.py     # Open VSX 이름 검색
│
└── security_scan/             # 직접 업로드 확장의 수신·저장·suppressor 전송
    ├── file_save.py           # 업로드 파일 scan_pending/ 임시 저장
    ├── send_suppressor.py     # suppressor /file_scan 전송 + 업로드 이력 기록
    ├── upload_registry.py     # 계정별 업로드 이력 DB 관리
    └── scan_pending/          # 임시 저장 폴더 (.gitignore 등록)
        └── .gitkeep
```

---

## 핵심 파일: recevie_result.py

`backend/` 루트에 단독으로 위치하며, 앱에서 가장 많은 역할을 혼자 담당합니다.

```
suppressor → POST /api/receive
               │
               ├── 1. 자동 정책 적용 (_apply_auto_policy)
               │       admin/policy_settings.json 읽기
               │       CRITICAL → auto reject / LOW → auto approve / 나머지 → review
               │
               ├── 2. Nexus 위치 조정 (_reconcile_nexus_location)
               │       admin/decision/nexus_file.py 호출
               │       판정에 따라 review → safe / review → reject / 삭제 처리
               │
               ├── 3. 분석 결과 파일 저장
               │       analysis_result/{decision}/{browser}/{name}/{version}/{id}/
               │       summary.json, dynamic.json, static.json 등
               │
               └── 4. review 판정 시 AI 2차 판단 (백그라운드)
                       ai_judgment/judge.py → judgment.json 저장
                       ai_judgment/slack.py → Slack 전송
```

> 이 파일이 `backend/` 루트에 있는 이유: `POLICY_PATH`가 `Path(__file__).parent / "admin" / "policy_settings.json"`으로 하드코딩돼 있어 현재 위치에서만 경로가 맞습니다.

---

## 전체 데이터 흐름

```
[사용자]
  │
  ├── 웹 스토어 검색 후 다운로드
  │     search/ → download/ → suppressor /api/holding (홀딩 큐)
  │                                     또는 /file_scan (즉시 스캔)
  │
  └── ZIP 직접 업로드
        security_scan/ → suppressor /file_scan
  │
  │         [suppressor 분석 완료]
  │                  ↓
  └── recevie_result.py ← POST /api/receive
        ├── 자동 정책 판정
        ├── Nexus 위치 조정
        ├── analysis_result/ 저장
        └── AI 판단 (백그라운드)
  │
  │
[관리자 대시보드]
  ├── admin/log.py        ← analysis_result/ 조회
  ├── admin/decision/     ← 승인(review→safe) / 거절(삭제)
  ├── admin/policy.py     ← 자동 정책 설정 변경
  ├── admin/permissions.py ← 유저·권한 관리
  └── nexus/nexus_repo.py ← Nexus 현황 조회·다운로드
```

---

## 패키지별 README

각 서브패키지에 상세 문서가 있습니다.

| 경로                       | 내용                    |
| -------------------------- | ----------------------- |
| `admin/README.md`          | 관리자 기능 전체        |
| `admin/decision/README.md` | 승인·거절 처리 상세     |
| `ai_judgment/README.md`    | LLM 2차 판단 모듈       |
| `auth/README.md`           | 인증·인가 시스템        |
| `db/migrations/README.md`  | DB 마이그레이션 규칙    |
| `download/README.md`       | 웹 스토어 다운로드 흐름 |
| `install_helper/README.md` | 배치 파일 생성          |
| `nexus/README.md`          | Nexus 연동              |
| `scenario/README.md`       | 시나리오 관리 프록시    |
| `search/README.md`         | 검색 API 오케스트레이션 |
| `search/browser/README.md` | 스토어별 크롤러         |
| `security_scan/README.md`  | 직접 업로드 수신·전송   |

---

## 주요 환경변수 (backend 전체)

| 변수명                                                                      | 사용 위치                                                      | 설명                                                             |
| --------------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------- |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`               | `database.py`                                                  | PostgreSQL 연결                                                  |
| `AUTH_SECRET`                                                               | `auth/security.py`                                             | 토큰 서명 키 (미설정 시 런타임 랜덤, 재시작 시 기존 토큰 무효화) |
| `AUTH_TOKEN_TTL_SECONDS`                                                    | `auth/security.py`                                             | 토큰 유효 시간 (기본 28800초)                                    |
| `SUPPRESSOR_PRIVATE_IP` / `PORT`                                            | `download/download_zip.py`, `security_scan/send_suppressor.py` | suppressor 서버 주소                                             |
| `SUPPRESSOR_PORT`                                                           | `scenario/scenario_id.py`                                      | suppressor 서버 포트                                             |
| `NEXUS_BASE_URL` / `NEXUS_REPOSITORY` / `NEXUS_USERNAME` / `NEXUS_PASSWORD` | `nexus/`, `admin/decision/`                                    | Nexus 연동                                                       |
| `ENABLE_AI_JUDGMENT`                                                        | `recevie_result.py`                                            | LLM 2차 판단 활성화 (기본 `true`)                                |
| `LOCAL_LLM_URL` / `LOCAL_LLM_MODEL`                                         | `ai_judgment/judge.py`                                         | Ollama 엔드포인트·모델                                           |
| `SLACK_WEBHOOK_URL`                                                         | `ai_judgment/slack.py`                                         | AI 판단 Slack 알림 웹훅                                          |
| `SEARCH_CACHE_TTL_SECONDS`                                                  | `search/search.py`                                             | 검색 결과 캐시 TTL (기본 300초)                                  |
