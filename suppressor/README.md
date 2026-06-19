# suppressor

Chrome/VSCode 확장 프로그램 보안 분석 서버입니다. ExtS3-Web-UI에서 전송된 확장 ZIP을 받아 **동적 RAG → 정적 분석 → 난독화 탐지** 순으로 실행하고 최종 리스크를 산출합니다.

> suppressor는 **감지기 + 보고기** 역할만 합니다. 최종 승인/거부 정책은 ExtS3-Web-UI가 결정합니다. 모든 `recommended_decision`은 항상 `review`로 반환됩니다.

---

## 전체 분석 파이프라인

`POST /file_scan` 실행 순서 (코드 기준):

```
POST /file_scan
  │
  ├─ 분기: browser == "vscode"
  │     └─ backend/vscode_analysis/ 정적 룰만 실행 → 결과 반환 (이하 단계 생략)
  │
  ├─ 1. Dynamic RAG        Dynamic_RAG/rag_fingerprint/ → vector_fingerprint 생성
  │                        embedding/embed.py           → bge-m3 임베딩
  │                        embedding/compare.py         → pgvector 유사도 검색
  │                        embedding/rerank/            → 증거 기반 재순위화
  │                        embedding/scenario/          → LLM 에이전트 + Playwright 동적 실행
  │                        → final_risk (LOW/MEDIUM/HIGH/CRITICAL)
  │
  ├─ 2. 정적 분석          backend/extanalysis_integration.py
  │                        → ExtAnalysis (manifest/URL/source.json 수집)
  │                        → backend/static_analysis.py (4개 스캐너 순차 실행)
  │                        → backend/clamav_scan.py (ClamAV 시그니처, 선택)
  │
  ├─ 3. 난독화 탐지        backend/scanners/minify_obfuscation.py (PracticalScanner)
  │                        → benign_minify / suspicious_obfuscation /
  │                           likely_malicious_obfuscation / readable_script
  │
  ├─ 4. 결과 저장          results_json/{extID}_{version}/ 에 JSON 6종 저장
  │
  ├─ 5. 리스크 집계        backend/risk_scoring.calculate_weighted_final_risk
  │                        가중치: dynamic 0.65 / static 0.20 / obfuscation 0.15
  │
  ├─ 6. Extension Profile  backend/profile/ → 버전별 변경 이력 · diff 생성
  │
  └─ 7. 결과 전송          send_web.py  → ExtS3-Web-UI (/api/receive)
                           slack/       → Slack 알림 (ENABLE_SLACK_FORWARD)
                           Nexus        → ZIP 업로드 (ENABLE_NEXUS_UPLOAD)
```

**리스크 판정 기준**

| 리스크   | 점수 범위 | 권장 조치      |
| -------- | --------- | -------------- |
| LOW      | < 0.30    | 자동 승인 고려 |
| MEDIUM   | 0.30–0.55 | 수동 검토      |
| HIGH     | 0.55–0.80 | 격리 후 검토   |
| CRITICAL | ≥ 0.80    | 차단 우선      |

---

## 주요 엔드포인트

| 메서드 | 경로                    | 설명                            |
| ------ | ----------------------- | ------------------------------- |
| POST   | `/file_scan`            | 확장 ZIP 수신 및 전체 분석 실행 |
| POST   | `/api/holding`          | 확장 홀딩 등록 (hm_new)         |
| GET    | `/api/plugins/download` | Nexus에서 ZIP 다운로드          |
| GET    | `/api/scenario/list`    | 시나리오 목록 조회              |
| POST   | `/api/scenario/upload`  | 시나리오 업로드                 |
| POST   | `/api/scenario/reload`  | 벡터 DB 전체 재적재             |

### `/file_scan` 요청 포맷 (multipart/form-data)

| 필드      | 타입 | 설명                                     |
| --------- | ---- | ---------------------------------------- |
| `file`    | File | 확장 ZIP/VSIX 파일                       |
| `extID`   | str  | 확장 식별자 (Chrome Extension ID 등)     |
| `browser` | str  | `chrome` / `edge` / `firefox` / `vscode` |
| `version` | str  | 버전 문자열                              |
| `extName` | str  | 확장 표시 이름                           |

---

## 디렉토리 구조

```
suppressor/
├── main.py                    # FastAPI 앱 진입점 · 전체 분석 오케스트레이션
├── holding.py                 # /api/holding 라우터
├── send_web.py                # ExtS3-Web-UI로 결과 전송
├── .env.example               # 환경변수 예시 (복사 후 .env로 저장)
├── docker-compose.pgvector.yml # pgvector DB 로컬 실행용
├── requirements.txt
│
├── backend/                   # 백엔드 분석 모듈
│   ├── extanalysis_integration.py  # ExtAnalysis 래퍼
│   ├── static_analysis.py          # 정적 스캐너 통합 러너
│   ├── risk_scoring.py             # 가중치 기반 최종 리스크 계산
│   ├── clamav_scan.py              # ClamAV 보조 스캔
│   ├── web_payload.py              # 결과 페이로드 구성
│   ├── database.py                 # PostgreSQL 연결 풀
│   ├── vscode_analysis/            # VSCode(VSIX) 전용 Tier1 정적 분석
│   ├── profile/                    # 버전별 Extension 변경 이력 · diff
│   ├── scanners/                   # 4개 정적 스캐너 + 난독화 탐지
│   └── tests/                      # 단위 테스트 (pytest, 88개)
│
├── Dynamic_RAG/               # 확장 정적 지문 추출
│   ├── rag_fingerprint/       # vector_fingerprint.json 생성 파이프라인
│   └── config/                # capability_mapping.json
│
├── embedding/                 # 임베딩 · 유사도 · 동적 시나리오 분석
│   ├── embed.py               # bge-m3 임베딩 생성
│   ├── base_db.py             # pgvector seed 적재
│   ├── pgvector_store.py      # PostgreSQL+pgvector 계층
│   ├── compare.py             # 코사인 유사도 검색
│   ├── scenario_router.py     # /api/scenario/* 라우터
│   ├── rerank/                # 증거 기반 재순위화
│   ├── scenario/              # LLM 에이전트 + Playwright 동적 분석
│   ├── base/                  # 벡터 DB seed (26개 악성 패턴 JSON)
│   └── scenario_docs/         # 26개 시나리오 LLM 참조 문서
│
├── ExtAnalysis/               # 외부 오픈소스 (MIT, Tuhinshubhra)
│   ├── core/                  # 분석 코어 (suppressor가 직접 import)
│   ├── db/permissions.json    # 권한 위험도 참조 DB
│   └── INTEGRATION.md         # suppressor 통합 방식 설명
│
├── hm_new/                    # 확장 홀딩 큐 매니저
│   ├── manager.py             # 홀딩 등록
│   ├── scheduler.py           # watchdog + APScheduler 릴리즈 스케줄러
│   ├── nexus.py               # Nexus holding 레포 연동
│   └── pending/               # 홀딩 대기 파일 (.gitignore 등록)
│
├── retro/                     # 승인 확장 주기적 재점검 모니터
│   └── retro_monitor.py       # 새 버전 탐지 + VT/YARA 평판 검사
│
├── slack/
│   └── main.py                # Slack 알림 전송
│
└── scripts/                   # CI 자동화 (PR 규칙 검사 · 생성 · 코드 리뷰)
```

---

## 환경 구축

### 사전 준비

- Python 3.11+
- PostgreSQL 16 + pgvector 확장 (아래 Docker 방식 또는 직접 설치)
- Ollama (임베딩 + LLM)
- Nexus Repository 3 (선택)
- ClamAV (선택)

### 1단계 — 코드 받기

```bash
git clone <repo-url> suppressor
cd suppressor
```

### 2단계 — Python 환경 설정

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### 3단계 — pgvector DB 실행

Docker를 사용하는 경우:

```bash
docker compose -f docker-compose.pgvector.yml up -d
```

> 컨테이너 포트가 `5433`으로 매핑됩니다. `.env`에 `PGVECTOR_DB_PORT=5433`을 반드시 설정하세요.

직접 설치하는 경우:

```sql
-- PostgreSQL에서 pgvector 활성화
CREATE EXTENSION IF NOT EXISTS vector;
```

### 4단계 — Ollama 모델 다운로드

```bash
ollama pull bge-m3
ollama pull qwen2.5:1.5b-instruct-q4_K_M
```

### 5단계 — 환경변수 설정

```bash
cp .env.example .env
# .env를 열어 실제 값으로 채우기
```

**최소 필수 설정:**

```env
# pgvector DB
PGVECTOR_DB_HOST=localhost
PGVECTOR_DB_PORT=5433           # docker-compose.pgvector.yml 사용 시
PGVECTOR_DB_USER=your_db_user
PGVECTOR_DB_PASSWORD=your_db_password
PGVECTOR_DB_NAME=your_db_name

# 결과 전달
WEB_RECEIVE_URL=http://localhost:8000/api/receive

# Nexus (사용 시)
NEXUS_BASE_URL=http://localhost:8081
NEXUS_REPOSITORY=es3
NEXUS_USERNAME=admin
NEXUS_PASSWORD=your_nexus_password
```

전체 환경변수 목록은 `.env.example` 참고.

### 6단계 — 서버 실행

```bash
uvicorn main:app --host 0.0.0.0 --port 8001
```

개발 시 자동 재시작:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

서버 시작 시 자동으로 수행됩니다:

- pgvector에 seed 데이터 26개 적재 (`ensure_knowledge_base_seeded`)
- hm_new 홀딩 스케줄러 시작
- retro 백그라운드 모니터 스레드 시작

---

## 동적 분석 환경

동적 분석은 Playwright로 실제 Chromium 브라우저를 제어합니다.

**headless 모드 (기본, 서버 환경):**

```env
DYNAMIC_HARNESS_HEADLESS=true
```

Linux 서버에서 headless가 안 될 경우 가상 디스플레이를 사용합니다:

```bash
Xvfb :99 -screen 0 1280x720x24 &
export DISPLAY=:99
```

**headed 모드 (로컬 디버깅):**

```env
DYNAMIC_HARNESS_HEADLESS=false
```

**타임아웃 조정:**

```env
DYNAMIC_ANALYSIS_TIMEOUT_SEC=120    # 전체 동적 분석 타임아웃
SERVICE_WORKER_TIMEOUT_MS=5000      # 서비스 워커 대기
```

---

## 분석 동작 확인

서버가 실행 중일 때 curl로 테스트합니다:

```bash
curl -X POST http://localhost:8001/file_scan \
  -F "file=@/path/to/extension.zip" \
  -F "extID=abcdefghijklmnopabcdefghijklmnop" \
  -F "browser=chrome" \
  -F "version=1.0.0" \
  -F "extName=TestExtension"
```

VSCode 확장 테스트:

```bash
curl -X POST http://localhost:8001/file_scan \
  -F "file=@/path/to/extension.vsix" \
  -F "extID=publisher.extension-name" \
  -F "browser=vscode" \
  -F "version=1.0.0" \
  -F "extName=TestExtension"
```

---

## 단위 테스트

```bash
# 전체 테스트
pytest backend/tests

# 폴더별
pytest backend/tests/vscode_analysis   # VSCode 룰 엔진 (66개)
pytest backend/tests/profile           # Extension Profile (22개)
```

---

## 기술 스택

| 역할      | 기술                                         |
| --------- | -------------------------------------------- |
| 서버      | Python 3.11 · FastAPI · Uvicorn              |
| 스케줄러  | APScheduler · watchdog                       |
| 정적 분석 | ExtAnalysis · ClamAV                         |
| 동적 분석 | Playwright (Chromium)                        |
| AI/ML     | Ollama (qwen2.5 · bge-m3) · numpy            |
| 벡터 DB   | PostgreSQL 16 + pgvector                     |
| 외부 연동 | Nexus Repository · Slack · VirusTotal (선택) |

---

## 설계 원칙

1. **증거 기반 탐지** — 모호한 휴리스틱보다 명확한 증거를 우선합니다. 동적 에이전트가 실제로 관찰한 네트워크 요청·스토리지 접근·DOM 조작이 판정의 근거가 됩니다.
2. **안전한 격리 환경** — 동적 분석은 mock page와 dummy value만 사용하고 실제 서비스 접근과 외부 전송을 차단합니다.
3. **감지기 역할 분리** — suppressor는 위험 신호를 보고하며, 최종 승인/거부 정책은 ExtS3-Web-UI가 담당합니다.
4. **단계별 폴백** — 임베딩 실패, LLM 오류, Playwright 충돌 등 각 단계가 실패해도 나머지 분석은 계속 진행됩니다.

---

## 주의사항 및 제한

- **동적 분석 시간 제한** — 각 시나리오는 최대 8 라운드(LLM 액션), 전체 타임아웃 내에서 실행됩니다. 모든 코드 경로가 실행되지는 않습니다.
- **확률적 판정** — 위험도 평가는 확률적이며 위음성/위양성이 존재할 수 있습니다.
- **Chrome Web Store 스크래핑** — retro 모니터의 버전 비교는 스토어 UI 변경 시 파싱 실패 가능성이 있습니다.
- **pgvector 재적재** — `embedding/base/` 또는 `config/capability_mapping.json`을 수정하면 `POST /api/scenario/reload`로 벡터 DB를 재적재해야 합니다.

---

## 하위 모듈 문서

| 경로                                    | 내용                                |
| --------------------------------------- | ----------------------------------- |
| `backend/README.md`                     | 백엔드 모듈 전체 구조               |
| `backend/vscode_analysis/README.md`     | VSCode Tier1 룰 엔진                |
| `backend/profile/README.md`             | Extension Profile · diff            |
| `backend/tests/README.md`               | 단위 테스트 전체                    |
| `Dynamic_RAG/README.md`                 | 정적 지문 추출 파이프라인           |
| `Dynamic_RAG/rag_fingerprint/README.md` | 지문 생성 12개 모듈                 |
| `embedding/README.md`                   | 임베딩 · 유사도 · 동적 시나리오     |
| `embedding/rerank/README.md`            | 재순위화 모듈                       |
| `embedding/scenario/README.md`          | LLM 에이전트 · Playwright 동적 분석 |
| `embedding/base/README.md`              | 벡터 DB seed 26개 패턴              |
| `embedding/scenario_docs/README.md`     | LLM 시나리오 참조 문서              |
| `hm_new/README.md`                      | 확장 홀딩 큐 매니저                 |
| `retro/README.md`                       | 주기적 재점검 모니터                |
| `slack/README.md`                       | Slack 알림                          |
| `scripts/README.md`                     | CI 자동화                           |
| `ExtAnalysis/INTEGRATION.md`            | ExtAnalysis 통합 방식               |
