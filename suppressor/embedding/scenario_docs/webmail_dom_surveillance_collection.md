# Scenario: webmail_dom_surveillance_collection

## 1. Purpose
Validate webmail-like DOM surveillance on mock HTML and confirm only synthetic email-like data is collected.

## 2. Matched Static Pattern
MutationObserver, DOM polling, and JSON serialization with POST suggest continuous collection behavior. Additional signals include specific email data fields such as emailSubject, senderAddress, recipientList, emailBodyText, and gmailThreadId being serialized and POSTed to a /collect endpoint.

## 3. Expected Flows
mock webmail DOM mutation -> observer capture -> serialized dummy email fields -> localhost transmission.

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
1. Run `load_extension` and verify extension id and manifest context.
2. Run `open_mock_page` to isolate execution in localhost.
3. Seed only dummy artifacts using `seed_dummy_local_storage` and `seed_dummy_cookie_store`.
4. Trigger relevant behavior with `click_extension_action` or `submit_mock_form`.
5. Use `wait` for timer/event-driven branches.
6. Collect evidence using network/runtime/storage/DOM/timer/console/tab/header/DNR collectors as applicable.
7. Execute `finish_analysis` once expected signals are observed or stop condition is hit.

## 7. Evidence to Collect
- Timestamped action log.
- Localhost-only outbound request list (method, URL, headers, body hash).
- Runtime message traces (direction, payload keys).
- Storage/cookie mutation deltas for dummy keys only.
- DOM or tab side-effect snapshots where relevant.

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
- This scenario is validated only through defensive, localhost-based dynamic verification.
- Any sign of real-world data or endpoint interaction requires immediate stop and report.
