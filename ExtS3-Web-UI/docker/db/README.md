# docker/db

PostgreSQL 컨테이너 초기화 스크립트 폴더입니다.

---

## 파일 구성

### init.sql

컨테이너가 **최초 생성될 때 딱 한 번** 자동 실행되는 SQL입니다.
`docker-compose.yml`에서 아래와 같이 마운트됩니다.

```yaml
volumes:
  - ./docker/db/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
```

PostgreSQL 공식 이미지는 `/docker-entrypoint-initdb.d/` 경로의 `.sql` 파일을 컨테이너 첫 시작 시 알파벳 순으로 자동 실행합니다. `db_data` 볼륨이 이미 존재하면 재실행되지 않습니다.

**현재 내용:**

- `admin` 스키마 생성
- `admin.users` 테이블 생성 (id, password 2개 컬럼)
- `admin.pending_files` 테이블 생성
- 예시 admin 계정 1건 삽입 (`example_admin_user`)

> ⚠️ **주의**: 이 파일은 컨테이너 초기화용 최소 스키마입니다. 실제 운영 스키마는 앱 시작 시 `backend/auth/bootstrap.py`의 `run_migrations()`가 `backend/db/migrations/` 파일들을 실행해서 완성합니다. 두 곳의 역할이 다릅니다.
>
> | 구분            | 파일                          | 실행 시점             | 역할                       |
> | --------------- | ----------------------------- | --------------------- | -------------------------- |
> | 컨테이너 초기화 | `docker/db/init.sql`          | 볼륨 최초 생성 시 1회 | 기본 스키마·테스트 계정    |
> | 앱 마이그레이션 | `backend/db/migrations/*.sql` | 앱 시작마다           | 전체 운영 스키마 누적 적용 |

---

## 경로 변경 불가

`docker-compose.yml`에 경로가 하드코딩돼 있습니다.

```yaml
- ./docker/db/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro
```

파일을 다른 위치로 옮기려면 `docker-compose.yml`의 해당 볼륨 경로도 함께 수정해야 합니다.
