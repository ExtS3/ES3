# frontend/templates/admin

관리자 전용 페이지 템플릿 모음입니다.
모든 라우트는 `main.py`의 `require_admin_page()`를 통해 admin 롤 보유 여부를 쿠키로 검증합니다. 미인증 시 `/login`으로 리다이렉트됩니다.

---

## 파일 구성

### admin_dash.html

**라우트**: `GET /admin`

관리자 메인 대시보드입니다.

- Nexus에 올라온 `review/` 경로 확장 목록을 날짜별 구분선과 페이지네이션으로 표시
- 각 항목에서 승인·거절 버튼 제공 (커스텀 확인 모달)
- 거절 이력 목록 및 PDF 다운로드 버튼
- 상단 카드: `/admin/permissions`, `/admin/policy` 바로가기

**로드 JS**: `common.js`, `admin/admin_pending.js`

---

### log.html

**라우트**: `GET /admin/log?id=...&name=...&browser=...&version=...&source_path=...`

확장 프로그램 분석 결과 상세 페이지입니다.

- URL 파라미터로 분석 대상을 특정해 `POST /api/admin/log` 호출
- 정적 분석, 동적 분석, 난독화, RAG 분석 4개 섹션 렌더링
- 자연어 위험 요약, 버전 변경 요약 카드 표시
- `summary.json` 다운로드 버튼, 분석 리포트 PDF 클라이언트 사이드 내보내기 (`html2canvas` + `jsPDF`)
- 승인·거절 버튼 (`decision.js`)

**로드 JS**: `common.js`, `upload.js`, `html2canvas.min.js`, `jspdf.umd.min.js`, `admin/admin_log.js`, `admin/decision.js`

> `upload.js` 로드는 불필요하나 `common.js`가 권한에 따라 버튼을 숨기므로 기능상 문제 없습니다.

---

### version_diff.html

**라우트**: `GET /admin/version-diff?id=...&name=...&browser=...&version=...`

버전 간 변경 내역 상세 페이지입니다. `log.html`의 "버전 diff 보기" 버튼에서 진입합니다.

- `sessionStorage`에서 버전 diff 데이터 읽기 (없으면 `POST /api/admin/log` 재조회)
- `manifest.json` 변경(권한·호스트 권한)과 코드 파일 변경 분리 렌더링
- 파일별 Unified Diff 뷰어 (추가/삭제 색상 구분)

**로드 JS**: `admin/version_diff.js`

---

### permissions.html

**라우트**: `GET /admin/permissions`

유저·롤·권한 관리 및 회원가입 요청 처리 페이지입니다.

- 회원가입 대기 요청 목록: 권한 체크박스 + 승인/거절 버튼
- 유저 목록: 롤·권한 아코디언 + "Save access" 버튼

**로드 JS**: `common.js`, `admin/permissions.js`

---

### policy.html

**라우트**: `GET /admin/policy`

자동 정책 설정 페이지입니다.

- CRITICAL 자동 거절, LOW 자동 승인 토글 스위치
- 저장 버튼 → `POST /api/admin/policy`
- 상단 "정책 문서 다운로드" 버튼 → `GET /api/admin/policy/default.pdf`

**로드 JS**: `admin/policy.js`

---

### policy_catalog.html

**라우트**: `GET /admin/policy-catalog`

Chrome 그룹 정책 배치 파일 생성 페이지입니다.

- 정책 타입 5종 드롭다운 선택 → 예시 JSON 자동 채움
- 미리보기 버튼 → 배치 스크립트 텍스트 출력
- 다운로드 버튼 → `.bat` 파일 다운로드

**로드 JS**: `admin/policy_catalog.js`
