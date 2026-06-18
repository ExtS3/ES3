# retro — 승인된 확장 주기적 재점검 모니터

Nexus Repository에 보관된 승인 확장 프로그램을 주기적으로 조회해 **새 버전 출시**와 **평판 변화**를 감지하고, 후속 파이프라인(holding / 재분석)을 위한 이벤트를 큐에 적재하는 감지기입니다.

> 이 모듈은 **감지기 + 큐 생산기** 역할만 합니다. Nexus에서 직접 삭제하거나 승인 상태를 바꾸지 않습니다.

## 파일 구조

```
retro/
├── retro_monitor.py             # 전체 모니터 로직
├── requirements-retro-monitor.txt
└── README.md
```

## 동작 방식

```
Nexus raw repository
    │ ZIP/CRX 에셋 목록 조회
    ▼
각 확장 다운로드 → manifest.json 분석
    │
    ├─ extension_id 추출
    │   ├─ 파일명/경로에서 직접 추출
    │   └─ manifest의 key 필드 → SHA256 → Chrome ID 변환
    │      (chrome_id_from_public_key_b64)
    │
    ├─ Chrome Web Store 버전 비교 (Playwright + BeautifulSoup 스크래핑)
    │   └─ store 버전 > Nexus 버전 → HOLD_FOR_NEW_VERSION 이벤트
    │
    ├─ VirusTotal 평판 검사 (선택, VT_API_KEY 필요)
    │   ├─ 파일 SHA256 평판
    │   └─ 연관 도메인 평판
    │   └─ 악화 감지 → HOLD_FOR_REPUTATION_REVIEW / QUARANTINE_RECOMMENDED 이벤트
    │
    └─ YARA 매칭 (선택, YARA_RULE_PATH 필요)
        └─ 새 매치 → HOLD_FOR_REPUTATION_REVIEW 이벤트

이벤트 → retro_queue.jsonl 적재
상태 → retro_state.json 갱신
```

## 생성 파일

### `retro_state.json`
마지막 점검 결과 상태 파일

### `retro_queue.jsonl`
후속 처리용 이벤트 큐. 줄별 JSON 형식.

이벤트 예시:
```json
{ "event_type": "HOLD_FOR_NEW_VERSION", "reason": "store_version_newer_than_nexus",
  "extension_id": "aapbdbdomjkkjkaonfhkkikfgjllcleb",
  "nexus_version": "2.0.16", "store_version": "2.0.17",
  "recommended_action": "enqueue_holding_or_reanalysis" }
```

## 이벤트 종류

| 이벤트 | 조건 | 권장 조치 |
|--------|------|-----------|
| `HOLD_FOR_NEW_VERSION` | store 버전 > Nexus 버전 | holding 큐 또는 재분석 큐로 전달 |
| `HOLD_FOR_REPUTATION_REVIEW` | VT/YARA 평판 악화 | 임시 보류 후 재분석 |
| `QUARANTINE_RECOMMENDED` | 강한 악성 신호 | 운영자 검토 대상으로 전달 |

## 핵심 클래스

### `Settings` — `retro_monitor.py`

환경 변수로 설정을 로드합니다. `Settings.from_env()`로 생성.

```python
settings = Settings.from_env()
monitor = RetroMonitor(settings)
monitor.run_once()
```

### `RetroMonitor` — `retro_monitor.py`

전체 모니터 루프 및 각 점검 단계 실행.

주요 메서드:
- `run_once()` — 1회 전체 점검
- `run_loop()` — `interval_hours` 주기로 반복 실행

### `chrome_id_from_public_key_b64(public_key_b64)` — `retro_monitor.py`

manifest의 `key` 필드(base64 공개키)에서 Chrome Extension ID를 복원합니다.
- SHA256 다이제스트 앞 32자 → 16진수 → `[a-p]` 문자 변환 (Chrome 인코딩 방식)
- `extension_id`가 파일명/경로에 없는 경우 이 방법으로 복원 시도

## 설치

```bash
pip install -r requirements-retro-monitor.txt
pip install python-dotenv
playwright install chromium
```

## 실행

```bash
# 1회 실행
python retro_monitor.py --once

# 반복 실행 (RETRO_INTERVAL_HOURS 주기)
python retro_monitor.py --loop
```

## 환경 변수

```env
# 필수: Nexus
NEXUS_BASE_URL=http://localhost:8081
NEXUS_REPOSITORY=es3
NEXUS_USERNAME=admin
NEXUS_PASSWORD=password

# 선택: TLS 검증
NEXUS_VERIFY_SSL=false

# 선택: 상태/큐 파일 경로
RETRO_STATE_PATH=./retro_state.json
RETRO_QUEUE_PATH=./retro_queue.jsonl

# 선택: 점검 주기 (반복 실행 시)
RETRO_INTERVAL_HOURS=24

# 선택: HTTP
REQUEST_TIMEOUT=30
USER_AGENT=retro-monitor/1.0
LOG_LEVEL=INFO

# 선택: VirusTotal
VT_API_KEY=

# 선택: YARA
YARA_RULE_PATH=

# 선택: LayerX 연동
LAYERX_BASE_URL=https://layerxsecurity.com
LAYERX_SAVE_RAW_HTML=false
LAYERX_SUMMARY_CHAR_LIMIT=400
```

## 보안 주의사항

- `.env` 파일은 절대 Git에 올리지 않습니다 (Nexus 비밀번호, VT API 키 포함)
- `retro_state.json`, `retro_queue.jsonl`도 `.gitignore`에 추가 권장
- 이미 노출된 키는 즉시 재발급 권장

## 한계

- `manifest.key`와 파일명/경로 모두 없으면 `extension_id` 복원 불가 → Chrome Web Store 버전 비교 제한
- Chrome Web Store 스크래핑은 UI 변경 시 파싱 실패 가능
- VT는 알려진 파일만 조회 — 신규 업로드된 파일은 `not_found` 응답 정상

## 추천 운영 방식

1. `HOLD_FOR_NEW_VERSION` → hm_new의 `request_holding`으로 전달
2. `HOLD_FOR_REPUTATION_REVIEW` → 분석 큐에 적재 후 재분석
3. `QUARANTINE_RECOMMENDED` → 운영자 알림 채널(Slack 등)으로 전달
