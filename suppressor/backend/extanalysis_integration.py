import json
import os
import re
import sys
import tarfile
import tempfile
import shutil
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

try:
    from backend.clamav_scan import run_clamav_bundle_scan
    from backend.scanners.common import read_json_file
    from backend.static_analysis import run_static_analysis
except ModuleNotFoundError:
    from clamav_scan import run_clamav_bundle_scan
    from scanners.common import read_json_file
    from static_analysis import run_static_analysis


# 프로젝트 내부 ExtAnalysis 디렉터리를 기준으로 통합 실행
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTANALYSIS_ROOT = os.path.join(PROJECT_ROOT, "ExtAnalysis")
EXTANALYSIS_LAB = os.path.join(EXTANALYSIS_ROOT, "lab")
BACKEND_RESULTS_DIR = os.path.join(PROJECT_ROOT, "backend", "results")
ARCHIVE_SUFFIXES = {".zip", ".crx", ".xpi", ".tar", ".gzip", ".tgz", ".tar.gz"}


def _ensure_extanalysis_importable() -> None:
    if EXTANALYSIS_ROOT not in sys.path:
        sys.path.insert(0, EXTANALYSIS_ROOT)


def _parse_analysis_id(result_text: str) -> Optional[str]:
    match = re.search(r"ID:\s*(EXA\d+)", result_text or "")
    if match:
        return match.group(1)
    return None


def _is_archive(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith((".zip", ".crx", ".xpi", ".tar", ".gzip", ".tgz", ".tar.gz"))


def _extract_archive(archive_path: str, destination: str) -> None:
    lowered = archive_path.lower()
    if lowered.endswith((".zip", ".crx", ".xpi")):
        with zipfile.ZipFile(archive_path, "r") as archive:
            archive.extractall(destination)
        return
    if lowered.endswith((".tar", ".gzip", ".tgz", ".tar.gz")):
        with tarfile.open(archive_path) as archive:
            archive.extractall(destination)
        return
    raise ValueError(f"Unsupported archive format: {archive_path}")


def _find_manifest_root(search_root: str) -> str:
    # 중첩 디렉터리 안 manifest.json까지 찾아 실제 확장 루트를 선택한다.
    root_path = Path(search_root)
    candidates = []
    for manifest_path in root_path.rglob("manifest.json"):
        normalized_parts = {part.lower() for part in manifest_path.parts}
        if "__macosx" in normalized_parts or ".git" in normalized_parts or "node_modules" in normalized_parts:
            continue
        relative_parent = manifest_path.parent.relative_to(root_path)
        depth = len(relative_parent.parts)
        candidates.append((depth, len(str(relative_parent)), str(manifest_path.parent)))

    if not candidates:
        raise FileNotFoundError(f"manifest.json not found under extracted archive: {search_root}")

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


@contextmanager
def _prepare_analysis_target(package_path: str) -> Iterator[str]:
    # ZIP/CRX/XPI/TAR는 먼저 풀고, manifest.json이 있는 실제 루트를 찾아 넘긴다.
    if not _is_archive(package_path):
        yield package_path
        return

    temp_extract_dir = tempfile.mkdtemp(prefix="extpkg_", dir=os.path.join(PROJECT_ROOT, "backend", ".tmp"))
    try:
        _extract_archive(package_path, temp_extract_dir)
        manifest_root = _find_manifest_root(temp_extract_dir)
        yield manifest_root
    finally:
        shutil.rmtree(temp_extract_dir, ignore_errors=True)


@contextmanager
def _disable_extanalysis_reputation_lookups() -> Iterator[None]:
    # ExtAnalysis 내부 VT/DNS/GeoIP 조회를 막고, 수집 결과만 사용한다.
    _ensure_extanalysis_importable()
    import core.ip2country as ip2country  # type: ignore
    import core.virustotal as virustotal  # type: ignore
    import core.analyze as analyze_module  # type: ignore

    original_domain_batch_scan = virustotal.domain_batch_scan
    original_scan_domain = virustotal.scan_domain
    original_get_country = ip2country.get_country
    original_dns_lookup = analyze_module.socket.gethostbyname

    def _domain_batch_scan(domains: Any) -> Dict[str, Any]:
        return {
            domain: [True, {"skipped": True, "reason": "reputation lookup disabled in integration"}]
            for domain in domains
        }

    def _scan_domain(domain: str) -> Any:
        return [True, {"skipped": True, "reason": "reputation lookup disabled in integration", "domain": domain}]

    def _get_country(_: str) -> Any:
        return [False, "country lookup disabled in integration"]

    def _dns_lookup(_: str) -> str:
        return "unknown"

    try:
        virustotal.domain_batch_scan = _domain_batch_scan
        virustotal.scan_domain = _scan_domain
        ip2country.get_country = _get_country
        analyze_module.socket.gethostbyname = _dns_lookup
        yield
    finally:
        virustotal.domain_batch_scan = original_domain_batch_scan
        virustotal.scan_domain = original_scan_domain
        ip2country.get_country = original_get_country
        analyze_module.socket.gethostbyname = original_dns_lookup


def _build_reputation_plan(static_result: Dict[str, Any]) -> Dict[str, Any]:
    # 후속 Vato/VT 조회는 정적 분석이 검증한 대상만 사용한다.
    reputation_targets = static_result.get("reputation_targets", [])
    return {
        "enabled": True,
        "status": "pending",
        "target_count": len(reputation_targets),
        "targets": reputation_targets,
    }


def _apply_clamav_result(static_result: Dict[str, Any], clamav_result: Dict[str, Any]) -> Dict[str, Any]:
    # ClamAV 감염 결과를 최종 집계에 반영한다.
    if not clamav_result.get("infected", False):
        return static_result

    findings = static_result.setdefault("findings", [])
    scan_result = static_result.setdefault("scan_result", {"critical": 0, "high": 0, "medium": 0, "low": 0})
    summary = static_result.setdefault("summary", {})

    findings.append(
        {
            "severity": "CRITICAL",
            "category": "clamav",
            "rule_id": "clamav_signature_hit",
            "title": "ClamAV signature hit detected",
            "evidence": {
                "infected_files": clamav_result.get("infected_files", []),
                "status": clamav_result.get("status"),
            },
            "recommendation": "Block the package and review the infected file paths before allowing distribution.",
        }
    )
    scan_result["critical"] = int(scan_result.get("critical", 0) or 0) + 1
    summary["overall_severity"] = "CRITICAL"
    summary["finding_count"] = len(findings)
    scanners = summary.setdefault("scanners", {})
    scanners["clamav_scan"] = {
        "status": clamav_result.get("status"),
        "infected": clamav_result.get("infected"),
        "infected_files": clamav_result.get("infected_files", []),
    }
    return static_result


def _save_backend_result(analysis_id: str, result: Dict[str, Any]) -> str:
    # 최종 통합 결과를 backend/results 아래에 JSON으로 저장한다.
    os.makedirs(BACKEND_RESULTS_DIR, exist_ok=True)
    output_path = os.path.join(BACKEND_RESULTS_DIR, f"{analysis_id}_analysis.json")
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
    return output_path


def run_extanalysis_and_static_scan(package_path: str) -> Dict[str, Any]:
    # ExtAnalysis 모듈을 동적으로 로드해 패키지 분석 실행
    package_path = os.path.abspath(package_path)
    if not os.path.exists(package_path):
        raise FileNotFoundError(f"Package not found: {package_path}")

    _ensure_extanalysis_importable()
    import core.analyze as analyze  # type: ignore

    os.makedirs(EXTANALYSIS_LAB, exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "backend", ".tmp"), exist_ok=True)
    with _prepare_analysis_target(package_path) as analysis_target:
        clamav_result = run_clamav_bundle_scan(package_path, analysis_target)
        with _disable_extanalysis_reputation_lookups():
            analysis_result = analyze.analyze(analysis_target)

    analysis_id = _parse_analysis_id(str(analysis_result))
    if not analysis_id:
        raise RuntimeError(f"ExtAnalysis failed: {analysis_result}")

    report_dir = os.path.join(EXTANALYSIS_ROOT, "reports", analysis_id)
    report_file = os.path.join(report_dir, "extanalysis_report.json")
    source_json = os.path.join(report_dir, "source.json")

    if not os.path.exists(report_file):
        raise RuntimeError(f"ExtAnalysis report not found: {report_file}")

    report = read_json_file(report_file)
    static_result = run_static_analysis(
        report=report,
        report_dir=report_dir,
        source_json_path=source_json if os.path.exists(source_json) else None,
    )
    static_result = _apply_clamav_result(static_result, clamav_result)
    reputation_targets = static_result.get("reputation_targets", [])
    reputation_plan = _build_reputation_plan(static_result)

    result = {
        "analysis_id": analysis_id,
        "report_dir": report_dir,
        "report_file": report_file,
        "source_json": source_json if os.path.exists(source_json) else None,
        "extanalysis_message": str(analysis_result),
        "clamav": clamav_result,
        "reputation_targets": reputation_targets,
        "reputation_plan": reputation_plan,
        "static_analysis": static_result,
    }
    result["backend_result_file"] = _save_backend_result(analysis_id, result)
    return result


def save_upload_to_temp(filename: str, content: bytes) -> str:
    # 업로드 파일을 임시 저장 후 ExtAnalysis에 넘길 실제 경로 생성
    temp_dir = os.path.join(PROJECT_ROOT, "backend", ".tmp")
    os.makedirs(temp_dir, exist_ok=True)
    suffix = os.path.splitext(filename or "")[1] or ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=temp_dir) as tmp:
        tmp.write(content)
        return tmp.name
