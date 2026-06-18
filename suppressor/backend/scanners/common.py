import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]
Finding = Dict[str, Any]

# 전 스캐너가 공통으로 사용하는 심각도 우선순위
SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


# 입력 타입을 강제해 스캐너 간 계약을 단순화
def ensure_dict(value: Any, name: str) -> JsonDict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def ensure_list(value: Any, name: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return value


# 외부 입력 심각도를 내부 표준 값으로 정규화
def normalize_severity(severity: str) -> str:
    lowered = str(severity or "").lower()
    return lowered if lowered in SEVERITY_ORDER else "low"


# 모든 스캐너가 동일한 finding 구조를 쓰도록 공통 생성
def add_finding(
    findings: List[Finding],
    severity_counts: Counter,
    severity: str,
    category: str,
    rule_id: str,
    title: str,
    evidence: JsonDict,
    recommendation: str,
) -> None:
    normalized = normalize_severity(severity)
    findings.append(
        {
            "severity": normalized.upper(),
            "category": category,
            "rule_id": rule_id,
            "title": title,
            "evidence": evidence,
            "recommendation": recommendation,
        }
    )
    severity_counts[normalized] += 1


# 리포트/소스 파일 로딩 유틸
def read_json_file(path: str) -> JsonDict:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as file:
            return file.read()
    except OSError:
        return None


# ExtAnalysis 결과 디렉터리에서 source.json 위치를 찾아 로드
def load_source_map(report_dir: Optional[str], explicit_source_json: Optional[str]) -> JsonDict:
    source_json_path = explicit_source_json
    if source_json_path is None and report_dir:
        candidate = os.path.join(report_dir, "source.json")
        if os.path.exists(candidate):
            source_json_path = candidate
    if not source_json_path or not os.path.exists(source_json_path):
        return {}
    return read_json_file(source_json_path)


# source.json을 실제 스캐너가 쓰기 쉬운 엔트리 목록으로 변환
def extract_source_entries(source_map: JsonDict) -> List[JsonDict]:
    entries: List[JsonDict] = []
    for source in source_map.values():
        if not isinstance(source, dict):
            continue
        location = source.get("location")
        entries.append(
            {
                "file_name": str(source.get("file_name", "unknown")),
                "relative_path": str(source.get("relative_path", source.get("file_name", "unknown"))),
                "location": location,
                "content": read_text(location) if isinstance(location, str) else None,
                "retirejs_result": source.get("retirejs_result", []),
            }
        )
    return entries


# 전체 findings를 바탕으로 최종 집계 결과 생성
def summarize_findings(findings: List[Finding], severity_counts: Counter) -> JsonDict:
    highest = "low"
    for finding in findings:
        severity = normalize_severity(finding.get("severity", "low"))
        if SEVERITY_ORDER[severity] > SEVERITY_ORDER[highest]:
            highest = severity
    return {
        "scan_result": {
            "critical": severity_counts["critical"],
            "high": severity_counts["high"],
            "medium": severity_counts["medium"],
            "low": severity_counts["low"],
        },
        "overall_severity": highest.upper(),
        "finding_count": len(findings),
    }
