# Dynamic_RAG/config

`rag_fingerprint` 모듈이 참조하는 정적 설정 파일 모음입니다.

---

## 파일 구성

### capability_mapping.json

확장 프로그램의 권한·API·진입점을 **능력(capability) 카테고리**로 매핑하는 참조 테이블입니다.
`rag_fingerprint/capability_mapper.py`의 `load_capability_mapping()`이 이 파일을 읽고, `analyzer.py`가 지문 생성 시 호출합니다.

**참조 경로**: `analyzer.py`가 `os.path.join(current_dir, "..", "config", "capability_mapping.json")`으로 상대 경로를 고정 참조합니다. 파일 위치를 변경하면 이 경로도 함께 수정해야 합니다.

**구조 (4개 섹션)**

| 섹션                            | 항목 수 | 설명                                                                                                |
| ------------------------------- | :-----: | --------------------------------------------------------------------------------------------------- |
| `permission_to_capability`      |   13    | `permissions` 선언 → capability 태그 (예: `"tabs"` → `["tab_access"]`)                              |
| `host_permission_to_capability` |    5    | `host_permissions` 와일드카드 패턴 → capability 태그 (예: `"<all_urls>"` → `["broad_page_access"]`) |
| `entrypoint_to_capability`      |    9    | 진입점 유형 → capability 태그 (예: `"content_script"` → `["dom_access", "page_context_access"]`)    |
| `api_to_capability`             |   21    | JS API 호출 → capability 태그 (예: `"fetch"` → `["external_network"]`)                              |

**역할**

분석 대상 확장이 사용하는 권한·API를 추상화된 capability 태그로 변환해 `vector_fingerprint`의 `capability_profile`을 구성합니다. 이 태그들이 임베딩 벡터로 변환되어 벡터 DB의 악성 패턴과 유사도 비교에 사용됩니다.

**수정 시 주의사항**

이 파일을 수정하면 기존 벡터 DB(`embedding/base/`)의 임베딩과 불일치가 생길 수 있습니다. capability 매핑을 변경한 후에는 벡터 DB를 재적재(`POST /api/scenario/reload`)해야 합니다.
