from pathlib import Path
from typing import Any

from .utils import load_json


def scan_dnr_rules(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    dnr = manifest.get("declarative_net_request", {}) or {}
    resources = dnr.get("rule_resources", []) or []
    summaries = []
    actions = set()
    for r in resources:
        rel = r.get("path")
        if not rel:
            continue
        path = root / rel
        if not path.exists():
            continue
        try:
            rules = load_json(path)
        except Exception:
            continue
        for rule in rules:
            action_type = ((rule.get("action") or {}).get("type") or "").strip()
            if action_type:
                actions.add(action_type)
            cond = rule.get("condition") or {}
            summaries.append(
                {
                    "action_type": action_type,
                    "url_filter": cond.get("urlFilter"),
                    "regex_filter": cond.get("regexFilter"),
                    "request_domains": cond.get("requestDomains", []),
                    "resource_types": cond.get("resourceTypes", []),
                }
            )
    return {
        "has_dnr": bool(resources),
        "action_types": sorted(actions),
        "rules_summary": summaries,
    }
