# suppressor

Chrome 확장 프로그램 보안 분석 서버. ExtS3-Web-UI에서 전송된 확장 ZIP을 받아 정적 분석·난독화 탐지·동적 RAG 분석을 순차 실행하고 최종 리스크를 산출합니다.

## 전체 분석 파이프라인

```
POST /file_scan
      │
      ├─ 1. ExtAnalysis  →  manifest/파일/URL/source.json 수집
      ├─ 2. 정적 분석    →  manifest_permission / manifest_behavior /
      │                      code_execution / code_navigation 스캐너
      ├─ 3. ClamAV       →  알려진 악성 시그니처 스캔 (선택)
      ├─ 4. 난독화 탐지  →  minify_obfuscation.PracticalScanner
      ├─ 5. Dynamic RAG  →  RAG 지문 추출 → 임베딩 유사도 매칭 →
      │                      LLM 에이전트 동적 시나리오 실행
      ├─ 6. 리스크 집계  →  risk_scoring.calculate_weighted_final_risk
      │                      (dynamic:0.65, static:0.20, obfuscation:0.15)
      └─ 7. 결과 전송    →  Web(ExtS3) / Slack / Nexus 업로드
```

리스크 판정: `LOW` → approve / `MEDIUM|HIGH|CRITICAL` → review

## 주요 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/file_scan` | 확장 ZIP 수신 및 전체 분석 실행 |
| POST | `/api/holding` | 확장 ID 홀딩 등록 (hm_new) |
| GET | `/api/plugins/download` | Nexus에서 ZIP 다운로드 |

## 기술 스택

- **서버**: Python 3.11 · FastAPI · Uvicorn · APScheduler
- **분석**: ExtAnalysis · ClamAV · Playwright · minify_obfuscation
- **AI/ML**: Ollama (qwen2.5) · mmh3 (벡터 해시) · numpy
- **외부 연동**: Nexus Repository · Supabase · Slack
- **기타**: python-dotenv · sentry-sdk · psycopg2-binary

## 디렉토리 구조

```
suppressor/
├── main.py                    # FastAPI 앱 진입점 · 전체 분석 오케스트레이션
├── minify_obfuscation.py      # PracticalScanner — JS 난독화/미니파이 판별기
├── judge.py                   # 최종 판정 로직
├── send_web.py                # ExtS3 Web UI로 결과 전송
├── holding.py                 # 홀딩 API 핸들러
├── requirements.txt
│
├── backend/                   # 스캔·분석·리스크 모듈
│   ├── extanalysis_integration.py  # ExtAnalysis 래퍼 (ZIP 해제·manifest 탐색·VT 우회)
│   ├── static_analysis.py          # 정적 스캐너 통합 러너
│   ├── risk_scoring.py             # 가중치 기반 최종 리스크 계산
│   ├── clamav_scan.py              # ClamAV 보조 스캔
│   ├── web_payload.py              # 결과 페이로드 구성
│   └── scanners/
│       ├── manifest_permission_scan.py  # permissions / host_permissions 탐지
│       ├── manifest_behavior_scan.py    # background / service_worker / WAR 탐지
│       ├── code_execution_scan.py       # eval / atob / new Function 탐지
│       ├── code_navigation_scan.py      # fetch / XHR / URL 문맥 분류
│       └── common.py                    # 공통 유틸 (source_map 로드, 결과 요약)
│
├── Dynamic_RAG/               # 정적 지문 추출 모듈
│   ├── rag_fingerprint/       # 확장 코드 → vector_fingerprint.json 변환
│   │   ├── main.py            # CLI 진입점 (extract 명령)
│   │   ├── analyzer.py        # 통합 분석기
│   │   ├── code_scanner.py    # JS 코드 패턴 스캔
│   │   ├── manifest_parser.py # manifest.json 파싱
│   │   ├── fingerprint_builder.py # 지문 JSON 생성
│   │   └── capability_mapper.py   # 능력 → 위협 카테고리 매핑
│   ├── config/capability_mapping.json
│   └── README.md → [Dynamic_RAG/README.md](Dynamic_RAG/README.md)
│
├── embedding/                 # 임베딩·유사도·동적 시나리오 분석
│   ├── embed.py               # 벡터 임베딩 생성
│   ├── base_db.py             # 기준 벡터 DB 로드
│   ├── compare.py             # 코사인 유사도 비교
│   ├── rerank/                # 매칭 결과 재순위화
│   │   ├── pipeline.py        # 리랭크 파이프라인
│   │   ├── feature_builder.py # 특징 벡터 생성
│   │   └── scorer.py          # 최종 점수 계산
│   ├── scenario/              # LLM 동적 시나리오 에이전트
│   │   ├── pipeline.py        # run_multi_scenario_dynamic_rag_analysis
│   │   ├── dynamic_agent.py   # LLM 에이전트 루프
│   │   ├── playwright_dynamic_harness.py # Playwright 브라우저 제어
│   │   ├── prompt_builder.py  # LLM 프롬프트 생성
│   │   ├── evidence_scorer.py # 시나리오별 증거 점수 계산
│   │   └── risk_classifier.py # 최종 동적 리스크 분류
│   ├── base/                  # 벡터 DB seed 데이터 (19개 악성 패턴 JSON)
│   ├── scenario_docs/         # 21개 동적 시나리오 문서 (LLM 참조용)
│   └── README.md → [embedding/README.md](embedding/README.md)
│
├── ExtAnalysis/               # 외부 라이브러리 (패키지 수집기 역할)
│   ├── core/                  # 분석 코어 (analyze, downloader, scans 등)
│   ├── frontend/              # ExtAnalysis 자체 웹 UI (현재 비활성)
│   └── db/permissions.json    # 권한 위험도 참조 데이터
│
├── hm_new/                    # 확장 홀딩 큐 매니저
│   ├── manager.py             # 홀딩 등록 API
│   ├── scheduler.py           # pending 폴더 감시 + 만료 릴리즈 스케줄링
│   ├── nexus.py               # Nexus holding 레포 연동
│   ├── pending/               # 홀딩 대기 파일 저장소
│   └── released/              # 릴리즈 완료 파일 저장소
│
├── retro/                     # 승인된 확장 주기적 재점검 모니터
│   ├── retro_monitor.py       # 새 버전 탐지 + VirusTotal/YARA 평판 검사
│   └── requirements-retro-monitor.txt
│
├── slack/
│   └── main.py                # Slack 알림 전송
│
├── legacy/                    # 구버전 코드 (미사용)
├── legacy2/                   # 구버전 난독화 파이프라인 (미사용)
├── pending_files/             # 분석 대기 확장 ZIP 파일들
│
├── STATIC_ANALYSIS_GUIDE.md  → [STATIC_ANALYSIS_GUIDE.md](STATIC_ANALYSIS_GUIDE.md)
├── obfuscation_README.md     → [obfuscation_README.md](obfuscation_README.md)
└── dynamic_readme.md         → [dynamic_readme.md](dynamic_readme.md)
```

## 설치 및 실행

```bash
cd suppressor
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m playwright install chromium
ollama pull bge-m3
ollama pull qwen2.5:1.5b-instruct-q4_K_M
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### `/file_scan` 요청 포맷 (multipart/form-data)

| 필드 | 타입 | 설명 |
|------|------|------|
| `file` | File | 확장 ZIP 파일 |
| `extID` | str | 확장 식별자 (Chrome Extension ID 등) |
| `browser` | str | `chrome` / `edge` / `firefox` |
| `version` | str | 버전 문자열 |
| `extName` | str | 확장 표시 이름 |

## 환경 변수

`.env` 파일을 `suppressor/` 루트에 생성합니다.

```env
# Nexus 연동
NEXUS_BASE_URL=http://<nexus-host>
NEXUS_REPOSITORY=<repository-name>
NEXUS_USERNAME=<username>
NEXUS_PASSWORD=<password>

# 결과 전송 토글
ENABLE_WEB_FORWARD=true
ENABLE_SLACK_FORWARD=false
ENABLE_NEXUS_UPLOAD=true

# ClamAV (선택)
CLAMSCAN_PATH=/usr/bin/clamscan
CLAMAV_DATABASE=/path/to/clamav/db

# 동적 분석
DYNAMIC_HARNESS_HEADLESS=true

# 리스크 가중치 (합=1.0, 미설정 시 기본값 사용)
RISK_WEIGHT_DYNAMIC=0.65
RISK_WEIGHT_STATIC=0.20
RISK_WEIGHT_OBFUSCATION=0.15

# LLM (Ollama)
LOCAL_LLM_URL=http://localhost:11434/api/chat
LOCAL_LLM_MODEL=qwen2.5:1.5b-instruct-q4_K_M

# 홀딩 매니저 (hm_new)
HOLDING_SECONDS=604800
NEXUS_REPO=holding

# 모니터링 (retro)
VT_API_KEY=<virustotal-api-key>
RETRO_INTERVAL_HOURS=24
```

## 리스크 판정 기준

| 리스크 | 점수 범위 | 권장 조치 |
|--------|-----------|-----------|
| LOW | < 0.30 | 자동 승인 |
| MEDIUM | 0.30–0.55 | 수동 검토 |
| HIGH | 0.55–0.80 | 격리 후 검토 |
| CRITICAL | ≥ 0.80 | 차단 우선 |

## 하위 모듈 문서

- [Dynamic_RAG/README.md](Dynamic_RAG/README.md) — 정적 지문 추출 파이프라인
- [embedding/README.md](embedding/README.md) — 임베딩 및 동적 시나리오 분석
- [hm_new/README.md](hm_new/README.md) — 확장 홀딩 큐 매니저
- [retro/README.md](retro/README.md) — 주기적 재점검 모니터
- [STATIC_ANALYSIS_GUIDE.md](STATIC_ANALYSIS_GUIDE.md) — 정적 분석 구조 및 로그 해석
- [obfuscation_README.md](obfuscation_README.md) — 난독화 탐지 스캐너 상세
- [dynamic_readme.md](dynamic_readme.md) — 동적 분석 개요
