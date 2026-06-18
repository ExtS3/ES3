# frontend/templates

ExtS3-Web-UI의 Jinja2 HTML 템플릿 전체 모음입니다.
`main.py`의 FastAPI 라우트가 각 템플릿을 렌더링하며, 인증 수준에 따라 세 가지로 분류됩니다.

---

## 디렉토리 구조

```
templates/
├── index.html                 # 메인 대시보드 (로그인 필요)
│
├── admin/                     # 관리자 전용 페이지 (admin 롤 필요)
│   ├── admin_dash.html        # 관리자 메인 — 승인 대기 목록, 거절 이력
│   ├── log.html               # 분석 결과 상세 — 리포트, PDF 내보내기
│   ├── version_diff.html      # 버전 간 변경 내역 diff 뷰어
│   ├── permissions.html       # 유저·롤·권한 관리, 회원가입 승인
│   ├── policy.html            # 자동 정책 설정 (CRITICAL 자동 거절 등)
│   └── policy_catalog.html    # Chrome 그룹 정책 배치 파일 생성
│
├── auth/                      # 인증 페이지 (인증 불필요)
│   ├── login.html             # 로그인
│   ├── signup.html            # 회원가입 요청
│   └── change_credentials.html # 초기 비밀번호 변경 (로그인 필요)
│
├── library/
│   └── library.html           # 승인 완료 확장 목록, CRX·배치 다운로드
│
├── scenario/                  # 시나리오 관리 (admin 롤 필요)
│   ├── scenario_id.html       # 시나리오 목록, 업로드, vectorDB 재적재
│   └── scenario_detail.html   # 시나리오 상세, MD 문서 렌더링
│
├── search/                    # 확장 검색 흐름
│   ├── search.html            # 브라우저 선택 + 검색어 입력
│   ├── list.html              # 검색 결과 목록, 정렬, 페이지네이션
│   ├── no_result.html         # 결과 없음 화면 (현재 미사용)
│   └── detail/
│       └── detail.html        # 확장 상세, 검토 요청 버튼
│
├── setting/
│   └── user_setting.html      # 사용자 설정 (UI만, 저장 기능 미구현)
│
└── upload/
    └── build.html             # ZIP/VSIX 직접 업로드, 보안 분석 요청
```

---

## 인증 수준별 분류

| 인증 수준     | 검증 함수                    | 해당 템플릿                                                                                |
| ------------- | ---------------------------- | ------------------------------------------------------------------------------------------ |
| 인증 불필요   | 없음                         | `auth/login.html`, `auth/signup.html`                                                      |
| 로그인 필요   | `require_authenticated_page` | `index.html`, `auth/change_credentials.html`, `library/`, `search/`, `setting/`, `upload/` |
| admin 롤 필요 | `require_admin_page`         | `admin/`, `scenario/`                                                                      |

미인증 접근 시 `/login`으로 리다이렉트됩니다.

---

## index.html

**라우트**: `GET /`
**인증**: 로그인 필요

메인 대시보드 페이지입니다.

**주요 기능**

- `GET /api/nexus/dashboard`로 Nexus 현황 조회
- 스토리지 사용량 프로그레스바, 에셋 수, 승인 비율 카드 업데이트
- `safe/` 경로 에셋 최대 3개를 카드로 렌더링 (이름 이니셜, 버전, 용량)
- Nexus blobstore 데이터 없을 때 클라이언트 사이드 합산 (`buildClientSummary`)

**로드 CSS**: `common/nav.css`
**로드 JS**: `common.js`, `upload.js`, `index.js`

---

## 공통 구조

모든 인증 페이지는 아래 공통 레이아웃을 공유합니다.

**헤더 (상단 고정)**

- 로고 (`/static/img/logo.png`)
- 네비게이션 탭: 대시보드 / 앱 탐색 / 라이브러리 / 시나리오 관리
- 현재 페이지에 해당하는 탭이 인디고 색상으로 활성화

**사이드바 (좌측 고정)**

- 각 페이지 링크 목록
- 하단: Upload 버튼 + Login/Logout 링크 (`common.js`가 동적 주입)
  - `admin` 롤 없으면 `/admin`, `/scenario` 링크 숨김
  - 비로그인이면 `/search`, `/library`, `/build` 링크 숨김
  - `upload` 권한 없으면 Upload 버튼 숨김

**공통 로드 파일**

- `vendor/tailwindcss-forms-container-queries.js` — Tailwind 플러그인 (모든 페이지)
- `common/nav.css` — 네비게이션 폰트 통일 (모든 페이지)
- `common.js` — 세션 조회, 네비게이션 권한 제어 (인증 페이지 전체)

---

## 알려진 문제

| 파일                                   | 문제                                                                  | 조치                                                     |
| -------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------- |
| `search/search.html`                   | 브라우저 아이콘을 외부 URL(`lh3.googleusercontent.com`)에서 직접 참조 | 폐쇄망 환경에서 깨짐. `static/img/`로 이전 권장          |
| `setting/user_setting.html`            | 프로필 이미지를 외부 URL에서 직접 참조                                | 동일                                                     |
| `setting/user_setting.html`            | 저장 기능 미구현 (전용 JS 없음)                                       | 향후 `js/setting/user_setting.js` 추가 필요              |
| `search/no_result.html`                | 어디서도 리다이렉트되지 않는 미사용 상태                              | 삭제 또는 `list.js`에서 연결                             |
| `search/detail/detail.html`            | `search/download.js` 로드하나 파일이 비어있음                         | `<script>` 태그 제거 또는 파일 채우기                    |
| `log.html`, `list.html`, `detail.html` | `upload.js` 불필요 로드                                               | `common.js`가 권한 따라 버튼 숨기므로 무해하나 정리 권장 |

---

## 하위 폴더 README

각 폴더에 상세 문서가 있습니다.

| 경로                 | 내용                      |
| -------------------- | ------------------------- |
| `admin/README.md`    | 관리자 페이지 6개 상세    |
| `auth/README.md`     | 인증 페이지 3개 상세      |
| `library/README.md`  | 라이브러리 페이지         |
| `scenario/README.md` | 시나리오 관리 페이지 2개  |
| `search/README.md`   | 검색 흐름 4개 페이지 상세 |
| `setting/README.md`  | 사용자 설정 페이지        |
| `upload/README.md`   | 파일 업로드 페이지        |
