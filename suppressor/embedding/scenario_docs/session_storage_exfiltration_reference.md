# Scenario: session_storage_exfiltration_reference

## 1. Purpose
Reference baseline for defensive validation of dummy session-like storage collection and localhost-only transmission flow.

## 2. Matched Static Pattern
document_start storage read, runtime message relay, periodic timer, and POST send signals indicate repeated session-like data movement. Additional signals include chrome.cookies.onChanged listener for cookie change monitoring and chrome.webRequest.onBeforeRequest.addListener for intercepting outbound requests before they are sent.

## 3. Expected Flows
document_start -> collect dummy storage -> runtime bridge -> background send to localhost mock receiver.

## 4. Safe Test Environment
- Chrome test profile only.
- Mock page only: `http://127.0.0.1:8080/mock/index.html`.
- Mock receiver only: `http://127.0.0.1:9999`.
- Dummy value seeding only.

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
1. load_extension.
2. open_mock_page.
3. seed dummy storage/cookies.
4. trigger extension action.
5. wait for timer branch.
6. collect runtime/network/storage evidence.
7. finish_analysis.

## 7. Evidence to Collect
- action timeline
- localhost request list
- runtime message traces
- dummy storage mutation deltas

## 8. Observation Format Expected from Harness
- `{action, status, timestamp, observations, safety_flags}` per step.

## 9. Scoring Guidance
- LOW: weak dynamic support.
- MEDIUM: partial reproduction.
- HIGH: core flow reproduced.
- CRITICAL: repeated/persistent full flow.

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
- finish_analysis and return structured, sanitized evidence.

## 13. Analyst Summary
- Use only localhost mock workflows and stop immediately on any real-world artifact.
