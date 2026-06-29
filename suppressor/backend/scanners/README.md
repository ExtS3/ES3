# backend/scanners

확장 프로그램 정적 분석을 수행하는 6개의 독립 스캐너 모듈입니다.
`manifest_permission_scan`, `manifest_behavior_scan`, `code_execution_scan`, `code_navigation_scan`, `evasion_injection_scan` 5개는 `static_analysis.py`의 `run_static_analysis`에서 순차 실행됩니다.
`minify_obfuscation.py`(PracticalScanner)는 `main.py`에서 직접 호출됩니다.

## 공통 반환 구조

```json
{
  "scanner": "manifest_permission_scan",
  "findings": [
    {
      "type": "dangerous_permission",
      "severity": "CRITICAL",
      "detail": "management",
      "source": "permissions"
    }
  ],
  "severity_counts": { "CRITICAL": 1, "HIGH": 0, "MEDIUM": 2, "LOW": 5 },
  "summary": { ... }
}
```

## 스캐너 목록

### `manifest_permission_scan.py`

`run_manifest_permission_scan(report)`

manifest의 권한 선언을 분석합니다.

검사 대상:

- `permissions` / `optional_permissions`
- `host_permissions` / `optional_host_permissions`
- `content_scripts.matches`

특이사항:

- `<all_urls>` 와일드카드는 별도 `wildcard_host_permissions` finding 생성
- 광고차단형 프로필(declarativeNetRequest만 있고 기타 위험 권한 없음)은 완화 처리
- `ExtAnalysis/db/permissions.json`의 risk·warning·description을 `permission_details`에 보존

주요 판정 기준:

| 권한                     | 판정     | 이유                   |
| ------------------------ | -------- | ---------------------- |
| `management`             | CRITICAL | 확장 관리 전체 권한    |
| `debugger`               | CRITICAL | 탭 전체 제어 가능      |
| `nativeMessaging`        | CRITICAL | 로컬 네이티브 앱 통신  |
| `scripting`              | HIGH     | 페이지 코드 실행       |
| `webRequest` (blocking)  | HIGH     | 네트워크 요청 가로채기 |
| `cookies` + `<all_urls>` | HIGH     | 전 사이트 쿠키 접근    |

---

### `manifest_behavior_scan.py`

`run_manifest_behavior_scan(report)`

manifest의 구조적 행위 패턴을 분석합니다.

검사 대상:

- `background` / `service_worker` 선언 유무
- `chrome_url_overrides` — 새 탭/홈페이지 교체
- `externally_connectable` — 외부 사이트와의 메시지 통신 허용 여부
- `web_accessible_resources` — 외부에 노출되는 리소스 범위

---

### `code_execution_scan.py`

`run_code_execution_scan(report, source_entries)`

JS 코드에서 위험한 실행 패턴을 탐지합니다.

탐지 패턴:

- `eval(...)` — 동적 코드 실행
- `new Function(...)` — 문자열 코드 실행
- `atob(...)` — Base64 디코딩 (난독화 우회 신호)
- `String.fromCharCode(...)` — 문자 코드 기반 난독화

오탐 완화:

- `Function("return this")()`, `(0, eval)("this")` — 정상 라이브러리 패턴으로 무시
- 알려진 라이브러리 파일명 (underscore, knockout, jquery 등)은 완화 처리
- 파서/에디터 라이브러리(codemirror 등)의 정상 패턴 무시

---

### `code_navigation_scan.py`

`run_code_navigation_scan(report, source_entries)`

외부 통신 및 탐색 패턴을 탐지하고 `reputation_targets`를 추출합니다.

탐지 패턴:

- `chrome.runtime.setUninstallURL(...)` — 제거 시 URL 이동
- `chrome.tabs.create(...)` — 탭 생성
- `window.open(...)` — 팝업 열기
- `fetch(...)` — 외부 HTTP 요청
- `XMLHttpRequest` — 구형 HTTP 요청

URL 문맥 분류:

- 문서/README/GitHub 이슈 링크 → 제외
- 테스트 도메인, `${...}` 템플릿 URL → 제외
- 실제 네트워크 통신 가능성 있는 URL → `reputation_targets`에 보존

---

### `evasion_injection_scan.py`

`run_evasion_injection_scan(report, source_entries)`

페이지에 숨겨진 코드를 주입하고 특정 조건에서만 동작해 탐지를 회피하는 패턴을 탐지합니다.
정상 확장이 악성 업데이트로 바뀌는 공급망형 위협(예: boannews idx=144344 — 인기 광고차단 확장이 업데이트로 숨겨진 JS를 주입)을 겨냥합니다.

탐지 패턴:

| rule_id                  | 심각도 | 의미                                                                  |
| ------------------------ | ------ | --------------------------------------------------------------------- |
| `inject_remote_script`   | HIGH   | `createElement('script')` + `.src=` — 원격 스크립트를 페이지에 주입   |
| `inject_inline_script`   | HIGH   | `createElement('script')` + `.text/.textContent/.innerHTML=` — 인라인 코드 주입 |
| `create_script_element`  | MEDIUM | `<script>` 동적 생성 (주입 가능성)                                    |
| `host_conditional_exec`  | MEDIUM | `location.hostname` 비교/부분일치 — 특정 사이트에서만 실행 (회피)      |
| `time_conditional_exec`  | LOW    | `getHours()` 등 시간 기반 게이팅 (time-bomb 신호)                     |

결합 판정 (스모킹 건):

- 같은 파일에서 **주입 패턴 + 회피 패턴이 동시에** 나타나면 `evasive_injection` finding을 추가로 생성
- 주입 신호 중 HIGH가 있으면 `CRITICAL`, 아니면 `HIGH`
- 라이브러리 파일(`.min.js`, `/vendor/` 등)은 전 패턴 `LOW`로 완화

---

### `common.py`

스캐너 공통 유틸리티.

| 함수                                            | 설명                                               |
| ----------------------------------------------- | -------------------------------------------------- |
| `load_source_map(report_dir, source_json_path)` | ExtAnalysis 생성 `source.json` 로드                |
| `extract_source_entries(source_map)`            | 파일 경로와 코드 내용 추출                         |
| `ensure_dict(value, name)`                      | None/비딕셔너리 안전 변환                          |
| `read_json_file(path)`                          | JSON 파일 읽기                                     |
| `summarize_findings(findings, severity_counts)` | overall_severity 계산 및 scan_result 딕셔너리 생성 |

---

### `minify_obfuscation.py` (PracticalScanner)

**호출 위치**: `main.py`에서 `from backend.scanners.minify_obfuscation import PracticalScanner`로 직접 import해 난독화 분석 단계(3번째)에서 실행됩니다. `static_analysis.py`를 거치지 않습니다.

ExtAnalysis `source.json`의 JS 파일을 대상으로 정상 빌드 결과물과 실제 난독화를 구분하는 경량 스캐너입니다.

#### Verdict 분류

| Verdict                        | 조건                                                                                                                    |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `benign_minify`                | `.min.js`, 알려진 라이브러리 파일명/헤더, 빌드 도구 흔적(webpack, rollup, esbuild 등) 존재 + 강한 난독화 핵심 신호 없음 |
| `readable_script`              | 일반적으로 읽을 수 있는 앱 로직. 약한 신호는 있으나 난독화 핵심 없음                                                    |
| `suspicious_obfuscation`       | 강한 난독화 핵심 신호 복수 존재. `_0x` 변수 + 헥사 인덱싱, `eval(atob(...))`, `importScripts`, `executeScript` 등       |
| `likely_malicious_obfuscation` | 강한 난독화 패턴이 외부 통신 또는 고위험 권한과 결합. `eval(atob(...))` + `fetch`, JSFuck/aaencode 등                   |

#### 탐지 신호 카테고리

**정상 신호 (benign_minify 근거)**

- 파일명 `.min.js`, 알려진 라이브러리명 (underscore, knockout, jquery, bootstrap 등)
- 알려진 라이브러리 헤더 문자열
- 빌드/번들 도구 주석 흔적 (Terser, UglifyJS, webpack, rollup, esbuild, swc, vite, parcel)
- 낮은 식별자 엔트로피, 긴 한 줄 번들 형태

**의심 난독화 핵심 신호**

- `_0x...` 형태의 헥사 변수명 다수
- `_0xabc[0x12]` 같은 헥사 배열 인덱싱
- `eval(atob(...))`, `Function(atob(...))`
- XOR decoder 패턴
- `chrome.scripting.executeScript(...)`, `chrome.tabs.executeScript(...)`
- `importScripts(...)`
- JSFuck 계열, aaencode 계열

**무시하는 안전 패턴**

- `Function("return this")()` — 정상 라이브러리 전역 객체 접근
- `(0, eval)("this")` — 동일

**rotation 난독화 판정 조건**
단순 `push/shift/splice`만으로는 의심하지 않음. 아래 세 조건이 동시 만족될 때만 rotation 난독화로 판정:

- `while(true)` 또는 `while(!![])`
- 배열 연산 (`push/shift/splice/unshift`)
- 난독화 문맥 (헥사 변수, 헥사 인덱싱, 큰 문자열 배열)

#### 출력 JSON 구조

```json
{
  "program_name": "ExtensionName",
  "overall_verdict": "mostly_benign_minify",
  "summary": {
    "benign_minify": 4,
    "readable_script": 3,
    "suspicious_obfuscation": 0,
    "likely_malicious_obfuscation": 0
  },
  "files": [
    {
      "path": "js/libs/underscore-min.js",
      "result": "benign_minify",
      "reasons": ["정상 라이브러리/빌드 흔적이 강하고 강한 난독화 핵심이 없음"],
      "details": {
        "minify_signals": [...],
        "suspicious_signals": [...],
        "ignored_signals": [...],
        "matched_high_risk_permissions": [...]
      }
    }
  ]
}
```

#### 한계

- 고급 난독화가 정상 라이브러리처럼 위장하면 탐지 어려움
- 동적 로딩 후에만 악성 동작이 드러나는 경우 정적 탐지 한계
- `benign_minify`가 절대적 안전을 의미하지 않음. 빠른 1차 triage 용도로 적합

---

## 의존 관계

- `ExtAnalysis/db/permissions.json` — 권한 위험도 참조 (`manifest_permission_scan`)
- `backend/extanalysis_integration.py` — source.json 경로 전달
- `backend/static_analysis.py` — manifest/code 스캐너 오케스트레이션
- `main.py` — `PracticalScanner` 직접 import (`minify_obfuscation.py`)
