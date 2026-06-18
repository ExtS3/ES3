# backend/security_scan

사용자가 직접 업로드한 확장 ZIP 파일을 수신하고 suppressor 분석 서버로 전달하는 모듈입니다.
웹 스토어 검색 후 다운로드하는 `download/` 모듈과 달리, 사내 개발 확장이나 외부에서 받은 파일을 직접 업로드하는 경로를 담당합니다.

---

## 디렉토리 구조

```
security_scan/
├── file_save.py          # 업로드 파일 임시 저장
├── send_suppressor.py    # suppressor로 파일 전송 + 업로드 이력 기록
├── upload_registry.py    # 계정별 업로드 이력 DB 관리
└── scan_pending/
    └── .gitkeep          # 임시 저장 폴더 유지용 (내용 없음, 정상)
```

---

## 파일 구성

### file_save.py

업로드된 ZIP/VSIX 파일을 `scan_pending/` 폴더에 임시 저장합니다.

| 메서드 | 경로                           | 권한                | 설명                                        |
| ------ | ------------------------------ | ------------------- | ------------------------------------------- |
| `POST` | `/api/security_scan/file_save` | `request_extension` | 파일을 `scan_pending/`에 저장하고 경로 반환 |

`SAVE_DIR`은 `main.py`에서 import해 정적 파일 마운트에도 사용됩니다.

> ⚠️ `file_save.py` 하단의 `GET /scan_pending` 엔드포인트와 `main.py`의 `/scan_pending` 정적 마운트는 개발 편의용으로 임시 작성된 코드입니다. 업로드된 파일이 인증 없이 외부에 노출되는 보안 취약점이므로 **운영 전 반드시 제거**해야 합니다. 코드에도 `# 반드시 후에 삭제할 것` 주석이 달려 있습니다.

---

### send_suppressor.py

업로드된 파일을 suppressor의 `/file_scan` 엔드포인트로 전송합니다.

| 메서드 | 경로                   | 권한                | 설명                                |
| ------ | ---------------------- | ------------------- | ----------------------------------- |
| `POST` | `/api/send_suppressor` | `request_extension` | suppressor로 파일 전송 (백그라운드) |

요청 파라미터:

| 필드          | 설명                                            |
| ------------- | ----------------------------------------------- |
| `file`        | ZIP 또는 VSIX 파일                              |
| `plugin_name` | 확장 ID (ext_id로 사용)                         |
| `browser`     | `Chrome` 또는 `VSCode`                          |
| `version`     | 버전 문자열                                     |
| `mode`        | `first` (첫 업로드) 또는 `update` (추가 업로드) |

**동작 흐름**

```
POST /api/send_suppressor
  │
  ├── upload_registry.commit_upload()   ← 소유권 검증 + DB 기록 (동기, 즉시 실패 가능)
  │
  └── BackgroundTasks.add_task()
        └── send_to_suppressor_task()   ← suppressor /file_scan으로 POST 전송
              └── timeout 300초
```

실제 전송은 백그라운드로 처리되므로 사용자에게는 즉시 `"processing"` 응답이 반환됩니다.

**주요 환경변수**

| 변수명                  | 설명                 |
| ----------------------- | -------------------- |
| `SUPPRESSOR_PRIVATE_IP` | suppressor 서버 IP   |
| `PORT`                  | suppressor 서버 포트 |

---

### upload_registry.py

계정별 확장 업로드 이력을 `extension_uploads` 테이블에서 관리합니다.
`send_suppressor.py`에서 파일 전송 전에 호출되어 소유권 충돌을 먼저 차단합니다.

**함수**

| 함수                                                                   | 설명                                                            |
| ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| `commit_upload(mode, ext_id, ext_name, browser, version, uploader_id)` | 업로드 확정 기록. 이름 중복 또는 소유권 불일치 시 HTTPException |
| `bump_patch(version)`                                                  | 버전 마지막 세그먼트 1 증가 (`1.0.1` → `1.0.2`)                 |

**API 엔드포인트**

| 메서드 | 경로                   | 설명                                                      |
| ------ | ---------------------- | --------------------------------------------------------- |
| `GET`  | `/api/uploads/mine`    | 현재 로그인 유저의 업로드 이력 조회                       |
| `POST` | `/api/uploads/resolve` | 업로드 모드(`first`/`update`) 사전 검증 및 버전 자동 계산 |

**업로드 모드**

| 모드     | 동작                                                            |
| -------- | --------------------------------------------------------------- |
| `first`  | 신규 등록. 동일 `ext_id`가 이미 있으면 409 반환                 |
| `update` | 기존 확장 업데이트. 본인 소유가 아니면 403 반환. 버전 자동 증가 |

---

## scan_pending/ 폴더

업로드된 파일이 임시 저장되는 런타임 폴더입니다.

- `.gitkeep` — 빈 폴더를 Git이 추적하게 하는 표준 파일입니다. **내용이 없는 게 정상입니다.**
- 실제 업로드 파일(`.zip`, `.vsix`)은 `.gitignore`에 등록돼 있어 Git에 포함되지 않습니다.
- `file_save.py`가 시작 시 폴더가 없으면 자동으로 생성하므로, `.gitkeep`을 삭제해도 기능상 문제는 없습니다. 다만 폴더 존재 의도를 명시하는 용도로 유지하는 것을 권장합니다.
- 로컬 테스트 시 업로드했던 파일이 이 폴더에 남아있을 수 있습니다. Git에는 올라가지 않으니 무시해도 됩니다.

---

## 의존 관계

```
main.py
  ├── security_scan/file_save.router
  ├── security_scan/file_save.SAVE_DIR      ← /scan_pending 정적 마운트용 (삭제 예정)
  ├── security_scan/send_suppressor.router
  └── security_scan/upload_registry.router

send_suppressor.py
  └── upload_registry.commit_upload()

upload_registry.py
  └── database.get_db_connection()          ← extension_uploads 테이블
```
