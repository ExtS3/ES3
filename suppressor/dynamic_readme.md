# suppressor

Chrome 확장 프로그램의 동적 분석 도구입니다.

## 기능

- Chrome 확장 프로그램 ZIP 파일을 로드하여 실제 실행 중 의심스러운 동작을 감지합니다.
- 네트워크 요청, DOM 조작, 스토리지 변조 등 다양한 위협을 탐지합니다.
- 각 단계별로 위험도를 평가하고 최종 위험 점수를 산출합니다.

## 설치

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

## 사용 방법

### 단일 파일 스캔
```bash
python3 main.py scan extension.zip
```

### 옵션
- `--headed`: 브라우저 창 표시
- `--verbose`: 상세 로그 출력
- `--debug-log 파일`: 로그 저장
- `--json-log 파일`: JSON 로그 저장

## 출력 예시

```json
{
  "extension_name": "Example",
  "extension_version": "1.0.0",
  "overall_risk": "high",
  "stages": [
    {
      "name": "runtime_network",
      "risk": "medium",
      "summary": "외부 요청 감지됨",
      "evidence": ["https://suspicious.com"],
      "metrics": {"requests": 2}
    }
  ]
}
```

## 프로젝트 구조

- `main.py`: CLI 인터페이스
- `dynamic_analysis/`: 분석 엔진
  - `scanner.py`: 핵심 분석 로직
  - `models.py`: 데이터 모델
  - `risk.py`: 위험 평가
- `tests/`: 단위 테스트
- `uBOL-home-main/`: uBlock Origin 리소스

# 결과 확인
print(f"확장명: {result.extension_name}")
print(f"버전: {result.extension_version}")
print(f"전체 위험도: {result.overall_risk.label()}")

# 각 단계의 상세 정보
for stage in result.stages:
    print(f"\n[{stage.name.upper()}] {stage.risk.label()}")
    print(f"  설명: {stage.summary}")
    for evidence in stage.evidence:
        print(f"  증거: {evidence}")
```

### JSON 결과 처리

```bash
# 결과를 파일에 저장
python3 main.py scan extension.zip > analysis.json

# 결과 필터링 (jq 필요)
cat analysis.json | jq '.stages[] | select(.risk == "high")'
```

## 테스트

```bash
# 모든 테스트 실행
python3 -m pytest tests/ -v

# 특정 테스트만 실행
python3 -m pytest tests/test_scanner.py -v
```

## 설계 원칙

이 프로젝트는 다음 원칙을 따릅니다:

1. **탐지 품질 우선**: 미적 리팩토링보다 탐지 정확도를 우선
2. **증거 기반**: 모호한 휴리스틱보다 명확한 증거 선호
3. **반복 개선**: 검사 → 실행 → 평가 → 수정 → 재실행 사이클 준수
4. **명확한 로깅**: 사용자가 왜 특정 위험도가 부여되었는지 이해 가능해야 함
5. **모듈화된 설계**: 새로운 단계나 규칙 추가가 용이한 구조

## 제한사항 및 주의사항

- **정적 분석 보완**: 이 도구는 동적 분석만 수행하며, 정적 코드 분석을 대체하지 않습니다
- **런타임 환경**: 분석 환경이 실제 사용 환경과 다를 수 있습니다
- **시간 제약**: 각 확장은 제한된 시간 내에 분석되므로 모든 코드 경로를 실행하지 않을 수 있습니다
- **위험도 확률적**: 위인도 평가는 확률적이며, 위음성/위양성이 존재할 수 있습니다

## 라이센스

이 프로젝트는 교육 및 보안 연구 목적으로 개발되었습니다.

## 기여

버그 보고나 개선사항은 이슈로 등록해주세요.
