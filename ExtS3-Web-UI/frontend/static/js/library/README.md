# frontend/static/js/library

승인된 확장 프로그램 라이브러리 페이지 전용 JavaScript 파일 모음입니다.

---

## 파일 구성

### library.js

**대응 템플릿**: `frontend/templates/library/library.html`

`safe/` 경로에 있는 Nexus 에셋 목록을 조회하고 라이브러리 페이지를 렌더링합니다.

**주요 기능**

- `POST /api/nexus/list`로 전체 에셋 조회 → `safe/` 경로만 필터링
- URL 파라미터 `extName`으로 이름 검색 필터 적용 (대소문자 무관, `decodeURIComponent` 처리)
- 페이지당 10개 페이지네이션
- 업데이트 가능 확장 수 통계 배지 표시 (`update_available === true` 카운트)
- 각 항목의 드롭다운 액션 메뉴 (항목 클릭 시 외부 클릭으로 닫힘)

**드롭다운 액션 3가지**

| 버튼               | 동작                                    | API                                        |
| ------------------ | --------------------------------------- | ------------------------------------------ |
| CRX 수동 설치 파일 | Nexus에서 ZIP 파일 직접 다운로드        | `GET /api/nexus/download?path=...`         |
| 정책 설치 배치     | Windows 레지스트리 설치 `.bat` 다운로드 | `POST /api/install-helper/batch`           |
| 정책 해제 배치     | Windows 레지스트리 제거 `.bat` 다운로드 | `POST /api/install-helper/uninstall-batch` |

**Nexus 경로 파싱 규칙**

```
safe/{browser}/{appName}/{version}/{extensionId}.zip
  [0]    [1]       [2]       [3]          [4]
```

---
