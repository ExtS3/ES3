# ExtS3 Docker 로컬 개발 공략집

이 문서는 팀원이 AWS 서버 없이 자기 PC에서 ExtS3 데모 환경을 띄우기 위한 실행 가이드입니다.

로컬 Docker 환경에서 같이 실행되는 구성은 다음과 같습니다.

- `ExtS3-Web-UI`: 웹 UI와 백엔드 API
- `suppressor`: 확장 프로그램 분석 서버
- `PostgreSQL`: 개발용 DB
- `Nexus Repository`: 확장 ZIP/CRX 보관소

## 1. 준비물

먼저 아래 도구를 설치합니다.

- Docker Desktop
- Git
- PowerShell 또는 Windows Terminal

Docker Desktop은 실행한 뒤, 왼쪽 아래 상태가 `Engine running`인지 확인합니다.

## 2. 폴더 구조

이 Docker Compose는 웹 서버 repo와 suppressor repo가 같은 상위 폴더에 있다고 가정합니다.

```text
workspace/
  ExtS3-Web-UI/
  suppressor/
```

예시:

```text
D:\ExtS3\
  ExtS3-Web-UI\
  suppressor\
```

중요: 폴더 이름이 다르면 `docker-compose.yml`의 suppressor build 경로도 같이 바꿔야 합니다.

```yaml
suppressor:
  build:
    context: ../suppressor
```

## 3. 코드 받기

아래 명령은 예시입니다. 실제 브랜치 이름은 팀에서 공유한 브랜치를 사용합니다.

```powershell
mkdir D:\ExtS3
cd D:\ExtS3

git clone https://github.com/ExtS3/ExtS3-Web-UI.git ExtS3-Web-UI
git clone https://github.com/ExtS3/suppressor.git suppressor
```

Docker 작업이 아직 `main`에 머지되지 않았다면, 팀장이 공유한 Docker 작업 브랜치로 이동합니다.

```powershell
cd D:\ExtS3\ExtS3-Web-UI
git checkout feature/docker-local-dev-env

cd D:\ExtS3\suppressor
git checkout feature/juhyeok
```

브랜치가 없다고 나오면 아직 원격에 push되지 않은 상태입니다. 이 경우 repo 담당자에게 Docker 작업 브랜치가 올라왔는지 먼저 확인해야 합니다.

## 4. 최초 실행

웹 서버 폴더로 이동합니다.

```powershell
cd D:\ExtS3\ExtS3-Web-UI
```

환경 변수 파일을 만듭니다.

```powershell
copy .env.example .env
```

처음 실행하거나 코드가 바뀐 뒤에는 build를 포함해서 실행합니다.

```powershell
docker compose up --build
```

터미널을 계속 점유하지 않게 백그라운드로 띄우고 싶으면 아래 명령을 사용합니다.

```powershell
docker compose up -d --build
```

## 5. 접속 주소

컨테이너가 모두 올라오면 아래 주소를 사용합니다.

```text
웹 서비스: http://localhost:8000
suppressor API 문서: http://localhost:8001/docs
Nexus: http://localhost:8081
PostgreSQL: localhost:5432
```

계정 값은 팀 또는 개인 로컬 환경에 맞게 `.env`와 `docker/db/init.sql`에서 직접 정합니다.

```text
웹 로그인 예시: example_admin_user / example_admin_password
Nexus 예시: example_nexus_user / example_nexus_password
PostgreSQL 예시: example_db_user / example_db_password
DB 이름 예시: example_db_name
```

## 6. 정상 실행 확인

다른 터미널에서 아래 명령으로 상태를 확인합니다.

```powershell
docker compose ps
```

정상 상태 예시는 다음과 같습니다.

```text
db           Up ... healthy
nexus        Up ... healthy
suppressor   Up ... healthy
exts3-demo   Up ... healthy
```

간단한 접속 확인:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:8001/docs" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:8081/service/rest/v1/status" -UseBasicParsing
```

모두 `200 OK`가 나오면 기본 실행은 성공입니다.

## 7. 기본 사용 흐름

1. `http://localhost:8000` 접속
2. `docker/db/init.sql`에 설정한 개발용 계정으로 로그인
3. 앱 탐색에서 확장 프로그램 검색
4. `요청하기` 클릭
5. 아직 Nexus에 없으면 확장 ZIP을 받아 suppressor 분석으로 넘김
6. 분석 완료 후 Nexus의 `review/`로 이동
7. 관리자 페이지에서 승인하면 `safe/`로 이동
8. 라이브러리 페이지에서 설치용 파일을 받을 수 있음

Nexus 폴더 의미:

```text
holding/ : 분석 대기
review/  : 분석 완료, 관리자 승인 대기
safe/    : 관리자 승인 완료, 라이브러리에 표시됨
```

라이브러리의 `설치` 메뉴에는 다음 기능이 있습니다.

- `CRX 수동 설치 파일`: 확장 ZIP/CRX 직접 다운로드
- `정책 설치 배치`: Chrome 정책 기반 설치용 `.bat`
- `정책 해제 배치`: Chrome 정책 제거용 `.bat`

## 8. 코드 수정 후 반영

이 Docker 구성은 앱 소스 전체를 컨테이너 이미지 안에 복사합니다. 따라서 Python, HTML, JS를 수정한 뒤에는 다시 빌드해야 반영됩니다.

```powershell
docker compose up -d --build
```

브라우저에 예전 JS가 남아 있으면 `Ctrl + F5`로 강력 새로고침합니다.

## 9. 종료와 초기화

컨테이너만 종료:

```powershell
docker compose down
```

DB와 Nexus 데이터까지 전부 초기화:

```powershell
docker compose down -v
docker compose up -d --build
```

주의: `down -v`는 PostgreSQL과 Nexus에 쌓인 데이터도 삭제합니다. 팀원에게 공유할 테스트 데이터가 있으면 사용하지 마세요.

## 10. 자주 나는 문제

### Docker Desktop이 꺼져 있음

증상:

```text
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified
```

해결:

Docker Desktop을 켜고 엔진 실행이 끝난 뒤 다시 실행합니다.

### suppressor 폴더를 못 찾음

증상:

```text
unable to prepare context: path "../suppressor" not found
```

해결:

`ExtS3-Web-UI`와 `suppressor`가 같은 상위 폴더 아래에 있는지 확인합니다. 폴더명이 `suppressor`와 다를 경우 `docker-compose.yml`의 build context를 실제 폴더명으로 수정합니다.

### 포트 충돌

증상:

```text
port is already allocated
```

해결:

`.env`에서 포트를 바꿉니다.

```text
APP_PORT=8002
SUPPRESSOR_PUBLISHED_PORT=8003
NEXUS_PUBLISHED_PORT=8082
DB_PUBLISHED_PORT=5433
```

그 다음 다시 실행합니다.

```powershell
docker compose up -d --build
```

### 라이브러리에 항목이 안 보임

확인할 것:

1. Nexus에 `safe/` 폴더 아래 ZIP이 있는지 확인
2. `/api/nexus/list`가 `safe/...` 경로를 반환하는지 확인
3. 브라우저에서 `Ctrl + F5`

확인 명령:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/nexus/list" -Method Post
```

`safe/Chrome/.../{id}.zip` 형태가 있어야 라이브러리에 표시됩니다.

### 요청했는데 계속 처리 중으로 보임

같은 확장 ID가 `holding/`과 `safe/`에 동시에 남아 있으면 상태가 헷갈릴 수 있습니다.

Nexus에서 중복 파일을 확인하고 오래된 `holding/` 테스트 파일을 지웁니다.

### 배치 파일 다운로드는 되는데 실행이 안 됨

정책 설치/해제 배치는 Windows 관리자 권한이 필요합니다.

배치 파일을 실행하면 UAC 권한 요청이 떠야 정상입니다. Chrome 정책을 바꾸기 때문에 Chrome 재시작이 필요합니다.

## 11. 팀원에게 공유할 짧은 안내문

아래 문구를 그대로 보내면 됩니다.

```text
Docker Desktop 켜고, ExtS3-Web-UI와 suppressor를 같은 폴더 아래에 clone한 다음 ExtS3-Web-UI 폴더에서 실행하면 됩니다.

cd D:\ExtS3\ExtS3-Web-UI
copy .env.example .env
docker compose up -d --build

접속:
- 웹: http://localhost:8000
- Nexus: http://localhost:8081
- suppressor docs: http://localhost:8001/docs

계정:
- 웹: docker/db/init.sql에 설정한 계정
- Nexus: .env에 설정한 계정

코드 수정 후에는 docker compose up -d --build 다시 해야 반영됩니다.
```
