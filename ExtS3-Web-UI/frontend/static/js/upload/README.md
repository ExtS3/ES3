# frontend/static/js/upload

확장 프로그램 직접 업로드 페이지 전용 JavaScript 파일입니다.

---

## 파일 구성

### build.js

**대응 템플릿**: `frontend/templates/upload/build.html`

ZIP/VSIX 파일을 직접 업로드해 보안 분석을 요청하는 페이지의 전체 로직을 담당합니다.

**업로드 모드 2가지**

| 모드     | 설명                                                                                  |
| -------- | ------------------------------------------------------------------------------------- |
| `first`  | 신규 확장 첫 업로드. 버전 자동 `1.0.0` 설정. 확장 이름 직접 입력                      |
| `update` | 기존 확장 버전 업. 내 업로드 목록(`GET /api/uploads/mine`)에서 선택. 버전 자동 1 증가 |

**업로드 실행 흐름**

```
buildBtn 클릭
  │
  ├── 파일 미선택 → 경고 모달
  │
  └── 업로드 확인 모달
        │
        └── POST /api/uploads/resolve   ← 이름 중복·소유권 검증 + 버전 확정
              │
              ├── POST /api/security_scan/file_save  ← scan_pending/ 임시 저장
              │
              └── POST /api/send_suppressor          ← suppressor 보안 분석 전송
                    │
                    ├── 성공 → 완료 모달 → /로 이동
                    └── 실패 → 오류 모달
```

두 번의 POST(`file_save` → `send_suppressor`)에 **동일한 `FormData`를 재사용**합니다.
`FormData`는 스트림이 아니라 재사용 가능한 객체이므로 정상 동작합니다.

**`update` 모드 선택 시 자동 채움**

`extSelect`에서 확장을 선택하면 `myExtensions` 배열에서 찾아 이름·버전·브라우저를 자동으로 입력 필드에 채웁니다. 이름 필드는 `readOnly`로 잠깁니다.

**커스텀 모달 (`showCustomConfirm`)**

Promise 기반 확인 다이얼로그입니다. `admin_pending.js`의 것과 동일한 구현이지만 `showCancel` 옵션이 추가됐습니다. `showCancel: false`로 호출하면 취소 버튼이 숨겨져 확인 전용 알림으로 사용할 수 있습니다.

> `admin_pending.js`와 동일한 패턴의 커스텀 모달이 각자 독립 구현돼 있습니다. 향후 `js/common/modal.js` 같은 공통 파일로 추출하면 유지보수가 쉬워집니다.

---

## 주의사항

**`response` 상태 확인 순서**

현재 코드에서 `scan_file`(send_suppressor) 응답을 먼저 확인하고, `response`(file_save) 응답을 나중에 확인합니다. 그런데 `response.json()`은 이미 두 번째 fetch 이후에 호출되는 구조라 `response` body 스트림이 아직 열려있어야 합니다. `FormData` 재사용과 마찬가지로 현재는 정상 동작하지만, 향후 fetch 순서를 변경할 경우 주의가 필요합니다.
