# embedding — 임베딩·유사도·동적 시나리오 분석 모듈

`Dynamic_RAG`에서 생성된 `vector_fingerprint`를 pgvector(PostgreSQL) 벡터 DB의 기준 패턴과 비교하고, 매칭된 시나리오를 Playwright + LLM 에이전트로 실행해 최종 동적 리스크를 산출합니다.

## 디렉토리 구조

```
embedding/
├── embed.py           # vector_fingerprint → 임베딩 벡터 생성 (Ollama bge-m3)
├── base_db.py         # pgvector 벡터 DB seed/조회 (기준 패턴 적재)
├── pgvector_store.py  # PostgreSQL+pgvector 연결·검색·삽입 (실제 DB 계층)
├── compare.py         # 코사인 유사도 비교 및 매칭 결과 반환
├── scenario_router.py # 시나리오 지식베이스 관리 API (/api/scenario/*)
├── embedding.json     # 최근 생성된 임베딩 캐시 (런타임 산출물)
├── requirements.txt   # 비어있음 (루트 requirements.txt에 의존)
│
├── rerank/            # 증거 기반 재순위화
│   ├── pipeline.py    # rerank_compare_result() — 핵심 리랭크 함수
│   ├── feature_builder.py # 지문 → rerank 특징 벡터 추출
│   └── scorer.py      # capability/behavior 중첩 점수 계산
│
├── scenario/          # LLM 동적 시나리오 에이전트
│   ├── pipeline.py    # run_multi_scenario_dynamic_rag_analysis() — 메인 API
│   ├── dynamic_agent.py   # LLM 에이전트 루프 (Ollama)
│   ├── playwright_dynamic_harness.py # Playwright 브라우저 제어
│   ├── prompt_builder.py  # LLM 프롬프트 생성
│   ├── evidence_scorer.py # 시나리오별 증거 점수 계산
│   ├── risk_classifier.py # 최종 동적 리스크 분류
│   └── ... (총 15개)
│
├── base/              # 벡터 DB seed 데이터 (26개 악성 패턴 JSON)
│   ├── session_storage_exfiltration_document_start.json
│   └── ... (총 26개)
│
└── scenario_docs/     # 26개 동적 시나리오 문서 (LLM 에이전트 참조용)
    ├── session_storage_exfiltration_document_start.md
    └── ... (총 26개)
```

## 전체 파이프라인

```
vector_fingerprint (Dynamic_RAG 출력)
        │
        ▼
embed.py (bge-m3 via Ollama Embeddings API)
        │ 임베딩 벡터
        ▼
compare.py → pgvector_store.search_vectors() → 코사인 유사도 검색
        │ 유사 패턴 후보 목록
        ▼
rerank/pipeline.py (rerank_compare_result)
  - 특징 벡터 기반 점수 보정
  - 확장 파일 직접 스캔으로 구체적 증거 추출
  - 시나리오별 negative penalty/bonus 적용
  - 강한 증거 있으면 해당 패턴 강제 주입
        │ 상위 3개 후보 패턴
        ▼
scenario/pipeline.py (run_multi_scenario_dynamic_rag_analysis)
  - 각 후보 패턴의 scenario_doc 로드
  - Playwright 브라우저 + mock 페이지 준비
  - LLM 에이전트가 시나리오 따라 액션 실행
  - 실행 observation → evidence_scorer → 시나리오 점수
  - 여러 시나리오 결과 → risk_classifier → 최종 리스크
        │
        ▼
final_risk: LOW | MEDIUM | HIGH | CRITICAL
```

## 루트 직속 파일 상세

### embed.py

`embed_fingerprint(fp_data)` — `capability_profile` 항목들을 텍스트로 join해 bge-m3 모델로 임베딩합니다. 실패 시 최대 3회 재시도(1s → 3s → 7s 백오프)하고 마지막까지 실패하면 빈 리스트를 반환합니다. 성공 시 결과를 `embedding/embedding.json`에 캐싱합니다.

Ollama API 버전에 따라 신규 엔드포인트(`/api/embed`, `embeddings` 키)와 구형 엔드포인트(`/api/embeddings`, `embedding` 키)를 자동으로 폴백해 처리합니다.

```python
from embedding.embed import embed_fingerprint
vector = embed_fingerprint(vector_fingerprint)  # → list[float]
```

### base_db.py

벡터 DB seed 적재를 담당합니다. 서버 시작 시 `main.py`의 `lifespan`에서 `ensure_knowledge_base_seeded()`를 호출합니다.

| 함수                                       | 역할                                                                                |
| ------------------------------------------ | ----------------------------------------------------------------------------------- |
| `ensure_knowledge_base_seeded()`           | 벡터 DB가 비어있으면 `store_all_knowledge_base()` 실행, 이미 있으면 건너뜀          |
| `store_all_knowledge_base()`               | `embedding/base/*.json` 전체를 읽어 임베딩 후 pgvector에 삽입                       |
| `normalize_base_record(file_path, data)`   | base JSON을 검증하고 `{pattern_name, doc_ref, vector_fingerprint}` 표준 형태로 변환 |
| `build_embedding_text(vector_fingerprint)` | 지문 dict를 정렬된 compact JSON 문자열로 변환 (임베딩 입력용)                       |
| `build_document_payload(record)`           | pgvector `document` 컬럼에 저장할 JSON 문자열 생성                                  |
| `embed_full_text(text)`                    | 임의 텍스트를 Ollama로 임베딩 (seed 내부용, 재시도 없음)                            |

### pgvector_store.py

PostgreSQL+pgvector와 직접 통신하는 DB 계층입니다. 다른 파일들은 이 파일을 통해서만 DB에 접근합니다.

| 함수                                                      | 역할                                              |
| --------------------------------------------------------- | ------------------------------------------------- |
| `ensure_schema(dim)`                                      | 테이블·pgvector extension 없으면 자동 생성        |
| `insert_vector_record(document, embedding)`               | 문서 + 임베딩 벡터 삽입                           |
| `search_vectors(embedding, match_threshold, match_count)` | 코사인 유사도 검색 (`1 - (embedding <=> vector)`) |
| `count_vectors()`                                         | 저장된 벡터 수 조회                               |
| `clear_vectors()`                                         | 전체 벡터 삭제 (재적재 전 호출)                   |

**환경변수**

| 변수                   | 기본값                | 설명                         |
| ---------------------- | --------------------- | ---------------------------- |
| `PGVECTOR_DB_HOST`     | `localhost`           | DB 호스트 (`DB_HOST`로 폴백) |
| `PGVECTOR_DB_PORT`     | `5432`                | DB 포트                      |
| `PGVECTOR_DB_USER`     | `example_db_user`     | DB 사용자                    |
| `PGVECTOR_DB_PASSWORD` | `example_db_password` | DB 비밀번호                  |
| `PGVECTOR_DB_NAME`     | `example_db_name`     | DB 이름                      |
| `PGVECTOR_TABLE`       | `public.es3_vector`   | 벡터 저장 테이블             |
| `EMBEDDING_DIM`        | `1024`                | 임베딩 차원 (bge-m3 = 1024)  |

### compare.py

`compareDB(embedding_vector)` — pgvector에서 유사도 검색을 실행하고 결과를 정규화해 반환합니다.

`normalize_compare_result_rows(results)` — pgvector 반환 rows를 `{id, score, similarity, payload}` 표준 구조로 변환합니다. `payload`에는 `pattern_name`, `doc_ref`, `vector_fingerprint`가 포함됩니다.

**환경변수**

| 변수                       | 기본값 | 설명                     |
| -------------------------- | ------ | ------------------------ |
| `PGVECTOR_MATCH_THRESHOLD` | `0`    | 유사도 최소 임계값 (0~1) |
| `PGVECTOR_MATCH_COUNT`     | `10`   | 반환할 최대 후보 수      |

> `FALLBACK_PATTERN_NAME = "session_storage_exfiltration_document_start"`가 하드코딩되어 있습니다. document 파싱 실패 시 이 패턴으로 폴백합니다. 해당 패턴이 삭제되면 폴백이 오작동할 수 있어 주의 필요합니다.

### scenario_router.py

시나리오 지식베이스 관리 API 라우터입니다. `main.py`에서 `/api/scenario` prefix로 등록됩니다. ExtS3-Web-UI의 시나리오 관리 페이지가 이 API를 호출합니다.

| 메서드 | 경로                                 | 설명                            |
| ------ | ------------------------------------ | ------------------------------- |
| GET    | `/api/scenario/db-status`            | 벡터 DB 적재 상태 조회          |
| GET    | `/api/scenario/list`                 | 전체 시나리오 목록              |
| GET    | `/api/scenario/detail/{scenario_id}` | 시나리오 상세 + MD 문서         |
| POST   | `/api/scenario/upload`               | JSON(필수)+MD(선택) 업로드      |
| DELETE | `/api/scenario/delete/{scenario_id}` | 개별 삭제 (`builtin=true` 차단) |
| POST   | `/api/scenario/reload`               | 벡터 DB 전체 재적재             |

### requirements.txt

**비어있습니다.** `embedding/` 모듈의 모든 의존성(`psycopg2-binary`, `requests`, `playwright` 등)은 루트 `requirements.txt`에서 관리합니다. 이 파일은 삭제해도 됩니다.

---

## 주요 함수 요약

### `embed_fingerprint(fp_data)` — `embed.py`

```python
from embedding.embed import embed_fingerprint
vector = embed_fingerprint(vector_fingerprint)  # → list[float]
```

### `rerank_compare_result(...)` — `rerank/pipeline.py`

```python
from embedding.rerank import rerank_compare_result
rag_rerank_result = rerank_compare_result(
    query_fingerprint=rag_fingerprint_result,
    compare_result=compare_result,
    min_final_score=0.0,
    extension_target=file_path,
)
```

### `run_multi_scenario_dynamic_rag_analysis(...)` — `scenario/pipeline.py`

```python
from embedding.scenario import run_multi_scenario_dynamic_rag_analysis

result = run_multi_scenario_dynamic_rag_analysis(
    vector_fingerprint=fingerprint,
    rerank_result=rag_rerank_result,
    execute_action=adapter.execute_action,
    target_url=preferred_target_url,
    response_mode="compact",
)
final_risk = result["final_risk"]["risk_level"]  # LOW|MEDIUM|HIGH|CRITICAL
```

---

## Ollama 모델 준비

```bash
ollama pull bge-m3
ollama pull qwen2.5:1.5b-instruct-q4_K_M
```

## 환경변수 (Ollama)

```env
EMBEDDING_MODEL=bge-m3
OLLAMA_EMBED_URL=http://localhost:11434/api/embed
OLLAMA_EMBED_LEGACY_URL=http://localhost:11434/api/embeddings

LOCAL_LLM_URL=http://localhost:11434/api/chat
LOCAL_LLM_MODEL=qwen2.5:1.5b-instruct-q4_K_M
LLM_CONTEXT=4096
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=256
LLM_TIMEOUT=300
OLLAMA_KEEP_ALIVE=5m
```

## 안전 원칙

- 실제 서비스/실제 계정 사용 금지
- 실제 token/cookie/session/password 수집 금지
- 실제 외부 C2 전송 금지
- mock page, dummy value, localhost endpoint만 사용
- `scenario_docs/`는 공격 실행이 아닌 방어적 동적 분석 검증 절차 제공 목적

---

## 알려진 문제

| 항목                                          | 내용                                                                                                    |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------- | --- |
| `embed_fingerprint` vs `embed_full_text` 중복 | Ollama 임베딩 호출 코드가 `embed.py`와 `base_db.py`에 유사하게 중복됨. 동작 무관, 통합 시점에 정리 권장 |
| `compare.py` FALLBACK 하드코딩                | `FALLBACK_PATTERN_NAME = "session_storage_exfiltration_document_start"` 패턴이 삭제되면 오작동 가능     |     |
| `requirements.txt` 빈 파일                    | 내용 없음. 삭제 가능                                                                                    |
