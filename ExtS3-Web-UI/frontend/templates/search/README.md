# frontend/templates/search

확장 프로그램 검색 흐름 전체를 담당하는 템플릿 모음입니다.
모든 라우트는 로그인 필요 (`require_authenticated_page`).

---

## 파일 구성 및 흐름

```
search.html  →  list.html  →  detail/detail.html
   (탐색)        (결과)           (상세)
                   ↓ 결과 없음
              no_result.html
```

---

### search.html

**라우트**: `GET /search`

브라우저 선택 + 검색어 입력 시작 페이지입니다.

- 브라우저 버튼(Chrome / VSCode) 클릭 → `selectBrow` 변수 저장
- ID 검색 / 이름 검색 토글 (`toggleSearch()`)
- 검색 실행 → `/search_list?extID=...&browser=...` 또는 `/search_list?extName=...&browser=...`

> 브라우저 아이콘을 외부 URL(`lh3.googleusercontent.com`)에서 직접 참조합니다. 네트워크 차단 환경에서는 아이콘이 깨질 수 있습니다. 필요 시 `static/img/`에 로컬 보관을 권장합니다.

**로드 JS**: `common.js`, `search/explore.js`

---

### list.html

**라우트**: `GET /search_list?extID=...&browser=...` 또는 `?extName=...&browser=...`

검색 결과 목록 페이지입니다.

- URL 파라미터로 `POST /api/search_id` 또는 `POST /api/search_name` 호출 (최대 50개)
- 정렬 컨트롤 동적 생성 (추천순 / 사용자순 / 별점순 / 최신순)
- 페이지당 8개 페이지네이션
- 결과 카드 클릭 → `/detail?extID=...&browser=...`
- 검색 중 공룡 로딩 애니메이션 (`dino-loader.css` + `dino_frame_*.png`)

**로드 CSS**: `common/nav.css`, `common/dino-loader.css`
**로드 JS**: `common.js`, `search/list.js`, `upload.js`

---

### no_result.html

**라우트**: `GET /no_result`

검색 결과 없음 페이지입니다.
현재 `list.html`에서 결과가 없을 때 이 페이지로 이동하지 않고 카드 영역에 "검색 결과가 없습니다" 문구를 인라인으로 표시합니다.
별도 JS 없이 정적 UI만 표시합니다.

> 현재 `list.js`에서 직접 참조하지 않아 실제로 라우팅되는 경우가 없습니다. 향후 사용하거나 삭제를 검토하세요.

**로드 JS**: `common.js`

---

### detail/ 폴더

#### detail/detail.html

**라우트**: `GET /detail?extID=...&browser=...` 또는 `?extName=...&browser=...`

확장 프로그램 상세 페이지입니다.

- URL 파라미터로 `POST /api/search_id` 또는 `POST /api/search_name` 호출
- 이름, 로고, 버전, 업데이트, 설명 표시
- 세션에서 `bypass_holding` 권한 확인 → 있으면 "즉시 검사" 버튼 노출
- "검토 요청" → `POST /api/nexus/exists` 확인 후 `POST /api/download_zip`

**로드 JS**: `common.js`, `upload.js`, `search/detail.js`

> `detail/` 폴더 안에 파일이 1개뿐인 구조가 어색하지만, `main.py`의 라우팅 경로가 `search/detail/detail.html`로 하드코딩되어 있어 현재는 이동하지 않는 것을 권장합니다.
