# frontend/templates/auth

인증 관련 페이지 템플릿 모음입니다.

---

## 파일 구성

### login.html

**라우트**: `GET /login`
**인증**: 불필요 (비로그인 접근 가능)

로그인 페이지입니다.

- ID/비밀번호 입력 후 `POST /api/auth/login`
- 로그인 성공 시 `result.redirect` 또는 `/`로 이동
- 하단 "회원가입 신청" → `/signup` 링크

**로드 CSS**: `auth/login.css`, `common/nav.css`
**로드 JS**: `auth/login.js` (`defer` 속성으로 비동기 로드)

---

### signup.html

**라우트**: `GET /signup`
**인증**: 불필요 (비로그인 접근 가능)

회원가입 요청 페이지입니다.
가입 즉시 계정이 생성되지 않고, 관리자가 `/admin/permissions`에서 승인해야 로그인이 가능합니다.

- ID/비밀번호 입력 후 `POST /api/auth/signup`
- 성공 시 "Wait for administrator approval" 메시지 표시

**로드 JS**: `auth/signup.js`

---

### change_credentials.html

**라우트**: `GET /change-credentials`
**인증**: 로그인 필요 (`require_authenticated_page`)

초기 비밀번호 변경 페이지입니다.
로그인 후 `must_change_credentials=true`인 계정은 이 페이지로 강제 리다이렉트됩니다.

- 페이지 진입 시 `GET /api/auth/me`로 현재 ID를 username 필드에 자동 채움
- 새 ID/비밀번호 입력 후 `POST /api/auth/change-credentials`

**로드 JS**: `auth/change_credentials.js`
