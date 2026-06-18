# frontend/static/img

프론트엔드에서 사용하는 이미지 파일 폴더입니다.

---

## 파일 구성

### logo.png

사이드바 상단에 표시되는 서비스 로고입니다.
`alt="Suppressor Logo"`, 높이 `h-14` ~ `h-16` 크기로 사용됩니다.

**참조 템플릿 (14곳)**

| 폴더        | 파일                                                                                     |
| ----------- | ---------------------------------------------------------------------------------------- |
| `admin/`    | `admin_dash.html`, `log.html`, `policy.html`, `policy_catalog.html`, `version_diff.html` |
| `library/`  | `library.html`                                                                           |
| `search/`   | `search.html`, `list.html`, `detail/detail.html`, `no_result.html`                       |
| `upload/`   | `build.html`                                                                             |
| `scenario/` | `scenario_id.html`, `scenario_detail.html`                                               |
| (루트)      | `index.html`                                                                             |

---

### dino_frame_02.png ~ dino_frame_05.png (4장)

검색 결과 로딩 중에 표시되는 공룡 스프라이트 애니메이션 프레임입니다.
HTML에서 직접 `<img>`로 사용하지 않고, `common/dino-loader.css`에서 `background-image`로 참조합니다.

- 크기: 248 × 263px, 투명 배경 PNG
- 프레임 순서: `f2 → f3 → f4 → f5` (0.1초 간격, 총 0.4초 루프)
- 참조 위치: `frontend/static/css/common/dino-loader.css`
- 실제 노출 위치: `frontend/templates/search/list.html` (검색 중 로딩 화면)

---
