import argparse
import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional

try:
    from backend.scanners.common import (
        ensure_dict,
        extract_source_entries,
        load_source_map,
        read_json_file,
        summarize_findings,
    )
    from backend.scanners.manifest_behavior_scan import run_manifest_behavior_scan
    from backend.scanners.manifest_permission_scan import run_manifest_permission_scan
    from backend.scanners.code_execution_scan import run_code_execution_scan
    from backend.scanners.code_navigation_scan import run_code_navigation_scan
except ModuleNotFoundError:
    from scanners.common import (
        ensure_dict,
        extract_source_entries,
        load_source_map,
        read_json_file,
        summarize_findings,
    )
    from scanners.manifest_behavior_scan import run_manifest_behavior_scan
    from scanners.manifest_permission_scan import run_manifest_permission_scan
    from scanners.code_execution_scan import run_code_execution_scan
    from scanners.code_navigation_scan import run_code_navigation_scan


JsonDict = Dict[str, Any]


# 정적 스캐너들을 순차 실행하고 결과를 하나로 합치는 메인 러너
def run_static_analysis(report: JsonDict, report_dir: Optional[str] = None, source_json_path: Optional[str] = None) -> JsonDict:
    report = ensure_dict(report, "report")

    # ExtAnalysis source.json을 읽어 코드 스캐너 입력으로 변환
    source_map = load_source_map(report_dir, source_json_path)
    source_entries = extract_source_entries(source_map)

    # 정적 분석 단계별 스캐너 목록
    scanner_results = [
        run_manifest_permission_scan(report),
        run_manifest_behavior_scan(report),
        run_code_execution_scan(report, source_entries),
        run_code_navigation_scan(report, source_entries),
    ]

    findings: List[Dict[str, Any]] = []
    severity_counts: Counter = Counter()
    scanner_summaries: Dict[str, Any] = {}

    # 스캐너별 결과를 통합해 최종 findings/카운트 생성
    for result in scanner_results:
        scanner_name = result["scanner"]
        scanner_summaries[scanner_name] = result["summary"]
        findings.extend(result["findings"])
        severity_counts.update(result["severity_counts"])

    meta = summarize_findings(findings, severity_counts)
    navigation_summary = scanner_summaries.get("code_navigation_scan", {})
    reputation_targets = navigation_summary.get("reputation_targets", [])
    return {
        "program_name": report.get("name", "unknown"),
        "program_version": report.get("version", "unknown"),
        "program_type": report.get("type", "extension"),
        "reputation_targets": reputation_targets,
        "summary": {
            **meta,
            "scanners": scanner_summaries,
        },
        "findings": findings,
        "scan_result": meta["scan_result"],
        "enabled_scanners": [result["scanner"] for result in scanner_results],
    }


# CLI로 단독 실행할 때 사용하는 인자
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run static-only extension analysis.")
    parser.add_argument("--report-file", required=True, help="Path to extanalysis_report.json")
    parser.add_argument("--source-json", help="Optional source.json path. If omitted, inferred from report directory.")
    return parser.parse_args()


# 리포트 파일 하나를 받아 정적 분석 결과를 출력
def main() -> None:
    args = parse_args()
    report = read_json_file(args.report_file)
    report_dir = os.path.dirname(os.path.abspath(args.report_file))
    result = run_static_analysis(report, report_dir=report_dir, source_json_path=args.source_json)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
