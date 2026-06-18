# frontend/static/js/search

확장 프로그램 검색 관련 페이지 전용 JavaScript 파일 모음입니다.

---

## 파일 구성

### explore.js

**대응 템플릿**: `frontend/templates/search/search.html`

검색 시작 페이지(브라우저 선택 + 검색어 입력)의 UI 로직을 담당합니다.

**주요 기능**

- 브라우저 선택 버튼(`Chrome` / `VSCode`) 활성화 상태 관리 → `selectBrow` 전역 변수에 저장
- 검색 방법 토글(`toggleSearch`) — ID 검색 / 이름 검색 버튼의 Tailwind 클래스를 직접 교체해 활성화 표시
- 검색 실행 시 검색 타입에 따라 파라미터 키 분기
  - ID 검색 → `/search_list?extID={value}&browser={browser}`
  - 이름 검색 → `/search_list?extName={value}&browser={browser}`

> `toggleSearch()`는 HTML의 `onclick` 속성에서 직접 호출됩니다.

---

### list.js

**대응 템플릿**: `frontend/templates/search/list.html`

검색 결과 목록 페이지의 렌더링과 정렬을 담당합니다.

**주요 기능**

- URL 파라미터 `extID` 또는 `extName`, `browser`로 API 분기
  - ID → `POST /api/search_id`
  - 이름 → `POST /api/search_name` (최대 50개 요청)
- 정렬 컨트롤 동적 생성 (`ensureSortControls`) — DOM에 없으면 `results-container` 앞에 삽입

**정렬 옵션**

| 키            | 기준                                                     |
| ------------- | -------------------------------------------------------- |
| `recommended` | `recommendation_score` 내림차순 (기본값)                 |
| `users`       | `users_count` 내림차순                                   |
| `rating`      | `rating_value` 내림차순, 동점 시 `users_count` 보조 정렬 |
| `updated`     | `updated_days` 오름차순 (작을수록 최신)                  |

- 페이지당 8개 페이지네이션
- 카드별 카테고리 테마 색상 매핑 (`Productivity`, `Utility`, `Dev Tools`, `Security`, `Analytics`)
- 로고 이미지 로드 실패 시 Google Material Symbol 아이콘으로 폴백

---

### detail.js

**대응 템플릿**: `frontend/templates/search/detail/detail.html`

확장 프로그램 상세 페이지의 조회 및 검토 요청 로직을 담당합니다.

**동작 흐름**

```
DOMContentLoaded
  │
  ├── URL 파라미터 extID 있음 → POST /api/search_id
  └── URL 파라미터 extName 있음 → POST /api/search_name
        │
        └── 상세 정보 렌더링 (이름, 로고, 버전, 업데이트, 설명)
              │
              └── GET /api/auth/session → 권한 확인
                    ├── bypass_holding 권한 있음 → '즉시 검사' 버튼 노출
                    └── 권한 없음 → '즉시 검사' 버튼 숨김
```

**검토 요청 흐름 (`requestExtensionScan`)**

1. `POST /api/nexus/exists`로 Nexus 존재 여부 확인
   - `review` 경로 → "검토 진행 중" 알림 후 중단
   - `safe` 경로 → 라이브러리 페이지로 리다이렉트
   - 미존재 → 다운로드 요청 진행
2. `POST /api/download_zip` 호출
   - `bypass_holding: false` → 홀딩 큐 등록
   - `bypass_holding: true` → 즉시 보안 검사 시작 (confirm 확인 후)

---

## 페이지 흐름

```
search.html (explore.js)
  └── 브라우저 선택 + 검색어 입력
        └── /search_list?extID=... 또는 ?extName=...

list.html (list.js)
  └── 검색 결과 카드 목록
        └── 카드 클릭 → /detail?extID=...&browser=...

detail/detail.html (detail.js)
  └── 상세 정보 + 검토 요청 버튼
        ├── 검토 요청 → POST /api/download_zip (홀딩)
        └── 즉시 검사 → POST /api/download_zip (bypass)
```
