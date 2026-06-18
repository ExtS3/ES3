# Scenario: browser_automation_remote_control

## 1. Purpose
Defensive validation candidate for remote browser automation control using injected helper toolchain.

## 2. Matched Static Pattern
Presence of click/fill/keyboard/form-submit/network/web-fetch helper scripts with tab/debugger/scripting capabilities indicates command-driven browser automation.

## 3. Expected Flows
remote command -> helper dispatch -> interaction/capture/fetch action -> background relay.

## 4. Safe Test Environment
- Local mock pages only.
- Dummy input and non-sensitive content only.

## 5. Allowed Dynamic Actions
- load_extension
- open_mock_page
- seed_dummy_local_storage
- seed_dummy_cookie_store
- click_extension_action
- submit_mock_form
- wait
- collect_runtime_messages
- collect_network_requests
- collect_storage_events
- collect_dom_events
- collect_timer_events
- collect_console_hooks
- collect_tab_events
- finish_analysis

## 6. Recommended Dynamic Analysis Procedure
1. Run `load_extension` and verify extension id and manifest context.
2. Run `open_mock_page` to isolate execution in localhost.
3. Seed only dummy artifacts using `seed_dummy_local_storage` and `seed_dummy_cookie_store`.
4. Trigger relevant behavior with `click_extension_action` or `submit_mock_form`.
5. Use `wait` for timer/event-driven branches.
6. Collect evidence using network/runtime/storage/DOM/timer/console/tab collectors as applicable.
7. Execute `finish_analysis` once expected signals are observed or stop condition is hit.

## 7. Evidence to Collect
- Timestamped action log.
- Localhost-only outbound request list (method, URL, headers, body hash).
- Runtime message traces (direction, payload keys).
- Storage/cookie mutation deltas for dummy keys only.
- DOM/tab side-effect snapshots where relevant.

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

