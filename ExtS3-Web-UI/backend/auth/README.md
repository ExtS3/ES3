# backend/auth

FastAPI 앱 전반의 인증·인가 시스템을 담당하는 모듈입니다.
외부 라이브러리(JWT 등) 없이 표준 라이브러리(`hmac`, `hashlib`, `secrets`)만으로 구현돼 있습니다.

---

## 파일 구성

### security.py

인증의 핵심 로직이 모두 모여 있는 파일입니다.

**토큰 발급·검증**

- `create_access_token(user_id)` — `{base64_payload}.{hmac_sig}` 형태의 커스텀 토큰 발급
- `decode_access_token(token)` — 서명 검증 + 만료 확인, 실패 시 401 raise
- 토큰은 쿠키(`exts3_auth`) 또는 `Authorization: Bearer` 헤더 양쪽 모두 수용

**비밀번호 해시**

- `hash_password(password)` — PBKDF2-SHA256, 26만 회 반복, 랜덤 salt 적용
- `verify_password(password, stored_hash)` — `hmac.compare_digest` 기반 타이밍 공격 방지

**FastAPI 의존성 함수**

- `get_current_user` — 토큰 추출 → 디코딩 → DB 조회까지 수행하는 Depends 함수
- `require_permission(permission)` — 특정 권한 보유 여부 검사 (`Depends(require_permission("upload"))` 형태로 사용)
- `require_admin` — `admin` 롤 보유 여부 검사

**인메모리 캐시**

- 유저 정보·롤·권한을 각각 TTL 5초(기본값, 환경변수 `AUTH_CACHE_TTL_SECONDS`로 조정) 캐싱
- 유저 정보 변경 시 `clear_auth_cache(user_id)` 로 즉시 무효화

**주요 환경변수**

| 변수명                   | 기본값           | 설명                                                                              |
| ------------------------ | ---------------- | --------------------------------------------------------------------------------- |
| `AUTH_SECRET`            | 런타임 랜덤 생성 | 토큰 서명 키. 재시작 시 기존 토큰 무효화되므로 운영 환경에서는 반드시 고정값 설정 |
| `AUTH_TOKEN_TTL_SECONDS` | `28800` (8시간)  | 토큰 유효 시간                                                                    |
| `AUTH_COOKIE_SECURE`     | `false`          | `true`로 설정하면 HTTPS 전용 쿠키로 전송                                          |
| `AUTH_CACHE_TTL_SECONDS` | `5`              | 유저·롤·권한 인메모리 캐시 TTL                                                    |

---

### login.py

인증 관련 API 엔드포인트를 정의합니다.

| 메서드 | 경로                           | 설명                                                                  |
| ------ | ------------------------------ | --------------------------------------------------------------------- |
| `POST` | `/api/auth/login`              | ID·비밀번호 검증 후 쿠키 발급                                         |
| `POST` | `/api/auth/logout`             | 쿠키 삭제                                                             |
| `GET`  | `/api/auth/me`                 | 현재 로그인 유저 정보(ID, 권한, 롤) 반환                              |
| `GET`  | `/api/auth/session`            | 세션 유효 여부 + 롤 라벨 반환 (비로그인 시 `guest` 반환, 401 아님)    |
| `POST` | `/api/auth/signup`             | 회원가입 요청 등록 (`signup_requests` 테이블에 `pending` 상태로 저장) |
| `POST` | `/api/auth/change-credentials` | 초기 비밀번호 변경 (로그인 직후 강제 변경 대상)                       |

**회원가입 흐름**

1. 유저가 `/api/auth/signup`으로 요청 → `signup_requests` 테이블에 `pending` 저장
2. 관리자가 `/api/admin/permissions/signup-requests/{id}/approve` 승인 → `users` 테이블에 실제 계정 생성
3. 유저가 로그인 → `must_change_credentials=true` 이면 `/change-credentials` 로 리다이렉트

---

### bootstrap.py

앱 시작 시(`@app.on_event("startup")`) `initialize_auth_system()`이 호출되어 아래 5단계를 순서대로 실행합니다.

1. **`run_migrations()`** — `backend/db/migrations/` 내 SQL 파일을 버전 순으로 실행 (이미 적용된 버전은 건너뜀)
2. **`ensure_auth_schema_compatibility()`** — 구버전 스키마에서 업그레이드 시 컬럼 추가 등 호환성 보장
3. **`ensure_extension_uploads_schema()`** — `extension_uploads` 테이블 생성 (없을 경우에만)
4. **`ensure_default_permissions_and_roles()`** — 기본 권한 8개·롤 4개 삽입, admin 롤에 전체 권한 부여
5. **`ensure_initial_admin()`** — admin 롤 유저가 없을 경우에만 `admin` 계정을 랜덤 비밀번호로 생성 후 콘솔에 1회 출력

> 초기 admin 비밀번호는 서버 시작 로그에 한 번만 출력됩니다. 로그인 후 반드시 변경하세요.

---

## 권한 목록

| 권한명                    | 설명                |
| ------------------------- | ------------------- |
| `upload`                  | 확장 파일 업로드    |
| `install_extension`       | 승인된 확장 설치    |
| `request_extension`       | 확장 검토 요청      |
| `approve_extension`       | 확장 승인·거절      |
| `manage_extension_policy` | 자동 정책 설정 변경 |
| `approve_signup`          | 회원가입 요청 승인  |
| `delete_user`             | 유저 삭제           |
| `bypass_holding`          | 홀딩 기간 우회      |

기본 `user` 롤에는 `upload`, `install_extension`, `request_extension` 3개만 부여됩니다.
`admin` 롤은 전체 권한을 보유합니다.

---

## 의존 관계

```
main.py (startup)
  └── bootstrap.initialize_auth_system()
        ├── db/migrations/001_auth_permissions.sql
        └── security.hash_password()

모든 API 엔드포인트
  └── security.require_permission() 또는 require_admin()
        └── security.get_current_user()
              └── security.decode_access_token()
                    └── DB: admin.users
```
