# embedding/scenario

rerank 결과로 선택된 악성 패턴 후보에 대해 **LLM 에이전트 + Playwright 브라우저**로 동적 시나리오를 실행하고 최종 동적 리스크를 산출하는 모듈입니다.

`main.py`의 `/file_scan`에서 rerank 직후 호출됩니다.

---

## 진입점

```python
from embedding.scenario import run_multi_scenario_dynamic_rag_analysis

result = run_multi_scenario_dynamic_rag_analysis(
    vector_fingerprint=fingerprint,        # Dynamic_RAG 지문
    rerank_result=rag_rerank_result,       # rerank 결과
    execute_action=adapter.execute_action, # Playwright 액션 콜백
    target_url=preferred_target_url,
    response_mode="compact",              # "compact" | "full" | "both"
)
final_risk = result["final_risk"]["risk_level"]  # LOW | MEDIUM | HIGH | CRITICAL
```

---

## 파일 구성

```
scenario/
├── config.py                     # 전역 상수 (임계값, 가중치, 경로)
├── loader.py                     # 시나리오 문서(.md) 로드
├── action_schema.py              # 허용·금지 액션 목록 및 검증
├── observation_schema.py         # 관찰 결과 정규화
├── dynamic_action_adapter.py     # execute_action → PlaywrightDynamicHarness 라우팅
├── playwright_dynamic_harness.py # Playwright 브라우저 제어 (2200줄)
├── dynamic_agent.py              # LLM 에이전트 루프
├── prompt_builder.py             # LLM 프롬프트 생성
├── llm_client.py                 # Ollama API 호출
├── selector.py                   # rerank 후보 → 실행 대상 선택
├── evidence_scorer.py            # 동적 관찰 결과 → 증거 점수
├── risk_classifier.py            # 시나리오 결과 → 최종 리스크
├── pipeline.py                   # 전체 파이프라인 오케스트레이션
├── compact.py                    # 결과 압축·요약 출력
└── __init__.py                   # 공개 API export
```

---

## 전체 파이프라인

```
run_multi_scenario_dynamic_rag_analysis(vector_fingerprint, rerank_result)
  │
  ├── selector.py: select_candidate_matches()
  │     rerank_result에서 min_final_score 이상, doc_ref 중복 없는 상위 3개 선택
  │     → 매칭 없으면 _classify_risk_from_fingerprint_only()로 정적 폴백
  │
  ├── [각 후보 패턴에 대해 반복]
  │     │
  │     ├── loader.py: load_scenario_doc(doc_ref)
  │     │     embedding/scenario_docs/{pattern}.md 로드
  │     │
  │     ├── dynamic_agent.py: run_llm_dynamic_analysis_agent()
  │     │     ┌── bootstrap: load_extension → open_mock_page
  │     │     └── [max_rounds=8 반복]
  │     │           prompt_builder: build_next_action_prompt_compact()
  │     │           llm_client: call_llm() → Ollama qwen2.5
  │     │           LLM 응답에서 action JSON 파싱
  │     │           action_schema: validate_agent_action() 검증
  │     │           dynamic_action_adapter: execute_action()
  │     │           → PlaywrightDynamicHarness 실행
  │     │           observation_schema: normalize_action_observation()
  │     │           finish_analysis 또는 timeout 시 종료
  │     │
  │     └── evidence_scorer.py: score_scenario_evidence()
  │           network_requests, runtime_messages, storage_events 분석
  │           → scenario_evidence_score (0.0~1.0)
  │           → safety_violation 여부 판정
  │
  ├── risk_classifier.py: classify_final_risk(scenario_results)
  │     모든 시나리오 결과 종합 → HIGH_RISK/CRITICAL_TAGS 매칭
  │     → final_risk: LOW | MEDIUM | HIGH | CRITICAL
  │
  └── compact.py: compact_dynamic_rag_result()
        response_mode에 따라 full/compact 반환
```

---

## 파일 상세

### config.py

전역 상수를 정의합니다.

| 상수                         | 값                                   | 설명                          |
| ---------------------------- | ------------------------------------ | ----------------------------- |
| `DEFAULT_MIN_FINAL_SCORE`    | 0.35                                 | 후보 선택 최소 점수           |
| `DEFAULT_MAX_DYNAMIC_ROUNDS` | 8                                    | LLM 에이전트 최대 실행 라운드 |
| `SCENARIO_DOC_BASE_DIR`      | `embedding/`                         | 시나리오 문서 기준 경로       |
| `SCORING_WEIGHTS`            | rerank:0.30, evidence:0.55, llm:0.15 | 최종 점수 가중치              |

### loader.py

`load_scenario_doc(doc_ref)` — `embedding/scenario_docs/` 하위 `.md` 문서를 읽어 LLM 프롬프트에 포함할 시나리오 설명을 반환합니다. path traversal 공격을 차단합니다(`base_dir` 밖 접근 시 `ValueError`).

### action_schema.py

LLM이 생성할 수 있는 액션의 허용·금지 목록을 정의합니다.

**ALLOWED_ACTIONS (21개)** — `load_extension`, `open_mock_page`, `seed_dummy_local_storage`, `collect_network_requests`, `finish_analysis` 등 분석 목적 액션만 허용합니다.

**FORBIDDEN_ACTIONS** — `login_real_service`, `collect_real_cookie`, `collect_real_token`, `send_to_real_external_server` 등 실제 서비스 침해 액션을 명시적으로 차단합니다.

`validate_agent_action(action)` — LLM 응답 액션을 실행 전 검증합니다. 금지 액션, 허용 목록 외 액션, unsafe target(실제 서비스 URL) 차단.

### observation_schema.py

`normalize_observations(observations)` — Playwright 실행 결과를 표준 구조로 정규화합니다. `network_requests`, `runtime_messages`, `storage_events`, `dom_events`, `timers`, `execution` 6개 키로 정규화하며 타입 방어 처리를 포함합니다.

`normalize_action_observation(action, observation)` — 개별 액션과 그 관찰 결과를 `{action, observation}` 쌍으로 묶습니다.

### dynamic_action_adapter.py

`DynamicActionAdapter` — `execute_action(action)` 호출을 `PlaywrightDynamicHarness`로 라우팅하는 브릿지입니다.

Playwright는 자체 이벤트 루프가 필요하므로 **전용 worker 스레드**를 생성하고 `queue.Queue`로 액션을 전달합니다. FastAPI의 async context에서 Playwright를 동기적으로 안전하게 실행하기 위한 구조입니다.

`close()` — worker 스레드 종료 + Playwright 정리. `main.py`의 `finally`에서 호출됩니다.

### playwright_dynamic_harness.py (2233줄)

Chrome 브라우저를 Playwright로 제어해 확장 프로그램의 실제 동작을 관찰합니다.

**핵심 보안 원칙**

- 실제 서비스 URL 접근 차단 (`is_safe_target_url`)
- 더미 값만 사용 (`seed_dummy_local_storage`, `body_contains_dummy_secret`)
- 실제 외부 네트워크 요청 차단 및 인터셉트 (`is_allowed_request`)
- mock page, localhost endpoint만 허용

**주요 기능**: 확장 ZIP 해제 → Chromium에 확장 로드 → mock 페이지 서빙 → 네트워크 요청 인터셉트 → content_script 실행 감지 → service worker 상태 확인 → 액션별 Playwright 제어

### dynamic_agent.py

`run_llm_dynamic_analysis_agent()` — LLM 에이전트 루프를 실행합니다.

1. bootstrap: `load_extension` → `open_mock_page` 순으로 자동 실행
2. `max_rounds`(최대 8번)만큼 반복: 프롬프트 생성 → LLM 호출 → 액션 파싱·검증 → 실행 → 히스토리 추가
3. `finish_analysis` 액션 또는 timeout으로 종료
4. `DYNAMIC_ANALYSIS_TIMEOUT_SEC` 환경변수로 전체 타임아웃 제어 (기본 60초)

### prompt_builder.py

LLM에 전달할 프롬프트를 생성합니다.

| 함수                                     | 용도                                              |
| ---------------------------------------- | ------------------------------------------------- |
| `build_agent_system_prompt()`            | 시스템 프롬프트 (역할, 안전 원칙, 허용 액션 목록) |
| `build_next_action_prompt_compact()`     | 다음 액션 요청 (compact, 실제 사용)               |
| `build_next_action_prompt()`             | 다음 액션 요청 (full)                             |
| `build_repair_prompt_for_invalid_json()` | JSON 파싱 실패 시 재생성 요청                     |

vector_fingerprint, 시나리오 문서, 관찰 히스토리를 요약해 LLM 컨텍스트 윈도우에 맞게 압축합니다.

### llm_client.py

`call_llm(messages, **kwargs)` — Ollama API를 호출합니다.

| 환경변수            | 기본값                            | 설명                               |
| ------------------- | --------------------------------- | ---------------------------------- |
| `LOCAL_LLM_URL`     | `http://localhost:11434/api/chat` | Ollama endpoint                    |
| `LOCAL_LLM_MODEL`   | `qwen2.5:1.5b-instruct-q4_K_M`    | 모델명                             |
| `LLM_TEMPERATURE`   | 0.1                               | 생성 온도                          |
| `LLM_MAX_TOKENS`    | 256                               | 최대 토큰                          |
| `LLM_TIMEOUT`       | 300                               | 요청 타임아웃(초)                  |
| `OLLAMA_KEEP_ALIVE` | 5m                                | 모델 메모리 유지 시간              |
| `ENABLE_LLM`        | 1                                 | `0`이면 LLM 호출 없이 빈 응답 반환 |

### selector.py

`select_candidate_matches(rerank_result, vector_fingerprint, min_final_score, max_matches)` — rerank 결과에서 실제 동적 분석을 실행할 후보를 선택합니다. doc_ref 중복을 제거하고 `_score_breakdown()`으로 보정 점수를 재계산해 최종 상위 3개를 반환합니다.

`select_best_match(rerank_result)` — 단일 최적 후보 반환.

### evidence_scorer.py

`score_scenario_evidence(vector_fingerprint, selected_match, llm_agent_result, observations)` — 동적 관찰 결과를 증거 점수(0.0~1.0)로 변환합니다.

safety_violation 감지를 최우선으로 처리합니다. 실제 외부 요청이 탐지되면 점수 계산 없이 즉시 `safety_violation=True`를 반환합니다.

패턴별 전용 스코어러: `_score_session_exfiltration`, `_score_proxy_vpn_pattern`, `_score_generic`

### risk_classifier.py

`classify_final_risk(scenario_results, vector_fingerprint, static_context)` — 모든 시나리오 결과를 종합해 최종 리스크를 분류합니다.

`compute_high_risk_behavior_flags()` — 시나리오별 관찰 totals와 vector_fingerprint를 결합해 CRITICAL/HIGH 트리거 조건을 평가합니다.

| 리스크   | 조건                                                                 |
| -------- | -------------------------------------------------------------------- |
| CRITICAL | safety_violation, 실제 외부 전송, 세션 탈취 고확신, 원격제어 조합 등 |
| HIGH     | 외부 통신 + 스토리지 접근, 의심 브라우저 자동화 등                   |
| MEDIUM   | 낮은 확신의 세션 접근, 의심 타이머 패턴 등                           |
| LOW      | 위 조건 없음                                                         |

### compact.py

분석 결과를 압축·요약합니다.

| 함수                                              | 용도                                       |
| ------------------------------------------------- | ------------------------------------------ |
| `compact_dynamic_rag_result(result)`              | 전체 결과를 `response_mode`에 맞게 압축    |
| `compact_agent_result(agent_result)`              | 에이전트 히스토리 압축 (중복 이벤트 dedup) |
| `compact_observation(observation)`                | 단일 관찰 결과 압축                        |
| `compact_result_json_line(compact_result)`        | 한 줄 JSON 로그                            |
| `compact_result_one_line_summary(compact_result)` | 한 줄 텍스트 요약                          |

`main.py`가 `compact_result_one_line_summary()`로 분석 진행 상황을 로그로 출력합니다.

---

## 안전 원칙

- 실제 token/cookie/session/password 수집 금지 (`FORBIDDEN_ACTIONS`)
- 실제 외부 서버 전송 금지 (Playwright 네트워크 인터셉트)
- 실제 서비스 URL 접근 금지 (`is_safe_target_url`)
- mock page, dummy value, localhost endpoint만 사용
- safety_violation 감지 시 즉시 분석 중단

---

## 검토 메모

- 15개 파일 모두 정상. `__init__.py` export 29개 전부 실제 정의와 일치.
- `generate_scenario_plan_from_rerank`은 `run_dynamic_rag_analysis`의 alias이며 코드베이스 어디서도 호출되지 않습니다. 하위 호환성을 위한 잔재로 보입니다.
- `prompt_builder._safe_dict`, `_safe_list`가 다른 파일과 중복 구현되어 있습니다. 동작 무관.
