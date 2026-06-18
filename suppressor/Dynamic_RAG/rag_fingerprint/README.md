# Dynamic_RAG/rag_fingerprint

Chrome 확장 프로그램의 ZIP 또는 디렉토리를 입력받아 **벡터 임베딩 대상 지문(vector_fingerprint)**을 생성하는 정적 분석 모듈입니다.

생성된 지문은 `embedding/` 모듈에서 bge-m3로 임베딩되어 pgvector 벡터 DB의 악성 패턴과 유사도 비교에 사용됩니다.

---

## 진입점

### 코드에서 호출

```python
from Dynamic_RAG.rag_fingerprint.analyzer import analyze_extension_static

result = analyze_extension_static(
    target="/path/to/extension.zip",
    output_dir=None,                    # None이면 파일 저장 없이 dict 반환
    include_declared_third_party=False,
)
vector_fingerprint = result["vector_fingerprint"]
```

`main.py`의 `/file_scan`은 `output_dir=None`으로 호출해 파일 저장 없이 dict를 직접 사용합니다.

### CLI 실행

```bash
python -m Dynamic_RAG.rag_fingerprint extract \
    /path/to/extension.zip \
    --output Dynamic_RAG/out/my_ext
```

`Dynamic_RAG/out/` 하위에 `extracted_code_features.json`과 `vector_fingerprint.json`이 생성됩니다.

---

## 파일 구성 및 역할

```
rag_fingerprint/
├── analyzer.py          # 오케스트레이터 — 전체 파이프라인 진입점
├── loader.py            # ZIP/디렉토리 로드, 임시 디렉토리 관리
├── manifest_parser.py   # manifest.json 파싱 및 프로필 생성
├── code_scanner.py      # JS 파일 정적 패턴 스캔
├── html_scanner.py      # HTML 파일에서 script 태그 추출
├── dnr_scanner.py       # declarativeNetRequest 룰셋 분석
├── capability_mapper.py # 권한·API → capability 태그 변환
├── flow_builder.py      # 데이터 흐름 패턴 예측
├── fingerprint_builder.py # 최종 지문 JSON 조립
├── utils.py             # 공통 유틸리티
├── main.py              # CLI 진입점
└── __init__.py          # 공개 API export
```

---

## 전체 파이프라인

```
analyze_extension_static(target)
  │
  ├── loader.py: load_extension_source()
  │     ZIP 해제(임시 디렉토리) 또는 디렉토리 로드
  │     manifest.json 위치 자동 탐색 (중첩 구조 지원)
  │
  ├── manifest_parser.py: parse_manifest() → build_manifest_profile()
  │     entrypoint 유형, host_access 분류, background 타입 등
  │
  ├── html_scanner.py: scan_html()
  │     HTML 파일에서 <script src> 경로와 인라인 스크립트 추출
  │     → JS 파일의 role(background/content_script/popup 등) 결정에 사용
  │
  ├── code_scanner.py: scan_js_file() × N → aggregate_js_scans()
  │     JS 파일별 40개 이상 패턴 탐지 (network/storage/messaging/DOM/dynamic 등)
  │     → 전체 집계(agg_all)와 벡터 범위 집계(agg_vector) 분리
  │     → node_modules, dist, build 등 제외 (utils.EXCLUDED_DIRS)
  │
  ├── dnr_scanner.py: scan_dnr_rules()
  │     declarativeNetRequest 룰셋 파일 파싱 → action_type 집계
  │
  ├── capability_mapper.py: map_capabilities()
  │     권한·진입점·API 신호 → capability 태그 변환
  │     config/capability_mapping.json 참조
  │
  ├── flow_builder.py: build_predicted_flows()
  │     신호 조합으로 데이터 흐름 패턴 예측
  │     (예: content_script → runtime_message → background → external_network)
  │
  └── fingerprint_builder.py: build_fingerprint()
        capability_profile, static_code_signals,
        behavior_tags, capability_combinations, predicted_flows 조립
        → vector_fingerprint.json 완성
```

---

## 파일 상세

### analyzer.py

전체 파이프라인을 오케스트레이션하는 핵심 파일입니다. 각 모듈의 결과를 받아 최종 `vector_fingerprint`를 만듭니다.

**`analyze_extension_static(target, output_dir, include_declared_third_party)`**
동기 함수. `output_dir=None`이면 파일 저장 없이 dict 반환. `finally`에서 임시 디렉토리를 반드시 정리합니다.

**`analyze_extension_with_ai(target, ...)`**
`analyze_extension_static`을 `asyncio.to_thread`로 감싼 async 래퍼입니다. 현재 추가 AI 처리 없이 static 결과를 그대로 반환합니다. `__init__.py`에서 export되지만 `main.py`에서는 직접 `analyze_extension_static`을 호출합니다.

**주요 내부 함수**

- `_build_manifest_js_roles()` — manifest의 background/content_scripts/popup 선언에서 JS 파일 → role 매핑
- `_html_role_for_path()` — HTML 파일이 어떤 extension page인지 분류
- `_classify_source()` — JS 파일이 first_party/third_party/minified인지 판별
- `_is_allowed_for_vector()` — 벡터화 범위 필터링 (third_party 기본 제외)

### loader.py

`ExtensionSource` 클래스로 확장 소스를 추상화합니다.

- ZIP 입력: `tempfile.TemporaryDirectory`로 해제 후 manifest.json 위치 탐색. zip bomb 방어를 위해 절대경로·`..` 포함 멤버를 건너뜁니다.
- 디렉토리 입력: manifest.json이 최상위에 없으면 재귀 탐색으로 확장 루트를 찾습니다.
- `source.cleanup()` — 분석 완료 후 임시 디렉토리 정리. `analyzer.py`의 `finally`에서 호출됩니다.

### manifest_parser.py

`build_manifest_profile()` — manifest에서 구조적 프로필을 추출합니다.

| 필드                    | 내용                                                                                    |
| ----------------------- | --------------------------------------------------------------------------------------- |
| `manifest_version`      | 2 또는 3                                                                                |
| `host_access`           | `none` / `targeted` / `limited` / `broad`                                               |
| `background_type`       | `service_worker` / `script` / `none`                                                    |
| `entrypoint_roles`      | `background`, `content_script`, `popup`, `options`, `side_panel`, `devtools`, `ruleset` |
| `content_script_run_at` | `document_start` / `document_end` / `document_idle` 목록                                |

`build_manifest_raw()` — 원본 manifest에서 권한·content_scripts·진입점을 정규화해 `extracted_code_features.json`에 저장합니다.

### code_scanner.py

`scan_js_file(path, role, source_class, is_minified)` — 단일 JS 파일을 40개 이상의 정규식 패턴으로 스캔합니다.

**탐지 신호 카테고리**

| 카테고리              | 탐지 내용                                                          |
| --------------------- | ------------------------------------------------------------------ |
| `network.*`           | fetch, XHR, sendBeacon, WebSocket, EventSource, jQuery ajax, axios |
| `messaging.*`         | runtime.sendMessage, runtime.onMessage, tabs.sendMessage           |
| `storage.*`           | localStorage, sessionStorage, chrome.storage.local/sync/session    |
| `delayed_execution.*` | setInterval, setTimeout                                            |
| `navigation.*`        | tabs.create, tabs.update, location.href, action.onClicked          |
| `dynamic.*`           | eval, new Function, importScripts                                  |
| `dom.*`               | form submit/input 이벤트, password/email 셀렉터                    |

`aggregate_js_scans(scans)` — 파일별 스캔 결과를 집계해 role별 신호, 키워드, URL, 도메인 정보를 합산합니다.

### html_scanner.py

`<script src="...">` 경로와 인라인 `<script>` 내용을 추출합니다. `analyzer.py`가 이 결과로 JS 파일의 role을 결정합니다. 인라인 스크립트는 임시 파일로 저장 후 `scan_js_file`로 스캔하고 즉시 삭제합니다.

### dnr_scanner.py

`declarativeNetRequest.rule_resources`에서 실제 룰 JSON을 읽어 action_type(`redirect`, `modifyHeaders`, `block` 등)을 집계합니다. `fingerprint_builder`의 behavior_tags 생성에 활용됩니다.

### capability_mapper.py

`config/capability_mapping.json`을 읽어 권한·진입점·API 신호를 capability 태그로 변환합니다. `analyzer.py`가 이 결과에 추가 로직(extra_caps, network 정제)을 적용해 최종 `capability_profile`을 완성합니다.

### flow_builder.py

`build_predicted_flows()` — 신호 조합으로 데이터 흐름 패턴을 예측합니다. 각 흐름은 `{trigger, source, path, sink}` 구조입니다.

예측하는 주요 흐름 패턴:

- `document_start` 인젝션 → localStorage 수집 → runtime_message → background → external_network
- timer(setInterval) → 주기적 외부 전송
- form_submit / DOM 입력 → 자격증명 탈취 흐름
- popup/extension_page → 외부 네트워크 요청
- background DNR redirect

### fingerprint_builder.py

`build_fingerprint()` — 앞선 모든 분석 결과를 최종 `vector_fingerprint` JSON으로 조립합니다.

`_build_behavior_tags()` — 신호 조합에서 고수준 행위 태그를 생성합니다.

| 태그                        | 조건                                     |
| --------------------------- | ---------------------------------------- |
| `early_injection`           | `document_start` content_script          |
| `page_storage_exfiltration` | localStorage/sessionStorage 접근         |
| `external_communication`    | 외부 네트워크 API 사용                   |
| `session_theft_pattern`     | storage 키워드에 session/auth/token 포함 |
| `request_modification`      | DNR redirect/modifyHeaders/block         |
| `redirect_hijacking`        | DNR redirect action                      |

`build_capability_combinations()` — host_access + capability 조합 패턴을 생성합니다.
`build_static_code_signals()` — 카테고리별 신호를 구조화된 dict로 변환합니다.

### utils.py

모듈 전체에서 공유하는 공통 유틸리티입니다.

| 함수/상수               | 역할                                                                    |
| ----------------------- | ----------------------------------------------------------------------- |
| `FingerprintError`      | 모듈 전용 예외 클래스                                                   |
| `EXCLUDED_DIRS`         | 스캔 제외 디렉토리 (`node_modules`, `dist`, `build`, `coverage`, `out`) |
| `DEFAULT_MAX_FILE_SIZE` | 파일당 최대 크기 (2MB)                                                  |
| `read_text_safe()`      | 크기 초과·없는 파일 안전 처리                                           |
| `iter_files()`          | EXCLUDED_DIRS 제외 파일 순회                                            |
| `prune_empty()`         | JSON 저장 시 빈 값(`None`, `[]`, `{}`, `False`) 제거                    |
| `fingerprint_hash()`    | 지문 데이터의 SHA-256 해시                                              |

### main.py

CLI 진입점입니다. `extract` 서브커맨드 하나를 제공합니다.

```bash
python -m Dynamic_RAG.rag_fingerprint extract <extension> --output <dir>
python -m Dynamic_RAG.rag_fingerprint extract extension.zip --output out/result --include-declared-third-party
```

`FingerprintError` 발생 시 exit code 2로 종료합니다.

---

## 반환 구조 (analyze_extension_static)

```python
{
    "status": "ok",
    "target": "/path/to/extension.zip",
    "analysis_type": "static_rag_fingerprint",
    "extracted_code_features": {
        "manifest_raw": {...},
        "entrypoints": [...],
        "js_scan_aggregate": {...},
        "js_scan_vector_scope": {...},
        "vector_filtering": {...},
    },
    "vector_fingerprint": {           # ← 임베딩 대상
        "manifest_profile": {...},
        "capability_profile": [...],
        "capability_combinations": [...],
        "static_code_signals": {...},
        "predicted_flows": [...],
        "behavior_tags": [...],
    },
    "output_paths": {
        "extracted_code_features": None,   # output_dir=None이면 None
        "vector_fingerprint": None,
    }
}
```

---

## 검토 메모

- 12개 파일 모두 코드 정상. 삭제·수정 대상 없음.
- `analyze_extension_with_ai`는 현재 `analyze_extension_static`의 async 래퍼 역할만 합니다. 향후 AI 처리 로직이 추가될 자리입니다.
- `utils.EXCLUDED_DIRS`에 `"out"`이 포함되어 있어 `Dynamic_RAG/out/` 내 파일은 스캔 대상에서 자동 제외됩니다.
