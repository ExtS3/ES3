# frontend/templates/scenario

시나리오 관리 페이지 템플릿 모음입니다.
모든 라우트는 admin 롤 필요 (`require_admin_page`).

---

## 파일 구성

### scenario_id.html

**라우트**: `GET /scenario`

시나리오 목록 관리 페이지입니다.

**주요 기능**

- vectorDB 상태 배지 (`GET /api/admin/scenario/db-status`)
- 전체 시나리오 목록 테이블 (`GET /api/admin/scenario/list`)
- ID/이름/태그 실시간 검색 필터
- JSON(필수) + MD(선택) 파일 업로드 (`POST /api/admin/scenario/upload`)
- 개별 삭제 (`DELETE /api/admin/scenario/delete/{id}`)
- vectorDB 전체 재적재 (`POST /api/admin/scenario/reload`)
- 기본 제공(`builtin`) 시나리오는 삭제 버튼 비활성화

**로드 JS**: `common.js`, `admin/scenario_id.js`

---

### scenario_detail.html

**라우트**: `GET /scenario/{scenario_id}`

시나리오 상세 페이지입니다.

**특이사항**: `scenario_id`를 Jinja2로 HTML에 직접 주입합니다.

```html
<script>
  window.__SCENARIO_ID__ = '{{ scenario_id }}'
</script>
```

`scenario_detail.js`는 이 전역 변수를 읽어 API를 호출합니다.

**주요 기능**

- `GET /api/admin/scenario/detail/{id}` 상세 조회
- 핑거프린트 4개 섹션 재귀 렌더링 (`manifest_profile` 등)
- MD 문서 인라인 렌더링 (자체 마크다운 파서)
- ID 클립보드 복사 버튼
- 기본 제공 시나리오는 삭제 버튼 숨김

**로드 JS**: `admin/scenario_detail.js`
