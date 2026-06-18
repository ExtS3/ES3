# docker/nexus

Nexus Repository 초기화 스크립트 폴더입니다.

---

## 파일 구성

### init-repository.sh

Nexus가 완전히 기동된 뒤 **레포지토리가 없을 경우에만** Raw Hosted 레포지토리를 자동 생성하는 스크립트입니다.
`docker-compose.yml`의 `nexus-init` 서비스가 이 파일을 실행합니다.

```yaml
nexus-init:
  image: curlimages/curl:8.11.1
  depends_on:
    nexus:
      condition: service_healthy
  volumes:
    - ./docker/nexus/init-repository.sh:/init-repository.sh:ro
  entrypoint: ['/bin/sh', '/init-repository.sh']
  restart: 'no'
```

**동작 순서:**

1. Nexus 헬스체크 통과 대기 (최대 5분, 5초 간격)
2. 레포지토리가 이미 존재하면 즉시 종료 (멱등성 보장)
3. 없으면 Nexus REST API로 Raw Hosted 레포지토리 생성

**생성되는 레포지토리 설정:**

| 항목                    | 값                    |
| ----------------------- | --------------------- |
| 타입                    | Raw Hosted            |
| Blob Store              | default               |
| Write Policy            | allow (덮어쓰기 허용) |
| Content Type Validation | 비활성                |

**사용하는 환경변수** (`docker-compose.yml`에서 주입):

| 변수명             | 기본값                   | 설명                  |
| ------------------ | ------------------------ | --------------------- |
| `NEXUS_REPOSITORY` | `extension-demo`         | 생성할 레포지토리명   |
| `NEXUS_BASE_URL`   | `http://nexus:8081`      | Nexus 내부 URL        |
| `NEXUS_USERNAME`   | `example_nexus_user`     | Nexus 관리자 계정     |
| `NEXUS_PASSWORD`   | `example_nexus_password` | Nexus 관리자 비밀번호 |

---

## 경로 변경 불가

`docker-compose.yml`에 경로가 하드코딩돼 있습니다.

```yaml
- ./docker/nexus/init-repository.sh:/init-repository.sh:ro
```

파일을 다른 위치로 옮기려면 `docker-compose.yml`의 해당 볼륨 경로도 함께 수정해야 합니다.
