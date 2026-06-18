# Dynamic_RAG — 정적 지문 추출 모듈

Chrome 확장 프로그램 ZIP/디렉토리를 입력받아 JS·HTML·DNR 코드를 정적으로 분석하고, 임베딩 및 시나리오 매칭에 사용할 `vector_fingerprint.json`을 생성합니다.

LLM 호출, 임베딩 수행, Vector DB 저장/검색은 이 모듈의 범위가 아닙니다. 순수 정적 분석 기반 JSON 생성만 수행합니다.

## 디렉토리 구조

```
Dynamic_RAG/
├── rag_fingerprint/
│   ├── main.py              # CLI 진입점 (extract 명령)
│   ├── analyzer.py          # 전체 파이프라인 오케스트레이션
│   ├── code_scanner.py      # JS 파일 신호 패턴 정규표현식 스캔
│   ├── html_scanner.py      # HTML 파일 인라인 스크립트 추출
│   ├── dnr_scanner.py       # declarativeNetRequest 룰 분석
│   ├── manifest_parser.py   # manifest.json 파싱 및 프로필 생성
│   ├── capability_mapper.py # 권한/신호 → capability 매핑
│   ├── fingerprint_builder.py # 최종 지문 JSON 조립
│   ├── flow_builder.py      # 예측 데이터 흐름 생성
│   ├── loader.py            # ZIP/디렉토리 로드 및 출력 디렉토리 준비
│   └── utils.py             # 공통 유틸 (파일 순회, JSON 저장 등)
├── config/
│   └── capability_mapping.json  # permission/entrypoint → capability 기준표
└── out/
    └── .gitkeep             # CLI 출력 디렉토리 (내용물은 git 미추적)
```

## CLI 사용법

```bash
# 기본 실행 (suppressor/ 루트에서)
python -m Dynamic_RAG.rag_fingerprint extract <extension_zip_or_dir> --output out/sample

# third-party 파일을 vector 범위에 포함할 경우
python -m Dynamic_RAG.rag_fingerprint extract <extension_zip_or_dir> --output out/sample --include-declared-third-party
```

## 출력 JSON 2종

### 1. `extracted_code_features.json` — 디버깅/상세 분석용

```json
{
  "manifest_raw": { ... },
  "entrypoints": [
    { "role": "background", "path": "background.js", "source_class": "first_party", "is_minified": false }
  ],
  "js_scan_aggregate": {
    "files": [...],
    "code_signals": { "signals": [...], "network": {...}, "keywords": {...} }
  },
  "js_scan_vector_scope": { ... },
  "vector_filtering": {
    "third_party_excluded_by_default": true,
    "include_declared_third_party": false,
    "excluded_files": [...]
  }
}
```

### 2. `vector_fingerprint.json` — 임베딩 입력용

```json
{
  "manifest_profile": {
    "host_access": "broad",
    "entrypoint_roles": ["background", "content_script"],
    "content_script_run_at": ["document_start"]
  },
  "capability_profile": ["broad_page_access", "external_network", "storage_access", ...],
  "capability_combinations": ["broad_page_access + content_script", ...],
  "static_code_signals": {
    "storage": { "apis": ["localStorage"], "keywords": ["token", "session"] },
    "network": { "apis": ["fetch"], "external_origin_present": true },
    "messaging": { "apis": ["runtime.sendMessage"], "patterns": ["content_script_to_background"] }
  },
  "predicted_flows": [...],
  "behavior_tags": ["early_injection", "external_communication", "session_theft_pattern"]
}
```

## 핵심 분석 파이프라인 — `analyzer.py`

`analyze_extension_static(target, output_dir, include_declared_third_party)` 실행 순서:

1. **로드**: ZIP 해제 또는 디렉토리 마운트 (`loader.py`)
2. **manifest 파싱**: 권한, host_permissions, content_scripts, background, popup 등 파싱
3. **JS 역할 분류**: 각 JS 파일에 `background` / `content_script` / `popup` / `extension_page` / `unknown_script` 역할 부여
4. **소스 분류**: `first_party` / `third_party` / `vendor` 분류 (node_modules, lib/, `.min.js` 등 기준)
5. **HTML 스캔**: HTML 파일에서 인라인 스크립트 추출 → JS 스캔에 포함
6. **JS 스캔** (`code_scanner.py`): 40여 개 패턴으로 신호 추출 (아래 참조)
7. **DNR 스캔** (`dnr_scanner.py`): declarativeNetRequest 룰 action 타입 분석
8. **Capability 매핑** (`capability_mapper.py`): 신호 + 권한 → capability_profile 생성
9. **지문 조립** (`fingerprint_builder.py`): behavior_tags, capability_combinations, static_code_signals 계산

## 탐지 신호 카테고리 (code_scanner.py)

| 카테고리  | 예시 신호                                                                                    |
| --------- | -------------------------------------------------------------------------------------------- |
| 네트워크  | `network.fetch`, `network.xhr`, `network.WebSocket`, `network.sendBeacon`, `network.axios`   |
| 메시징    | `messaging.runtime.sendMessage`, `messaging.runtime.onMessage`, `messaging.tabs.sendMessage` |
| 스토리지  | `storage.localStorage`, `storage.sessionStorage`, `storage.chrome.storage.local`             |
| 지연 실행 | `delayed_execution.setInterval`, `delayed_execution.setTimeout`                              |
| 탐색      | `navigation.tabs.create`, `navigation.tabs.update`, `navigation.location.href`               |
| 동적 실행 | `dynamic.eval`, `dynamic.new_function`, `dynamic.importScripts`                              |
| DOM       | `dom.event.submit`, `dom.event.input`, `dom.selector.password`, `dom.selector.email`         |

## Capability → behavior_tags 매핑 예시

| 신호 조합                               | behavior_tag                                      |
| --------------------------------------- | ------------------------------------------------- |
| `content_script_run_at: document_start` | `early_injection`                                 |
| `localStorage` + `network.fetch`        | `session_theft_pattern`, `external_communication` |
| `runtime.sendMessage`                   | `message_passing_bridge`                          |
| `setInterval`                           | `repeated_exfiltration`                           |
| DNR `redirect` action                   | `redirect_hijacking`, `request_modification`      |

## vector 범위 제외 기준

기본적으로 third-party/vendor 파일은 vector 범위에서 제외됩니다.

- `node_modules/` 하위
- `lib/` 하위
- `.min.js` 파일
- jquery, bootstrap, lodash, react, vue, angular 포함 파일명

`--include-declared-third-party` 플래그를 사용하면 manifest `background`/`content_scripts`에 직접 선언된 third-party 파일만 vector 범위에 포함할 수 있습니다.

## 외부 연동 API

```python
from Dynamic_RAG.rag_fingerprint.analyzer import analyze_extension_static

result = analyze_extension_static(
    target="extension.zip",
    output_dir="out/sample",
    include_declared_third_party=False,
)
# result["vector_fingerprint"] → embedding 입력으로 전달
```

비동기 버전 (`analyze_extension_with_ai`)도 동일한 정적 분석만 수행하며 `asyncio.to_thread`로 래핑됩니다.

## 보안 원칙

- 실제 token/session/cookie/개인정보 수집 금지
- 실제 서비스 공격 목적 사용 금지
- `vector_fingerprint.json`에 실제 URL, 민감값, 코드 스니펫 포함 금지
