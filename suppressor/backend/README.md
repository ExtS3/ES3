# backend

확장 프로그램 분석의 핵심 로직을 담당하는 모듈입니다. ExtAnalysis 래퍼, 정적 스캐너 통합, ClamAV 연동, 리스크 가중치 계산, 결과 페이로드 구성을 포함합니다.

## 파일 목록

| 파일                         | 역할                                                           |
| ---------------------------- | -------------------------------------------------------------- |
| `extanalysis_integration.py` | ExtAnalysis 실행 래퍼. ZIP 해제·manifest 탐색·VT 우회          |
| `static_analysis.py`         | 4개 스캐너를 순차 실행하고 결과를 통합하는 러너                |
| `risk_scoring.py`            | dynamic/static/obfuscation 결과를 가중 합산해 최종 리스크 계산 |
| `clamav_scan.py`             | ClamAV로 원본 ZIP과 추출 루트 2단계 스캔                       |
| `web_payload.py`             | ExtS3 Web UI 전송용 결과 페이로드 구성                         |
| `scanners/`                  | 4개 개별 정적 스캐너 모듈                                      |

## 주요 함수

### `run_extanalysis_and_static_scan(file_path)` — `extanalysis_integration.py`

전체 정적 분석 파이프라인의 진입점.

1. ZIP/CRX/XPI를 임시 디렉토리에 해제
2. `manifest.json`이 없는 중첩 ZIP 구조도 재귀 탐색으로 확장 루트 발견
3. ExtAnalysis 실행 (VirusTotal/GeoIP/DNS 조회 우회)
4. `source.json` 기반으로 `run_static_analysis` 호출
5. ClamAV 보조 스캔 (`CLAMSCAN_PATH` 설정 시)

반환 구조:

```json
{
  "analysis_id": "EXA000123",
  "static_analysis": { "summary": {...}, "findings": [...], "scan_result": {...} },
  "reputation_targets": [...],
  "clamav": { "status": "clean", "infected": false }
}
```

### `run_static_analysis(report, report_dir, source_json_path)` — `static_analysis.py`

4개 스캐너를 순차 실행하고 findings와 severity_counts를 통합합니다.

```python
scanner_results = [
    run_manifest_permission_scan(report),
    run_manifest_behavior_scan(report),
    run_code_execution_scan(report, source_entries),
    run_code_navigation_scan(report, source_entries),
]
```

CLI 단독 실행:

```bash
python static_analysis.py --report-file extanalysis_report.json
```

### `calculate_weighted_final_risk(...)` — `risk_scoring.py`

3개 분석 결과를 가중 합산해 최종 리스크를 계산합니다.

| 컴포넌트    | 기본 가중치 | 환경 변수                 |
| ----------- | ----------- | ------------------------- |
| dynamic     | 0.65        | `RISK_WEIGHT_DYNAMIC`     |
| static      | 0.20        | `RISK_WEIGHT_STATIC`      |
| obfuscation | 0.15        | `RISK_WEIGHT_OBFUSCATION` |

**에스컬레이션 규칙:**

- dynamic이 HIGH/CRITICAL이면 가중 점수 무시하고 해당 레벨로 승격
- static에 CRITICAL finding 1개 이상이면 최소 HIGH
- obfuscation이 HIGH/CRITICAL이고 dynamic도 MEDIUM+ 이면 최소 HIGH

**판정:**

- 항상 `recommended_decision: "review"` 고정

> suppressor는 위험 신호만 보고하며 최종 승인·거부 정책은 ExtS3-Web-UI가 결정합니다. 이전 버전에서 LOW → approve 동작이 있었으나 현재 코드는 모든 경우에 review를 반환합니다.

## 실행 로그 해석

분석 실행 중 주요 로그 패턴과 의미입니다.

| 로그 패턴                                                  | 의미                                                                                                                                  |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `[✓] manifest.json found at ...`                           | 중첩 ZIP 구조에서 확장 루트를 재귀 탐색으로 발견                                                                                      |
| `[i] source.json not found`                                | ExtAnalysis가 `source.json`을 생성하지 못한 경우. 정적 코드 스캐너(code_execution, code_navigation)가 빈 소스로 실행됨                |
| `[i] Discoverd Permission: management`                     | `manifest.json`에서 권한 탐지. `manifest_permission_scan`에서 위험도 판정                                                             |
| `[+] Found URL: https://...`                               | 패키지 내부 문자열에서 URL 발견. 단독으로 악성 의미는 아님. `code_navigation_scan`의 문맥 분류 후 `reputation_targets` 포함 여부 결정 |
| `[i] Starting virustotal analysis of domains. [SLOW MODE]` | ExtAnalysis 직접 실행 시 나타남. `extanalysis_integration.py`를 통한 정상 경로에서는 VT 조회가 우회됨                                 |

## ClamAV 결과 해석

```json
{ "status": "clean" }
```

시그니처 기반으로 감염 없음.

```json
{ "status": "infected", "infected_files": [...] }
```

알려진 악성 시그니처 매칭. 최종 리스크가 `CRITICAL`로 승격됨.

```json
{ "status": "unavailable" }
```

`CLAMSCAN_PATH` 미설정 또는 바이너리를 찾을 수 없음.

```json
{ "status": "error" }
```

DB 경로 오류, 실행 오류 등. `CLAMAV_DATABASE` 설정 확인 필요.

## 운영 권장 기준

| 리스크     | 권장 조치           |
| ---------- | ------------------- |
| `LOW`      | 자동 승인           |
| `MEDIUM`   | 수동 검토           |
| `HIGH`     | 격리 또는 승인 대기 |
| `CRITICAL` | 차단 우선           |

ClamAV(알려진 시그니처 탐지)와 정적 스캐너(구조·행위 힌트)는 역할이 다르므로 두 결과를 함께 해석해야 합니다.

## scanners/ 모듈

자세한 내용은 [scanners/README.md](scanners/README.md)를 참고하세요.

## 의존 관계

- `ExtAnalysis/` — 패키지 수집기 (외부 라이브러리)
- `ExtAnalysis/db/permissions.json` — 권한 위험도 참조 데이터
- ClamAV 바이너리 (`CLAMSCAN_PATH`)
- 상위 `main.py`에서 `run_extanalysis_and_static_scan` 호출
