# backend/db/migrations

앱 시작 시 자동으로 실행되는 PostgreSQL 마이그레이션 파일 폴더입니다.
별도의 마이그레이션 도구 없이 `backend/auth/bootstrap.py`의 `run_migrations()`가 직접 처리합니다.

---

## 실행 방식

앱이 시작될 때(`@app.on_event("startup")`) 아래 순서로 동작합니다.

1. 이 폴더의 `*.sql` 파일을 **파일명 오름차순**으로 정렬
2. 각 파일에 대해 `admin.schema_migrations` 테이블에 이미 적용된 버전인지 확인
3. 미적용 파일만 순서대로 실행 후 버전 기록

이미 적용된 파일은 재실행되지 않으므로 **멱등성**이 보장됩니다.

---

## 파일 목록

| 파일                       | 내용                                                                        |
| -------------------------- | --------------------------------------------------------------------------- |
| `001_auth_permissions.sql` | `admin` 스키마 및 인증·권한 관련 전체 테이블 생성, 기본 권한·롤 데이터 삽입 |
| `002_extension_registry.sql` | `extension_registry` 테이블 생성 (Nexus 레포 현황 미러링, id+version 중복 확인용) |

### 001_auth_permissions.sql 상세

생성하는 테이블:

| 테이블                    | 설명                                                              |
| ------------------------- | ----------------------------------------------------------------- |
| `admin.schema_migrations` | 마이그레이션 적용 이력 관리                                       |
| `admin.users`             | 유저 계정 (id, password_hash, must_change_credentials, is_active) |
| `admin.roles`             | 롤 정의 (admin, user, department\_\*)                             |
| `admin.permissions`       | 권한 정의 (upload, install_extension 등 8개)                      |
| `admin.user_roles`        | 유저 ↔ 롤 매핑                                                    |
| `admin.role_permissions`  | 롤 ↔ 권한 매핑                                                    |
| `admin.user_permissions`  | 유저 개별 권한 오버라이드                                         |
| `admin.signup_requests`   | 회원가입 요청 대기 목록                                           |

삽입하는 기본 데이터:

- 권한 8개: `upload`, `delete_user`, `manage_extension_policy`, `request_extension`, `bypass_holding`, `install_extension`, `approve_extension`, `approve_signup`
- 롤 5개: `admin`, `user`, `department_security`, `department_it`, `department_ops`
- `admin` 롤 → 전체 권한 부여
- `user`, `department_*` 롤 → `request_extension`, `upload`, `install_extension` 3개 부여

---

### 002_extension_registry.sql 상세

`search_path=admin`(`database.py`)이 적용된 연결로 실행되므로 실제로는 `admin.extension_registry`에 생성됩니다.

| 테이블                | 설명                                                                                     |
| ---------------------- | ---------------------------------------------------------------------------------------- |
| `extension_registry`  | Nexus 레포 현황 미러링. PK `(ext_id, version)` — 같은 id라도 버전이 다르면 별개 행       |

컬럼: `ext_name`, `browser`, `status`(`review`/`safe`/`reject`), `decided_at`(승인·거절 확정 시각), `created_at`, `updated_at`.
사용하는 코드는 `backend/extension_registry.py` (`backend/README.md`의 "extension_registry.py" 섹션 참고).

> `extension_uploads` 테이블(직접 업로드 소유권·버전 관리용, `security_scan/upload_registry.py`)과는 별개입니다.
> 이 테이블은 이 폴더의 마이그레이션 패턴 대신 `auth/bootstrap.py`의 `ensure_extension_uploads_schema()`에서 인라인으로 생성되는
> 기존 코드라 그대로 두었습니다.

---

## 새 마이그레이션 추가 방법

테이블 추가·컬럼 변경 등이 필요할 때 이 폴더에 새 파일을 추가하면 됩니다.

**파일 명명 규칙**: `{3자리 번호}_{내용 설명}.sql`

```
002_add_extension_uploads.sql
003_add_audit_log.sql
```

번호가 빠진 파일이 먼저 실행되므로 번호를 반드시 순서대로 지정하세요.

**작성 시 주의사항**

- `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` 등 멱등성을 보장하는 구문 사용 권장
- 한 번 적용된 파일은 수정해도 재실행되지 않습니다. 기존 파일 수정 대신 새 파일을 추가하세요.
- 롤백 기능은 없으므로 파괴적인 변경(`DROP`, `TRUNCATE`)은 신중하게 작성하세요.

---

## 관련 코드

```
backend/auth/bootstrap.py
  └── MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"
  └── run_migrations()  ← 앱 시작 시 자동 호출
```
