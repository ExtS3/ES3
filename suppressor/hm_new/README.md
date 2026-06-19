# hm_new — 홀딩 큐 매니저

확장 프로그램을 즉시 분석하지 않고 일정 시간 **홀딩(보류)** 했다가 만료 시점에 `/file_scan`으로 전달하는 파이프라인입니다.

`main.py`의 `lifespan`에서 `hm_start()`로 서버 시작 시 자동으로 실행됩니다.

---

## 동작 흐름

```
holding.py (/api/holding 라우터)
  └── request_holding(ext_id, browser, version, ext_name, file_data)
        ├── nexus.upload()             → Nexus holding/ 경로에 ZIP 저장
        └── pending/{ext_id}.json 생성 → 스케줄러가 파일 감지

scheduler.py (watchdog + APScheduler)
  ├── pending/ 폴더 감시 (watchdog)
  │     └── .json 파일 생성 감지 → trigger=date 잡 등록
  ├── 서버 재시작 시 pending/ 기존 파일로 잡 재등록
  └── 만료 시각 도달 (_release_job)
        ├── nexus.download()           → Nexus에서 ZIP 다운로드
        ├── POST /file_scan            → 분석 파이프라인으로 전달
        ├── nexus.delete()             → Nexus holding/ 파일 삭제
        └── pending/{ext_id}.json 삭제
```

---

## 파일 구성

### config.py

환경변수 로드 및 전역 설정입니다. `.env`를 `hm_new/` → 부모(suppressor 루트) 순으로 탐색합니다.

| 변수               | 기본값                            | 설명                                          |
| ------------------ | --------------------------------- | --------------------------------------------- |
| `HOLDING_SECONDS`  | `30`                              | 홀딩 대기 시간 (초). 실서비스: `604800` (7일) |
| `NEXUS_BASE_URL`   | `http://localhost:8081`           | Nexus 서버 URL                                |
| `NEXUS_REPOSITORY` | `es3`                             | Nexus 레포지토리명                            |
| `NEXUS_USERNAME`   | `admin`                           | Nexus 사용자                                  |
| `NEXUS_PASSWORD`   | `admin123`                        | Nexus 비밀번호                                |
| `PENDING_DIR`      | `hm_new/pending`                  | 대기 파일 디렉토리                            |
| `OUTPUT_DIR`       | `hm_new/released`                 | 릴리즈 완료 디렉토리                          |
| `FILE_SCAN_URL`    | `http://localhost:8000/file_scan` | 분석 전달 엔드포인트                          |

### manager.py

`request_holding()` — 홀딩 등록 진입점입니다. 이미 홀딩 중인 확장(`pending/` 파일 존재)은 중복 등록을 거부합니다.

### nexus.py

Nexus raw repository와 통신합니다. 저장 경로: `holding/{browser}/{ext_name}/{version}/{ext_id}.zip`

| 함수         | 역할                      |
| ------------ | ------------------------- |
| `upload()`   | ZIP 바이너리 PUT 업로드   |
| `download()` | ZIP 바이너리 GET 다운로드 |
| `delete()`   | 파일 삭제 (404는 무시)    |

### scheduler.py

APScheduler `BackgroundScheduler` + watchdog `Observer`로 구성됩니다.

- **watchdog**: `pending/` 폴더에 `.json` 파일이 생성되면 즉시 `_register_from_pending()` 호출
- **APScheduler**: `trigger="date"`로 정확한 만료 시각에 `_release_job()` 실행
- **재시작 복구**: 서버 재시작 시 `pending/`에 남은 `.json` 파일들을 읽어 잡 재등록. 이미 만료된 파일은 즉시 릴리즈

### **main**.py

CLI 진입점입니다.

```bash
python -m hm_new              # 스케줄러 단독 실행 (Ctrl+C로 종료)
python -m hm_new hold <id>   # 특정 확장 홀딩 등록
```

`_ensure_packages()`가 실행 시 `requirements.txt`의 패키지를 자동 설치합니다. 단, 루트 `requirements.txt`에 이미 동일 패키지가 포함되어 있어 suppressor 통합 환경에서는 불필요합니다.

---

## 디렉토리

### pending/

홀딩 대기 중인 확장의 메타 JSON 파일이 저장됩니다.

```json
{
  "extension_id": "abcdefg...",
  "browser": "chrome",
  "version": "1.0.0",
  "ext_name": "My Extension",
  "release_at": "2025-01-01T00:00:00+00:00"
}
```

런타임 생성 파일이므로 `.gitkeep`으로 폴더 구조만 git에 유지합니다.
