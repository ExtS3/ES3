# scripts

자동 PR 파이프라인 + 코드 리뷰 자동화 스크립트 모음입니다.
feature/fix/docs/refactor 브랜치를 push할 때 규칙 검사 → PR 자동 생성 → 코드 리뷰 리포트 생성까지 이어집니다.

`.github/workflows/`가 완비되어 **CI에 정상 연결되어 있습니다.**

---

## 전체 흐름

```
push (feature/**, fix/**, docs/**, refactor/**)
  └── .github/workflows/auto-pr.yml
        ├── scripts/check_rules.py    ← 5가지 규칙 검사
        └── scripts/create_pr.py      ← 규칙 통과 시 PR 자동 생성

PR 생성 / 업데이트 (→ develop, main)
  └── .github/workflows/auto-code-review.yml
        └── scripts/review_pr.py      ← 코드 변경 정밀 분석 + PR 코멘트 게시
```

규칙 정의 파일: `.github/pipeline-rules.yml`

---

## 파일 구성

### check_rules.py

PR 생성 전 5가지 규칙을 검사하고 결과를 `rule_check_result.json`에 저장합니다.

| 규칙           | 검사 내용                         | 실패 시          |
| -------------- | --------------------------------- | ---------------- |
| 1. 브랜치 이름 | 허용 prefix, 허용 문자, 최대 길이 | PR 생성 차단     |
| 2. README.md   | 파일 존재, 최소 줄 수             | PR 생성 차단     |
| 3. 필수 파일   | `required_files` 존재 여부        | PR 생성 차단     |
| 4. 금지 파일   | `blocked_files.patterns` 매칭     | PR 생성 차단     |
| 5. 커밋 메시지 | Conventional Commits 형식         | 설정에 따라 차단 |

`main`, `develop`, `staging` 브랜치는 검사를 건너뜁니다(SKIP).

### create_pr.py

`rule_check_result.json`을 읽어 GitHub API로 PR을 자동 생성합니다. 브랜치명에서 PR 제목을 만들고(`feature/123-add-login` → `[Feature] #123 Add Login`), 변경 파일 목록과 규칙 검사 결과를 본문에 포함합니다. 생성된 URL을 `created_pr_url.txt`에 저장합니다.

필요 환경변수: `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_HEAD_REF`/`GITHUB_REF_NAME`, (선택) `PR_BASE_BRANCH`, `PR_ALLOW_FALLBACK_TO_MAIN`.

### review_pr.py

PR의 변경 코드를 정밀 분석해 리뷰 리포트를 생성합니다.

**분석 항목 9가지**: 변경 요약, 신규 로직(함수·클래스), 삭제/수정된 인터페이스, 의존성 변화(`requirements.txt`), import 검증, 정적 오류(pyflakes), 복잡도 경고, 위험 패턴(`eval`/`exec`/하드코딩 시크릿 등), 종합 판정.

**종합 판정**: `MERGE_READY` / `NEEDS_REVIEW` / `BLOCK`

출력: `pr_review_result.json`, `pr_review_result.md`. workflow가 md를 PR 코멘트로 게시하고 BLOCK이면 인라인 코멘트도 추가합니다.

> `review_pr.py` 자신은 위험 패턴 문자열(`eval`, `exec` 등)을 포함하므로 자기 자신을 분석에서 제외합니다.

---
