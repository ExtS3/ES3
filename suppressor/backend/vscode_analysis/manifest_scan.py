"""Manifest(package.json) 룰: M-001, M-002, M-004, M-005, M-006."""

from collections import Counter
from typing import Any, Dict, List, Tuple

try:
    from backend.scanners.common import add_finding
    from backend.vscode_analysis.rules import PUBLISHER_WHITELIST, RULE_META
except ModuleNotFoundError:  # pragma: no cover - import shim
    from scanners.common import add_finding
    from vscode_analysis.rules import PUBLISHER_WHITELIST, RULE_META


def _emit(findings, counts, rule_id, evidence):
    severity, category, title, recommendation = RULE_META[rule_id]
    add_finding(findings, counts, severity, category, rule_id, title, evidence, recommendation)


def scan_manifest(manifest: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Counter]:
    """package.json dict를 받아 manifest 룰 findings + severity_counts 반환."""
    findings: List[Dict[str, Any]] = []
    counts: Counter = Counter()

    if not isinstance(manifest, dict):
        return findings, counts

    # M-001: activationEvents에 "*" 단독 포함
    activation = manifest.get("activationEvents")
    if isinstance(activation, list) and "*" in activation:
        _emit(findings, counts, "M-001", {"activationEvents": activation})

    # M-002: enabledApiProposals 사용 ∧ publisher ∉ 화이트리스트
    proposals = manifest.get("enabledApiProposals")
    if isinstance(proposals, list) and len(proposals) > 0:
        publisher = str(manifest.get("publisher", "")).lower()
        if publisher not in PUBLISHER_WHITELIST:
            _emit(findings, counts, "M-002",
                  {"publisher": manifest.get("publisher"), "enabledApiProposals": proposals})

    # M-004: extensionKind 키 부재 ∨ "workspace" 포함
    if "extensionKind" not in manifest:
        _emit(findings, counts, "M-004", {"reason": "extensionKind 키 부재"})
    else:
        kind = manifest.get("extensionKind")
        kinds = kind if isinstance(kind, list) else [kind]
        if "workspace" in kinds:
            _emit(findings, counts, "M-004", {"extensionKind": kind})

    # M-005: scripts.postinstall / scripts.preinstall 존재
    scripts = manifest.get("scripts")
    if isinstance(scripts, dict):
        hooks = {k: scripts[k] for k in ("postinstall", "preinstall") if k in scripts}
        if hooks:
            _emit(findings, counts, "M-005", {"scripts": hooks})

    # M-006: extensionPack 비어있지 않음
    pack = manifest.get("extensionPack")
    if isinstance(pack, list) and len(pack) > 0:
        _emit(findings, counts, "M-006", {"extensionPack": pack})

    return findings, counts
