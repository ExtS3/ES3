# ExtS3 로컬 실행 가이드

이 문서는 처음 세팅하는 개발자가 로컬 PC에서 ExtS3 전체 스택을 순서대로 따라할 수 있도록 작성되었습니다.
기존 팀원용 문서([TEAM_DOCKER_GUIDE.md](TEAM_DOCKER_GUIDE.md))를 보완하며, AI 판단(`ai_judgment`) 관련 설정이 추가되어 있습니다.

---

## 0. 전체 구성 한눈에 보기

### 서비스 목록

| 서비스                      | 역할                         | 기본 포트 |
| --------------------------- | ---------------------------- | --------- |
| `exts3-demo` (ExtS3-Web-UI) | 웹 UI + 백엔드 API           | 8000      |
| `suppressor`                | 확장 프로그램 보안 분석 서버 | 8001      |
| `db` (PostgreSQL 16)        | 사용자·확장 메타데이터 DB    | 5432      |
| `nexus` (Sonatype Nexus 3)  | 확장 ZIP/CRX 파일 저장소     | 8081      |
| Ollama                      | 로컬 LLM (AI 판단 기능)      | 11434     |

> **Ollama는 Docker 밖 호스트에서 직접 실행**합니다. 나머지 4개 서비스는 Docker Compose로 함께 기동됩니다.

### 서비스 간 의존 관계

`docker-compose.yml`의 `depends_on` 기준:

- `exts3-demo`는 `db`, `nexus`, `suppressor` 세 서비스가 모두 **healthy** 상태가 된 뒤에 기동됩니다.
- `suppressor`는 `nexus`가 **healthy** 상태이고 `nexus-init`(저장소 초기화 작업)이 **완료**된 뒤에 기동됩니다.
- `nexus-init`은 Nexus가 healthy가 되자마자 저장소를 한 번 생성하고 종료되는 일회성 컨테이너입니다.

따라서 전체 기동 순서는 `db` · `nexus` → `nexus-init` → `suppressor` → `exts3-demo` 입니다.

---

## 1. 사전 준비물

### Docker Desktop

컨테이너 런타임으로 사용합니다.

- 설치: https://www.docker.com/products/docker-desktop
- 실행 확인: Docker Desktop을 켠 뒤 왼쪽 아래 상태가 **Engine running** 인지 확인합니다.

```bash
# 설치 및 엔진 실행 여부 확인
docker version
```

정상이면 `Server: Docker Engine` 항목에 버전이 출력됩니다.

### Git

소스 코드 버전 관리에 사용합니다.

```bash
git --version
```

### Ollama (AI 판단 기능을 사용할 경우)

로컬 LLM을 호스트에서 실행하기 위해 필요합니다.

- 설치: https://ollama.com
- 설치 후 필요한 모델을 pull합니다.

```bash
ollama pull bge-m3
ollama pull qwen2.5:1.5b-instruct-q4_K_M
```

> AI 판단 기능이 필요 없으면 Ollama 없이 실행할 수 있습니다. `.env`에서 `ENABLE_AI_JUDGMENT=false`로 설정하면 됩니다.

---

## 2. 폴더 구조 확인

이 Docker Compose 구성은 두 레포지토리가 **같은 상위 폴더** 아래에 있어야 합니다.

```text
workspace/          ← 상위 폴더 (이름은 무관)
  ExtS3-Web-UI/     ← 이 레포 (docker compose 실행 위치)
  suppressor/       ← suppressor 레포
```

### suppressor 폴더명 확인

`docker-compose.yml`의 suppressor build context는 `../suppressor`로 설정되어 있습니다.

```yaml
suppressor:
  build:
    context: ../suppressor
```

`suppressor` 레포를 clone한 폴더명이 다를 경우 이 값을 실제 폴더명에 맞게 수정해야 합니다.
폴더명이 맞지 않으면 `docker compose up` 시 아래 오류가 발생합니다.

```text
unable to prepare context: path "../suppressor" not found
```

---

## 3. .env 파일 설정

### 3-1. ExtS3-Web-UI/.env

`.env.example`을 `.env`로 복사한 뒤 값을 채웁니다.

**macOS/Linux:**

```bash
cp .env.example .env
```

**Windows:**

```powershell
copy .env.example .env
```

아래 표는 `.env.example`에 있는 변수 전체 목록입니다.

| 변수명                          | 예시값                   | 설명                                                             | 필수 여부            |
| ------------------------------- | ------------------------ | ---------------------------------------------------------------- | -------------------- |
| `APP_PORT`                      | `8000`                   | 웹 UI 외부 접속 포트                                             | 선택                 |
| `DB_HOST`                       | `db`                     | DB 호스트. Docker 내부에서는 `db`, 로컬 직접 실행 시 `localhost` | 필수                 |
| `DB_PORT`                       | `5432`                   | DB 내부 포트 (컨테이너 내부)                                     | 선택                 |
| `DB_PUBLISHED_PORT`             | `5432`                   | DB 외부 노출 포트 (호스트에서 접속 시)                           | 선택                 |
| `DB_USER`                       | `example_db_user`        | PostgreSQL 사용자명                                              | **필수 (직접 설정)** |
| `DB_PASSWORD`                   | `example_db_password`    | PostgreSQL 비밀번호                                              | **필수 (직접 설정)** |
| `DB_NAME`                       | `example_db_name`        | PostgreSQL 데이터베이스 이름                                     | **필수 (직접 설정)** |
| `NEXUS_BASE_URL`                | `http://nexus:8081`      | Nexus 내부 URL. Docker 내부에서는 `http://nexus:8081`            | 필수                 |
| `NEXUS_PUBLISHED_PORT`          | `8081`                   | Nexus 외부 노출 포트                                             | 선택                 |
| `NEXUS_REPOSITORY`              | `extension-demo`         | Nexus 저장소 이름                                                | **필수 (직접 설정)** |
| `NEXUS_USERNAME`                | `example_nexus_user`     | Nexus 접속 계정                                                  | **필수 (직접 설정)** |
| `NEXUS_PASSWORD`                | `example_nexus_password` | Nexus 접속 비밀번호                                              | **필수 (직접 설정)** |
| `NEXUS_STORAGE_LIMIT_BYTES`     | (비어있음)               | Nexus 저장 용량 제한. 비워두면 무제한                            | 선택                 |
| `SUPPRESSOR_PRIVATE_IP`         | `suppressor`             | Docker 내부 suppressor 호스트명                                  | 필수                 |
| `SUPPRESSOR_PORT`               | `8001`                   | suppressor 내부 포트                                             | 선택                 |
| `SUPPRESSOR_PUBLISHED_PORT`     | `8001`                   | suppressor 외부 노출 포트                                        | 선택                 |
| `EXTERNAL_RUNNER_MODE`          | `file`                   | suppressor 실행 모드                                             | 선택                 |
| `ENABLE_LOCAL_LIBRARY_FALLBACK` | `true`                   | 로컬 라이브러리 폴백 활성화 여부                                 | 선택                 |

> `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `NEXUS_USERNAME`, `NEXUS_PASSWORD`, `NEXUS_REPOSITORY`는 예시값이 들어있지만 **실제 환경에 맞게 변경해야 합니다**. 특히 운영 환경에서는 반드시 교체하세요.

#### AI 판단(ai_judgment) 관련 변수

`.env.example`에는 포함되어 있지 않지만, AI 판단 기능을 사용하려면 `.env`에 직접 추가해야 합니다.

| 변수명                   | 기본값                            | 설명                                         |
| ------------------------ | --------------------------------- | -------------------------------------------- |
| `ENABLE_AI_JUDGMENT`     | `true`                            | `false`로 설정 시 AI 판단 비활성화           |
| `LOCAL_LLM_URL`          | `http://localhost:11434/api/chat` | Ollama API 엔드포인트                        |
| `LOCAL_LLM_MODEL`        | `qwen2.5:1.5b-instruct-q4_K_M`    | 사용할 Ollama 모델명                         |
| `AI_JUDGMENT_MAX_TOKENS` | `1024`                            | LLM 최대 생성 토큰 수                        |
| `LLM_TIMEOUT`            | `120`                             | LLM 요청 타임아웃(초)                        |
| `LLM_TEMPERATURE`        | `0.1`                             | 샘플링 온도. 낮을수록 결정론적 출력          |
| `SLACK_WEBHOOK_URL`      | (없음, 필수)                      | Slack 알림 수신용 Incoming Webhook URL       |
| `DASHBOARD_BASE_URL`     | `http://localhost:8000`           | Slack 메시지에 삽입할 대시보드 링크 base URL |

> **Docker Compose 환경에서의 `LOCAL_LLM_URL` 주의사항**
>
> Ollama는 호스트(PC)에서 직접 실행됩니다. 컨테이너 안에서 호스트 Ollama에 접근하려면 `localhost`가 아니라 `host.docker.internal`을 사용해야 합니다.
> `docker-compose.yml`의 `exts3-demo` 서비스에 `extra_hosts: - "host.docker.internal:host-gateway"` 설정이 있어 이 주소로 호스트에 접근할 수 있습니다.
>
> ```env
> LOCAL_LLM_URL=http://host.docker.internal:11434/api/chat
> ```

아래는 `.env` 하단에 추가할 AI 판단 설정 블록 예시입니다.

```env
# AI 판단 모듈 (Docker Compose 환경 기준)
ENABLE_AI_JUDGMENT=true
LOCAL_LLM_URL=http://host.docker.internal:11434/api/chat
LOCAL_LLM_MODEL=qwen2.5:1.5b-instruct-q4_K_M
AI_JUDGMENT_MAX_TOKENS=1024
LLM_TIMEOUT=120
LLM_TEMPERATURE=0.1
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
DASHBOARD_BASE_URL=http://localhost:8000
```

### 3-2. suppressor/.env

Docker Compose로 실행할 때는 suppressor의 환경변수가 `docker-compose.yml`을 통해 주입되므로, **suppressor 전용 `.env` 파일은 별도로 필요하지 않습니다**.

suppressor를 Docker Compose 없이 독립적으로 실행할 경우에만 `suppressor/` 루트에 `.env` 파일을 만들어야 합니다.

| 변수명                     | 예시값                            | 설명                               | 필수 여부 |
| -------------------------- | --------------------------------- | ---------------------------------- | --------- |
| `NEXUS_BASE_URL`           | `http://localhost:8081`           | Nexus 주소                         | **필수**  |
| `NEXUS_REPOSITORY`         | `extension-demo`                  | Nexus 저장소 이름                  | **필수**  |
| `NEXUS_USERNAME`           | `example_nexus_user`              | Nexus 계정                         | **필수**  |
| `NEXUS_PASSWORD`           | `example_nexus_password`          | Nexus 비밀번호                     | **필수**  |
| `ENABLE_WEB_FORWARD`       | `true`                            | 분석 결과를 Web-UI로 전송할지 여부 | **필수**  |
| `ENABLE_SLACK_FORWARD`     | `false`                           | Slack으로 분석 결과 전송 여부      | 선택      |
| `ENABLE_NEXUS_UPLOAD`      | `true`                            | Nexus에 분석 파일 업로드 여부      | **필수**  |
| `EXTERNAL_RUNNER_MODE`     | `file`                            | 외부 분석 실행 모드                | 선택      |
| `LOCAL_LLM_URL`            | `http://localhost:11434/api/chat` | Ollama API 엔드포인트              | 선택      |
| `LOCAL_LLM_MODEL`          | `qwen2.5:1.5b-instruct-q4_K_M`    | Ollama 모델명                      | 선택      |
| `DYNAMIC_HARNESS_HEADLESS` | `true`                            | Playwright 헤드리스 모드           | 선택      |
| `RISK_WEIGHT_DYNAMIC`      | `0.65`                            | 동적 분석 리스크 가중치 (합=1.0)   | 선택      |
| `RISK_WEIGHT_STATIC`       | `0.20`                            | 정적 분석 리스크 가중치            | 선택      |
| `RISK_WEIGHT_OBFUSCATION`  | `0.15`                            | 난독화 분석 리스크 가중치          | 선택      |
| `HOLDING_SECONDS`          | `604800`                          | 홀딩 유지 시간(초). 기본 7일       | 선택      |
| `NEXUS_REPO`               | `holding`                         | 홀딩 전용 Nexus 저장소 이름        | 선택      |
| `CLAMSCAN_PATH`            | `/usr/bin/clamscan`               | ClamAV 실행 파일 경로              | 선택      |
| `CLAMAV_DATABASE`          | `/path/to/clamav/db`              | ClamAV DB 경로                     | 선택      |
| `VT_API_KEY`               | (없음)                            | VirusTotal API 키 (retro 모니터용) | 선택      |
| `RETRO_INTERVAL_HOURS`     | `24`                              | retro 재점검 주기(시간)            | 선택      |

> `CLAMSCAN_PATH`, `CLAMAV_DATABASE`, `VT_API_KEY`는 비워두어도 나머지 분석이 정상 동작합니다.

---

## 4. Docker Compose로 실행 (권장)

### 4-1. 최초 실행

`ExtS3-Web-UI` 폴더 안에서 실행합니다.

```bash
cd ExtS3-Web-UI
```

`.env` 파일을 만들고 값을 채웁니다.

**macOS/Linux:**

```bash
cp .env.example .env
# .env 를 열어 3. .env 파일 설정 섹션을 참고해 값을 채운다
```

**Windows PowerShell:**

```powershell
copy .env.example .env
# .env 를 열어 3. .env 파일 설정 섹션을 참고해 값을 채운다
```

빌드와 실행을 함께 합니다 (터미널 점유, 로그 실시간 출력).

```bash
docker compose up --build
```

터미널을 점유하지 않고 백그라운드로 실행하려면 아래 명령을 사용합니다.

```bash
docker compose up -d --build
```

> **Nexus 초기화 시간 안내**
>
> Nexus는 JVM 기반 서비스로 최초 기동에 **최대 2~3분** 이상 소요될 수 있습니다.
> `docker-compose.yml`에 `start_period: 60s` · `retries: 20` · `interval: 15s`로 헬스체크가 설정되어 있으며,
> Nexus가 healthy 상태가 될 때까지 suppressor와 exts3-demo는 기다립니다.
> 로그에 `nexus  | Started Sonatype Nexus` 메시지가 보이면 정상 기동된 것입니다.

### 4-2. 정상 실행 확인

다른 터미널에서 컨테이너 상태를 확인합니다.

```bash
docker compose ps
```

정상 기동된 경우 아래와 유사하게 출력됩니다.

```text
NAME           STATUS
db             Up ... (healthy)
nexus          Up ... (healthy)
suppressor     Up ... (healthy)
exts3-demo     Up ... (healthy)
```

`nexus-init`은 저장소 생성 후 종료(`Exited (0)`)되는 정상 동작입니다.

각 서비스 접속 확인:

**macOS/Linux:**

```bash
curl -s http://localhost:8000/ | head -5
curl -s http://localhost:8001/docs | head -5
curl -s http://localhost:8081/service/rest/v1/status
```

**Windows PowerShell:**

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:8001/docs" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:8081/service/rest/v1/status" -UseBasicParsing
```

세 요청 모두 `200 OK`가 반환되면 기본 실행은 성공입니다.

### 4-3. 코드 수정 후 재빌드

이 Docker 구성은 앱 소스 전체를 이미지 안에 복사합니다. Python, HTML, JS 파일을 수정한 뒤에는 다시 빌드해야 반영됩니다.

```bash
docker compose up -d --build
```

브라우저에 이전 JS/CSS가 남아 있으면 `Ctrl + F5`로 강력 새로고침합니다.

### 4-4. 종료 및 초기화

컨테이너만 종료 (DB, Nexus 데이터 유지):

```bash
docker compose down
```

DB와 Nexus 데이터까지 전부 삭제하고 초기 상태로 되돌리려면:

```bash
docker compose down -v
docker compose up -d --build
```

> **주의**: `down -v`는 PostgreSQL과 Nexus에 쌓인 모든 데이터를 삭제합니다. 팀원과 공유하는 테스트 데이터가 있으면 사용하지 마세요.

---

## 5. Ollama 설정 (AI 판단 기능 사용 시)

AI 판단(`ai_judgment`) 기능은 로컬 Ollama가 실행 중이어야 동작합니다. Ollama는 호스트(PC)에서 직접 실행해야 하며, Docker 컨테이너로 띄우지 않습니다.

```bash
# 1. Ollama 설치 (https://ollama.com)

# 2. 필요한 모델 pull
ollama pull bge-m3
ollama pull qwen2.5:1.5b-instruct-q4_K_M

# 3. Ollama 서버 실행 확인 (모델 목록 반환 시 정상)
curl http://localhost:11434/api/tags
```

Docker Compose 환경에서 `.env`에 설정할 값:

```env
LOCAL_LLM_URL=http://host.docker.internal:11434/api/chat
LOCAL_LLM_MODEL=qwen2.5:1.5b-instruct-q4_K_M
ENABLE_AI_JUDGMENT=true
```

> Ollama 없이 실행하려면 `ENABLE_AI_JUDGMENT=false`로 설정하면 됩니다.
> AI 판단은 suppressor가 `review` 판정을 내린 확장 프로그램에 대해서만 백그라운드로 실행되므로, 비활성화해도 파일 저장·Nexus 업로드·관리자 승인 등 나머지 기능은 정상 동작합니다.

---

## 6. 서비스별 접속 주소 정리

| 서비스              | 주소                       | 비고                                 |
| ------------------- | -------------------------- | ------------------------------------ |
| 웹 UI               | http://localhost:8000      | 메인 대시보드                        |
| suppressor API 문서 | http://localhost:8001/docs | FastAPI Swagger UI                   |
| Nexus               | http://localhost:8081      | 확장 파일 저장소                     |
| PostgreSQL          | localhost:5432             | DB 직접 접속 시 (DB 클라이언트 사용) |
| Ollama              | http://localhost:11434     | 호스트에서 직접 실행 (Docker 외부)   |

### 로그인 계정

**웹 UI 로그인**

`docker/db/init.sql`에 초기 계정이 설정됩니다.

```text
아이디:     example_admin_user
비밀번호:   example_admin_password
```

실제 사용 환경에서는 `docker/db/init.sql`과 `.env`의 `DB_USER`, `DB_PASSWORD` 값을 변경하세요.

**Nexus 로그인**

`.env`의 `NEXUS_USERNAME` / `NEXUS_PASSWORD` 값을 사용합니다.

```text
아이디:     (NEXUS_USERNAME 값)
비밀번호:   (NEXUS_PASSWORD 값)
```

**PostgreSQL 직접 접속 (DB 클라이언트)**

```text
Host:     localhost
Port:     5432 (또는 DB_PUBLISHED_PORT 값)
Database: (DB_NAME 값)
User:     (DB_USER 값)
Password: (DB_PASSWORD 값)
```

---

## 7. 자주 발생하는 문제와 해결법

### Docker Desktop이 꺼져 있음

**문제**: `docker compose up` 실행 시 아래 오류가 발생합니다.

```text
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified
```

**원인**: Docker Desktop이 실행되어 있지 않거나 엔진이 아직 기동 중입니다.

**해결**: Docker Desktop을 켜고 왼쪽 아래 상태가 **Engine running**이 될 때까지 기다린 뒤 다시 실행합니다.

---

### suppressor 폴더를 못 찾음

**문제**: `docker compose up` 실행 시 아래 오류가 발생합니다.

```text
unable to prepare context: path "../suppressor" not found
```

**원인**: clone한 suppressor 폴더명이 `docker-compose.yml`의 build context(`../suppressor`)와 다릅니다.

**해결**: `docker-compose.yml`을 열어 suppressor build context를 실제 폴더명으로 수정합니다.

```yaml
suppressor:
  build:
    context: ../실제폴더명
```

---

### 포트 충돌

**문제**: `docker compose up` 실행 시 아래 오류가 발생합니다.

```text
port is already allocated
```

**원인**: 해당 포트를 이미 다른 프로세스가 점유하고 있습니다.

**해결**: `.env` 파일에서 충돌하는 포트를 변경한 뒤 재실행합니다. (섹션 8 참고)

---

### 라이브러리에 항목이 안 보임

**문제**: 확장 프로그램 승인을 완료했는데 라이브러리 페이지에 항목이 표시되지 않습니다.

**원인**: Nexus의 `safe/` 폴더 아래에 파일이 없거나, `/api/nexus/list`가 올바른 경로를 반환하지 않고 있습니다.

**해결**:

1. Nexus UI(`http://localhost:8081`)에서 `safe/` 폴더 아래 ZIP 파일이 있는지 확인합니다.
2. 아래 명령으로 API 응답에 `safe/Chrome/.../ID.zip` 형태가 있는지 확인합니다.
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/nexus/list" -Method Post
   ```
3. 브라우저에서 `Ctrl + F5`로 강력 새로고침합니다.

---

### 요청했는데 계속 처리 중으로 보임

**문제**: 확장 프로그램 요청 후 상태가 계속 "처리 중"으로 표시됩니다.

**원인**: 같은 확장 ID가 Nexus의 `holding/`과 `safe/`에 동시에 존재해 상태가 충돌하고 있습니다.

**해결**: Nexus에서 중복 파일을 확인하고, 오래된 `holding/` 테스트 파일을 삭제합니다.

---

## 8. 포트 충돌 시 변경 방법

`.env` 파일에서 아래 포트 변수를 변경하면 외부 노출 포트를 바꿀 수 있습니다.

```env
APP_PORT=8000                  # 웹 UI (exts3-demo)
SUPPRESSOR_PUBLISHED_PORT=8001 # suppressor
NEXUS_PUBLISHED_PORT=8081      # Nexus
DB_PUBLISHED_PORT=5432         # PostgreSQL
```

예시 — 모두 다른 포트로 변경할 경우:

```env
APP_PORT=8002
SUPPRESSOR_PUBLISHED_PORT=8003
NEXUS_PUBLISHED_PORT=8082
DB_PUBLISHED_PORT=5433
```

변경 후에는 반드시 재빌드 및 재시작해야 반영됩니다.

```bash
docker compose up -d --build
```

> 포트를 변경했다면 섹션 6의 접속 주소도 그에 맞게 바꿔서 접속해야 합니다.
> 또한 `.env`의 `DASHBOARD_BASE_URL`과 suppressor의 `WEB_SERVER_URL`도 포트 변경에 맞게 업데이트하세요.
