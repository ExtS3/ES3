# backend/admin/decision

관리자가 확장 프로그램에 대해 승인 또는 거절 결정을 내리는 API 모듈입니다.
결정이 내려지면 Nexus Repository의 파일 위치를 이동·삭제하고, 분석 결과 폴더를 정리합니다.

---

## 파일 구성

### approve.py

확장을 승인할 때 호출됩니다.

**`POST /api/decision/approve`** (`approve_extension` 권한 필요)

```
Nexus: review/{browser}/{name}/{version}/{id}.zip
            ↓ move
       safe/{browser}/{name}/{version}/{id}.zip

analysis_result/review/{browser}/{name}/{version}/{id}/ → 삭제
```

---

### reject.py

확장을 거절할 때 호출됩니다.

**`POST /api/decision/reject`** (`approve_extension` 권한 필요)
**`GET /api/decision/rejects`** — 거절 이력 목록 조회
**`GET /api/decision/rejects/report.pdf`** — 거절 이력 PDF 다운로드

```
Nexus: review/{browser}/{name}/{version}/{id}.zip → 삭제

backend/admin/reject_list.json 에 이력 추가
analysis_result/review/{browser}/{name}/{version}/{id}/ → 삭제
```

`reject_list.json`은 `.gitignore`에 등록된 런타임 파일입니다.

---

### nexus_file.py

`approve.py`와 `reject.py` 양쪽에서 import해서 사용하는 Nexus 연동 유틸 모음입니다.
직접 라우터를 노출하지 않습니다.

주요 함수:

| 함수                                                   | 설명                                                       |
| ------------------------------------------------------ | ---------------------------------------------------------- |
| `build_nexus_path(status, browser, name, version, id)` | `{status}/{browser}/{name}/{version}/{id}.zip` 경로 조립   |
| `fetch_nexus_asset_paths()`                            | Nexus 전체 에셋 경로 목록 조회 (페이지네이션 포함)         |
| `resolve_review_source_path(path)`                     | 요청 경로와 실제 Nexus 경로를 대소문자 무관하게 매칭       |
| `move_nexus_file(src, dst)`                            | GET → PUT → DELETE 순서로 파일 이동                        |
| `delete_nexus_file(path)`                              | Nexus 파일 삭제 (404도 성공 처리)                          |
| `delete_analysis_result_for_review_path(path)`         | `analysis_result/` 내 해당 폴더 삭제                       |
| `append_reject_record(record)`                         | `reject_list.json`에 거절 이력 추가                        |
| `build_reject_report_pdf(records)`                     | 거절 이력 PDF 바이트 생성 (외부 라이브러리 없이 직접 구현) |

---

## 의존 관계

```
main.py
  ├── decision/approve.router
  └── decision/reject.router
        └── nexus_file.py  →  Nexus REST API
                           →  analysis_result/ (로컬 파일시스템)
                           →  backend/admin/reject_list.json
```
