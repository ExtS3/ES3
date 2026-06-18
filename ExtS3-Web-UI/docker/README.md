# docker

`docker-compose.yml`이 참조하는 컨테이너 초기화 스크립트 모음입니다.
앱 서비스(`exts3-demo`, `suppressor`)가 의존하는 인프라(PostgreSQL, Nexus)를 처음 기동할 때 자동으로 실행됩니다.

---

## 디렉토리 구조

```
docker/
├── db/
│   └── init.sql              # PostgreSQL 컨테이너 최초 기동 시 실행되는 초기 스키마
└── nexus/
    └── init-repository.sh    # Nexus 기동 후 레포지토리 자동 생성 스크립트
```

---

## 파일별 역할

### db/init.sql

PostgreSQL 컨테이너가 **최초 생성될 때 1회** 자동 실행됩니다.
`admin` 스키마와 기본 테이블을 생성하고 예시 계정을 삽입합니다.

실제 운영 스키마 전체는 앱 시작 시 `backend/auth/bootstrap.py`가 `backend/db/migrations/`를 실행해서 완성합니다. 이 파일은 컨테이너가 처음 올라올 때 최소한의 구조를 잡아두는 용도입니다.

자세한 내용은 `db/README.md` 참고.

---

### nexus/init-repository.sh

Nexus 컨테이너가 완전히 기동된 뒤 `nexus-init` 서비스가 실행합니다.
레포지토리가 이미 있으면 건너뛰므로 멱등성이 보장됩니다.

자세한 내용은 `nexus/README.md` 참고.

---

## docker-compose.yml과의 관계

이 폴더의 파일들은 `docker-compose.yml`에 경로가 **직접 하드코딩**돼 있습니다.
파일 위치를 변경하면 컨테이너 마운트가 깨지므로 반드시 `docker-compose.yml`도 함께 수정해야 합니다.

```yaml
# db 서비스
volumes:
  - ./docker/db/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro

# nexus-init 서비스
volumes:
  - ./docker/nexus/init-repository.sh:/init-repository.sh:ro
```

---

## 전체 컨테이너 기동 순서

```
docker compose up
  │
  ├── db (PostgreSQL)
  │     └── init.sql 실행 (볼륨 최초 생성 시)
  │           healthcheck 통과 대기
  │
  ├── vector-db (PGVector)
  │     healthcheck 통과 대기
  │
  ├── nexus (Nexus Repository)
  │     healthcheck 통과 대기 (최대 5분)
  │     └── nexus-init 실행
  │           init-repository.sh → Raw Hosted 레포지토리 생성
  │
  └── exts3-demo + suppressor
        (db, nexus, nexus-init, vector-db 모두 준비된 후 시작)
```
