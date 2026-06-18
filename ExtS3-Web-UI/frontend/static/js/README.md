# frontend/static/js

ExtS3-Web-UI 프론트엔드 JavaScript 전체 모음입니다.
페이지별 역할에 따라 폴더로 구분되며, 루트의 3개 파일은 전체 페이지 공통 또는 메인 대시보드 전용입니다.

---

## 디렉토리 구조

```
js/
├── common.js          # 전체 페이지 공통 — 세션 조회, 네비게이션 권한 제어
├── index.js           # 메인 대시보드 전용 — Nexus 통계 카드 렌더링
├── upload.js          # 메인 대시보드 전용 — Upload 버튼 → /build 이동 (1줄)
│
├── admin/             # 관리자 페이지 전용 JS (9개 파일)
├── auth/              # 인증 페이지 전용 JS (3개 파일)
├── library/           # 라이브러리 페이지 전용 JS (2개 파일)
├── search/            # 검색 페이지 전용 JS (4개 파일)
└── upload/            # 파일 업로드 페이지 전용 JS (1개 파일)
```

---

## 루트 파일

### common.js

**참조 템플릿**: 12개 전체 페이지 공통

모든 페이지에서 가장 먼저 실행되는 핵심 파일입니다. 세션 상태에 따라 네비게이션 전체를 제어합니다.

**사이드바 하단 버튼 동적 생성**

`side-bottom` div에 Upload 버튼(`moveBuild`)과 Login/Logout 링크를 innerHTML로 주입합니다.
`upload.js`의 클릭 이벤트는 이 버튼이 생성된 이후에 등록됩니다.

**세션 조회 및 전역 공유**

`GET /api/auth/session`을 호출하고 결과를 `window.exts3SessionPromise`(Promise)로 전역 노출합니다.
다른 JS 파일은 `await window.exts3SessionPromise`로 중복 API 호출 없이 세션을 재사용합니다.

캐시 전략:

- `sessionStorage('exts3_session_cache')` TTL 15초 우선 사용
- `localStorage('exts3_auth_token')` 있으면 `Authorization: Bearer` 헤더로 함께 전송

**권한 기반 네비게이션 제어**

| 조건               | 처리                                                                   |
| ------------------ | ---------------------------------------------------------------------- |
| `admin` 롤 없음    | `/admin`, `/scenario` 링크 숨김                                        |
| 비로그인           | `/search`, `/library`, `/build`, `/user_set` 링크 숨김                 |
| `upload` 권한 없음 | Upload 버튼 숨김                                                       |
| 로그인 상태        | Login → Logout으로 교체, 클릭 시 `POST /api/auth/logout` + 캐시 초기화 |
| 항상               | 헤더에 롤 배지(`sessionRoleBadge`) 삽입                                |

**헤더 검색창**

`header input`에 Enter 키 및 검색 아이콘 클릭 이벤트를 등록해 `/library?extName=...`으로 이동합니다.

---

### index.js

**참조 템플릿**: `frontend/templates/index.html`

메인 대시보드의 Nexus 현황 통계와 최근 승인 확장 카드를 렌더링합니다.

- `GET /api/nexus/dashboard`로 전체 에셋 + 스토리지 요약 조회
- 스토리지 사용량 프로그레스바, 에셋 수, 승인 비율 업데이트
- Nexus blobstore 데이터가 없을 때 클라이언트 사이드에서 합산 (`buildClientSummary`)
- `safe/` 경로 에셋 최대 3개를 카드로 렌더링

이 파일에만 있는 유틸 함수:

| 함수                     | 설명                                                      |
| ------------------------ | --------------------------------------------------------- |
| `formatBytes(bytes)`     | `1048576 → "1 MB"` 단위 자동 변환                         |
| `getSafeItemMeta(item)`  | Nexus 경로 `safe/{name}/{version}/{id}.zip`에서 메타 추출 |
| `buildClientSummary()`   | blobstore 데이터 없을 때 클라이언트 합산                  |
| `updateDashboardStats()` | 위 데이터를 받아 DOM 일괄 업데이트                        |

---

### upload.js

**참조 템플릿**: `frontend/templates/index.html`

`moveBuild` 버튼 클릭 시 `/build`로 이동하는 단 1줄짜리 파일입니다.
`common.js`가 버튼을 먼저 생성한 뒤 이 파일이 로드되므로 순서 문제 없이 정상 작동합니다.
`upload` 권한이 없으면 `common.js`가 버튼을 숨기므로 클릭 자체가 발생하지 않습니다.

---

## 하위 폴더 요약

각 폴더에 README가 있습니다. 아래는 폴더별 담당 범위 요약입니다.

### admin/

관리자 전용 페이지 9개 파일. 분석 로그 조회, 승인·거절 처리, 권한·정책·시나리오 관리, 버전 diff 뷰어를 담당합니다.
→ 자세한 내용은 `admin/README.md` 참고.

### auth/

로그인, 회원가입, 초기 비밀번호 변경 3개 파일. 인증 API 호출과 토큰/세션 초기화를 담당합니다.
→ 자세한 내용은 `auth/README.md` 참고.

### library/

승인 완료(`safe/`) 확장 목록 페이지 파일. Nexus 에셋 조회, 이름 검색 필터, CRX/배치 파일 다운로드 드롭다운을 담당합니다.
→ 자세한 내용은 `library/README.md` 참고.

### search/

확장 검색 흐름 전체 4개 파일. 브라우저 선택 → 검색 결과 목록 → 상세 페이지 → 검토 요청까지의 흐름을 담당합니다.
→ 자세한 내용은 `search/README.md` 참고.

### upload/

ZIP/VSIX 직접 업로드 1개 파일. 첫 업로드 / 버전 업 모드 분기, 파일 저장 및 suppressor 전송 요청을 담당합니다.
→ 자세한 내용은 `upload/README.md` 참고.

---

### 중복 구현 (나중에 정리)

아래 함수들이 여러 파일에 각자 독립 구현돼 있습니다. 동작에는 문제없으나 수정 시 여러 파일을 동시에 고쳐야 합니다. 향후 `js/utils/` 같은 공통 유틸로 추출을 권장합니다.

| 함수                                    | 중복 위치                                                                                               |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `escapeHtml()`                          | `index.js`, `admin/admin_log.js`, `admin/scenario_detail.js`, `search/list.js`, `library/library.js` 등 |
| `showCustomConfirm()` / `showConfirm()` | `admin/admin_pending.js`, `admin/scenario_id.js`, `admin/scenario_detail.js`, `upload/build.js`         |
| `showToast()`                           | `admin/scenario_id.js`, `admin/scenario_detail.js`                                                      |
| `splitVersionDiff()`                    | `admin/admin_log.js`, `admin/version_diff.js`                                                           |
