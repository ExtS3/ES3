# backend/tests

suppressor 백엔드 단위 테스트 모음입니다. **pytest 기반**, 총 88개 테스트.

> 이름이 `tests`지만 잠깐 쓰는 임시 파일이 아닙니다. 운영 코드를 수정하거나 룰을 변경할 때 의도치 않은 동작 변화를 잡아주는 안전망입니다. **삭제하면 안 됩니다.**

---

## 전체 실행

```bash
# 레포 루트에서 전체 한 번에
pytest backend/tests

# 상세 출력
pytest backend/tests -v

# 폴더별 실행
pytest backend/tests/profile
pytest backend/tests/vscode_analysis
```

> pytest가 없으면 `pip install pytest`로 설치합니다. 운영 의존성이 아니라 `requirements.txt`에 추가하지 않아도 됩니다.

---

## 디렉토리 구조

```
backend/tests/
├── profile/                    # backend/profile/ 검증 (22개)
│   ├── conftest.py             # backend/ sys.path 추가
│   └── test_builder.py         # 스냅샷·diff·프로필 조립 전체
│
└── vscode_analysis/            # backend/vscode_analysis/ 검증 (66개)
    ├── conftest.py             # backend/ sys.path 추가
    ├── test_decision.py        # 판정 계약 (4개)
    ├── test_manifest_scan.py   # M 계열 룰 (12개)
    ├── test_code_scan.py       # C/X 계열 룰 + 면제 로직 (46개)
    ├── test_corpus_benign.py   # 정상 확장 오탐 검증 (3개, 코퍼스 없으면 skip)
    └── test_runner_glassworm.py # GlassWorm 합성 VSIX E2E (1개)
```

---

## 폴더별 커버리지

### profile/ — `backend/profile/` 검증

Extension Profile 모듈(버전별 객관적 변경 이력)을 검증합니다.

| 대상                                 | 내용                                                                                                       |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `content_hash`                       | 파일 순서 무관 동일 해시, 내용 변경 시 해시 변경                                                           |
| `is_minified`                        | 긴 단일 줄·디코딩 불가 바이트 → True, 일반 코드·None → False                                               |
| `make_unified_diff`                  | 기본 diff 생성, max_lines 초과 truncation                                                                  |
| `normalize_manifest_state`           | MV2 host_permissions 분리, MV3 permissions 유지                                                            |
| `build_snapshot`                     | 기본 생성, top_dir rerooting, manifest 없는 ZIP → ValueError                                               |
| `compute_diff`                       | 권한·manifest·파일 변경 감지, blob_loader 유무에 따른 인라인/pointer-only 분기, 미니파이 파일 pointer-only |
| `build_profile` + `validate_profile` | 첫 버전 생성·스키마 검증, 두 번째 버전 diff 첨부, ext_id 누락 → ValueError                                 |

자세한 내용은 `profile/README.md` 참고.

### vscode_analysis/ — `backend/vscode_analysis/` 검증

VSCode 확장 Tier1 룰 엔진 전체를 검증합니다.

> **`backend/vscode_analysis/`(운영 코드)** 와 **`backend/tests/vscode_analysis/`(테스트 코드)** 는 완전히 다른 역할입니다. 이름이 같은 것은 테스트가 어떤 모듈을 대상으로 하는지 명확히 하기 위한 Python 표준 관례입니다.

| 대상               | 내용                                                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `decision.py`      | 판정 계약 — `decision`은 항상 `review`, 자동 approve 절대 미생성, fail-closed                                                   |
| `manifest_scan.py` | M-001/002/004/005/006 발화·면제                                                                                                 |
| `code_scan.py`     | C-003/004/006/007/009/010/011 + X-001/002/003 발화·면제. publisher 화이트리스트와 무관한 코드 룰, node_modules 경로별 면제 범위 |
| `runner.py`        | GlassWorm 합성 VSIX E2E — Critical 3건 + `suggest_reject=True`                                                                  |
| 정상 확장 코퍼스   | 5종 VSIX Critical 오탐 0건 (코퍼스 없는 환경에서는 자동 skip)                                                                   |

자세한 내용은 `vscode_analysis/README.md` 참고.

---

## 테스트 추가 방법

- 파일명: `test_*.py`, 함수명: `test_*`
- 위치: 대상 모듈 경로와 동일하게 배치
  - `backend/profile/` → `backend/tests/profile/`
  - `backend/vscode_analysis/` → `backend/tests/vscode_analysis/`
- 새 하위 폴더 생성 시 `conftest.py`로 `backend/`를 `sys.path`에 추가 (기존 conftest.py 참고)

---

## 현재 커버리지 공백

아래 모듈은 테스트가 없습니다. 향후 추가 권장 대상입니다.

| 모듈                                 | 비고                                      |
| ------------------------------------ | ----------------------------------------- |
| `backend/scanners/`                  | 4개 정적 스캐너 + `minify_obfuscation.py` |
| `backend/risk_scoring.py`            | 가중치 기반 리스크 집계                   |
| `backend/extanalysis_integration.py` | ZIP 해제·manifest 탐색                    |
