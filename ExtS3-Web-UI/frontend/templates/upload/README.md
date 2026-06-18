# frontend/templates/upload

## build.html

**라우트**: `GET /build`
**인증**: 로그인 필요 (`require_authenticated_page`)

ZIP/VSIX 파일을 직접 업로드해 보안 분석을 요청하는 페이지입니다.

**주요 기능**

- 업로드 모드 탭 전환:
  - `first` — 신규 확장 첫 업로드. 버전 `1.0.0` 자동 설정
  - `update` — 기존 확장 버전 업. `GET /api/uploads/mine`으로 내 업로드 목록 조회 후 선택
- 파일 선택 → 업로드 확인 모달 → `POST /api/uploads/resolve` (이름 중복·소유권 검증 + 버전 확정)
- `POST /api/security_scan/file_save` → 임시 저장
- `POST /api/send_suppressor` → suppressor 보안 분석 전송 (백그라운드)
- 완료 시 `/`로 이동

**로드 JS**: `common.js`, `upload.js`, `upload/build.js`
