# frontend/static/js/admin

관리자 페이지 전용 JavaScript 파일 모음입니다.
각 파일은 대응하는 HTML 템플릿에서 `<script src="...">` 태그로 로드됩니다.

---

## 파일 구성

### admin_log.js

**대응 템플릿**: `frontend/templates/admin/log.html`

분석 결과 상세 페이지의 전체 로직을 담당합니다.

**주요 기능**

- URL 파라미터(`id`, `name`, `browser`, `version`, `source_path`)를 읽어 `POST /api/admin/log` 호출
- 수신한 JSON을 파싱해 기본 정보, 보안 배지(CRITICAL/HIGH/MEDIUM/LOW 카운트), 분석 리포트 렌더링
- 정적 분석, 동적 분석, 난독화, RAG 분석 4개 섹션을 각각 렌더링
- 자연어 위험 요약 자동 생성 (`renderHumanRiskSummary`)
- 버전 변경 요약 카드 렌더링 + `version_diff.js` 페이지 연결 (`setupVersionDiffButton`)
  - 버전 diff 데이터를 `sessionStorage`에 저장해 페이지 이동 시 재사용
- `summary.json` 다운로드 버튼, `html2canvas` + `jsPDF`로 PDF 클라이언트 사이드 내보내기

> `splitVersionDiff()` 함수가 이 파일과 `version_diff.js` 양쪽에 동일하게 정의돼 있습니다. 두 페이지 간 공유 모듈이 없어 복사된 상태입니다.

---

### admin_pending.js

**대응 템플릿**: `frontend/templates/admin/admin_dash.html`

관리자 대시보드 페이지의 로직을 담당합니다.

**주요 기능**

- `POST /api/nexus/list`로 Nexus 에셋 목록 조회 → `review/` 경로 필터링 → 날짜 내림차순 정렬
- 날짜별 구분선이 있는 페이지네이션 테이블 렌더링 (페이지당 4개)
- 드래그와 클릭 구분 처리 (`handleMouseDown` / `handleRowClick`, `mousedown` 좌표 차 5px 기준)
- 커스텀 confirm 모달 (`showCustomConfirm`) — Promise 기반 비동기 확인 다이얼로그
- 승인 → `POST /api/decision/approve`, 거절 → `POST /api/decision/reject` 호출
- 거절 목록 조회 (`GET /api/decision/rejects`) 및 PDF 다운로드 버튼 연결
- 거절 목록 패널이 DOM에 없으면 동적으로 생성 (`ensureRejectListContainer`)

> ⚠️ `approveApp`, `rejectApp` 함수가 파일 안에 2번씩 선언돼 있습니다. 위쪽은 `alert`만 쓰는 미완성 버전, 아래쪽은 실제 서버 fetch 완성 버전입니다. JavaScript 특성상 마지막 선언이 덮어쓰므로 동작에는 문제없지만, 위쪽 미완성 함수 2개는 삭제 권장합니다.

---

### decision.js

**대응 템플릿**: `frontend/templates/admin/log.html` (승인/거절 버튼 영역)

분석 결과 상세 페이지의 승인·거절 버튼 로직입니다.

**동작**

- URL 파라미터에서 `id`, `name`, `browser`, `version`, `source_path` 추출
- 승인 버튼 → `POST /api/decision/approve`
- 거절 버튼 → `POST /api/decision/reject`
- 처리 후 `/admin`으로 리다이렉트

---

### permissions.js

**대응 템플릿**: `frontend/templates/admin/permissions.html`

유저·롤·권한 관리 페이지의 로직입니다.

**주요 기능**

- 페이지 진입 시 권한 목록, 롤 목록, 유저 목록, 회원가입 요청 목록을 `Promise.all`로 동시 조회
- 회원가입 요청 목록: 권한 체크박스와 승인/거절 버튼 렌더링
  - 승인 → `POST /api/admin/permissions/signup-requests/{id}/approve`
  - 거절 → `POST /api/admin/permissions/signup-requests/{id}/reject`
- 유저 목록: 롤·권한 체크박스를 `<details>` 아코디언으로 렌더링
  - "Save access" 클릭 시 롤·권한 동시 저장 (PUT 2회 순차 호출)
- 표시 롤은 `admin`, `user`만 노출 (`visibleRoleNames` 필터)

---

### policy.js

**대응 템플릿**: `frontend/templates/admin/policy.html`

자동 정책 설정 페이지의 로직입니다.

**주요 기능**

- 페이지 진입 시 `GET /api/admin/policy`로 현재 설정 조회 → 체크박스에 반영
- 저장 버튼 → `POST /api/admin/policy`로 변경값 전송
- 성공/실패 메시지를 인라인 배너로 표시

**관리하는 설정값**

| 필드                           | 설명                           |
| ------------------------------ | ------------------------------ |
| `critical_auto_reject_enabled` | CRITICAL 위험도 자동 거절 여부 |
| `low_auto_approve_enabled`     | LOW 위험도 자동 승인 여부      |
| `fallback_decision`            | 항상 `"review"` 고정 전송      |

---

### policy_catalog.js

**대응 템플릿**: `frontend/templates/admin/policy_catalog.html`

Chrome 그룹 정책 배치 파일 생성 페이지의 로직입니다. IIFE(`(() => { ... })()`)로 스코프 격리돼 있습니다.

**주요 기능**

- 페이지 진입 시 `GET /api/install-helper/policy-catalog/types`로 정책 타입 5종 목록 조회
- 타입 선택 시 예시 JSON 자동 채움 + 정책 이름 힌트 표시
- 미리보기 버튼 → `POST /api/install-helper/policy-catalog/render` → 배치 스크립트 텍스트 출력
- 다운로드 버튼 → `POST /api/install-helper/policy-catalog/download` → `.bat` 파일 다운로드
- 인증은 `HttpOnly` 쿠키(`exts3_auth`) 자동 포함 방식 (`credentials: 'same-origin'`)

---

### scenario_id.js

**대응 템플릿**: `frontend/templates/scenario/scenario_id.html`

시나리오 목록 관리 페이지의 로직입니다.

**주요 기능**

- vectorDB 상태 조회 (`GET /api/admin/scenario/db-status`) → 상태 배지 표시
- 시나리오 전체 목록 조회 (`GET /api/admin/scenario/list`) → 테이블 렌더링
- 이름/ID/태그 기반 실시간 검색 필터
- JSON 파일(필수) + MD 파일(선택) 업로드 (`POST /api/admin/scenario/upload`)
- 개별 시나리오 삭제 (`DELETE /api/admin/scenario/delete/{id}`)
- vectorDB 전체 재적재 (`POST /api/admin/scenario/reload`)
- 커스텀 확인 다이얼로그 (`showConfirm`, Promise 기반) + 토스트 알림 (`showToast`)
- 기본 제공(`builtin`) 시나리오는 삭제 버튼 비활성화

---

### scenario_detail.js

**대응 템플릿**: `frontend/templates/scenario/scenario_detail.html`

시나리오 상세 페이지의 로직입니다.

**주요 기능**

- `window.__SCENARIO_ID__`에서 ID를 읽어 `GET /api/admin/scenario/detail/{id}` 조회
- 핑거프린트 4개 섹션(`manifest_profile`, `capability_profile`, `static_code_signals`, `predicted_flows`) 재귀 렌더링
- MD 문서 렌더링 (외부 라이브러리 없이 자체 마크다운 파서 구현)
  - 지원: 헤딩(`#`, `##`, `###`), 순서/비순서 목록, 코드 펜스, 굵게, 인라인 코드
- 기본 제공 시나리오는 삭제 버튼 숨김, 커스텀 시나리오만 삭제 가능
- ID 클립보드 복사 버튼
- `showConfirm` / `showToast` — `scenario_id.js`와 동일 유틸 (별도 공유 모듈 없이 각자 보유)

---

### version_diff.js

**대응 템플릿**: `frontend/templates/admin/version_diff.html`

버전 간 변경 내역 상세 페이지의 로직입니다.

**주요 기능**

- `sessionStorage`에서 `version_diff:{id}:{version}` 키로 데이터 읽기 (이전 페이지에서 저장한 값)
- `sessionStorage`에 없으면 `POST /api/admin/log`로 재조회
- manifest.json 변경(권한·호스트 권한·기타 필드)과 코드 파일 변경을 분리 렌더링
- 파일별 Unified Diff 뷰어 (`renderUnifiedDiff`) — 추가(녹색) / 삭제(빨간색) / 컨텍스트 3열 테이블
- 난독화/압축 파일은 diff 대신 안내 메시지 표시
- `splitVersionDiff()` — `admin_log.js`와 동일한 로직 (별도 공유 모듈 없이 복사된 상태)

---

## 공통 패턴

**커스텀 모달** (`showCustomConfirm` / `showConfirm`)
Promise를 반환해 `await`로 사용자 선택을 기다립니다. `admin_pending.js`와 `scenario_id.js`, `scenario_detail.js`가 각자 구현을 보유합니다.

**토스트 알림** (`showToast`)
`scenario_id.js`와 `scenario_detail.js`가 동일한 구현을 보유합니다.

**`splitVersionDiff()`**
`admin_log.js`와 `version_diff.js`가 동일한 함수를 각자 보유합니다.

> 위 3가지는 현재 동작에 문제는 없지만, 향후 `js/admin/utils.js` 같은 공통 유틸 파일로 추출하면 유지보수가 쉬워집니다.

---

## 참조 현황

| 파일                 | 참조 템플릿                     |
| -------------------- | ------------------------------- |
| `admin_log.js`       | `admin/log.html`                |
| `admin_pending.js`   | `admin/admin_dash.html`         |
| `decision.js`        | `admin/log.html`                |
| `permissions.js`     | `admin/permissions.html`        |
| `policy.js`          | `admin/policy.html`             |
| `policy_catalog.js`  | `admin/policy_catalog.html`     |
| `scenario_id.js`     | `scenario/scenario_id.html`     |
| `scenario_detail.js` | `scenario/scenario_detail.html` |
| `version_diff.js`    | `admin/version_diff.html`       |
