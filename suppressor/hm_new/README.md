# hm_new — 확장 홀딩 매니저

보안 검토가 필요한 확장 프로그램을 Nexus에 임시 보관(홀딩)했다가, 지정된 시간이 경과하면 자동으로 `/file_scan`으로 재분석을 요청하는 스케줄러입니다.

> **주의**: 홀딩 만료 시 `released/` 폴더에 파일이 생성되지 않습니다. 만료 후 동작은 Nexus ZIP 다운로드 → `/file_scan` POST → Nexus 삭제입니다.

## 구조

```
hm_new/
├── config.py      환경변수 로드 및 전역 설정 (HOLDING_SECONDS, FILE_SCAN_URL 등)
├── nexus.py       Nexus raw repository 연동 (ZIP 업로드/다운로드/삭제)
├── manager.py     홀딩 등록 (Nexus 업로드 + pending 파일 생성)
├── scheduler.py   pending 폴더 watchdog 감시 + APScheduler 만료 잡 등록
├── __main__.py    CLI 진입점 (스케줄러 시작 또는 hold 명령)
├── pending/       홀딩 대기 JSON 파일 저장소 ({extension_id}.json)
└── released/      (레거시 폴더, 현재 코드에서 사용하지 않음)
```

## 실제 홀딩 플로우

```
hold 요청 (request_holding)
    │
    ├─ Nexus 업로드: extensions/chrome/{ext_name}/{version}/{ext_id}.zip
    │
    └─ pending/{ext_id}.json 생성:
       { "extension_id": "...", "browser": "...", "version": "...",
         "ext_name": "...", "release_at": "2026-05-26T10:00:00+00:00" }

watchdog가 파일 감지 → APScheduler에 trigger="date" 잡 등록

만료 시각 도달 → _release_job 실행:
    1. Nexus에서 ZIP 다운로드
    2. /file_scan으로 multipart POST (재분석 요청)
    3. Nexus에서 ZIP 삭제
    4. pending/{ext_id}.json 삭제
```

## 재시작 복구

스케줄러 시작 시 `pending/` 폴더에 남아있는 `.json` 파일을 전부 읽어 잡 재등록합니다.
이미 만료된 항목은 즉시 `_release_job`을 실행합니다.

## FastAPI 통합 (main.py에서 호출)

```python
from hm_new import start as hm_start, stop as hm_stop

# lifespan startup
hm_start()

# lifespan shutdown
hm_stop()
```

`POST /api/holding` 엔드포인트는 `holding.py`를 통해 `request_holding`을 호출합니다.

## CLI 사용

```bash
# 터미널 1 — 스케줄러 실행 (계속 켜놓기)
python -m hm_new

# 터미널 2 — 홀딩 등록 (미사용; 실제 운영에서는 /api/holding API 사용)
python -m hm_new hold <extension_id>
```

## 주요 함수

### `request_holding(extension_id, browser, version, ext_name, file_data)` — `manager.py`

- 이미 `pending/{extension_id}.json`이 존재하면 중복 홀딩 방지 후 반환
- Nexus에 ZIP 업로드 → pending 파일 생성
- `HOLDING_SECONDS` 후 만료 시각(`release_at`)을 ISO 형식으로 저장

### `start()` / `stop()` — `scheduler.py`

- `start()`: BackgroundScheduler(UTC) 시작 → pending 폴더 복구 → watchdog Observer 시작
- `stop()`: scheduler shutdown

## 환경 변수 (.env)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `HOLDING_SECONDS` | 30 | 홀딩 시간 (실서비스: 604800 = 7일) |
| `FILE_SCAN_URL` | http://localhost:8001/file_scan | 만료 시 재분석 전송 주소 |
| `NEXUS_BASE_URL` | http://localhost:8081 | Nexus 주소 |
| `NEXUS_REPO` | holding | Nexus 홀딩용 레포 이름 |
| `NEXUS_USER` | admin | Nexus 계정 |
| `NEXUS_PASSWORD` | — | Nexus 비밀번호 |
| `PENDING_DIR` | pending | 홀딩 대기 파일 폴더 |

## 의존 관계

- `APScheduler` — 만료 시각 기반 잡 실행
- `watchdog` — pending 폴더 파일 시스템 감시
- `requests` — Nexus HTTP 및 `/file_scan` POST
- 상위 `main.py`의 `lifespan`에서 `start`/`stop` 호출
