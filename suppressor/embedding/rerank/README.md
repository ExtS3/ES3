# embedding/rerank

벡터 유사도 1차 검색 결과를 **구체적 정적 증거** 기반으로 재순위화(rerank)하는 모듈입니다.
`compareDB()`가 반환한 후보 패턴들에 실제 확장 ZIP을 직접 스캔한 API 증거를 결합해 최종 순위를 계산합니다.

`main.py`의 `/file_scan`에서 벡터 검색(`compare.py`) 직후에 호출됩니다.

---

## 진입점

```python
from embedding.rerank import rerank_compare_result

rag_rerank_result = rerank_compare_result(
    query_fingerprint=vector_fingerprint,   # Dynamic_RAG가 생성한 지문
    compare_result=compare_result,          # compareDB() 반환값
    min_final_score=0.0,                    # 이 점수 미만 후보 제거
    extension_target=file_path,            # 확장 ZIP 경로 (증거 수집용)
)
```

---

## 파일 구성

```
rerank/
├── __init__.py          # build_rerank_features, compare_rerank_features, rerank_compare_result export
├── feature_builder.py   # vector_fingerprint → 비교 가능한 특징 집합으로 변환
├── scorer.py            # 두 특징 집합 간 점수 계산 (가중 합산)
└── pipeline.py          # 전체 rerank 오케스트레이션 + 구체적 증거 수집
```

---

## 파일 상세

### feature_builder.py

`build_rerank_features(vector_fingerprint)` — `vector_fingerprint` dict를 비교 연산에 적합한 집합(set) 기반 특징으로 변환합니다.

**출력 구조**

| 필드                   | 원본                      | 변환 방식                                 |
| ---------------------- | ------------------------- | ----------------------------------------- | ---------------- | -------- | --------------------- |
| `capability_set`       | `capability_profile`      | 문자열 집합                               |
| `capability_combo_set` | `capability_combinations` | `+` 구분자 → `                            | ` 정규화 후 집합 |
| `flow_set`             | `predicted_flows`         | `trigger=...                              | source=...       | path=... | sink=...` 문자열 집합 |
| `behavior_tag_set`     | `behavior_tags`           | 문자열 집합                               |
| `signal_set`           | `static_code_signals`     | 섹션별 flatten 후 `section.api` 형태 집합 |

`signal_set` flatten 대상 섹션: `network`, `storage`, `messaging`, `dom_input`, `delayed_execution`, `navigation`, `request_modification`, `dynamic_execution`, `debugger`, `file_clipboard`

---

### scorer.py

`compare_rerank_features(query_features, candidate_features, vector_similarity, weights)` — 두 특징 집합을 비교해 최종 점수를 계산합니다.

**기본 가중치**

| 항목                           | 가중치 | 계산 방식                                    |
| ------------------------------ | :----: | -------------------------------------------- |
| `vector_similarity`            |  0.30  | pgvector 코사인 유사도 (외부 전달)           |
| `behavior_tag_overlap`         |  0.25  | Jaccard 유사도                               |
| `capability_combo_containment` |  0.25  | 후보 combo가 쿼리 combo 토큰에 포함되는 비율 |
| `flow_match`                   |  0.10  | 후보 flow 중 쿼리와 일치하는 비율            |
| `signal_overlap`               |  0.10  | Jaccard 유사도                               |

`final_score = Σ (각 항목 점수 × 가중치)`

`weights` 파라미터로 가중치를 외부에서 오버라이드할 수 있습니다.

**`_combo_tokens(combo)`** — `|` 또는 `+` 구분자로 콤보를 토큰으로 분해합니다. `capability_combo_containment` 계산에 사용됩니다.

---

### pipeline.py

`rerank_compare_result(query_fingerprint, compare_result, min_final_score, extension_target)` — 전체 rerank 파이프라인을 실행합니다.

**처리 흐름**

```
1. build_rerank_features(query_fingerprint)
   → query의 특징 집합 생성

2. _extract_concrete_evidence(query_fingerprint, extension_target)
   → 확장 ZIP을 직접 해제해 구체적 API 증거 수집
   → 스크린샷, 원격제어, DOM 조작, 세션 탈취, 브라우저 지문 등 카테고리별 분류

3. 각 후보 패턴에 대해:
   a. build_rerank_features(candidate_fingerprint)
   b. compare_rerank_features() → base_score (가중 합산)
   c. _scenario_evidence_adjustment(pattern_name, evidence)
      → 패턴별로 구체적 증거와 매칭해 보정 점수 계산
      → negative_penalty 적용 (맞지 않는 증거 0.10씩 감점)
   d. final_score = base_score + static_capability_score
                  + concrete_api_evidence_score - negative_penalty
   e. min_final_score 미만이면 제외

4. 강제 주입(force-inject):
   → captureVisibleTab, chrome.debugger 등 강한 증거가 있으면
     대응 패턴을 벡터 점수 무관하게 후보에 추가 (final_score=0.42 고정)

5. 정렬:
   → 1차: final_score 내림차순
   → 2차: concrete_api_evidence 보유 여부 우선 + final_score 내림차순
   → 상위 3개 선택
```

**구체적 증거 카테고리 (`_scan_extension_static_evidence`)**

| 증거 카테고리             | 탐지 내용                                                           |
| ------------------------- | ------------------------------------------------------------------- |
| `screenshot_evidence`     | `captureVisibleTab`, `captureScreenshot`, `screenshot-helper.js` 등 |
| `page_content_evidence`   | `document.body.innerText`, `querySelector`, `textContent` 등        |
| `dom_tampering_evidence`  | `innerHTML`, `outerHTML`, `insertAdjacentHTML` 등                   |
| `remote_control_evidence` | `chrome.debugger`, `scripting.executeScript`, `inject-bridge.js` 등 |
| `session_read_evidence`   | `localStorage`, `sessionStorage`, `chrome.cookies` 등               |
| `session_send_evidence`   | `fetch`, `POST`, `XMLHttpRequest` 등 외부 전송                      |
| `session_bridge_evidence` | `runtime.sendMessage` + 네트워크 조합                               |
| `fingerprinting_evidence` | `navigator.userAgent`, `canvas`, `AudioContext` 등                  |

**강제 주입 패턴**

| 조건                                                    | 주입되는 패턴                                                                    |
| ------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `screenshot_evidence` 또는 `page_content_evidence` 있음 | `tabs_capture_visible_tab_exfiltration`, `page_screenshot_or_content_capture`    |
| `remote_control_evidence` 있음                          | `browser_automation_remote_control`, `remote_browser_control_debugger_scripting` |

---

## 반환 구조

```python
{
    "query_rerank_features": {...},          # 쿼리 특징 집합
    "vector_top_pattern": "...",             # 벡터 유사도 1위 패턴
    "vector_top_score": 0.85,
    "evidence_rerank_top_pattern": "...",    # 증거 보정 후 1위 패턴
    "evidence_rerank_top_score": 0.72,
    "top_candidate_patterns": [...],         # 상위 3개 패턴명
    "selected_candidates": [...],            # 상위 3개 상세 결과
    "reranked_matches": [...],               # 전체 보정 결과
    "evidence_injected_candidates": [...],   # 강제 주입된 패턴명
    "concrete_static_evidence": [...],       # 수집된 구체적 증거
    "skipped": [...]                         # 지문 없어서 건너뛴 후보
}
```
