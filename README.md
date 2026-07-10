# ES3 — 확장 프로그램 보안 심사 플랫폼

크롬/VSCode 확장 프로그램을 보안 심사하는 사내 플랫폼입니다.

```text
ES3/
├── docker-compose.yml   # 전체 스택 정의 (여기서 실행)
├── ExtS3-Web-UI/        # 웹 UI + 백엔드 API
└── suppressor/          # 보안 분석 서버
```

## 처음 세팅하기

### 필요 도구

- Docker가 돌아가는 환경 (`docker compose` 명령을 쓸 수 있으면 됩니다)
- Git

### 1. 클론

```powershell
git clone <이 레포 주소>
cd ES3
```

이후 모든 명령은 이 위치(레포 루트)에서 실행합니다.

### 2. 환경 파일 복사 후 실행

```powershell
copy ExtS3-Web-UI\.env.example .env    # Windows (macOS/Linux: cp ExtS3-Web-UI/.env.example .env)
docker compose up --build -d
```

`.env`는 수정 없이 그대로 동작합니다. 첫 실행은 이미지 다운로드(약 10GB) 때문에 10~20분 걸릴 수 있습니다.

### 3. 임베딩 모델 다운로드 (최초 1회)

suppressor의 RAG 검색에 필요한 모델을 ollama 컨테이너에 받습니다.

```powershell
docker compose exec ollama ollama pull bge-m3
docker compose restart suppressor
```

suppressor 로그에 `seed complete: success=26 fail=0`이 뜨면 성공입니다.

```powershell
docker compose logs suppressor | Select-String "seed complete"   # Windows
docker compose logs suppressor | grep "seed complete"            # macOS/Linux
```

### 4. 접속 및 로그인

브라우저에서 http://localhost:8000 접속.

관리자 계정은 최초 기동 때 자동 생성되고 비밀번호가 로그에 **한 번만** 출력됩니다.

```powershell
docker compose logs exts3-web | Select-String -Context 1,3 "administrator account created"   # Windows
docker compose logs exts3-web | grep -A 3 "administrator account created"                    # macOS/Linux
```

`admin` + 출력된 비밀번호로 로그인하면 첫 로그인 시 비밀번호 변경을 요구합니다.

> 비밀번호를 잃어버렸다면 DB에서 admin 계정을 지우고 재시작하면 새로 발급됩니다.
>
> ```powershell
> docker compose exec db psql -U example_db_user -d example_db_name -c "DELETE FROM admin.user_roles WHERE user_id='admin'; DELETE FROM admin.users WHERE id='admin';"
> docker compose restart exts3-web
> ```

## 포트 구조 (단일 진입점)

외부에 공개되는 포트는 웹(8000) 하나뿐입니다. 나머지는 compose 내부 네트워크에서 서비스명으로만 통신하며 외부에서 직접 접근할 수 없습니다.

| 서비스 | 역할 | 외부 접근 |
| --- | --- | --- |
| exts3-web | 웹 UI + API | **:8000 공개** |
| nexus | 확장 파일 저장소 | 이 PC에서만 `127.0.0.1:8081` (admin / admin123) |
| db, vector-db, suppressor, ollama | DB·분석·임베딩 | 불가 (내부 전용) |

DB에 직접 쿼리해야 할 때: `docker compose exec db psql -U example_db_user -d example_db_name`

## 일상 사용

```powershell
docker compose up -d              # 시작 (재부팅 후에도 이것만 치면 됨. 모델·데이터는 볼륨에 유지)
docker compose logs -f exts3-web  # 웹 앱 로그 실시간 보기
docker compose ps                 # 상태 확인
docker compose down               # 정지 (데이터 유지)
docker compose down -v            # 완전 초기화 (데이터 삭제, 3번 모델 다운로드부터 다시)
```

> 로그는 전체(`docker compose logs -f`)로 보면 여러 서비스가 섞여 읽기 어렵습니다.
> 위처럼 서비스명(`exts3-web`, `suppressor` 등)을 붙여 필요한 것만 보세요.

## 사내에 이미 Nexus가 있다면

내장 Nexus 대신 기존 서버에 연결할 수 있습니다. `.env`에 외부 Nexus 주소·계정·레포지토리를 설정한 뒤:

```powershell
docker compose -f docker-compose.yml -f docker-compose.external-nexus.yml up -d
```

자세한 조건은 [docker-compose.external-nexus.yml](docker-compose.external-nexus.yml) 상단 주석 참고.

## 상세 문서

- [ExtS3-Web-UI/LOCAL_SETUP_GUIDE.md](ExtS3-Web-UI/LOCAL_SETUP_GUIDE.md) — 환경 변수 상세
- [ExtS3-Web-UI/TEAM_DOCKER_GUIDE.md](ExtS3-Web-UI/TEAM_DOCKER_GUIDE.md) — 팀원용 실행 공략집
- [ExtS3-Web-UI/README.md](ExtS3-Web-UI/README.md) — 웹 앱 레포 문서
