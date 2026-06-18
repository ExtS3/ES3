# backend/search/browser

Chrome 웹스토어와 Open VSX Registry에서 확장 프로그램 정보를 가져오는 크롤러 모음입니다.
각 파일은 동기(`requests`) / 비동기(`httpx`) 버전을 쌍으로 제공합니다.
`search/search.py`의 `_gather_extension_info()`에서 비동기 버전이 병렬 호출됩니다.

---

## 파일 구성

### chrome_id.py

Chrome 웹스토어 상세 페이지를 크롤링해서 확장 정보를 반환합니다.

**대상 URL**: `https://chromewebstore.google.com/detail/{extension_id}?hl=en`

**함수**

| 함수                                             | 설명                                     |
| ------------------------------------------------ | ---------------------------------------- |
| `get_extension_info(extension_id)`               | 동기 버전. `download/chrome.py`에서 사용 |
| `get_extension_info_async(client, extension_id)` | 비동기 버전. `search.py`에서 병렬 호출   |

**반환 구조**

```json
{
  "success": true,
  "data": {
    "id": "확장 ID",
    "name": "확장 이름",
    "logo_url": "아이콘 URL",
    "version": "1.2.3",
    "users": "100K",
    "users_count": 100000,
    "rating": "4.5",
    "rating_value": 4.5,
    "updated": "2024-03-15",
    "last_updated": "2024-03-15",
    "summary": "확장 설명",
    "description": "확장 설명",
    "url": "스토어 URL"
  }
}
```

**파싱 전략 (우선순위 순)**

1. `<h1>` 태그 (이름)
2. `<script type="application/ld+json">` JSON-LD 데이터
3. `<meta>` og/twitter 태그
4. `.QDHp8e` CSS 클래스 기반 상세 필드 파싱 (버전, 업데이트 날짜)
5. 전체 텍스트 정규식 폴백

> Chrome 웹스토어는 HTML 구조가 자주 바뀝니다. CSS 클래스명(`.mN52G`, `.QDHp8e` 등)이 변경되면 파싱이 실패할 수 있습니다. 이 경우 정규식 폴백으로 넘어갑니다.

---

### chrome_name.py

Chrome 웹스토어 검색 페이지를 크롤링해서 확장 ID 목록을 반환합니다.

**대상 URL**: `https://chromewebstore.google.com/search/{검색어}`

**함수**

| 함수                                             | 설명        |
| ------------------------------------------------ | ----------- |
| `search_by_name(extension_name, limit=40)`       | 동기 버전   |
| `search_by_name_async(extension_name, limit=40)` | 비동기 버전 |

**검색 전략 (3단계 폴백)**

1. `httpx` / `requests` 기본 요청 → HTML에서 `/detail/{id}` 패턴으로 ID 추출
2. 결과 부족 시 관련 쿼리 변형(`"{name} extension"`, `"{name} chrome"` 등 6가지) 병렬 추가 검색
3. 환경변수 `CHROME_SEARCH_USE_SELENIUM=true` 설정 시 Selenium 헤드리스 브라우저로 폴백 (스크롤 로드 지원)

**환경변수**

| 변수명                       | 기본값  | 설명                                                   |
| ---------------------------- | ------- | ------------------------------------------------------ |
| `CHROME_SEARCH_USE_SELENIUM` | `false` | `true`로 설정 시 requests 실패 후 Selenium 폴백 활성화 |

> Selenium 폴백을 사용하려면 `chromedriver`가 PATH에 있어야 합니다.

---

### vscode_id.py

Open VSX REST API로 VS Code 확장 상세 정보를 조회합니다.
Chrome 크롤러와 달리 공식 API를 사용하므로 파싱 안정성이 높습니다.

**대상 API**: `https://open-vsx.org/api/{publisher}/{name}/latest`

**함수**

| 함수                                        | 설명        |
| ------------------------------------------- | ----------- |
| `vscode_search_by_id(ext_id)`               | 동기 버전   |
| `vscode_search_by_id_async(client, ext_id)` | 비동기 버전 |

`ext_id` 형식은 `publisher.name` (예: `ms-python.python`)

**반환 구조**는 `chrome_id.py`와 동일한 스키마를 따릅니다.
`timestamp` 필드를 `YYYY-MM-DD` 형식으로 정규화해서 `search.py`의 날짜 파서와 호환합니다.

---

### vscode_name.py

Open VSX 검색 API로 VS Code 확장 ID 목록을 반환합니다.

**대상 API**: `https://open-vsx.org/api/-/search`

**함수**

| 함수                                          | 설명        |
| --------------------------------------------- | ----------- |
| `vscode_search_by_name(query, size=20)`       | 동기 버전   |
| `vscode_search_by_name_async(query, size=20)` | 비동기 버전 |

응답의 `extensions` 배열에서 `{namespace}.{name}` 형태의 ID 목록을 추출해서 반환합니다.

---

## 공통 반환 규칙

모든 파일의 반환 구조는 `search.py`가 `_valid_result()`로 검증합니다.

```python
def _valid_result(info):
    return (
        info.get("success")
        and info.get("data")
        and info["data"].get("name")
        and info["data"]["name"] != "Chrome 웹스토어에 오신 것을 환영합니다"
    )
```

실패 시에는 `{"success": False, "error": "오류 메시지"}`를 반환하며, 예외를 raise하지 않습니다.
`_gather_extension_info()`가 병렬 실행하므로 한 개가 실패해도 다른 결과에 영향을 주지 않습니다.

---

## 의존 관계

```
search/search.py
  ├── chrome_id.get_extension_info_async()    ← 병렬 상세 조회
  ├── chrome_name.search_by_name_async()      ← ID 목록 수집
  ├── vscode_id.vscode_search_by_id_async()   ← 병렬 상세 조회
  └── vscode_name.vscode_search_by_name_async() ← ID 목록 수집

download/chrome.py
  └── chrome_id.get_extension_info()          ← 동기 버전 단독 사용
```
