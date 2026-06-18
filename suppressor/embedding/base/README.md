# embedding/base

벡터 DB seed 데이터입니다. 26개의 악성 확장 행위 패턴을 정의한 JSON 파일들이 있으며, 서버 시작 시 `base_db.py`의 `ensure_knowledge_base_seeded()`가 이 파일들을 읽어 pgvector DB에 임베딩 벡터로 적재합니다.

`/file_scan`이 분석한 확장의 `vector_fingerprint`는 이 seed 데이터와 코사인 유사도로 비교되어 가장 유사한 악성 패턴을 찾아냅니다.

---

## 구조

각 JSON 파일은 하나의 악성 패턴을 정의합니다.

```json
{
  "scenario_id": "meoilhadanfaddhibdnpflaeeccpghgl",  // 고정 32자 ID (builtin 고유)
  "builtin": true,                                     // 기본 제공 시나리오 표시
  "pattern_name": "session_storage_exfiltration_document_start",
  "doc_ref": "scenario_docs/session_storage_exfiltration_document_start.md",
  "vector_fingerprint": {
    "manifest_profile": { ... },       // manifest 구조 프로필
    "capability_profile": [ ... ],     // 능력 태그 목록
    "capability_combinations": [ ... ],// capability 조합 패턴
    "static_code_signals": { ... },    // JS 코드 신호
    "predicted_flows": [ ... ],        // 예측 데이터 흐름
    "behavior_tags": [ ... ]           // 고수준 행위 태그
  }
}
```

`vector_fingerprint` 구조는 `Dynamic_RAG/rag_fingerprint/`가 실제 확장 분석 시 생성하는 구조와 동일합니다. 이 seed 데이터가 알려진 악성 패턴의 기준 지문 역할을 합니다.

---

## 패턴 목록 (26개)

| 파일명                                          | 행위 태그                                                                    |
| ----------------------------------------------- | ---------------------------------------------------------------------------- |
| `ad_frame_inline_injection`                     | ad_frame_injection, csp_bypass, html_injection, search_result_overlay        |
| `ad_fraud_session_replay`                       | ad_fraud, session_replay, bloom_filter, fake_traffic                         |
| `affiliate_cookie_stuffing`                     | affiliate_fraud, cookie_stuffing, tab_abuse, silent_navigation               |
| `anti_debugging_trace_removal`                  | anti_debugging, trace_removal, devtools_detection, storage_cleanup           |
| `browser_automation_remote_control`             | remote_browser_control, browser_automation, debugger_abuse, script_injection |
| `browser_fingerprinting_environment_collection` | browser_fingerprinting, environment_collection, external_communication       |
| `browsing_profile_exfiltration`                 | browsing_history_exfiltration, persistent_tracking, user_profiling           |
| `c2_response_dom_innerhtml_injection`           | dom_injection, unsafe_innerhtml, remote_content_injection                    |
| `console_method_silencing_override`             | anti_analysis, debug_evasion                                                 |
| `dnr_security_header_bypass`                    | security_header_bypass, csp_removal, header_spoofing, request_modification   |
| `dynamic_config_polling_remote_interval`        | polling_configuration, adaptive_polling, periodic_execution                  |
| `input_change_event_collection`                 | input_collection, form_monitoring, data_exfiltration                         |
| `oauth_profile_collection_exfiltration`         | oauth_token_usage, account_profile_collection, identity_abuse                |
| `page_screenshot_or_content_capture`            | screen_capture, page_content_capture, browser_screenshot                     |
| `popunder_ad_tab_injection`                     | popunder_ad, background_tab, remote_config_abuse, ad_injection               |
| `remote_browser_control_debugger_scripting`     | debugger_access, remote_browser_control, script_injection                    |
| `remote_dom_event_content_manipulation`         | content_tampering, dom_event_abuse, remote_script_trigger                    |
| `session_reinjection_local_storage_overwrite`   | session_reinjection, storage_overwrite, remote_navigation                    |
| `session_storage_exfiltration_document_start`   | session_theft_pattern, page_storage_exfiltration, repeated_exfiltration      |
| `session_storage_exfiltration_reference`        | credential_or_token_exfiltration_pattern, message_passing_bridge             |
| `startup_c2_backdoor_tabs_create`               | startup_backdoor, remote_command_or_config, tab_open_from_remote_response    |
| `tabs_capture_visible_tab_exfiltration`         | screen_capture, data_exfiltration                                            |
| `translation_proxy_user_text_exfiltration`      | translation_proxy, user_text_exfiltration, proxy_configuration               |
| `webmail_dom_content_tampering`                 | email_modification, content_tampering, dom_injection                         |
| `webmail_dom_surveillance_collection`           | webmail_surveillance, email_collection, data_exfiltration                    |
| `websocket_c2_remote_control`                   | websocket_c2, http_relay, response_exfiltration, remote_command_execution    |

---

## 코드에서의 역할

**`base_db.py` — seed 적재**

서버 시작 시 `ensure_knowledge_base_seeded()`가 벡터 DB가 비어있으면 이 파일들을 읽어 임베딩 후 pgvector에 삽입합니다. 이미 적재된 경우 건너뜁니다.

**`scenario_router.py` — 관리 API**

`GET /api/scenario/list`가 이 파일들을 순회합니다. `builtin=true`인 파일은 `DELETE /api/scenario/delete/{id}`에서 삭제가 차단됩니다.

**`embedding/compare.py` — 유사도 검색**

`/file_scan` 시 분석 대상 확장의 `vector_fingerprint`가 임베딩된 후, 이 seed 데이터의 임베딩 벡터들과 코사인 유사도로 비교됩니다.

---

## 새 패턴 추가 방법

1. 위 JSON 구조로 새 파일 작성 (`builtin: false`로 설정)
2. `embedding/scenario_docs/`에 동일한 이름의 `.md` 문서 작성 (`doc_ref` 경로와 일치)
3. `POST /api/scenario/upload`로 업로드하거나 파일을 직접 배치 후 `POST /api/scenario/reload`로 재적재

`builtin: true`는 기본 제공 패턴 전용입니다. 직접 추가하는 패턴은 `builtin: false`로 설정해야 삭제 보호가 적용되지 않습니다.

---

## 검토 메모

- 26개 파일 모두 구조 정상. `scenario_id` 중복 없음. 모든 `doc_ref` 파일 존재 확인.
- `base/`의 모든 패턴에 대응하는 `scenario_docs/` 문서가 존재합니다. 26개 패턴과 26개 문서가 1:1 대응합니다.
