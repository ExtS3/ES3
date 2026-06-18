# backend/tests/vscode_analysis

`backend/vscode_analysis/` 모듈의 단위 테스트입니다. **pytest 기반**으로 총 66개 테스트를 포함합니다.

> 이 폴더는 삭제하면 안 됩니다. VSCode 확장 Tier1 룰 엔진 전체를 커버하며, 룰 추가·수정·면제 로직 변경 시 오탐/미탐 회귀를 방지하는 안전망입니다.

---

## 실행 방법

```bash
# 레포 루트에서
pytest backend/tests/vscode_analysis

# 단일 파일
pytest backend/tests/vscode_analysis/test_code_scan.py

# 상세 출력
pytest backend/tests/vscode_analysis -v
```

> pytest가 없으면 `pip install pytest`로 설치합니다. `requirements.txt`에 추가하지 않아도 됩니다.

---

## 파일 구성

### conftest.py

`backend/` 디렉토리를 `sys.path`에 추가해 `from vscode_analysis.xxx import ...` import가 정상 동작하도록 설정합니다.

```python
BACKEND_DIR = .../suppressor/backend/   # ← sys.path에 추가
# 이후 from vscode_analysis.decision import ... → backend/vscode_analysis/decision.py 로 해석
```

---

### test_decision.py (4개)

`backend/vscode_analysis/decision.py`의 판정 계약을 검증합니다.

| 테스트                                      | 검증 내용                                                    |
| ------------------------------------------- | ------------------------------------------------------------ |
| `test_critical_suggests_reject_and_review`  | Critical 1건 이상 → `suggest_reject=True`, `decision=review` |
| `test_high_medium_only_is_review_no_reject` | High/Medium만 → `suggest_reject=False`, `decision=review`    |
| `test_no_findings_is_review_not_approve`    | findings 없음 → 자동 approve 생성 안 함, `decision=review`   |
| `test_error_status_is_review_failclosed`    | `status=error` → fail-closed, `decision=review`              |

**핵심 계약**: `decision`은 항상 `review`이며 자동 승인은 절대 생성되지 않습니다.

---

### test_manifest_scan.py (12개)

`backend/vscode_analysis/manifest_scan.py`의 M 계열 룰 5개를 검증합니다.

| 룰    | 테스트 수 | 검증 내용                                                                         |
| ----- | :-------: | --------------------------------------------------------------------------------- |
| M-001 |     2     | `*` 와일드카드 activationEvents 발화 / 구체적 이벤트 미발화                       |
| M-002 |     3     | 서드파티 API proposals 발화 / 화이트리스트 publisher 면제 / proposals 없음 미발화 |
| M-004 |     3     | extensionKind 누락 발화 / workspace 발화 / ui-only 미발화                         |
| M-005 |     2     | postinstall 스크립트 발화 / 없음 미발화                                           |
| M-006 |     2     | extensionPack 선언 발화 / 빈 pack 미발화                                          |

---

### test_code_scan.py (46개)

`backend/vscode_analysis/code_scan.py`의 C/X 계열 룰 10개와 면제 로직을 검증합니다.

**룰별 테스트**

| 룰    | 테스트 수 | 검증 내용                                                                                                                   |
| ----- | :-------: | --------------------------------------------------------------------------------------------------------------------------- |
| C-003 |    14     | eval/new Function/vm.runIn\* 발화, 번들러 폴리필(`return this`) 면제, `require` shim 면제, 동적 입력·연결·변수는 면제 안 됨 |
| C-004 |     3     | 비가시 유니코드 발화, 일반 텍스트 미발화, 소수 비가시 문자 미발화                                                           |
| C-006 |     4     | 알려진 C2 IP 발화, 정상 IP 미발화, publisher 화이트리스트 무관 발화, node_modules 경로도 발화                               |
| C-007 |     7     | AWS/Azure/GCP 메타데이터 자격증명 경로 발화, 정상 인스턴스 메타데이터 면제, 자격증명+인스턴스 동시 포함 시 발화             |
| C-009 |     2     | GitHub secret 검색 쿼리 발화, 정상 GitHub URL 미발화                                                                        |
| C-010 |     2     | Solana wallet 관련 발화, 정상 코드 미발화                                                                                   |
| C-011 |     3     | `.node` native 모듈 발화, 정상 require 미발화, node_modules 경로 미발화(FP 방지)                                            |
| X-001 |     2     | PAT + credential 컨텍스트 발화, PAT 단독 미발화                                                                             |
| X-002 |     4     | OpenAI/AWS 키 발화, 마스킹(EXAMPLE/PLACEHOLDER) 면제                                                                        |
| X-003 |     2     | GCP 서비스 계정 키 발화, 정상 코드 미발화                                                                                   |

**특히 중요한 테스트 그룹**

`test_c007_fires_identity_even_with_instance_path` — 자격증명 경로와 인스턴스 메타데이터 경로가 같은 파일에 있을 때 자격증명은 절대 면제되지 않음을 검증합니다. 보안 설계의 핵심 제약 사항입니다.

`test_c003_fires_even_when_publisher_whitelisted` / `test_c006_fires_even_when_publisher_whitelisted` — 침해된 신뢰 publisher 위협모델을 검증합니다. publisher가 화이트리스트에 있어도 코드 룰(C-003/C-006)은 반드시 발화합니다.

`test_c003_skipped_in_node_modules` / `test_c011_skipped_in_node_modules` — FP 우려 룰(C-003/C-011)은 node_modules 경로에서 면제됩니다. 반면 `test_c006_fires_in_node_modules` / `test_c004_fires_in_node_modules` — 보안 결정적 룰(C-006/C-004)은 node_modules 경로에서도 반드시 발화합니다.

---

### test_corpus_benign.py (3개)

실제 정상 VSCode 확장 5개를 대상으로 Critical 오탐이 없는지 검증하는 회귀 테스트입니다.

| 테스트                                           | 검증 내용                                         |
| ------------------------------------------------ | ------------------------------------------------- |
| `test_benign_no_critical_false_positive`         | 5개 VSIX에서 Critical 발화 0건, 반환 구조 키 검증 |
| `test_python_apiproposals_whitelisted`           | ms-python은 화이트리스트 publisher라 M-002 미발화 |
| `test_eslint_postinstall_is_medium_not_critical` | postinstall(M-005)은 Medium, Critical 아님        |

**주의사항**: `CORPUS_DIR`과 `ABS_CORPUS` 모두 접근 불가한 환경에서는 `pytest.skip`으로 자동 건너뜁니다. CI 환경에서는 항상 skip되며 `test_benign_no_critical_false_positive` 3개가 skip 처리됩니다.

> `ABS_CORPUS = r"D:/SJH_Data/01_Personal/..."` — 개발자 로컬 경로가 하드코딩되어 있습니다. 코드 동작에는 영향 없으나 (없으면 skip), 팀 공유 코퍼스 경로로 교체하거나 환경변수(`VSIX_CORPUS_DIR`)로 외부화하는 것을 권장합니다.

---

### test_runner_glassworm.py (1개)

GlassWorm 캠페인을 모사한 합성 VSIX로 end-to-end 통합 테스트를 수행합니다.

**합성 VSIX 구성**:

- 비가시 유니코드 6자 → C-004 (Critical)
- `eval(decode(p))` → C-003 (Critical)
- 알려진 C2 IP `199.247.10.166` fetch → C-006 (Critical)

**검증 내용**: `run_vscode_static_analysis()` 전체 실행 → Critical 3건 이상 발화 → `suggest_reject=True` 반환.

이 테스트는 룰 엔진 전체를 실제 VSIX 분석 흐름으로 검증하는 유일한 E2E 테스트입니다. 룰 로직을 변경할 때 이 테스트가 깨지면 GlassWorm 수준의 악성 확장을 탐지하지 못할 수 있습니다.

---

## 검토 메모

- 코드 정상. 삭제 금지.
- `pytest` Pylance 오류는 `pip install pytest`로 해결됩니다.
- `test_corpus_benign.py`의 `ABS_CORPUS` 하드코딩 경로 정리 권장 (동작에는 무관).
- 현재 `runner.py`의 manifest + code 통합 흐름에 대한 unit 테스트는 `test_runner_glassworm.py` 1개뿐입니다. 향후 다양한 시나리오의 통합 테스트 추가를 권장합니다.
