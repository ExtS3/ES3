# backend/admin

관리자 전용 기능 전체를 담당하는 패키지입니다.
확장 프로그램 승인·거절, 분석 결과 조회, 정책 설정, 유저·권한 관리를 포함합니다.
모든 엔드포인트는 `admin` 롤 또는 특정 권한(`require_admin` / `require_permission`)을 통해 보호됩니다.

---

## 디렉토리 구조

```
admin/
├── decision/                  # 확장 승인·거절 처리
│   ├── approve.py             # 승인 API → Nexus review → safe 이동
│   ├── reject.py              # 거절 API → Nexus 파일 삭제 + 이력 기록
│   └── nexus_file.py          # Nexus 연동 유틸 (두 파일 공유)
├── infra_cluster.py           # 인프라 클러스터 오염 판정 (BadBlocker 자매 확장 대응)
├── log.py                     # 분석 결과 조회 + PDF 리포트 생성
├── pending.py                 # ⚠️ 비활성 라우터 (main.py에서 주석처리됨)
├── permissions.py             # 유저·롤·권한 CRUD + 회원가입 승인·거절
├── policy.py                  # 자동 정책 설정 + JSON/PDF 다운로드
├── settings.py                # 앱 설정 (Slack 웹훅 URL 저장·조회)
└── policy_settings.json       # 자동 정책 설정값 (런타임 읽기·쓰기)
```

---

## 파일별 역할

### log.py

suppressor가 결과를 전송하면 `recevie_result.py`가 `analysis_result/{decision}/{browser}/{name}/{version}/{id}/` 경로에 JSON 파일들을 저장합니다. `log.py`는 이 경로를 탐색해 읽어서 관리자 대시보드에 제공합니다.

| 메서드 | 경로                 | 설명                   |
| ------ | -------------------- | ---------------------- |
| `POST` | `/api/admin/log`     | 분석 결과 JSON 반환    |
| `POST` | `/api/admin/log/pdf` | 분석 결과 PDF 다운로드 |

읽는 파일: `summary.json`, `dynamic.json`, `static.json`, `obfuscation.json`, `external.json`, `decision_rag_result.json`

---

### permissions.py

유저·롤·권한 CRUD 및 회원가입 요청 처리. 모든 엔드포인트는 `admin` 롤 필요.

| 메서드     | 경로                                                  | 설명                     |
| ---------- | ----------------------------------------------------- | ------------------------ |
| `GET`      | `/api/admin/permissions/users`                        | 유저 목록 (롤·권한 포함) |
| `POST`     | `/api/admin/permissions/users`                        | 유저 직접 생성           |
| `DELETE`   | `/api/admin/permissions/users/{id}`                   | 유저 삭제                |
| `PUT`      | `/api/admin/permissions/users/{id}/permissions`       | 유저 권한 오버라이드     |
| `PUT`      | `/api/admin/permissions/users/{id}/roles`             | 유저 롤 변경             |
| `GET/POST` | `/api/admin/permissions/roles`                        | 롤 조회·생성             |
| `GET`      | `/api/admin/permissions`                              | 전체 권한 목록           |
| `GET`      | `/api/admin/permissions/signup-requests`              | 회원가입 대기 목록       |
| `POST`     | `/api/admin/permissions/signup-requests/{id}/approve` | 회원가입 승인            |
| `POST`     | `/api/admin/permissions/signup-requests/{id}/reject`  | 회원가입 거절            |

---

### policy.py

자동 정책 설정 관리. `recevie_result.py`가 분석 결과 수신 시마다 이 설정을 읽어 자동 판정에 적용합니다.

| 메서드 | 경로                             | 설명                                  |
| ------ | -------------------------------- | ------------------------------------- |
| `GET`  | `/api/admin/policy`              | 현재 정책 조회                        |
| `POST` | `/api/admin/policy`              | 정책 변경                             |
| `GET`  | `/api/admin/policy/default.json` | 현재 정책 JSON 파일 다운로드          |
| `GET`  | `/api/admin/policy/default.pdf`  | 현재 정책 표 형태 PDF 다운로드 (reportlab, Windows 맑은 고딕 사용) |

**정책 설정값** (`policy_settings.json`):

| 키                             | 기본값     | 설명                        |
| ------------------------------ | ---------- | --------------------------- |
| `critical_auto_reject_enabled` | `true`     | CRITICAL 위험도 자동 거절   |
| `low_auto_approve_enabled`     | `false`    | LOW 위험도 자동 승인        |
| `fallback_decision`            | `"review"` | 그 외 기본 판정 (변경 불가) |

---

### settings.py

관리자 앱 설정. 현재는 Slack Incoming Webhook URL 저장·조회만 담당합니다.
사이드바의 "Slack 연동" 버튼(관리자 전용, `common.js`)에서 호출하며, 값은 DB `admin.app_settings` 테이블(키: `slack_webhook_url`)에 저장됩니다.
`backend/ai_judgment/slack.py`가 알림 전송 시 이 값을 우선 사용하고, 없으면 `SLACK_WEBHOOK_URL` 환경변수로 폴백합니다.

| 메서드 | 경로                               | 설명                                  |
| ------ | ---------------------------------- | ------------------------------------- |
| `GET`  | `/api/admin/settings/slack-webhook` | 연동 여부 + 마스킹된 URL 반환         |
| `POST` | `/api/admin/settings/slack-webhook` | 웹훅 URL 저장 (hooks.slack.com 검증) |

---

### decision/

확장 프로그램 승인·거절 처리. 자세한 내용은 `decision/README.md` 참고.

---

### infra_cluster.py

인프라 클러스터 오염 판정. BadBlocker(island.io, 2026-06) 사례 대응 — 거부 이력이 있는
확장과 백엔드 인프라(코드 내 외부 도메인)를 공유하는 확장은 risk_score와 무관하게
자동 승인을 차단하고 수동 review로 강등합니다.

- `record_signals(...)` — `recevie_result.py`가 결과 수신 시마다 확장별 외부 도메인
  (`web_payload.static_analysis.external_domains`)을 `extension_infra.json`에 누적
- `find_cluster_taint(...)` — 거부 기록(`reject_list.json`)과 도메인 조인으로 오염 판정.
  오염 상태를 저장하지 않고 판정 시점에 도출하므로 거부 기록 변경에 자동으로 일관됨
- 공용 CDN·플랫폼 도메인(`BENIGN_DOMAINS` allowlist)은 연관 근거에서 제외
- 오염 시 `summary.json`의 `auto_policy.cluster_taint`에 근거(공유 도메인·상대 확장) 기록,
  자동 승인이던 판정은 `reason: cluster_tainted`로 review 강등

---

### pending.py ⚠️

**현재 비활성 상태.** `main.py`에서 import가 주석처리돼 있고, DB에 `pending_files` 테이블도 없습니다.
활성화하거나 삭제 여부를 결정해야 합니다.

---

## 런타임 생성 파일

| 파일                   | 생성 주체            | 설명                                       |
| ---------------------- | -------------------- | ------------------------------------------ |
| `policy_settings.json` | `policy.py`          | 정책 설정값. Git 추적 O (기본값 관리 목적) |
| `reject_list.json`     | `decision/reject.py` | 거절 이력 누적. `.gitignore` 등록 O        |
| `extension_infra.json` | `infra_cluster.py`   | 확장별 인프라 신호 누적. `.gitignore` 등록 O |

---

## 의존 관계

```
main.py
  ├── admin/log.py              → analysis_result/ (로컬 파일시스템)
  ├── admin/policy.py           → admin/policy_settings.json
  ├── admin/permissions.py      → DB: admin.users / roles / permissions / signup_requests
  ├── admin/settings.py         → DB: admin.app_settings (Slack 웹훅 URL)
  └── admin/decision/
        ├── approve.py          → nexus_file.py → Nexus REST API
        └── reject.py           → nexus_file.py → Nexus REST API
                                → admin/reject_list.json

backend/recevie_result.py       → admin/policy_settings.json (자동 정책 읽기)
                                → admin/decision/nexus_file.py (Nexus 위치 조정)
```
