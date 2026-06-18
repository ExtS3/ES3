# tests/install_helper

`backend/install_helper/policy_catalog.py`의 Pydantic 모델과 배치 스크립트 렌더러를 검증하는 단위 테스트입니다.

---

## 실행 방법

```bash
# 레포 루트에서
python -m unittest tests.install_helper.test_policy_catalog
```

---

## 파일 구성

### test_policy_catalog.py

외부 의존 없이 순수하게 모델 로직과 렌더러 출력을 검증합니다.

**테스트 클래스 6개**

#### `IdValidationTests` — ID 유효성 검사 함수

| 테스트                 | 검증 내용                                                     |
| ---------------------- | ------------------------------------------------------------- |
| `test_valid_id`        | 소문자 a-p, 32자 ID를 유효로 판단 (대소문자 무관)             |
| `test_invalid_id`      | 짧은 ID, 허용 알파벳 외 문자 포함 ID, 빈 문자열을 무효로 판단 |
| `test_wildcard_helper` | `*`와 유효 ID는 통과, 그 외 문자열은 거부                     |

#### `ExtensionSettingsTests` — `ExtensionSettingsRule` / `ExtensionSettingsPolicy`

| 테스트                                         | 검증 내용                                                              |
| ---------------------------------------------- | ---------------------------------------------------------------------- |
| `test_force_installed_uses_default_update_url` | `force_installed` 모드는 `update_url`을 자동 주입                      |
| `test_blocked_mode_omits_update_url`           | `blocked` 모드는 `update_url` 필드 자체를 제외                         |
| `test_override_update_url_only_when_true`      | `override_update_url=True`일 때만 dict에 포함                          |
| `test_permission_lists_passthrough`            | 권한 목록, 호스트 차단 목록이 그대로 전달되는지                        |
| `test_policy_requires_at_least_one_rule`       | rules가 빈 dict이면 Pydantic ValidationError                           |
| `test_policy_rejects_bad_key`                  | 유효하지 않은 ID 또는 `*` 외 와일드카드를 키로 사용 시 ValidationError |
| `test_policy_normalizes_uppercase_id`          | 대문자 ID를 소문자로 정규화해서 저장                                   |
| `test_policy_json_is_sorted_compact`           | JSON 출력이 공백 없이 압축되고 키가 정렬되는지                         |

#### `ForcelistTests` — `ExtensionInstallForcelistPolicy`

| 테스트                         | 검증 내용                                  |
| ------------------------------ | ------------------------------------------ |
| `test_entry_serialization`     | `{id};{update_url}` 형식 직렬화            |
| `test_entry_rejects_bad_id`    | 잘못된 ID로 entry 생성 시 ValidationError  |
| `test_policy_requires_entries` | 빈 목록으로 policy 생성 시 ValidationError |

#### `BlocklistAllowlistTests` — 블록리스트 / 허용 목록 정책

| 테스트                            | 검증 내용                              |
| --------------------------------- | -------------------------------------- |
| `test_blocklist_accepts_wildcard` | blocklist는 `*` 허용                   |
| `test_blocklist_normalizes_case`  | blocklist 항목을 소문자로 정규화       |
| `test_allowlist_rejects_wildcard` | allowlist는 `*` 거부 (ValidationError) |

#### `AllowedTypesTests` — `ExtensionAllowedTypesPolicy`

| 테스트               | 검증 내용                                             |
| -------------------- | ----------------------------------------------------- |
| `test_serialization` | `ExtensionType` 열거형이 문자열 리스트로 직렬화되는지 |

#### `BatchRendererTests` — 배치 스크립트 렌더러 5종

| 테스트                                     | 검증 내용                                                                   |
| ------------------------------------------ | --------------------------------------------------------------------------- |
| `test_extension_settings_batch`            | `ExtensionSettings` 배치에 UAC 체크, 레지스트리 키, `Set-ItemProperty` 포함 |
| `test_forcelist_batch_has_indexed_subkeys` | forcelist는 `\1`, `\2` 번호 서브키로 렌더링                                 |
| `test_blocklist_batch`                     | blocklist 배치 공통 구조 검증                                               |
| `test_allowlist_batch`                     | allowlist 배치 공통 구조 검증                                               |
| `test_allowed_types_batch`                 | allowed_types 배치 공통 구조 검증                                           |
| `test_powershell_escape_single_quote`      | 값 안의 싱글쿼트(`'`)가 PowerShell 이스케이프(`''`)로 처리되는지            |

---

## 이 테스트가 중요한 이유

배치 스크립트는 Windows 엔드포인트의 레지스트리를 직접 수정합니다. 렌더링 오류가 있으면 스크립트 실행 자체가 실패하거나 잘못된 정책이 적용될 수 있습니다.

특히 `test_powershell_escape_single_quote`는 호스트 차단 URL 등에 싱글쿼트가 포함될 경우 PowerShell 구문 오류를 방지하는 이스케이프 처리를 검증합니다. 렌더러를 수정할 때 이 테스트가 깨지면 실제 배포 환경에서 배치 파일이 오동작할 수 있습니다.
