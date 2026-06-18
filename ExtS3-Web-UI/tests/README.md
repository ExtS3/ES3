# tests

ExtS3-Web-UI 백엔드 단위 테스트 모음입니다.
외부 네트워크나 DB 없이 `unittest.mock`으로 의존성을 차단해 실행됩니다.

---

## 디렉토리 구조

```
tests/
├── browser/
│   └── test_vscode.py         # VS Code(Open VSX) 검색·다운로드 모듈 검증
└── install_helper/
    └── test_policy_catalog.py # Chrome 그룹 정책 모델·배치 렌더러 검증
```

---

## 전체 실행

```bash
# 레포 루트에서 모든 테스트 한 번에
python -m unittest discover -s tests -p "test_*.py"
```

## 폴더별 실행

```bash
python -m unittest tests.browser.test_vscode
python -m unittest tests.install_helper.test_policy_catalog
```

---

## 테스트 파일별 커버리지

| 테스트 파일                             | 검증 대상 모듈                                                                                                   | 테스트 수 |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | :-------: |
| `browser/test_vscode.py`                | `backend/search/browser/vscode_id.py`<br>`backend/search/browser/vscode_name.py`<br>`backend/download/vscode.py` |   11개    |
| `install_helper/test_policy_catalog.py` | `backend/install_helper/policy_catalog.py`                                                                       |   22개    |

자세한 내용은 각 폴더의 README를 참고하세요.

---

## 테스트 추가 방법

새 테스트 파일은 아래 규칙을 따르면 `discover` 명령으로 자동 수집됩니다.

- 파일명: `test_*.py`
- 클래스: `unittest.TestCase` 상속
- 메서드: `test_` 접두어
- 위치: `tests/` 하위 (폴더 구조는 대상 모듈의 `backend/` 하위 구조와 대응하도록 배치)

```
backend/search/browser/vscode_id.py
  └── tests/browser/test_vscode.py

backend/install_helper/policy_catalog.py
  └── tests/install_helper/test_policy_catalog.py
```

---

## 주의사항

이 폴더는 이름이 `tests`지만 **삭제하면 안 됩니다.** 운영 코드의 동작 계약을 검증하는 실제 테스트입니다.

특히 아래 두 가지는 리팩토링 시 반드시 테스트를 통과해야 합니다.

- `vscode_download()` 반환 파일명 형식(`{ext_id}-{version}.vsix`) — `download_zip.py`의 파일 전송 로직과 정합해야 하는 계약 접점
- `render_extension_settings_batch()` 등 배치 렌더러 — 렌더링 오류 시 Windows 엔드포인트에서 잘못된 정책이 적용될 수 있음
