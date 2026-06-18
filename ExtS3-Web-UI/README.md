# ExtS3-Web-UI

## Docker로 로컬 실행

팀원 PC마다 같은 방식으로 서버를 띄우기 위한 기본 실행 방식입니다.

자세한 팀원용 실행 공략집은 [TEAM_DOCKER_GUIDE.md](TEAM_DOCKER_GUIDE.md)를 확인하세요.

### 필요 도구

- Docker Desktop
- Git

### 실행

이 compose 구성은 `ExtS3-Web-UI`와 `suppressor`가 같은 상위 폴더 아래에 있다고 가정합니다.

```text
workspace/
  ExtS3-Web-UI/
  suppressor/
```

```powershell
copy .env.example .env
docker compose up --build
```

웹 서버, suppressor, PostgreSQL, Nexus가 함께 올라오면 브라우저에서 접속합니다.

```text
http://localhost:8000
```

Nexus는 아래 주소에서 확인할 수 있습니다.

```text
http://localhost:8081
```

suppressor FastAPI 문서는 아래 주소에서 확인할 수 있습니다.

```text
http://localhost:8001/docs
```

로그인 값은 `.env`와 `docker/db/init.sql`에서 로컬 개발용으로 직접 정합니다.

```text
웹 로그인 예시: example_admin_user / example_admin_password
Nexus 예시: example_nexus_user / example_nexus_password
```

### 환경 변수

`.env.example`을 `.env`로 복사한 뒤 로컬 환경에 맞게 수정합니다.

- `APP_PORT`: 로컬에서 접속할 포트
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: PostgreSQL 접속 정보
- `NEXUS_BASE_URL`, `NEXUS_REPOSITORY`, `NEXUS_USERNAME`, `NEXUS_PASSWORD`: Nexus 접속 정보
- `SUPPRESSOR_PRIVATE_IP`, `SUPPRESSOR_PORT`: Docker 내부 suppressor 서버 접속 정보
- `SUPPRESSOR_PUBLISHED_PORT`: 로컬 PC에서 suppressor에 접속할 포트

기본값은 PostgreSQL, Nexus, suppressor가 Docker Compose 안에서 함께 실행되는 상황을 기준으로 합니다.

### 데이터 초기화

PostgreSQL과 Nexus 데이터는 Docker volume에 저장됩니다. 초기 상태로 다시 만들 때만 아래 명령을 사용합니다.

```powershell
docker compose down -v
docker compose up --build
```

### CI 검증

GitHub Actions는 push 또는 PR 시 Docker Compose 설정 검증과 웹 서버 image build를 실행합니다.

## 파이썬 버전

3.11.2

## 1) 웹 서버 실행

### 요구사항

- Python 3.11+
- `pip`

### 설치 및 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

서버가 뜨면 아래로 접속:

- `http://127.0.0.1:8000`

주요 페이지:

- `/` 메인
- `/login` 로그인
- `/search` 검색
- `/admin` 관리자

## 2) 환경 변수 설정

`main.py`에서 아래 Nexus 환경 변수를 사용합니다.

```env
NEXUS_BASE_URL="http://localhost:8081"
NEXUS_REPOSITORY="<your-repo-name>"
NEXUS_USERNAME="admin"
NEXUS_PASSWORD="<your-password>"
```

프로젝트 루트의 `.env`에 설정 후 서버를 재시작하세요.

## 3) Nexus 최소 세팅 (Docker)

### 컨테이너 실행

```bash
docker volume create nexus-data

docker run -d \
  --name nexus \
  -p 8081:8081 \
  -p 5000:5000 \
  -v nexus-data:/nexus-data \
  sonatype/nexus3
```

### 웹 UI 접속

- `http://localhost:8081`
- 초기 비밀번호 확인:

```bash
docker exec -it nexus cat /nexus-data/admin.password
```

### 저장소 생성

Nexus UI에서 `Settings > Repositories > Create repository`로 들어가 저장소를 생성하고,
그 이름을 `.env`의 `NEXUS_REPOSITORY`에 넣으면 됩니다.

## 4) 빠른 점검

1. Nexus UI 접속 확인 (`8081`)
2. FastAPI 서버 실행 확인 (`8000`)
3. `.env`의 Nexus 값이 실제 설정과 일치하는지 확인
