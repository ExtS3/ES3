# backend/search

확장 프로그램 검색 API를 담당하는 모듈입니다.
`search.py`가 오케스트레이터 역할을 하고, `browser/` 하위 4개 파일이 각 스토어별 크롤러를 담당합니다.

---

## 디렉토리 구조

```
search/
├── search.py          # API 엔드포인트 + 결과 정렬·캐싱·스코어링
└── browser/
    ├── chrome_id.py   # Chrome 웹스토어 ID 기반 상세 조회
    ├── chrome_name.py # Chrome 웹스토어 이름 기반 검색
    ├── vscode_id.py   # Open VSX ID 기반 상세 조회
    └── vscode_name.py # Open VSX 이름 기반 검색
```

---

## search.py

`browser/` 4개 파일을 import해서 조합하는 API 엔드포인트 파일입니다.

**API 엔드포인트**

| 메서드 | 경로               | 설명                                   |
| ------ | ------------------ | -------------------------------------- |
| `POST` | `/api/search_name` | 이름으로 확장 검색 (Chrome / VS Code)  |
| `POST` | `/api/search_id`   | ID로 확장 상세 조회 (Chrome / VS Code) |

요청 파라미터:

| 필드             | 설명                            |
| ---------------- | ------------------------------- |
| `extension_name` | 검색어 (search_name 전용)       |
| `extension_id`   | 확장 ID (search_id 전용)        |
| `browser`        | `"Chrome"` 또는 `"VSCode"`      |
| `limit`          | 최대 결과 수 (기본 20, 최대 80) |

**검색 흐름 (이름 검색 기준)**

```
POST /api/search_name
  │
  ├── Chrome  → chrome_name.search_by_name_async()  → 확장 ID 목록
  └── VSCode  → vscode_name.vscode_search_by_name_async() → 확장 ID 목록
        │
        └── _gather_extension_info()  ← 최대 12개 동시 조회 (Semaphore)
              ├── Chrome → chrome_id.get_extension_info_async()
              └── VSCode → vscode_id.vscode_search_by_id_async()
                    │
                    └── _enrich_result()  ← 스코어 계산 후 정렬
```

**추천 점수 산출 방식 (`_recommendation_score`)**

| 항목             | 최대 점수 | 계산 방식                                            |
| ---------------- | --------- | ---------------------------------------------------- |
| 평점             | 100점     | `rating × 20`                                        |
| 인기도           | 72점      | `log10(users + 1) × 12`                              |
| 최신성           | 18점      | 180일 이내 18점, 365일 12점, 730일 6점, 이후 0점     |
| 검색어 일치      | 45점      | 이름 완전 일치 28점 + 부분 일치 비율 가중            |
| 정보 누락 패널티 | -5점/항목 | name, description, version, logo_url 누락 시 각 -5점 |

**인메모리 캐시**

검색 결과를 TTL 300초(기본값, `SEARCH_CACHE_TTL_SECONDS`로 조정) 동안 캐싱합니다.
캐시 키는 `(검색유형, browser, 검색어, limit)` 조합입니다.

**주요 환경변수**

| 변수명                      | 기본값 | 설명                    |
| --------------------------- | ------ | ----------------------- |
| `SEARCH_CACHE_TTL_SECONDS`  | `300`  | 검색 결과 캐시 TTL (초) |
| `SEARCH_DEFAULT_LIMIT`      | `20`   | 기본 검색 결과 수       |
| `SEARCH_DETAIL_CONCURRENCY` | `12`   | 상세 정보 동시 조회 수  |

---

## browser/ 하위 파일 요약

| 파일             | 대상 스토어     | 동기/비동기   | 설명                             |
| ---------------- | --------------- | ------------- | -------------------------------- |
| `chrome_id.py`   | Chrome 웹스토어 | 동기 + 비동기 | 확장 ID로 상세 페이지 크롤링     |
| `chrome_name.py` | Chrome 웹스토어 | 동기 + 비동기 | 이름 검색으로 ID 목록 추출       |
| `vscode_id.py`   | Open VSX        | 동기 + 비동기 | Open VSX REST API로 ID 조회      |
| `vscode_name.py` | Open VSX        | 동기 + 비동기 | Open VSX 검색 API로 ID 목록 반환 |

자세한 내용은 `browser/README.md` 참고.

---

## 의존 관계

```
main.py
  └── search/search.router

search/search.py
  ├── browser/chrome_id.get_extension_info_async()
  ├── browser/chrome_name.search_by_name_async()
  ├── browser/vscode_id.vscode_search_by_id_async()
  └── browser/vscode_name.vscode_search_by_name_async()

backend/download/chrome.py
  └── browser/chrome_id.get_extension_info()  ← 동기 버전 별도 사용
```
