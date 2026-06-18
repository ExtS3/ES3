# scripts

자동 PR 파이프라인 + 코드 리뷰 자동화 스크립트 모음입니다.
feature/fix/docs/refactor 브랜치를 push할 때 규칙 검사 → PR 자동 생성 → 코드 리뷰 리포트 생성까지 이어집니다.

---

## 전체 흐름

```
push (feature/**, fix/**, docs/**, refactor/**)
  └── auto-pr.yml
        ├── check_rules.py    ← 5가지 규칙 검사
        └── create_pr.py      ← 규칙 통과 시 PR 자동 생성

PR 생성 / 업데이트 (→ develop, main)
  └── auto-code-review.yml
        └── review_pr.py      ← 코드 변경 정밀 분석 + PR 코멘트 게시
```

---

## 파일 구성

### check_rules.py

PR 생성 전 5가지 규칙을 검사하고 결과를 `rule_check_result.json`에 저장합니다.
`auto-pr.yml`의 `Rule Check` 스텝에서 호출됩니다.

**규칙 목록**

| 규칙           | 검사 내용                                        | 실패 시                     |
| -------------- | ------------------------------------------------ | --------------------------- |
| 1. 브랜치 이름 | 허용 prefix, 허용 문자(`[a-z0-9\-/]`), 최대 길이 | PR 생성 차단                |
| 2. README.md   | 파일 존재 여부, 최소 줄 수                       | PR 생성 차단                |
| 3. 필수 파일   | `required_files` 목록의 파일 존재 여부           | PR 생성 차단                |
| 4. 금지 파일   | `blocked_files.patterns` 패턴에 매칭되는 파일    | PR 생성 차단                |
| 5. 커밋 메시지 | Conventional Commits 형식 (`<type>: <desc>`)     | `fail` 설정 시 PR 생성 차단 |

`main`, `develop`, `staging` 브랜치는 검사를 건너뜁니다(`SKIP`).

**런타임 출력**: `rule_check_result.json`

---

### create_pr.py

`rule_check_result.json`을 읽어 GitHub API로 PR을 자동 생성합니다.
`auto-pr.yml`의 `Auto PR` 스텝에서 호출됩니다.

**동작 흐름**

1. base 브랜치 결정 (`PR_BASE_BRANCH`, 기본값 `develop`) → 없으면 `PR_ALLOW_FALLBACK_TO_MAIN` 여부에 따라 `main` 대체 또는 오류 종료
2. 동일 브랜치의 열린 PR이 이미 있으면 생성 없이 종료
3. 브랜치명에서 PR 제목 자동 생성 — `feature/123-add-login` → `[Feature] #123 Add Login`
4. PR 본문 생성: 변경 파일 목록 + 규칙 검사 결과 테이블 + 경고 항목
5. `POST /repos/{repo}/pulls` 호출
6. 생성된 PR URL을 `created_pr_url.txt`에 저장

**필요 환경변수**

| 변수                                     | 필수 | 설명                                                   |
| ---------------------------------------- | ---- | ------------------------------------------------------ |
| `GITHUB_TOKEN`                           | ✅   | PR 생성 권한 토큰 (Actions 자동 주입)                  |
| `GITHUB_REPOSITORY`                      | ✅   | `owner/repo` 형식 (Actions 자동 주입)                  |
| `GITHUB_HEAD_REF` 또는 `GITHUB_REF_NAME` | ✅   | 현재 브랜치명 (Actions 자동 주입)                      |
| `PR_BASE_BRANCH`                         | ❌   | PR 대상 브랜치 (기본값: `develop`)                     |
| `PR_ALLOW_FALLBACK_TO_MAIN`              | ❌   | `true`이면 develop 없을 때 main 대체 (기본값: `false`) |

**런타임 출력**: `created_pr_url.txt`

---

### review_pr.py

PR의 변경 코드를 정밀 분석해 PM이 Merge 판단에 쓸 수 있는 리포트를 생성합니다.
`auto-code-review.yml`의 `Run Code Review Analysis` 스텝에서 호출됩니다.

**분석 항목 9가지**

| 항목        | 내용                                                               |
| ----------- | ------------------------------------------------------------------ |
| 변경 요약   | 어떤 파일이 추가·수정·삭제됐는지                                   |
| 신규 로직   | 추가된 함수·클래스·FastAPI 엔드포인트 목록                         |
| 삭제/수정   | 기존 인터페이스의 변경·제거 여부                                   |
| 의존성 변화 | `requirements.txt` 추가·삭제·버전 변경                             |
| import 검증 | 새로 추가된 import가 requirements에 있는지                         |
| 정적 오류   | pyflakes 기반 undefined/unused 심볼                                |
| 복잡도 경고 | 함수 길이 80줄 초과, 중첩 깊이 5 초과                              |
| 위험 패턴   | `eval`, `exec`, `os.system`, `shell=True`, 하드코딩 시크릿 의심 등 |
| 종합 판정   | `MERGE_READY` / `NEEDS_REVIEW` / `BLOCK`                           |

**판정 기준**

| 판정           | 조건                                                                      |
| -------------- | ------------------------------------------------------------------------- |
| `BLOCK`        | BLOCK 심각도 이슈 1건 이상 (eval/exec/하드코딩 시크릿 등)                 |
| `NEEDS_REVIEW` | HIGH 이슈 존재, 또는 기존 함수·클래스 제거, 또는 의존성 삭제·다운그레이드 |
| `MERGE_READY`  | 위 조건 해당 없음                                                         |

**런타임 출력**

| 파일                    | 내용                                           |
| ----------------------- | ---------------------------------------------- |
| `pr_review_result.json` | 분석 결과 전체 (이슈 목록, 심볼 변경, 판정 등) |
| `pr_review_result.md`   | PR 코멘트용 Markdown 리포트                    |

`auto-code-review.yml`이 `pr_review_result.md`를 읽어 PR 코멘트로 게시하고, BLOCK 판정 시 인라인 코멘트도 추가합니다.

**필요 환경변수** (Actions에서 자동 세팅)

| 변수              | 설명               |
| ----------------- | ------------------ |
| `REVIEW_BASE_SHA` | diff 기준 커밋 SHA |
| `REVIEW_HEAD_SHA` | 분석 대상 커밋 SHA |
| `REVIEW_BRANCH`   | 브랜치명           |
| `PR_NUMBER`       | PR 번호            |

> `scripts/review_pr.py` 자체는 위험 패턴 문자열(`eval`, `exec` 등)을 포함하고 있어 자기 자신을 분석 대상에서 제외합니다 (`SELF_SKIP` 처리).

---

## 규칙 설정 파일

**`.github/pipeline-rules.yml`** — `check_rules.py`가 읽는 규칙 정의 파일입니다.

```yaml
branch:
  allowed_prefixes:
    - feature/
    - fix/
    - docs/
    - refactor/
  max_length: 60
  require_issue_number: false

readme:
  min_lines: 10

required_files:
  - README.md
  - .gitignore

blocked_files:
  patterns:
    - '.env'
    - '.env.local'
    - '*.pem'

commit_message:
  conventional_commits: fail
  allowed_types:
    - feat
    - fix
    - docs
    - style
    - refactor
    - chore

pr:
  base_branch: develop
  allow_fallback_to_main: true
```

---

## 런타임 생성 파일 (.gitignore 등록 권장)

아래 파일들은 CI 실행 중에 생성되며 Git에 커밋할 필요가 없습니다.

```gitignore
rule_check_result.json
created_pr_url.txt
pr_review_result.json
pr_review_result.md
```

---

## 의존 관계 전체

```
.github/
├── pipeline-rules.yml          ← check_rules.py 규칙 정의
└── workflows/
    ├── auto-pr.yml             ← push 시 실행
    │     ├── check_rules.py   → rule_check_result.json
    │     └── create_pr.py     → created_pr_url.txt
    │
    └── auto-code-review.yml    ← PR 생성·업데이트 시 실행
          └── review_pr.py     → pr_review_result.json
                               → pr_review_result.md
                               → PR 코멘트 게시 (GitHub Actions Script)
```
