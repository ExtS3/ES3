# CLAUDE.md — suppressor 작업 네비게이션

이 문서는 Claude Code가 **suppressor** 레포에서 코드 수정 또는 기능 추가 작업을 받았을 때, 레포 전체를 처음부터 훑지 않고 **작업 대상 위치를 즉시 파악**하기 위한 네비게이션 문서다.

> **사용 원칙**: 아래 "작업 유형별 진입 위치" 표에서 작업에 맞는 진입 위치를 찾고, **해당 폴더의 README.md를 먼저 읽은 뒤** 작업에 착수한다. 전체 레포를 순차적으로 훑지 않는다. 상세 동작은 이 문서가 아니라 각 폴더의 README.md에 있다.

---

## 레포 기본 정보

- **레포명**: suppressor
- **역할**: Chrome/VSCode 확장 프로그램 보안 분석 서버. ExtS3-Web-UI에서 전송된 확장 ZIP을 받아 분석 결과를 반환
- **진입점**: `main.py` (루트) — FastAPI 앱, `/file_scan` 엔드포인트, 전체 분석 파이프라인 오케스트레이션
- **실행 포트**: 8001
- **연관 레포**: `ExtS3-Web-UI` (웹 UI + 백엔드, 별도 레포 `../ExtS3-Web-UI/`. 향후 이 레포와 합쳐질 예정)

---

## 실제 분석 파이프라인 (코드 기준 실행 순서)

```
POST /file_scan
  │
  ├─ 분기: browser == "vscode" → backend/vscode_analysis/ 만 실행 후 반환
  │
  ├─ 1. Dynamic RAG   Dynamic_RAG/rag_fingerprint/ → vector_fingerprint
  │                   embedding/embed.py            → bge-m3 임베딩
  │                   embedding/compare.py          → pgvector 유사도 검색
  │                   embedding/rerank/             → 증거 기반 재순위화
  │                   embedding/scenario/           → LLM + Playwright 동적 실행
  │
  ├─ 2. 정적 분석     backend/extanalysis_integration.py → ExtAnalysis 래퍼
  │                   backend/static_analysis.py         → 5개 스캐너 실행
  │                   backend/clamav_scan.py             → ClamAV (선택)
  │
  ├─ 3. 난독화 탐지   backend/scanners/minify_obfuscation.py
  │
  ├─ 4. 리스크 집계   backend/risk_scoring.py (dynamic:0.65 / static:0.20 / obf:0.15)
  │
  ├─ 5. 프로필 저장   backend/profile/ → 버전별 변경 이력 · diff
  │
  └─ 6. 결과 전송     send_web.py → ExtS3-Web-UI
                      slack/      → Slack 알림
                      Nexus       → ZIP 업로드
```

---

## 전체 디렉토리 구조

```
suppressor/
├── main.py                          # FastAPI 진입점, 전체 분석 파이프라인
├── holding.py                       # /api/holding 라우터
├── send_web.py                      # ExtS3-Web-UI로 결과 전송
│
├── backend/                         # 백엔드 분석 모듈
│   ├── extanalysis_integration.py   # ExtAnalysis 래퍼 (ZIP 해제·VT 우회)
│   ├── static_analysis.py           # 정적 스캐너 통합 러너
│   ├── risk_scoring.py              # 가중치 기반 최종 리스크 계산
│   ├── clamav_scan.py               # ClamAV 보조 스캔
│   ├── web_payload.py               # 결과 페이로드 구성
│   ├── vscode_analysis/             # VSCode(VSIX) 전용 Tier1 정적 분석
│   ├── profile/                     # 버전별 Extension 변경 이력 · diff
│   ├── scanners/                    # 5개 정적 스캐너 + 난독화 탐지
│   └── tests/                       # 단위 테스트 (pytest, 88개)
│
├── Dynamic_RAG/                     # 확장 정적 지문 추출
│   ├── rag_fingerprint/             # vector_fingerprint.json 생성 파이프라인 (12개 py)
│   └── config/                      # capability_mapping.json
│
├── embedding/                       # 임베딩 · 유사도 · 동적 시나리오 분석
│   ├── embed.py                     # bge-m3 임베딩 생성
│   ├── base_db.py                   # pgvector seed 적재
│   ├── pgvector_store.py            # PostgreSQL+pgvector 계층
│   ├── compare.py                   # 코사인 유사도 검색
│   ├── scenario_router.py           # /api/scenario/* 라우터
│   ├── rerank/                      # 증거 기반 재순위화 (4개 py)
│   ├── scenario/                    # LLM 에이전트 + Playwright 동적 분석 (15개 py)
│   ├── base/                        # 벡터 DB seed (26개 악성 패턴 JSON)
│   └── scenario_docs/               # 26개 시나리오 LLM 참조 문서
│
├── ExtAnalysis/                     # 외부 오픈소스 (MIT, Tuhinshubhra)
│   └── core/                        # 분석 코어 (suppressor가 직접 import)
│
├── hm_new/                          # 확장 홀딩 큐 매니저
├── retro/                           # 승인 확장 주기적 재점검 모니터
├── slack/                           # Slack 알림 전송
└── scripts/                         # CI 자동화 (PR 규칙 검사·생성·코드 리뷰)
```

---

## 작업 유형별 진입 위치

> 각 작업의 **진입 위치**로 이동하기 전에, 표의 **README** 열에 명시된 README.md를 반드시 먼저 읽는다.

### 분석 파이프라인 수정

| 작업                                  | 진입 위치                                | README                              |
| ------------------------------------- | ---------------------------------------- | ----------------------------------- |
| 전체 파이프라인 흐름·순서 변경        | `main.py`                                | `README.md`                         |
| 정적 분석 진입·ExtAnalysis 연동       | `backend/extanalysis_integration.py`     | `backend/README.md`                 |
| 정적 스캐너 추가·수정 (manifest/code) | `backend/scanners/`                      | `backend/scanners/README.md`        |
| 난독화 탐지 수정                      | `backend/scanners/minify_obfuscation.py` | `backend/scanners/README.md`        |
| 최종 리스크 가중치·집계 수정          | `backend/risk_scoring.py`                | `backend/README.md`                 |
| ClamAV 연동 수정                      | `backend/clamav_scan.py`                 | `backend/README.md`                 |
| VSCode(VSIX) 전용 분석 수정           | `backend/vscode_analysis/`               | `backend/vscode_analysis/README.md` |
| Extension Profile·버전 diff 수정      | `backend/profile/`                       | `backend/profile/README.md`         |
| 결과 페이로드 구성 수정               | `backend/web_payload.py`                 | `backend/README.md`                 |
| ExtS3-Web-UI로 결과 전송 수정         | `send_web.py`                            | `README.md`                         |

### Dynamic RAG (지문 추출·벡터 검색)

| 작업                                                     | 진입 위치                                     | README                                  |
| -------------------------------------------------------- | --------------------------------------------- | --------------------------------------- |
| 지문 추출 파이프라인 전체                                | `Dynamic_RAG/rag_fingerprint/analyzer.py`     | `Dynamic_RAG/rag_fingerprint/README.md` |
| JS 코드 패턴 스캔 수정                                   | `Dynamic_RAG/rag_fingerprint/code_scanner.py` | `Dynamic_RAG/rag_fingerprint/README.md` |
| capability 매핑 수정                                     | `Dynamic_RAG/config/capability_mapping.json`  | `Dynamic_RAG/config/README.md`          |
| capability 매핑 수정 (주의: 수정 후 벡터 DB 재적재 필요) | `Dynamic_RAG/config/capability_mapping.json`  | `Dynamic_RAG/config/README.md`          |
| CLI 지문 추출 실행                                       | `Dynamic_RAG/rag_fingerprint/main.py`         | `Dynamic_RAG/README.md`                 |
| 전체 Dynamic_RAG 흐름 파악                               | `Dynamic_RAG/`                                | `Dynamic_RAG/README.md`                 |

### 임베딩·유사도·동적 시나리오

| 작업                                  | 진입 위치                                          | README                              |
| ------------------------------------- | -------------------------------------------------- | ----------------------------------- |
| 임베딩 벡터 생성 수정 (Ollama bge-m3) | `embedding/embed.py`                               | `embedding/README.md`               |
| pgvector DB 연결·검색·삽입 수정       | `embedding/pgvector_store.py`                      | `embedding/README.md`               |
| 벡터 DB seed 적재 수정                | `embedding/base_db.py`                             | `embedding/README.md`               |
| 유사도 검색 수정                      | `embedding/compare.py`                             | `embedding/README.md`               |
| 재순위화(rerank) 수정                 | `embedding/rerank/pipeline.py`                     | `embedding/rerank/README.md`        |
| 동적 시나리오 에이전트 수정           | `embedding/scenario/pipeline.py`                   | `embedding/scenario/README.md`      |
| LLM 에이전트 루프 수정                | `embedding/scenario/dynamic_agent.py`              | `embedding/scenario/README.md`      |
| Playwright 브라우저 제어 수정         | `embedding/scenario/playwright_dynamic_harness.py` | `embedding/scenario/README.md`      |
| LLM 프롬프트 수정                     | `embedding/scenario/prompt_builder.py`             | `embedding/scenario/README.md`      |
| 동적 리스크 분류 수정                 | `embedding/scenario/risk_classifier.py`            | `embedding/scenario/README.md`      |
| 악성 패턴 seed 추가·수정              | `embedding/base/`                                  | `embedding/base/README.md`          |
| 시나리오 LLM 참조 문서 수정           | `embedding/scenario_docs/`                         | `embedding/scenario_docs/README.md` |
| 시나리오 관리 API 수정                | `embedding/scenario_router.py`                     | `embedding/README.md`               |

### 부가 기능

| 작업                                   | 진입 위치                                | README             |
| -------------------------------------- | ---------------------------------------- | ------------------ |
| 홀딩 API 수정 (/api/holding)           | `holding.py` + `hm_new/`                 | `hm_new/README.md` |
| 홀딩 스케줄러·Nexus 연동 수정          | `hm_new/scheduler.py`, `hm_new/nexus.py` | `hm_new/README.md` |
| 재점검 모니터 수정 (버전 탐지·VT·YARA) | `retro/retro_monitor.py`                 | `retro/README.md`  |
| Slack 알림 수정                        | `slack/main.py`                          | `slack/README.md`  |
| Nexus 플러그인 다운로드 수정           | `main.py` (`/api/plugins/download`)      | `README.md`        |

### 테스트

| 작업                            | 진입 위치                        | README                                    |
| ------------------------------- | -------------------------------- | ----------------------------------------- |
| VSCode 룰 엔진 테스트 (66개)    | `backend/tests/vscode_analysis/` | `backend/tests/vscode_analysis/README.md` |
| Extension Profile 테스트 (22개) | `backend/tests/profile/`         | `backend/tests/profile/README.md`         |
| 전체 테스트 실행                | `pytest backend/tests`           | `backend/tests/README.md`                 |

### 인프라·CI

| 작업                  | 진입 위치                                        | README                       |
| --------------------- | ------------------------------------------------ | ---------------------------- |
| pgvector DB 로컬 실행 | `docker-compose.pgvector.yml`                    | `README.md`                  |
| 자동 PR 파이프라인    | `scripts/check_rules.py`, `scripts/create_pr.py` | `scripts/README.md`          |
| 자동 코드 리뷰        | `scripts/review_pr.py`                           | `scripts/README.md`          |
| PR 규칙 정의          | `.github/pipeline-rules.yml`                     | `scripts/README.md`          |
| ExtAnalysis 통합 방식 | `ExtAnalysis/`                                   | `ExtAnalysis/INTEGRATION.md` |

---

## 작업 전 필수 규칙

1. **작업 전 해당 위치의 README.md를 반드시 먼저 읽는다.** 위 표에서 진입 위치를 찾고, README.md를 읽은 뒤 작업한다. 전체 레포를 순차적으로 훑지 않는다.

2. **새 API 엔드포인트를 추가할 때**는 `backend/` 하위 해당 모듈에 로직을 작성하고 `main.py`에 `app.include_router()`로 등록한다. `main.py`에 직접 비즈니스 로직을 작성하지 않는다.

3. **분석 파이프라인 단계를 추가·수정할 때**는 각 단계가 실패해도 나머지 분석이 계속 진행되도록 `try/except`로 감싸고 `{"status": "error", "message": ...}` 형태로 폴백한다. 기존 단계들의 패턴을 따른다.

4. **pgvector 관련 작업** 시 `embedding/pgvector_store.py`를 통해서만 DB에 접근한다. `psycopg2`를 다른 파일에서 직접 import하지 않는다.

5. **`Dynamic_RAG/config/capability_mapping.json`을 수정**하면 기존 벡터 DB와 불일치가 생긴다. 수정 후 반드시 `POST /api/scenario/reload`로 벡터 DB를 재적재한다.

6. **악성 패턴 seed(`embedding/base/`)를 추가**할 때는 `embedding/scenario_docs/`에 동일한 이름의 `.md` 문서도 함께 작성한다. 두 파일은 1:1 대응이 유지되어야 한다.

7. **VSCode 룰(`backend/vscode_analysis/rules.py`)을 수정**할 때는 `backend/tests/vscode_analysis/`의 테스트를 반드시 통과시킨다. 특히 `test_runner_glassworm.py`(E2E)와 `test_corpus_benign.py`(오탐 방지)를 확인한다.

8. **ExtAnalysis(`ExtAnalysis/`)는 외부 오픈소스**다. `core/` 내부 코드를 직접 수정하지 않는다. 동작을 바꿔야 할 경우 `backend/extanalysis_integration.py`의 monkey-patching 방식을 사용한다.

9. **suppressor는 감지기 역할만 한다.** `recommended_decision`은 항상 `"review"`를 반환하며, 최종 승인/거부 정책은 ExtS3-Web-UI가 결정한다. 이 원칙을 바꾸는 코드를 작성하지 않는다.

10. **이 파일(CLAUDE.md)과 각 폴더의 README.md는 코드 변경과 함께 업데이트한다.** 새 파일을 추가하거나 구조를 변경하면 해당 위치의 README.md와 이 파일의 구조도를 함께 반영한다.

---

## 연관 레포 참고

- **ExtS3-Web-UI** (`../ExtS3-Web-UI/`) — 웹 UI + 백엔드 API. suppressor로 파일을 전송하고 분석 결과를 수신한다. 향후 이 레포와 통합될 예정이다.
- 두 레포는 현재 독립 실행 구조이며, suppressor는 포트 8001, ExtS3-Web-UI는 포트 8000을 사용한다.
