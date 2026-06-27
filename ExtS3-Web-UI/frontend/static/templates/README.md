# frontend/static/templates

시나리오 업로드용 양식(템플릿) 파일을 모아둔 폴더입니다.
`/scenario` 페이지의 "양식 보기" 버튼을 누르면 뜨는 모달에서 이 폴더의 파일을 fetch해 미리보고, 다운로드할 수 있습니다.

---

## 파일 구성

### scenario_template.json

시나리오 JSON 업로드 양식입니다.

- 고정 필드(`pattern_name`, `doc_ref`, `vector_fingerprint.manifest_profile`, `capability_profile`, `capability_combinations`, `predicted_flows`, `behavior_tags`)는 빈 값으로 채워져 있어 그대로 입력하면 됩니다.
- `static_code_signals`는 시나리오마다 카테고리/하위 키가 자유롭게 쓰이는 영역입니다(기존 시나리오 25개에서 `dom_query`, `network`, `cookie`, `websocket` 등 37종이 발견됨). 그래서 `dom_query` / `network` / `storage` 3종만 예시로 넣어두고, 필요에 따라 추가하거나 불필요한 항목은 삭제하는 방식으로 설계했습니다.
- `scenario_id`, `builtin` 필드는 포함하지 않습니다. 둘 다 업로드 시 백엔드/suppressor 쪽에서 채워지는 값이라 템플릿에 넣으면 오히려 혼동을 줄 수 있습니다.

**참조 위치**: `frontend/templates/scenario/scenario_id.html`의 `#tpl-download-json`(다운로드 링크), `#tpl-json-content`(미리보기 영역)

---

### scenario_template.md

시나리오 설명 MD 업로드 양식입니다.

- suppressor `embedding/scenario_docs/`의 기존 문서 27개를 비교한 결과, 4 · 5 · 8 · 9 · 10 · 11 · 12번 섹션(안전 테스트 환경 / 허용된 동적 액션 / 관찰 포맷 / 스코어링 가이드 / 안전 중단 조건 / 금지 액션 / 완료 액션)은 거의 모든 문서에서 동일한 고정 boilerplate였습니다. 그래서 이 섹션들은 채워진 상태로 두고 그대로 사용하도록 했습니다.
- 1 · 2 · 3 · 6 · 7 · 13번 섹션(목적 / 매칭된 정적 패턴 / 예상 플로우 / 분석 절차 / 수집할 증거 / 분석가 요약)만 시나리오마다 내용이 달라서, 해당 섹션에는 `<!-- -->` 주석으로 작성 가이드를 남겨뒀습니다.

**참조 위치**: `frontend/templates/scenario/scenario_id.html`의 `#tpl-download-md`(다운로드 링크), `#tpl-md-content`(미리보기 영역)

---

## 참조 현황

| 파일                      | 참조 템플릿                                       |
| ------------------------- | -------------------------------------------------- |
| `scenario_template.json`  | `scenario/scenario_id.html` (양식 보기 모달) |
| `scenario_template.md`    | `scenario/scenario_id.html` (양식 보기 모달) |

> 두 파일 모두 정적 파일로 두는 방식이라 suppressor 서버 상태와 무관하게 항상 접근 가능합니다. 다만 suppressor 쪽 스키마 컨벤션(특히 `static_code_signals` 카테고리)이 바뀌면 이 폴더의 내용도 같이 갱신해야 합니다.
