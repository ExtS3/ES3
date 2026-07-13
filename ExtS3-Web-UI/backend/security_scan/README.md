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
├── scan_status.py        # 검사 내역(잡) 상태 저장소 + 조회/SSE/내부 콜백 API
├── scan_jobs/            # 잡 상태 JSON 저장 폴더 (런타임, .gitignore)
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
  ├── extension_registry.check_registry_duplicate(plugin_name, version)
  │     └── 이미 존재하면 409 반환 (버전이 다르면 별개 확장으로 통과)
  │
  ├── upload_registry.commit_upload()   ← 소유권 검증 + DB 기록 (동기, 즉시 실패 가능)
  ├── extension_registry.upsert_registry_entry(status="review")
  │
  └── BackgroundTasks.add_task()
        └── send_to_suppressor_task()   ← suppressor /file_scan으로 POST 전송
              └── timeout 300초
```

`extension_registry`는 `upload_registry`(계정별 소유권·버전 제안용)와 별개로, 업로드/웹스토어 다운로드
출처를 구분하지 않고 Nexus 레포 현황을 미러링하는 공용 테이블입니다. 상세는 `backend/README.md`의
"extension_registry.py" 섹션 참고.

실제 전송은 백그라운드로 처리되므로 사용자에게는 즉시 `"processing"` 응답이 반환됩니다.

**주요 환경변수**

| 변수명                  | 설명                 |
| ----------------------- | -------------------- |
| `SUPPRESSOR_PRIVATE_IP` | suppressor 서버 IP   |
| `PORT`                  | suppressor 서버 포트 |

---

### scan_status.py

`/admin/scan-status` 검사 내역 페이지의 상태 저장소이자 API입니다. 잡 상태는 `scan_jobs/scan_jobs.json` 파일에 저장됩니다.

| 메서드   | 경로                                | 권한             | 설명                                          |
| -------- | ----------------------------------- | ---------------- | --------------------------------------------- |
| `GET`    | `/api/scan-status`                  | 로그인 사용자    | 전체 잡 목록 + 상태별 카운트                  |
| `GET`    | `/api/scan-status/stream`           | 로그인 사용자    | SSE 실시간 스트림 (1초 주기, 변경 시만 push)  |
| `POST`   | `/api/internal/scan-status/{job_id}`| 콜백 토큰        | suppressor가 단계별 진행률을 보고하는 내부 콜백 |
| `DELETE` | `/api/admin/scan-status/{job_id}`   | 관리자           | 잡 내역 삭제                                  |

**상태 라이프사이클**: `holding`(홀딩 대기) → `queued`(대기) → `running`(검사 진행 중) → `review`(검토 대기) / `safe`(승인) / `reject`(거부), 실패 시 `error`.

**잡 생성/갱신 경로** (모든 검사 시작 경로가 여기로 모입니다):

- 직접 업로드 `/api/send_suppressor` → 잡 생성 후 job_id·progress_url·progress_token을 suppressor로 전달
- 웹스토어 다운로드 `/api/download_zip` → 잡 생성 (홀딩 경로면 `holding` 상태). progress 정보는 suppressor holding pending json에 저장돼 릴리즈 시 `/file_scan`으로 전달
- suppressor `/file_scan` → 단계별로 `/api/internal/scan-status/{job_id}` 콜백 (started→file_saved→…→complete)
- 결과 수신 `/api/receive` → `update_job_by_ext(ext_id, version)`으로 최종 판정(review/safe/reject) 반영
- 관리자 승인/거부 `/api/decision/approve|reject` → 잡 상태 safe/reject 갱신

**환경변수**: `SCAN_STATUS_CALLBACK_BASE_URL` (suppressor가 콜백할 웹 서버 주소), `SCAN_STATUS_CALLBACK_TOKEN` (콜백 검증 토큰, 빈 값이면 검증 생략).

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
