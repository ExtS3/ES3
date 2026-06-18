# backend/nexus

Nexus Repository와의 연동을 담당하는 모듈입니다.
에셋 목록 조회, 존재 확인, 파일 다운로드, 대시보드 요약 정보를 제공합니다.

---

## 파일 구성

### nexus_repo.py

Nexus REST API 연동 함수와 FastAPI 엔드포인트가 모두 담긴 파일입니다.
동기(`requests`) / 비동기(`httpx`) 버전이 쌍으로 구현돼 있어 호출 컨텍스트에 따라 선택해서 사용합니다.

**주요 환경변수**

| 변수명                              | 설명                                            |
| ----------------------------------- | ----------------------------------------------- |
| `NEXUS_BASE_URL`                    | Nexus 서버 주소 (예: `http://localhost:8081`)   |
| `NEXUS_REPOSITORY`                  | 대상 레포지토리명                               |
| `NEXUS_USERNAME`                    | 인증 사용자명                                   |
| `NEXUS_PASSWORD`                    | 인증 비밀번호                                   |
| `NEXUS_STORAGE_LIMIT_BYTES`         | 스토리지 한도 (blobstore 메트릭 없을 때 폴백값) |
| `NEXUS_DASHBOARD_CACHE_TTL_SECONDS` | 대시보드 캐시 TTL (기본값: `30`초)              |

---

**API 엔드포인트**

| 메서드 | 경로                   | 권한                | 설명                                                                |
| ------ | ---------------------- | ------------------- | ------------------------------------------------------------------- |
| `POST` | `/api/nexus/list`      | `install_extension` | 레포지토리 전체 에셋 목록 반환 (비동기)                             |
| `POST` | `/api/nexus/exists`    | `install_extension` | 특정 확장이 Nexus에 존재하는지 확인 + 상태(`safe`/`review` 등) 반환 |
| `GET`  | `/api/nexus/download`  | `install_extension` | `safe/` 경로의 ZIP 파일 스트리밍 다운로드                           |
| `GET`  | `/api/nexus/dashboard` | 없음                | 에셋 목록 + 스토리지 요약 정보 반환 (30초 캐시)                     |

---

**주요 내부 함수**

| 함수                                      | 설명                                                   |
| ----------------------------------------- | ------------------------------------------------------ |
| `fetch_nexus_assets()` / `_async`         | 전체 에셋 목록 조회 (페이지네이션 자동 처리)           |
| `fetch_nexus_assets_by_name()` / `_async` | 확장 ID로 에셋 검색 (`.zip`, `.vsix` 후보명 병렬 조회) |
| `fetch_nexus_blobstores()` / `_async`     | blobstore 스토리지 사용량 조회                         |
| `build_dashboard_summary()`               | 에셋·blobstore 데이터로 대시보드 요약 JSON 생성        |
| `fetch_dashboard_payload()` / `_async`    | 위 두 데이터를 합쳐 캐시와 함께 반환                   |

**대시보드 요약 구조**

```json
{
  "totalStorageBytes": 1073741824,
  "availableStorageBytes": 536870912,
  "storageLimitBytes": 1610612736,
  "activeRepositoryCount": 12,
  "totalAssetCount": 48,
  "safeAssetCount": 12,
  "extensionActivityPercent": 25
}
```

`safeAssetCount`는 `safe/` 경로에 있는 에셋(승인 완료 확장) 수,
`extensionActivityPercent`는 전체 에셋 중 승인 완료 비율입니다.

---

## Nexus 경로 구조

```
{repository}/
  ├── review/   ← suppressor 분석 대기 중
  ├── safe/     ← 승인 완료, 설치 가능
  └── reject/   ← 거절 처리
       └── {browser}/{extName}/{version}/{extID}.zip
```

`/api/nexus/download`는 `safe/` 경로의 파일만 다운로드 허용합니다.

---

## 의존 관계

```
main.py
  └── nexus/nexus_repo.router

backend/admin/decision/nexus_file.py  ← 승인·거절 시 Nexus 파일 이동·삭제 (별도 구현)
backend/nexus/nexus_repo.py           ← 목록 조회·존재 확인·다운로드·대시보드
```

> `admin/decision/nexus_file.py`와 이 파일은 모두 Nexus를 다루지만 역할이 다릅니다.
> `nexus_file.py`는 파일 이동·삭제 등 쓰기 작업, `nexus_repo.py`는 조회·다운로드 등 읽기 작업을 담당합니다.
