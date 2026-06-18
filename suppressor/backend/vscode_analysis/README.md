# backend/vscode_analysis

VSCode 확장(VSIX) 전용 정적 분석 모듈입니다. Chrome 파이프라인(동적 RAG·난독화)과 완전히 분리된 독립 모듈로, `main.py`의 `/file_scan`에서 `browser == "vscode"`일 때만 실행됩니다.

Tier1 룰 기반(정규식 전용, AST 금지)으로 VSIX 내부의 `extension/package.json`과 소스 파일을 스캔해 위험 신호를 탐지합니다. **자동 승인은 생성하지 않으며 모든 결과는 `decision=review`로 반환됩니다(fail-closed).**

---

## 진입점

```python
from backend.vscode_analysis.runner import run_vscode_static_analysis

result = run_vscode_static_analysis(vsix_path)
# result["decision"]["suggest_reject"] == True  → 거부 권장
# result["decision"]["suggest_reject"] == False → 수동 검토
```

`main.py`의 `_run_vscode_scan()`이 이 함수를 호출합니다.

---

## 파일 구성

```
backend/vscode_analysis/
├── __init__.py          # 패키지 설명 (진입점 안내)
├── rules.py             # 룰 패턴 상수·화이트리스트·IOC 정의
├── manifest_scan.py     # M 계열 룰 (package.json 분석)
├── code_scan.py         # C/X 계열 룰 (소스 파일 분석)
├── runner.py            # 분석 오케스트레이터 (진입점)
└── decision.py          # 최종 판정 로직
```

---

## 파일 상세

### rules.py

모든 룰의 정규식 패턴, 화이트리스트, IOC 상수를 정의합니다. 다른 파일들은 이 파일만 import합니다.

**화이트리스트 / IOC 상수**

| 상수                           | 용도                                                       |
| ------------------------------ | ---------------------------------------------------------- |
| `PUBLISHER_WHITELIST`          | M-002 면제 publisher (ms-vscode, github, microsoft 등 6개) |
| `KNOWN_C2_IPS`                 | C-006 알려진 C2 IP 9개 (GlassWorm·Anivia 캠페인)           |
| `CLOUD_METADATA_ENDPOINTS`     | C-007 클라우드 메타데이터 엔드포인트 4개                   |
| `C007_CREDENTIAL_PATHS`        | 자격증명 탈취 경로 정규식 (절대 면제 안 함)                |
| `C007_INSTANCE_METADATA_PATHS` | 정상 VM 탐지 경로 정규식 (조건부 면제)                     |
| `SECRET_MASK_TOKENS`           | X-002 면제 마스킹 토큰 (EXAMPLE, PLACEHOLDER, XXX)         |

**룰 패턴 (C003~X003)**

| 상수                        | 룰                                                    |
| --------------------------- | ----------------------------------------------------- |
| `C003_EVAL`                 | eval / new Function / vm.runIn\*                      |
| `C003_EXEMPT_RETURN_THIS`   | globalThis 폴리필 면제 (`Function("return this")`)    |
| `C003_EXEMPT_EVAL_REQUIRE`  | CommonJS require shim 면제 (`eval("require('...')")`) |
| `C004_INVISIBLE`            | 비가시 Unicode 5자+ 연속                              |
| `C009_GITHUB_SEARCH`        | GitHub Search commits dead-drop                       |
| `C010_BACKUP_CHANNEL`       | Solana RPC / Google Calendar ical                     |
| `C011_NATIVE_NODE`          | native `.node` 모듈                                   |
| `X001_PAT` + `X001_CONTEXT` | Marketplace PAT (52자 base32 + vsce/marketplace 맥락) |
| `X002_SECRETS`              | LLM/클라우드 API 키 (OpenAI sk-, AWS AKIA, 등)        |
| `X003_GCP_KEY`              | GCP 서비스계정 private key                            |

**RULE_META**

15개 룰의 `(severity, category, title, recommendation)` 튜플을 보관합니다. `manifest_scan.py`와 `code_scan.py`의 `_emit()`이 이 딕셔너리에서 finding 메타를 가져옵니다.

---

### manifest_scan.py

`scan_manifest(manifest)` — `extension/package.json` dict를 받아 M 계열 룰 5개를 적용합니다.

| 룰    | 심각도 | 조건                                                     |
| ----- | ------ | -------------------------------------------------------- |
| M-001 | HIGH   | `activationEvents`에 `"*"` 포함                          |
| M-002 | HIGH   | `enabledApiProposals` 사용 + publisher가 화이트리스트 밖 |
| M-004 | MEDIUM | `extensionKind` 누락 또는 `"workspace"` 포함             |
| M-005 | MEDIUM | `scripts.postinstall` 또는 `scripts.preinstall` 존재     |
| M-006 | MEDIUM | `extensionPack` 비어있지 않음                            |

---

### code_scan.py

`scan_source_file(file_name, content)` — 단일 소스 파일에 C/X 계열 룰 10개를 적용합니다.
`scan_sources(source_files)` — 파일 목록을 순회해 전체 findings를 합산합니다.

**vendored 제외 정책**

`node_modules/` 경로 파일은 FP 우려가 있는 룰만 면제합니다.

| 룰                                | node_modules 처리                             |
| --------------------------------- | --------------------------------------------- |
| C-003 (eval)                      | 면제 (번들 라이브러리 FP 방지)                |
| C-011 (native .node)              | 면제 (정상 native dep FP 방지)                |
| C-004, C-006, C-007, C-009, C-010 | **면제 안 함** (보안 결정적 룰)               |
| X-001, X-002, X-003               | **면제 안 함** (시크릿은 vendored에서도 발화) |

**C-003 면제 로직**

eval/new Function/vm.runIn\* 탐지 시 번들러 보일러플레이트만 좁게 면제합니다.

- `Function("return this")` / `(0, eval)("this")` → globalThis 폴리필 (면제)
- `eval("require('...')")` → CommonJS require shim (면제)
- 그 외 동적 입력, 변수, 연결(concatenation) → 면제 안 함

**C-007 면제 로직**

클라우드 메타데이터 접근 시 자격증명 경로(`identity/token/iam` 등)가 있으면 무조건 발화합니다. 자격증명 경로 없이 인스턴스 메타데이터 정상 경로(`/metadata/instance`)만 있는 경우만 면제합니다.

**publisher_whitelisted 파라미터**

코드 룰(C/X)에는 영향 없습니다. 침해된 신뢰 publisher 위협모델을 통과시키지 않기 위함입니다. 파라미터는 호환성을 위해 유지하되 내부에서 사용하지 않습니다.

---

### runner.py

`run_vscode_static_analysis(vsix_path)` — 모듈의 진입점입니다.

**처리 흐름**

```
VSIX(zip) 열기
  ├── 실패 → _error_result() 반환 (raise 금지)
  │
  ├── _read_manifest() → extension/package.json 파싱
  └── _collect_sources() → 소스 파일 수집
        ├── SOURCE_EXT (.js/.ts/.cjs/.mjs) — C/X 룰 대상
        ├── SECRET_EXT (.json/.map/.md/.env 추가) — X 룰 대상
        └── 5MB 초과 파일 스킵 (zip bomb 방어)

scan_manifest(manifest) → M 계열 findings
scan_sources(sources, whitelisted) → C/X 계열 findings

findings 합산 → summarize_findings() → scan_result
decision_mod.decide(scan_result) → 최종 판정
```

**반환 구조**

```python
{
    "program_name": "extension-name",
    "program_version": "1.0.0",
    "program_type": "vscode-extension",
    "findings": [...],
    "scan_result": {"critical": 0, "high": 1, "medium": 2, "low": 0},
    "status": "ok",           # 오류 시 "error"
    "decision": {
        "decision": "review",
        "suggest_reject": True,   # Critical >= 1 시
        "reason": "..."
    }
}
```

---

### decision.py

`decide(severity_counts, status)` — 심각도 카운트와 상태를 받아 판정을 반환합니다.

| 조건                | decision |   suggest_reject    |
| ------------------- | -------- | :-----------------: |
| `status == "error"` | review   | False (fail-closed) |
| critical >= 1       | review   |  True (거부 권장)   |
| 그 외               | review   |        False        |

`decision`은 항상 `"review"`입니다. suppressor는 위험 신호만 보고하고 최종 승인·거부는 ExtS3-Web-UI가 정책에 따라 결정합니다.

---

## import shim 패턴

모든 파일이 아래 패턴으로 import 경로를 이중화합니다.

```python
try:
    from backend.scanners.common import add_finding  # main.py에서 실행 시
except ModuleNotFoundError:
    from scanners.common import add_finding          # tests/에서 직접 실행 시
```

`main.py`는 suppressor 루트에서 실행되어 `backend.*`로 접근하고, `backend/tests/`의 conftest.py는 `backend/`를 sys.path에 추가해 `vscode_analysis.*`로 접근합니다. 두 경로 모두 정상 동작합니다.

---

## 테스트

이 모듈의 테스트는 `backend/tests/vscode_analysis/`에 있습니다 (66개). 자세한 내용은 해당 폴더의 README 참고.
