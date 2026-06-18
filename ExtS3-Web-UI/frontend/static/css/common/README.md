# frontend/static/css/common

전체 페이지에서 공통으로 사용하는 스타일 폴더입니다.

---

## 파일 구성

### nav.css

네비게이션 바와 사이드바의 폰트를 통일하는 공통 스타일입니다.
사실상 **모든 템플릿(21곳)** 에서 참조하는 전역 스타일입니다.

**담당 스타일**

| 셀렉터                       | 설명                                                                              |
| ---------------------------- | --------------------------------------------------------------------------------- |
| `:root` 변수                 | `--exts3-nav-font`, `--exts3-nav-font-size(14px)`, `--exts3-nav-font-weight(600)` |
| `body > header.fixed`        | 상단 고정 헤더 내부 폰트 통일                                                     |
| `body > aside.fixed`         | 사이드바 내부 폰트 통일                                                           |
| `.material-symbols-outlined` | 아이콘 폰트 크기 고정 (20px)                                                      |
| `input::placeholder`         | 검색창 플레이스홀더 굵기 조정                                                     |

레이아웃·색상은 각 템플릿의 인라인 스타일 또는 Tailwind로 처리합니다. 이 파일은 **폰트 일관성**만 담당합니다.

---

### dino-loader.css

검색 결과 로딩 중에 표시되는 공룡 애니메이션 스타일입니다.
현재 `frontend/templates/search/list.html` 한 곳에서 참조하지만, 다른 페이지에서도 재사용 가능한 공통 컴포넌트로 `common/`에 위치합니다.

**동작 방식**

4장의 프레임 이미지(`dino_frame_02~05.png`)를 같은 자리에 겹쳐두고, 매 0.1초마다 한 장씩 즉시 켜고 끄는 방식입니다(`opacity: 0 ↔ 1`). 페이드 없이 즉시 전환되므로 선명한 스프라이트 느낌을 냅니다.

**담당 스타일**

| 클래스                            | 설명                                         |
| --------------------------------- | -------------------------------------------- |
| `.dino-loader`                    | 전체 로더 컨테이너 (중앙 정렬, 패딩)         |
| `.dino-sprite`                    | 프레임 이미지 겹침 영역 (150×128px)          |
| `.dino-frame`                     | 각 프레임 이미지. `f2~f5` 클래스로 구분      |
| `.dino-loading-text`              | 하단 로딩 텍스트                             |
| `.dot`                            | 점 세 개 페이드 애니메이션                   |
| `@keyframes dino-flip`            | 프레임당 25% 구간만 불투명, 나머지 즉시 투명 |
| `@keyframes dino-dot`             | 점 순차 밝아지는 애니메이션                  |
| `@media (prefers-reduced-motion)` | 애니메이션 비선호 시 첫 프레임 정지 표시     |

**사용하는 이미지** (`frontend/static/img/`):
`dino_frame_02.png`, `dino_frame_03.png`, `dino_frame_04.png`, `dino_frame_05.png`

---
