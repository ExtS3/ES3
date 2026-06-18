# frontend/static/js/auth

인증 관련 페이지 전용 JavaScript 파일 모음입니다.

---

## 파일 구성

### login.js

**대응 템플릿**: `frontend/templates/auth/login.html`

로그인 폼 제출 처리를 담당합니다.

**동작 흐름**

1. `POST /api/auth/login` 호출
2. 응답의 `token`을 `localStorage('exts3_auth_token')`에 저장
3. `sessionStorage('exts3_session_cache')` 초기화 후 `/api/auth/session` 재조회
4. 세션 정보를 15초 TTL로 `sessionStorage`에 캐싱
5. `result.redirect` 또는 `/`로 이동

> `localStorage` 토큰은 `common.js`의 `loadSession()`에서 `Authorization: Bearer` 헤더로 읽어 사용됩니다. 서버는 `HttpOnly` 쿠키와 Bearer 토큰 양쪽을 모두 수용하므로 정상 동작합니다.

---

### signup.js

**대응 템플릿**: `frontend/templates/auth/signup.html`

회원가입 요청 폼 제출을 담당합니다.

**동작 흐름**

1. `POST /api/auth/signup` 호출
2. 성공 시 "Wait for administrator approval" 메시지 표시 후 폼 초기화
3. 실패 시 서버 오류 메시지 인라인 표시

관리자가 승인하기 전까지는 로그인 불가합니다. (`backend/admin/permissions.py`의 `/signup-requests/{id}/approve` 참고)

---

### change_credentials.js

**대응 템플릿**: `frontend/templates/auth/change_credentials.html`

초기 비밀번호 변경 폼을 담당합니다. 로그인 직후 `must_change_credentials=true`인 계정은 이 페이지로 리다이렉트됩니다.

**동작 흐름**

1. 페이지 진입 시 `GET /api/auth/me`로 현재 유저 ID를 읽어 username 필드에 자동 채움 (IIFE로 즉시 실행)
2. 폼 제출 시 `POST /api/auth/change-credentials` 호출
3. 응답의 `token`을 `localStorage`에 저장
4. `result.redirect` 또는 `/`로 이동

---

## 공통 사항

`login.js`와 `change_credentials.js` 모두 응답 토큰을 `localStorage('exts3_auth_token')`에 저장합니다.
이 값은 `frontend/static/js/common.js`의 `loadSession()`에서 읽혀 `Authorization: Bearer` 헤더로 사용됩니다.
서버(`auth/security.py`)는 쿠키와 헤더 양쪽을 모두 수용하므로 정상 동작입니다.
