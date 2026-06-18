# backend/download

웹 스토어에서 확장 프로그램을 다운로드하고 suppressor로 전송하는 모듈입니다.
사용자가 검색 결과에서 확장을 선택하면 이 모듈이 스토어에서 직접 파일을 받아 보안 분석 파이프라인으로 넘깁니다.

---

## 파일 구성

### download_zip.py

다운로드 흐름 전체를 조율하는 API 엔드포인트 파일입니다.

**`POST /api/download_zip`** (`request_extension` 권한 필요)

요청 파라미터:

| 필드             | 설명                                                                 |
| ---------------- | -------------------------------------------------------------------- |
| `extension_id`   | 확장 ID (Chrome: 영문 32자, VS Code: `publisher.name` 형식)          |
| `browser`        | `"Chrome"` 또는 `"VSCode"`                                           |
| `version`        | 확장 버전 (VS Code 다운로드 시 필수)                                 |
| `extName`        | 확장 표시 이름                                                       |
| `bypass_holding` | `true`이면 홀딩 큐를 건너뛰고 즉시 스캔 (`bypass_holding` 권한 필요) |

**동작 흐름**

```
사용자 요청
  │
  ├── Chrome → chrome_download(extID)
  │     └── Google CRX API에서 .zip 다운로드 → downloads/ 저장
  │
  └── VSCode → vscode_download(extID, version)
        └── Open VSX API에서 .vsix 다운로드 → downloads/ 저장
  │
  ├── bypass_holding=false → suppressor /api/holding (홀딩 큐 등록)
  └── bypass_holding=true  → suppressor /file_scan  (즉시 스캔)
        ↑ BackgroundTask로 비동기 전송, 사용자에게는 즉시 success 응답
```

**주요 환경변수**

| 변수명                  | 설명                                                            |
| ----------------------- | --------------------------------------------------------------- |
| `SUPPRESSOR_PRIVATE_IP` | suppressor 서버 IP                                              |
| `PORT`                  | suppressor 서버 포트                                            |
| `FILE_SCAN_URL`         | suppressor `/file_scan` 전체 URL (설정 시 위 두 변수 대신 사용) |

---

### chrome.py

Google CRX API에서 Chrome 확장을 다운로드합니다.

**`chrome_download(extID, save_path="downloads") → str | None`**

- `https://clients2.google.com/service/update2/crx` 엔드포인트 사용
- Chrome 123.0 User-Agent로 요청 (구버전 UA는 204 응답으로 거부됨)
- 확장 이름은 `get_extension_info(extID)`로 조회해 파일명으로 사용
- 파일명 특수문자(`\ / : * ? " < > |`) 제거 후 `{확장명}.zip`으로 저장
- 성공 시 로컬 저장 경로 반환, 실패 시 `None` 반환

---

### vscode.py

Open VSX Registry API에서 VS Code 확장을 다운로드합니다.

**`vscode_download(ext_id, version, save_path="downloads") → str | None`**

- `ext_id`는 `publisher.name` 형식 (예: `ms-python.python`)
- `https://open-vsx.org/api/{publisher}/{name}/{version}/file/...vsix` 경로에서 직접 다운로드
- `{ext_id}-{version}.vsix` 파일명으로 저장
- 버전이 없거나 `"N/A"`이면 다운로드 스킵 후 `None` 반환

---

## 런타임 생성 폴더

`downloads/` 폴더가 다운로드 시 자동 생성됩니다.
`.gitignore`에 `downloads/`가 등록돼 있어 Git에는 포함되지 않습니다.

---

## 의존 관계

```
main.py
  └── download_zip.router

download_zip.py
  ├── chrome.chrome_download()
  │     └── backend/search/browser/chrome_id.get_extension_info()
  └── vscode.vscode_download()
```
