# backend/tests/profile

`backend/profile/` 모듈의 단위 테스트입니다. **pytest 기반**으로 총 22개 테스트를 포함합니다.

> 이 폴더는 삭제하면 안 됩니다. Extension Profile의 스냅샷 생성·diff 계산·프로필 조립 로직을 리팩토링할 때 안전망 역할을 합니다.

---

## 실행 방법

```bash
# 레포 루트에서
pytest backend/tests/profile

# 단일 파일
pytest backend/tests/profile/test_builder.py

# 상세 출력
pytest backend/tests/profile -v
```

> pytest가 없으면 `pip install pytest`로 설치합니다. 운영 의존성이 아니라 개발 환경에만 필요하므로 `requirements.txt`에 추가하지 않아도 됩니다.

---

## 파일 구성

### conftest.py

`backend/` 디렉토리를 `sys.path`에 추가해 `from profile.builder import ...` import가 표준 라이브러리의 `profile` 모듈보다 우선 동작하도록 설정합니다.

```python
BACKEND_DIR = .../suppressor/backend/   # ← sys.path에 추가
# 이후 from profile.builder import ... → backend/profile/builder.py 로 해석
```

### test_builder.py

`backend/profile/builder.py`의 공개 함수 전체를 검증합니다 (22개 테스트).

**테스트 그룹별 내용**

| 그룹                                 | 테스트 수 | 검증 내용                                                                                                                                          |
| ------------------------------------ | :-------: | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `content_hash`                       |     2     | 파일 순서 무관 동일 해시, 내용 변경 시 해시 변경                                                                                                   |
| `is_minified`                        |     4     | 긴 단일 줄 → True, 일반 코드 → False, 디코딩 불가 바이트 → True, None → False                                                                      |
| `make_unified_diff`                  |     2     | 기본 diff 생성, max_lines 초과 시 truncated=True                                                                                                   |
| `normalize_manifest_state`           |     2     | MV2 host_permissions 분리, MV3 permissions 그대로 유지                                                                                             |
| `build_snapshot`                     |     3     | 기본 스냅샷 생성, 최상위 디렉토리 제거(rerooting), manifest 없는 ZIP → ValueError                                                                  |
| `compute_diff`                       |     5     | 권한·manifest 변경 감지, 파일 추가·삭제, blob_loader 있을 때 인라인 diff 생성, blob_loader 없을 때 pointer-only, 미니파이 파일은 항상 pointer-only |
| `build_profile` + `validate_profile` |     4     | 첫 버전 프로필 생성 + 스키마 검증 통과, 두 번째 버전 diff 첨부, ext_id 없으면 ValueError, 필수 필드 누락 시 오류 반환                              |

**주요 픽스처**

`_make_zip(tmp_path, name, manifest, files, top_dir)` — pytest의 `tmp_path`를 이용해 테스트용 Chrome 확장 ZIP을 즉석에서 생성합니다. 실제 파일 없이 모든 테스트가 독립적으로 실행됩니다.

**특히 중요한 테스트**

`test_compute_diff_inline_modified_with_blob_loader` — blob_loader가 이전 버전 파일 바이트를 sha256으로 조회해 인라인 unified diff를 생성하는 핵심 경로를 검증합니다. 이 테스트가 깨지면 버전 diff 뷰어에 표시되는 코드 변경 내역이 올바르지 않을 수 있습니다.

`test_build_profile_second_version_attaches_diff` — 두 버전에 걸친 전체 흐름(스냅샷 → diff → 프로필 조립 → 스키마 검증)을 end-to-end로 검증하는 통합 테스트입니다.

---

## 검토 메모

- 코드 정상. 삭제 금지.
- `pytest` Pylance 오류(`가져오기 "pytest"을(를) 확인할 수 없습니다`)는 코드 문제가 아닙니다. VS Code 인터프리터에 pytest가 설치되어 있지 않아서 발생합니다. `pip install pytest`로 해결됩니다.
- 현재 `local_store.py`(디스크 저장/로드)에 대한 테스트는 없습니다. 향후 커버리지 확대 시 추가 권장 대상입니다.
