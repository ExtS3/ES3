# Scenario: <pattern_name>

## 1. Purpose
<!-- 이 시나리오가 검증하려는 행위를 1~2문장으로 작성하세요. -->

## 2. Matched Static Pattern
<!-- JSON 파일의 static_code_signals와 매칭되는 정적 패턴을 설명하세요. -->

## 3. Expected Flows
<!-- trigger -> source -> path -> sink 흐름을 한 줄로 요약하세요. (JSON의 predicted_flows와 일치해야 함) -->

## 4. Safe Test Environment
- Chrome test profile only.
- Extension under analysis loaded from local file path.
- Mock page only: `http://127.0.0.1:8080/mock/index.html`.
- Mock receiver only: `http://127.0.0.1:9999`.
- Dummy storage/cookie/token/session values only.
- No real account, real service, or production endpoint access.

## 5. Allowed Dynamic Actions
- load_extension
- open_mock_page
- seed_dummy_local_storage
- seed_dummy_cookie_store
- click_extension_action
- submit_mock_form
- wait
- collect_network_requests
- collect_runtime_messages
- collect_storage_events
- collect_dom_events
- collect_timer_events
- collect_console_hooks
- collect_tab_events
- collect_header_modifications
- collect_dnr_rule_updates
- finish_analysis

## 6. Recommended Dynamic Analysis Procedure
<!-- 5번 액션 중 이 시나리오에 필요한 것만 순서대로 나열하세요. -->
1.
2.
3.

## 7. Evidence to Collect
<!-- 이 시나리오에서 수집해야 할 증거 항목을 나열하세요. -->
-

## 8. Observation Format Expected from Harness
- JSON object per step: `{action, status, timestamp, observations, safety_flags}`.
- `observations` includes only mock artifacts and sanitized payload previews.
- `safety_flags` includes booleans for all stop-condition keys.

## 9. Scoring Guidance
- LOW: Static match is weak and dynamic evidence is not reproduced.
- MEDIUM: Partial flow reproduced with limited impact.
- HIGH: Core flow reproduced with repeated or multi-signal confirmation.
- CRITICAL: Full flow reproduced with persistent automation or multi-surface impact.

## 10. Safety Stop Conditions
- real_service_used=true
- real_secret_observed=true
- non_localhost_sensitive_transmission=true
- real_oauth_detected=true
- real_cookie_detected=true
- real_account_detected=true
- 실제 서비스 URL 접근
- 실제 사용자 데이터 접근
- 금지 action 요청

## 11. Forbidden Actions
- login_real_service
- collect_real_cookie
- collect_real_token
- collect_real_session
- send_to_real_external_server
- bypass_authentication
- exploit_real_target
- access_real_user_data

## 12. Expected Finish Action
- Run `finish_analysis` and return structured evidence bundle with risk rationale.

## 13. Analyst Summary
<!-- 이 시나리오가 방어적/로컬호스트 기반으로만 검증됨을 명시하고, 실제 데이터 접근 시 즉시 중단해야 함을 요약하세요. -->
