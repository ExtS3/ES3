# slack

분석 결과를 Slack으로 알림 전송하는 모듈입니다.
`main.py`의 `/file_scan` 마지막 결과 전송 단계에서 `ENABLE_SLACK_FORWARD=true`일 때 호출됩니다.

---

## 파일명이 main.py인 이유

`slack/main.py`라는 이름은 **Python 패키지 관례**입니다.
`from slack.main import run_with_scan_input`으로 suppressor의 `main.py`가 import하는 동시에, `python slack/main.py --scan-json '...'`으로 **CLI 단독 실행도 가능**하도록 하나의 파일에 담은 구조입니다.

---

## 진입점

**코드에서 호출:**

```python
from slack.main import run_with_scan_input as run_slack_with_scan_input
flow = run_slack_with_scan_input(scan_input)
```

**CLI 단독 실행:**

```bash
python slack/main.py --scan-file result.json
python slack/main.py --scan-json '{"extension_id": "...", "risk_level": "HIGH"}'
```

import 실패 시 suppressor `main.py`는 `_slack_available=False`로 graceful degradation합니다.

---

## 핵심 함수

| 함수                                  | 역할                                                  |
| ------------------------------------- | ----------------------------------------------------- |
| `run_with_scan_input(scan_input)`     | 메인 진입점. 정규화 → 판정 → 전송 → 결과 반환         |
| `normalize_scan_input(scan_input)`    | 다양한 형태의 분석 결과를 표준 `ScanResults`로 정규화 |
| `score_scan_results(results)`         | 정규화 결과로 `safe`/`review` 1차 판정                |
| `build_slack_payload(label, results)` | Slack Block Kit 메시지 페이로드 구성                  |
| `send_slack_notification(payload)`    | `SLACK_WEBHOOK_URL`로 POST 전송                       |
| `make_dashboard_url(...)`             | 메시지에 삽입할 대시보드 링크 생성                    |

---

## 판정 오버라이드 로직

`run_with_scan_input`은 자체 점수 판정 후, upstream(risk_scoring)의 `decision`/`risk_level`이 있으면 그 값으로 덮어씁니다. `safe`가 아닐 때만 Slack 알림을 전송합니다.

| upstream 값                                          | 최종 판정            |
| ---------------------------------------------------- | -------------------- |
| `reject` / `high` / `critical` / `review` / `medium` | `review` → 알림 전송 |
| `approve` / `safe` / `low`                           | `safe` → 알림 미전송 |

> 코드에 `meduim`(오타) 문자열도 함께 매칭합니다. upstream 오타에 대한 방어 처리입니다.

---

## 환경 변수

| 변수                   | 설명                                              |
| ---------------------- | ------------------------------------------------- |
| `SLACK_WEBHOOK_URL`    | Slack Incoming Webhook URL. 미설정 시 전송 건너뜀 |
| `ENABLE_SLACK_FORWARD` | `main.py`에서 이 모듈 호출 여부 토글              |
| `DASHBOARD_BASE_URL`   | 메시지에 삽입할 대시보드 링크 base URL            |

---
