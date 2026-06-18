# embedding/scenario_docs

26개 악성 패턴 시나리오의 **LLM 참조 문서** 모음입니다.

`embedding/base/`의 각 JSON이 벡터 DB에서 유사도 매칭에 사용되는 기준 지문이라면, 이 `.md` 파일들은 매칭된 패턴에 대해 **LLM 에이전트가 동적 분석을 어떻게 수행할지 안내하는 지침서**입니다.

분석 대상 확장의 `vector_fingerprint`가 특정 패턴과 유사하다고 판정되면, `embedding/scenario/loader.py`가 해당 패턴의 `.md` 파일을 읽어 LLM 프롬프트에 포함시킵니다. LLM은 이 문서를 보고 어떤 액션을 실행할지 결정합니다.

---

## 파일 구성

각 파일명은 `embedding/base/`의 JSON `pattern_name`과 1:1 대응합니다.

```
scenario_docs/
├── ad_frame_inline_injection.md
├── ad_fraud_session_replay.md
├── affiliate_cookie_stuffing.md
├── anti_debugging_trace_removal.md
├── browser_automation_remote_control.md
├── browser_fingerprinting_environment_collection.md
├── browsing_profile_exfiltration.md
├── c2_response_dom_innerhtml_injection.md
├── console_method_silencing_override.md
├── dnr_security_header_bypass.md
├── dynamic_config_polling_remote_interval.md
├── input_change_event_collection.md
├── oauth_profile_collection_exfiltration.md
├── page_screenshot_or_content_capture.md
├── popunder_ad_tab_injection.md
├── remote_browser_control_debugger_scripting.md
├── remote_dom_event_content_manipulation.md
├── session_reinjection_local_storage_overwrite.md
├── session_storage_exfiltration_document_start.md
├── session_storage_exfiltration_reference.md
├── startup_c2_backdoor_tabs_create.md
├── tabs_capture_visible_tab_exfiltration.md
├── translation_proxy_user_text_exfiltration.md
├── webmail_dom_content_tampering.md
├── webmail_dom_surveillance_collection.md
└── websocket_c2_remote_control.md
```

---

## 문서 구조

모든 26개 파일이 동일한 13개 섹션으로 작성되어 있습니다.

| 섹션                                        | 내용                                               |
| ------------------------------------------- | -------------------------------------------------- |
| 1. Purpose                                  | 이 시나리오가 검증하는 악성 행위 목적              |
| 2. Matched Static Pattern                   | 이 시나리오를 트리거하는 정적 신호 패턴            |
| 3. Expected Flows                           | 예측되는 데이터 흐름 (trigger → source → sink)     |
| 4. Safe Test Environment                    | 분석 환경 안전 원칙 (mock page, localhost only 등) |
| 5. Allowed Dynamic Actions                  | 이 시나리오에서 LLM이 사용할 수 있는 액션 목록     |
| 6. Recommended Dynamic Analysis Procedure   | LLM에게 권장하는 분석 단계별 절차                  |
| 7. Evidence to Collect                      | 수집해야 할 증거 항목                              |
| 8. Observation Format Expected from Harness | Harness가 반환하는 관찰 결과 형식                  |
| 9. Scoring Guidance                         | LOW/MEDIUM/HIGH/CRITICAL 판정 기준                 |
| 10. Safety Stop Conditions                  | 즉시 분석 중단해야 하는 조건                       |
| 11. Forbidden Actions                       | 이 시나리오에서 절대 실행 금지 액션                |
| 12. Expected Finish Action                  | 분석 완료 시 실행할 마무리 액션                    |
| 13. Analyst Summary                         | 분석가용 요약 및 주의사항                          |

---

## 코드에서의 역할

**`embedding/scenario/loader.py`** — `load_scenario_doc(doc_ref)`가 이 폴더에서 파일을 읽습니다. `doc_ref`는 `embedding/base/`의 JSON에서 `"doc_ref": "scenario_docs/{pattern_name}.md"` 형태로 지정됩니다. path traversal 공격을 차단합니다(`embedding/` 밖 접근 불가).

**`embedding/scenario/prompt_builder.py`** — `_extract_scenario_sections(scenario_doc)`가 읽어온 문서에서 섹션을 파싱해 LLM 프롬프트를 구성합니다. 특히 섹션 5(Allowed Dynamic Actions)와 6(Recommended Procedure)이 LLM이 다음 액션을 결정하는 핵심 지침이 됩니다.

**`embedding/scenario/pipeline.py`** — `run_multi_scenario_dynamic_rag_analysis()`에서 선택된 후보 패턴마다 이 문서를 로드해 `run_llm_dynamic_analysis_agent()`에 전달합니다.

---

## 새 시나리오 문서 추가 방법

1. `embedding/base/`에 대응하는 JSON 파일 추가 (방법은 `embedding/base/README.md` 참고)
2. 위 13개 섹션 구조로 `.md` 파일 작성
3. 파일명은 JSON의 `pattern_name`과 동일하게 지정
4. JSON의 `"doc_ref": "scenario_docs/{파일명}.md"` 경로와 일치하는지 확인

---

## 검토 메모

- 26개 파일 모두 13개 섹션 구조 완비.
- `embedding/base/`의 26개 JSON과 1:1 대응 확인 완료.
