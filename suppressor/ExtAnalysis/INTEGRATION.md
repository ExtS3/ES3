# INTEGRATION.md — suppressor 통합 가이드

이 문서는 ExtAnalysis가 suppressor에 어떻게 통합되어 있는지 설명합니다.
ExtAnalysis 자체에 대한 설명은 `README.md`를 참고하세요.

---

## 통합 개요

suppressor는 ExtAnalysis를 **독립 서버로 실행하지 않고** `core/analyze.py`를 Python 모듈로 직접 import해 사용합니다. Flask 웹 UI, 외부 API 조회(VirusTotal/GeoIP/DNS)는 모두 우회하고 확장 프로그램 코드 수집·분석 기능만 활용합니다.

```
suppressor/backend/extanalysis_integration.py
    └── sys.path에 ExtAnalysis/ 추가
    └── import core.analyze → analyze.analyze(extension_dir)
    └── VT/GeoIP/DNS monkey-patch로 외부 조회 차단
    └── reports/{ID}/extanalysis_report.json 읽기
    └── backend/static_analysis.py에 전달
```

---

## 실제로 사용하는 파일

| 파일/폴더             | 용도                                                                 |
| --------------------- | -------------------------------------------------------------------- |
| `core/analyze.py`     | `analyze(extension_dir)` — 분석 핵심 진입점                          |
| `core/virustotal.py`  | monkey-patching 대상 (외부 VT 조회 우회)                             |
| `core/ip2country.py`  | monkey-patching 대상 (GeoIP 조회 우회)                               |
| `core/` 전체          | `analyze.py`의 내부 의존 모듈                                        |
| `db/permissions.json` | `backend/scanners/manifest_permission_scan.py`가 권한 DB로 직접 참조 |
| `db/geoip.mmdb`       | `core/ip2country.py` 내부 의존                                       |
| `reports/`            | 분석 결과 JSON 저장 경로 (런타임 생성)                               |
| `lab/`                | 확장 프로그램 추출 작업 디렉토리 (런타임 생성)                       |
| `settings.json`       | ExtAnalysis 실행 설정                                                |

---

## 사용하지 않는 파일

suppressor 통합에서 아래 항목들은 참조하지 않습니다.

| 파일/폴더            | 설명                                      |
| -------------------- | ----------------------------------------- |
| `frontend/`          | ExtAnalysis 원본 Flask 웹 UI              |
| `templates/`         | 웹 UI HTML 템플릿                         |
| `static/`            | 웹 UI CSS·JS·이미지                       |
| `extanalysis.py`     | ExtAnalysis 단독 실행 진입점 (Flask 서버) |
| `docker-compose.yml` | ExtAnalysis 자체 독립 실행용              |
| `Dockerfile`         | ExtAnalysis 자체 독립 실행용              |

위 항목들은 삭제해도 suppressor 동작에 영향이 없습니다.

---

## 외부 조회 우회 방식

`extanalysis_integration.py`의 `_disable_extanalysis_reputation_lookups()`가 분석 실행 전에 아래 함수들을 monkey-patch합니다.

| 원본 함수                             | 우회 동작                                |
| ------------------------------------- | ---------------------------------------- |
| `virustotal.domain_batch_scan`        | 모든 도메인을 `{"skipped": True}`로 반환 |
| `virustotal.scan_domain`              | 동일                                     |
| `ip2country.get_country`              | `"country lookup disabled"` 반환         |
| `analyze_module.socket.gethostbyname` | `"unknown"` 반환                         |

분석 완료 후 `finally`에서 원본 함수를 복원합니다. 이 구조 덕분에 suppressor는 VT API 키 없이, 외부 네트워크 없이 ExtAnalysis를 실행할 수 있습니다.

---

## 분석 흐름

```
run_extanalysis_and_static_scan(package_path)
  │
  ├── ZIP/CRX 해제 → manifest.json 위치 탐색
  │     (_prepare_analysis_target, _find_manifest_root)
  │
  ├── run_clamav_bundle_scan()          ← ClamAV 보조 스캔
  │
  ├── _disable_extanalysis_reputation_lookups()
  │     └── core.analyze.analyze(extension_dir)
  │           → ExtAnalysis/reports/{ID}/extanalysis_report.json 생성
  │
  ├── run_static_analysis(report, report_dir)
  │     └── backend/scanners/ 4개 스캐너 실행
  │
  ├── _apply_clamav_result()            ← ClamAV 결과 병합
  │
  └── _save_backend_result()            ← backend/results/ 저장
```

---

## 런타임 생성 디렉토리

아래 두 디렉토리는 런타임에 자동 생성되며 `.gitignore`에 등록되어 있습니다.

| 경로                   | 용도                                                 |
| ---------------------- | ---------------------------------------------------- |
| `ExtAnalysis/reports/` | 분석 결과 JSON 저장 (`{ID}/extanalysis_report.json`) |
| `ExtAnalysis/lab/`     | 확장 프로그램 다운로드·추출 임시 작업 공간           |

---

## settings.json 설정

suppressor 통합 환경에서 유효한 설정 항목입니다.

| 키                       | 기본값 | 설명                                         |
| ------------------------ | ------ | -------------------------------------------- |
| `virustotal_api`         | `""`   | 비워두면 VT 조회가 monkey-patch로 우회됩니다 |
| `results_directory_path` | `""`   | 비워두면 `reports/` 디렉토리 사용            |
| `lab_directory_path`     | `""`   | 비워두면 `lab/` 디렉토리 사용                |
| `ignore_css`             | `true` | CSS 파일 분석 여부                           |
| `extract_comments`       | `true` | 코드 주석 추출 여부                          |
| `extract_base64_strings` | `true` | Base64 문자열 추출 여부                      |
| `extract_ipv4_addresses` | `true` | IPv4 주소 추출 여부                          |

---

## 출처

ExtAnalysis는 [Tuhinshubhra/ExtAnalysis](https://github.com/Tuhinshubhra/ExtAnalysis) (MIT License)를 기반으로 합니다.
