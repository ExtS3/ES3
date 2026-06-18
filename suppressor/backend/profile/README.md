# backend/profile

확장 프로그램의 **버전별 객관적 변경 이력**을 기록하는 모듈입니다.
분석 결과(위험도)가 아니라 "이 확장이 무엇이고 버전 간 무엇이 바뀌었는가"(manifest 사실, 파일 해시·크기, diff)를 저장합니다.

`main.py`의 `/file_scan` 후반부에서 호출되어 이전 버전 대비 변경 사항을 계산하고, 그 결과가 ExtS3-Web-UI의 버전 diff 뷰어(`admin/version_diff.html`)로 전달됩니다.

---

## 파일 구성

```
backend/profile/
├── __init__.py                       # 공개 API export
├── builder.py                        # 스냅샷 생성·diff 계산·프로필 조립
├── local_store.py                    # 프로필·blob 로컬 디스크 저장소
└── extension-profile.schema.json     # 프로필 JSON 스키마 (validate_profile 참조)
```

---

## 공개 API

`__init__.py`가 `builder.py`에서 아래 함수들을 export합니다.

```python
from backend.profile import (
    build_profile,      # 스냅샷을 프로필에 추가 (신규 생성 또는 append)
    build_snapshot,     # 단일 버전의 스냅샷 생성
    compute_diff,       # 두 스냅샷 간 diff 계산
    content_hash,       # 파일 목록의 콘텐츠 해시
    is_minified,        # 미니파이 여부 판별
    make_unified_diff,  # unified diff 텍스트 생성
    validate_profile,   # 프로필 JSON 스키마 검증
)
```

---

## 파일 상세

### builder.py

**스냅샷 생성**

- `build_snapshot(source)` — ZIP 또는 파일 목록에서 한 버전의 스냅샷 생성. manifest 정규화 + 파일별 sha256·크기·미니파이 여부 기록. `(snapshot, file_bytes)` 튜플 반환
- `normalize_manifest_state(manifest)` — manifest를 비교 가능한 정규 형태로 변환 (권한·호스트 권한 정렬 등)
- `content_hash(files)` — 전체 파일 집합의 단일 해시

**diff 계산**

- `compute_diff(prev, curr)` — 두 스냅샷 비교. 권한 델타, manifest 변경, 파일별 변경을 반환
  - 인라인 파일 diff는 양쪽 바이트가 모두 있어야 생성. 현재 버전은 `curr_file_bytes`, 이전 버전은 `blob_loader(sha256)`로 로드
  - 한쪽이라도 바이트가 없으면 해당 파일은 pointer-only(`blob_ref` 있고 `diff=null`)로 degrade
  - **미니파이 파일은 설계상 항상 pointer-only** (diff를 생성하지 않음)
- `make_unified_diff(old, new)` — 텍스트 파일의 unified diff 생성 (최대 라인·바이트 제한 적용)

**프로필 조립**

- `build_profile(curr_snapshot, prev_profile)` — 신규 프로필 생성 또는 기존 프로필에 스냅샷 추가
  - 첫 버전(`prev_profile is None`)이면 `diff_from_previous`가 null이고 `ext_id`를 반드시 전달
  - 이후 버전은 최신 저장 스냅샷 대비 diff를 첨부하고 identity는 이전 프로필에서 승계
- `validate_profile(profile)` — `extension-profile.schema.json`으로 JSON 스키마 검증. 오류 문자열 리스트 반환 (빈 리스트면 유효)

### local_store.py

프로필과 파일 blob의 로컬 디스크 저장소입니다.

| 함수                            | 역할                                                                          |
| ------------------------------- | ----------------------------------------------------------------------------- |
| `load_profile(ext_id)`          | 저장된 프로필 JSON 로드 (없으면 `None`)                                       |
| `save_profile(ext_id, profile)` | 프로필 JSON 저장                                                              |
| `store_blobs(file_bytes)`       | 파일 바이트를 sha256 기준 blob으로 저장 (diff 재구성용)                       |
| `make_blob_loader()`            | sha256 → 바이트를 반환하는 loader 생성. `compute_diff`의 `blob_loader`로 전달 |

저장 경로: `PROFILE_STORE_DIR` 환경변수 (미설정 시 `./profiles/`).
하위에 `profiles/`(JSON)와 `blobs/`(파일 바이트)로 나뉩니다.

### extension-profile.schema.json

`validate_profile()`이 `jsonschema` 라이브러리로 검증할 때 참조하는 Draft 2020-12 JSON 스키마입니다. 프로필 구조 변경 시 함께 갱신해야 합니다.

---

## 동작 흐름 (main.py 호출 순서)

```
새 버전 분석 시 (main.py /file_scan 후반부):
  1. build_snapshot(ZIP 경로) → (snapshot, file_bytes)
  2. store_blobs(file_bytes)          ← 다음 버전 diff를 위해 보관
  3. load_profile(extID)              ← 이전 프로필 (없으면 None)
  4. build_profile(snapshot, prev_profile, blob_loader=make_blob_loader())
       └ 내부에서 compute_diff → 권한·manifest·파일 변경 계산
  5. validate_profile(profile_doc)    ← 스키마 검증 (경고 출력 후 계속)
  6. save_profile(extID, profile_doc)
```

---

## 환경 변수

| 변수                | 기본값       | 설명                       |
| ------------------- | ------------ | -------------------------- |
| `PROFILE_STORE_DIR` | `./profiles` | 프로필·blob 저장 루트 경로 |

`./profiles/`는 `.gitignore`에 등록되어 있습니다.

---

## 테스트

이 모듈의 테스트는 `backend/tests/profile/test_builder.py`에 있습니다 (22개).

---

## 알려진 문제

**`jsonschema` 패키지 누락** — `validate_profile()`은 `import jsonschema`를 실행하지만 `requirements.txt`에 등록되어 있지 않습니다. 환경에 따라 `ImportError`가 발생할 수 있습니다. main.py 호출부는 실패 시 경고만 출력하고 계속 진행하므로 분석 자체가 중단되지는 않지만, `requirements.txt`에 `jsonschema`를 추가하는 것을 권장합니다.
