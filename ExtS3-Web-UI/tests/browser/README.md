# tests/browser

`backend/search/browser/` 및 `backend/download/` 의 VS Code(Open VSX) 관련 모듈을 검증하는 단위 테스트입니다.

---

## 실행 방법

```bash
# 레포 루트에서
python -m unittest tests.browser.test_vscode
```

---

## 파일 구성

### test_vscode.py

외부 HTTP 요청은 `unittest.mock.patch`로 차단하고, 실제 네트워크 없이 실행됩니다.

**테스트 클래스 3개**

#### `VscodeIdTest` — `vscode_id.vscode_search_by_id()`

| 테스트                                    | 검증 내용                                                                                                      |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `test_success_returns_dict_with_12_keys`  | 성공 시 `success=True`이고 반환 dict가 Chrome 크롤러와 동일한 12개 키를 가지는지                               |
| `test_normalization_mapping`              | Open VSX 응답 필드 → 내부 스키마 정규화 (displayName→name, downloadCount→users_count, timestamp→YYYY-MM-DD 등) |
| `test_failure_returns_dict_not_none`      | 네트워크 오류 시 예외를 raise하지 않고 `{success: False, error: ...}` dict 반환                                |
| `test_malformed_id_returns_dict_not_none` | `.` 없는 잘못된 ID 입력 시에도 dict 반환 (크래시 없음)                                                         |

#### `VscodeNameTest` — `vscode_name.vscode_search_by_name()`

| 테스트                            | 검증 내용                                                            |
| --------------------------------- | -------------------------------------------------------------------- |
| `test_returns_list_of_id_strings` | `{namespace}.{name}` 형태의 ID 목록 반환, namespace 없는 항목은 스킵 |
| `test_failure_returns_empty_list` | 오류 시 빈 리스트 반환 (예외 없음)                                   |

#### `VscodeDownloadTest` — `vscode.vscode_download()`

| 테스트                                            | 검증 내용                                                                           |
| ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `test_success_path_and_filename_contract`         | 반환 경로가 `{ext_id}-{version}.vsix` 형식인지, 호출된 Open VSX URL 포맷이 정확한지 |
| `test_falsy_version_returns_none_without_request` | `version=None`이면 HTTP 요청 없이 `None` 반환                                       |
| `test_failure_returns_none`                       | 다운로드 실패 시 `None` 반환                                                        |
| `test_malformed_id_returns_none`                  | `.` 없는 잘못된 ID 입력 시 `None` 반환                                              |

---

## 이 테스트가 중요한 이유

`test_success_path_and_filename_contract`는 단순 동작 확인을 넘어 **계약 접점**을 검증합니다.

`vscode_download()`의 반환 파일명(`{ext_id}-{version}.vsix`)은 `download_zip.py`에서 suppressor로 전송할 때 그대로 사용됩니다. 이 형식이 바뀌면 파일 전송이 조용히 깨질 수 있어, 리팩토링 시 이 테스트가 깨지면 반드시 `download_zip.py`도 함께 확인해야 합니다.
