# backend/install_helper

승인된 Chrome 확장을 Windows 엔드포인트에 설치·제거·정책 적용하기 위한 `.bat` 스크립트를 동적으로 생성하는 모듈입니다.
사용자가 라이브러리 페이지에서 다운로드 버튼을 누르면 실행 가능한 배치 파일을 즉시 받을 수 있습니다.

> **Windows 전용**: 생성되는 배치 파일은 Windows 레지스트리(`HKLM\Software\Policies\Google\Chrome`)를 조작하므로 Windows 환경에서만 동작합니다.

---

## 파일 구성

### batch.py

단일 확장 설치·제거용 배치 파일을 생성하는 엔드포인트입니다.

**API**

| 메서드 | 경로                                  | 설명                        |
| ------ | ------------------------------------- | --------------------------- |
| `POST` | `/api/install-helper/batch`           | 설치용 `.bat` 파일 다운로드 |
| `POST` | `/api/install-helper/uninstall-batch` | 제거용 `.bat` 파일 다운로드 |

두 엔드포인트 모두 `install_extension` 권한이 필요합니다.

요청 파라미터:

| 필드           | 설명                                                |
| -------------- | --------------------------------------------------- |
| `extension_id` | Chrome 확장 ID (소문자 영문 32자, `[a-p]{32}` 패턴) |
| `extName`      | 확장 표시 이름 (파일명에 사용, 특수문자 자동 제거)  |

**생성되는 배치 파일 동작 (설치)**

1. UAC 관리자 권한 확인 → 없으면 자동으로 권한 상승 재실행
2. PowerShell로 `HKLM\...\Chrome\ExtensionSettings` 레지스트리 키에 정책 JSON 등록
   ```json
   {
     "<extension_id>": {
       "installation_mode": "normal_installed",
       "update_url": "...",
       "override_update_url": true
     }
   }
   ```
3. Chrome `Preferences` 파일에서 `external_uninstalls` 항목 제거 (이전 제거 마커 클리어)
4. Chrome 프로세스 종료 후 `chrome://extensions` 페이지로 재실행

**생성되는 배치 파일 동작 (제거)**

1. UAC 관리자 권한 확인
2. `ExtensionSettings`에서 해당 확장 항목만 제거 (다른 정책은 보존)
3. Chrome 재시작

---

### policy_catalog.py

Chrome 표준 5종 그룹 정책을 Pydantic 모델로 정의하고 배치 스크립트로 렌더링하는 로직입니다.
`policy_catalog_router.py`에서 import해서 사용합니다.

**지원 정책 5종**

| 정책 타입            | Chrome 정책명               | 설명                                                    |
| -------------------- | --------------------------- | ------------------------------------------------------- |
| `forcelist`          | `ExtensionInstallForcelist` | 지정 확장 강제 설치, 사용자 제거 불가                   |
| `blocklist`          | `ExtensionInstallBlocklist` | 설치 차단 (`*`로 전체 차단 가능)                        |
| `allowlist`          | `ExtensionInstallAllowlist` | blocklist `*` 설정 시 허용 예외 목록                    |
| `extension_settings` | `ExtensionSettings`         | 확장별 세부 정책 (권한 제한, 호스트 차단, 최소 버전 등) |
| `allowed_types`      | `ExtensionAllowedTypes`     | 설치 가능한 확장 타입 제한 (`extension`, `theme` 등)    |

**Pydantic 모델 구조**

```
ExtensionSettingsPolicy
  └── rules: Dict[str, ExtensionSettingsRule]  # 확장 ID 또는 "*" 와일드카드
        └── installation_mode, update_url, blocked_permissions, runtime_blocked_hosts ...

ExtensionInstallForcelistPolicy
  └── entries: List[ExtensionInstallForcelistEntry]  # id + update_url

ExtensionInstallBlocklistPolicy / AllowlistPolicy
  └── entries: List[str]  # 확장 ID 목록 (blocklist는 "*" 허용)

ExtensionAllowedTypesPolicy
  └── types: List[ExtensionType]  # extension, theme, user_script 등
```

레지스트리 등록 방식은 정책 타입에 따라 두 가지로 나뉩니다.

- **문자열 단일 값** (`ExtensionSettings`): JSON 전체를 하나의 REG_SZ 값으로 저장
- **서브키 목록** (나머지 4종): `{PolicyName}\1`, `{PolicyName}\2` 형태의 번호 서브키로 저장

---

### policy_catalog_router.py

정책 카탈로그 REST API 엔드포인트를 정의합니다. 모든 엔드포인트는 `admin` 롤이 필요합니다.

| 메서드 | 경로                                          | 설명                                      |
| ------ | --------------------------------------------- | ----------------------------------------- |
| `GET`  | `/api/install-helper/policy-catalog/types`    | 5종 정책 타입 목록 + 예시 JSON 반환       |
| `POST` | `/api/install-helper/policy-catalog/render`   | 입력 JSON → 배치 스크립트 텍스트 미리보기 |
| `POST` | `/api/install-helper/policy-catalog/download` | 입력 JSON → `.bat` 파일 다운로드          |

요청 body 예시 (`render` / `download` 공통):

```json
{
  "policy_type": "extension_settings",
  "payload": {
    "rules": {
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": {
        "installation_mode": "force_installed",
        "blocked_permissions": ["downloads", "cookies"]
      },
      "*": { "installation_mode": "blocked" }
    }
  }
}
```

---

## 의존 관계

```
main.py
  ├── batch.router                  ← /api/install-helper/batch, /uninstall-batch
  └── policy_catalog_router.router  ← /api/install-helper/policy-catalog/*
        └── policy_catalog.py       ← Pydantic 모델 + 배치 렌더러
```
