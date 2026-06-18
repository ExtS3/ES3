"""VSCode 정적 분석 진입점.

run_vscode_static_analysis(vsix_path):
  VSIX(zip) 해제 -> extension/package.json -> 소스 순회 -> manifest+code 룰 합산
  -> run_static_analysis와 동일한 반환 키 구조 + decision 첨부.
파싱/해제 실패 시 status="error" 형태 반환 (raise 금지).
"""

import json
import re
import zipfile
from collections import Counter
from typing import Any, Dict, List

try:
    from backend.scanners.common import summarize_findings
    from backend.vscode_analysis import decision as decision_mod
    from backend.vscode_analysis.manifest_scan import scan_manifest
    from backend.vscode_analysis.code_scan import scan_sources
    from backend.vscode_analysis.rules import PUBLISHER_WHITELIST
except ModuleNotFoundError:  # pragma: no cover - import shim
    from scanners.common import summarize_findings
    from vscode_analysis import decision as decision_mod
    from vscode_analysis.manifest_scan import scan_manifest
    from vscode_analysis.code_scan import scan_sources
    from vscode_analysis.rules import PUBLISHER_WHITELIST


SOURCE_EXT = re.compile(r"\.(js|ts|cjs|mjs)$", re.IGNORECASE)
# 시크릿(X 룰)은 더 넓은 파일을 대상으로 (카탈로그 X 룰: .json/.map/.md 등 포함)
SECRET_EXT = re.compile(r"\.(js|ts|cjs|mjs|json|map|md|env)$", re.IGNORECASE)
MAX_FILE_BYTES = 5 * 1024 * 1024  # 파일당 5MB 상한 (zip bomb/거대 번들 방어)


def _error_result(message: str) -> Dict[str, Any]:
    empty = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    return {
        "program_name": "unknown",
        "program_version": "unknown",
        "program_type": "vscode-extension",
        "reputation_targets": [],
        "summary": {
            "scan_result": empty,
            "overall_severity": "LOW",
            "finding_count": 0,
            "scanners": {},
        },
        "findings": [],
        "scan_result": empty,
        "enabled_scanners": ["vscode_manifest_scan", "vscode_code_scan"],
        "status": "error",
        "error": message,
        "decision": decision_mod.decide(empty, status="error"),
    }


def _read_manifest(zf: zipfile.ZipFile) -> Dict[str, Any]:
    try:
        raw = zf.read("extension/package.json")
    except KeyError:
        return {}
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        return {}


def _collect_sources(zf: zipfile.ZipFile) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for info in zf.infolist():
        name = info.filename
        if info.is_dir():
            continue
        if not (SOURCE_EXT.search(name) or SECRET_EXT.search(name)):
            continue
        if info.file_size > MAX_FILE_BYTES:
            continue
        try:
            raw = zf.read(name)
        except (KeyError, zipfile.BadZipFile, OSError):
            continue
        entries.append({
            "file_name": name,
            "content": raw.decode("utf-8", errors="replace"),
        })
    return entries


def run_vscode_static_analysis(vsix_path: str) -> Dict[str, Any]:
    try:
        zf = zipfile.ZipFile(vsix_path)
    except (zipfile.BadZipFile, FileNotFoundError, OSError) as exc:
        return _error_result(f"VSIX 열기 실패: {exc}")

    try:
        with zf:
            manifest = _read_manifest(zf)
            sources = _collect_sources(zf)
    except (zipfile.BadZipFile, OSError) as exc:
        return _error_result(f"VSIX 해제 실패: {exc}")

    findings: List[Dict[str, Any]] = []
    severity_counts: Counter = Counter()

    m_findings, m_counts = scan_manifest(manifest)
    findings.extend(m_findings)
    severity_counts.update(m_counts)

    publisher = str(manifest.get("publisher", "")).lower()
    whitelisted = publisher in PUBLISHER_WHITELIST
    c_findings, c_counts = scan_sources(sources, publisher_whitelisted=whitelisted)
    findings.extend(c_findings)
    severity_counts.update(c_counts)

    meta = summarize_findings(findings, severity_counts)
    scan_result = meta["scan_result"]

    return {
        "program_name": manifest.get("name", "unknown"),
        "program_version": manifest.get("version", "unknown"),
        "program_type": "vscode-extension",
        "reputation_targets": [],
        "summary": {
            **meta,
            "scanners": {
                "vscode_manifest_scan": {"finding_count": len(m_findings)},
                "vscode_code_scan": {
                    "finding_count": len(c_findings),
                    "source_files_scanned": len(sources),
                },
            },
        },
        "findings": findings,
        "scan_result": scan_result,
        "enabled_scanners": ["vscode_manifest_scan", "vscode_code_scan"],
        "status": "ok",
        "decision": decision_mod.decide(scan_result, status="ok"),
    }
