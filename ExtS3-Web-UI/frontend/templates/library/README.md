# frontend/templates/library

## library.html

**라우트**: `GET /library` 또는 `GET /library?extName=...`
**인증**: 로그인 필요 (`require_authenticated_page`)

승인 완료(`safe/`) 확장 프로그램 목록 페이지입니다.

**주요 기능**

- `POST /api/nexus/list`로 전체 에셋 조회 → `safe/` 경로만 필터링
- URL 파라미터 `extName`으로 이름 검색 필터 적용 (대소문자 무관)
- 페이지당 10개 페이지네이션
- 업데이트 가능 확장 수 통계 배지
- 각 항목 드롭다운 액션 메뉴:
  - CRX 수동 설치 파일 → `GET /api/nexus/download`
  - 정책 설치 배치 → `POST /api/install-helper/batch`
  - 정책 해제 배치 → `POST /api/install-helper/uninstall-batch`
- 헤더 검색창 Enter 또는 아이콘 클릭 시 `/library?extName=...`으로 이동

**로드 JS**: `common.js`, `library/library.js`
