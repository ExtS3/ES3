from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

SEVERITY_KEYS = ("critical", "high", "medium", "low")


def normalize_risk_level(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    low = str(value).strip().lower()
    mapping = {
        "critical": "CRITICAL",
        "high": "HIGH",
        "medium": "MEDIUM",
        "low": "LOW",
        "unknown": "UNKNOWN",
        "inconclusive": "UNKNOWN",
        "치명": "CRITICAL",
        "높음": "HIGH",
        "보통": "MEDIUM",
        "낮음": "LOW",
    }
    return mapping.get(low, "UNKNOWN")


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clip_text(value: object, limit: int = 280) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _extract_severity_counts(value: Any) -> dict:
    d = _safe_dict(value)
    return {k: int(d.get(k, 0) or 0) for k in SEVERITY_KEYS}


def summarize_static_result(static_result: dict) -> dict:
    status = str(static_result.get("status", "skipped")) if isinstance(static_result, dict) else "skipped"
    analysis = _safe_dict(static_result.get("static_analysis")) if isinstance(static_result, dict) else {}
    scan = _safe_dict(analysis.get("scan_result"))
    summary = _safe_dict(analysis.get("summary"))
    findings = _safe_list(analysis.get("findings"))

    key_findings = []
    for f in findings[:8]:
        if not isinstance(f, dict):
            continue
        evidence = f.get("evidence")
        evidence_text = _clip_text(evidence, 220) if not isinstance(evidence, dict) else _clip_text(str(evidence), 220)
        key_findings.append(
            {
                "title": str(f.get("title", "")),
                "severity": normalize_risk_level(f.get("severity")),
                "description": _clip_text(f.get("recommendation") or f.get("category") or "", 220),
                "evidence": evidence_text,
                "file": str(f.get("file") or f.get("path") or ""),
                "line": f.get("line") if isinstance(f.get("line"), int) else None,
            }
        )

    permissions = _safe_list(_safe_dict(analysis.get("manifest_context")).get("permissions"))
    host_permissions = _safe_list(_safe_dict(analysis.get("manifest_context")).get("host_permissions"))
    external_domains = _safe_list(analysis.get("reputation_targets"))

    suspicious_apis: list[str] = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        rule_id = str(f.get("rule_id", "")).lower()
        if "api" in rule_id or "execution" in rule_id or "navigation" in rule_id:
            title = str(f.get("title") or f.get("rule_id") or "")
            if title and title not in suspicious_apis:
                suspicious_apis.append(title)

    severity_counts = _extract_severity_counts(scan)
    overall = normalize_risk_level(summary.get("overall_severity"))

    return {
        "status": status if status in {"success", "error", "skipped"} else "success",
        "summary": _clip_text(
            summary.get("reason")
            or f"Static findings={summary.get('finding_count', len(findings))}, overall={overall}",
            260,
        ),
        "severity_counts": severity_counts,
        "key_findings": key_findings,
        "permissions": [str(x) for x in (permissions + host_permissions)][:30],
        "external_domains": [str(x) for x in external_domains][:20],
        "suspicious_apis": suspicious_apis[:20],
    }


def summarize_obfuscation_result(obfuscation_result: dict) -> dict:
    status = str(obfuscation_result.get("status", "skipped")) if isinstance(obfuscation_result, dict) else "skipped"
    if status in {"error", "skipped"}:
        return {
            "status": status,
            "summary": _clip_text(obfuscation_result.get("message", f"obfuscation {status}"), 260),
            "risk_level": "UNKNOWN" if status == "error" else "LOW",
            "key_indicators": [],
            "obfuscated_files": [],
            "packed_or_minified": False,
        }

    summary = _safe_dict(obfuscation_result.get("summary"))
    files = _safe_list(obfuscation_result.get("files"))
    overall = str(obfuscation_result.get("overall", "")).lower()

    if "likely_malicious" in overall:
        risk = "HIGH"
    elif "suspicious" in overall:
        risk = "MEDIUM"
    elif "minified" in overall:
        risk = "LOW"
    else:
        risk = "UNKNOWN"

    key_indicators = []
    obfuscated_files = []
    packed_or_minified = False

    for row in files[:20]:
        if not isinstance(row, dict):
            continue
        verdict = str(row.get("verdict", "")).lower()
        rel_path = str(row.get("file", ""))
        signals = _safe_list(row.get("suspicious_signals"))
        minify_signals = _safe_list(row.get("minify_signals"))
        if verdict in {"suspicious_obfuscation", "likely_malicious_obfuscation"}:
            obfuscated_files.append(rel_path)
            key_indicators.append(
                {
                    "type": verdict,
                    "severity": "HIGH" if "likely_malicious" in verdict else "MEDIUM",
                    "description": _clip_text("; ".join([str(x) for x in signals[:3]]) or verdict, 220),
                    "evidence": _clip_text("; ".join([str(x) for x in signals[:5]]), 220),
                    "file": rel_path,
                }
            )
        if verdict == "minified_or_bundled":
            packed_or_minified = True
            if minify_signals:
                key_indicators.append(
                    {
                        "type": "minified_or_bundled",
                        "severity": "LOW",
                        "description": _clip_text("; ".join([str(x) for x in minify_signals[:3]]), 220),
                        "evidence": _clip_text("; ".join([str(x) for x in minify_signals[:5]]), 220),
                        "file": rel_path,
                    }
                )

    return {
        "status": "success",
        "summary": _clip_text(
            summary.get("decision_reason")
            or f"overall={obfuscation_result.get('overall', 'unknown')} suspicious={summary.get('suspicious_obfuscation', 0)}",
            260,
        ),
        "risk_level": risk,
        "key_indicators": key_indicators[:12],
        "obfuscated_files": obfuscated_files[:20],
        "packed_or_minified": bool(packed_or_minified),
    }


def summarize_dynamic_result(dynamic_result: dict) -> dict:
    status = str(dynamic_result.get("status", "skipped")) if isinstance(dynamic_result, dict) else "skipped"
    if status in {"error", "skipped"}:
        return {
            "status": status,
            "summary": _clip_text(dynamic_result.get("message") or dynamic_result.get("error") or f"dynamic {status}", 260),
            "risk_level": "UNKNOWN" if status == "error" else "LOW",
            "risk_score": 0.0,
            "matched_scenarios": [],
            "risk_factors": [],
            "runtime_evidence": {
                "network_requests": 0,
                "storage_access": 0,
                "message_events": 0,
                "external_posts": 0,
                "dom_mutations": 0,
            },
            "key_observations": [],
        }

    final_risk = _safe_dict(dynamic_result.get("final_risk"))
    risk_level = normalize_risk_level(final_risk.get("risk_level"))
    risk_score = _to_float(final_risk.get("risk_score"), 0.0)
    matched_scenarios = [str(x) for x in _safe_list(final_risk.get("matched_scenarios"))][:10]
    risk_factors = [str(x) for x in _safe_list(final_risk.get("risk_factors"))][:20]

    scenario_rows = _safe_list(dynamic_result.get("scenario_results_summary"))
    totals = {
        "network_requests": 0,
        "storage_access": 0,
        "message_events": 0,
        "external_posts": 0,
        "dom_mutations": 0,
    }
    observations = []

    for row in scenario_rows[:8]:
        if not isinstance(row, dict):
            continue
        agent = _safe_dict(row.get("agent_result"))
        obs_totals = _safe_dict(agent.get("observation_totals"))
        totals["network_requests"] += int(obs_totals.get("network_requests", 0) or 0)
        totals["storage_access"] += int(obs_totals.get("storage_events", 0) or 0)
        totals["message_events"] += int(obs_totals.get("runtime_messages", 0) or 0)
        totals["external_posts"] += int(obs_totals.get("external_post_count", 0) or 0)
        totals["dom_mutations"] += int(obs_totals.get("dom_events", 0) or 0)

        observations.append(
            {
                "scenario": str(row.get("pattern_name", "")),
                "description": _clip_text(row.get("match_status") or row.get("error") or "dynamic scenario evaluated", 220),
                "evidence": _clip_text("; ".join([str(x) for x in _safe_list(row.get("concrete_api_evidence"))[:4]]), 220),
                "severity": risk_level,
            }
        )

    return {
        "status": "success",
        "summary": _clip_text(final_risk.get("reason") or "Dynamic RAG completed", 260),
        "risk_level": risk_level,
        "risk_score": risk_score,
        "matched_scenarios": matched_scenarios,
        "risk_factors": risk_factors,
        "runtime_evidence": totals,
        "key_observations": observations,
    }


def summarize_rag_result(rag_fingerprint_result: dict, rag_rerank_result: dict) -> dict:
    if not isinstance(rag_fingerprint_result, dict) and not isinstance(rag_rerank_result, dict):
        return {
            "status": "skipped",
            "summary": "RAG skipped",
            "top_patterns": [],
            "fingerprint_summary": {"permissions": [], "apis": [], "hosts": [], "behaviors": []},
        }

    reranked = _safe_list(_safe_dict(rag_rerank_result).get("reranked_matches"))
    top_patterns = []
    for m in reranked[:5]:
        if not isinstance(m, dict):
            continue
        score = _to_float(m.get("final_score"), 0.0)
        top_patterns.append(
            {
                "pattern_name": str(m.get("pattern_name", "")),
                "score": score,
                "threshold_passed": bool(score >= 0.35),
                "evidence": [str(x) for x in _safe_list(m.get("concrete_api_evidence"))[:10]],
            }
        )

    vf = _safe_dict(rag_fingerprint_result.get("vector_fingerprint"))
    manifest = _safe_dict(vf.get("manifest_profile"))
    static = _safe_dict(vf.get("static_code_signals"))
    storage = _safe_dict(static.get("storage"))
    network = _safe_dict(static.get("network"))

    permissions = [str(x) for x in _safe_list(manifest.get("permissions"))][:20]
    hosts = [str(x) for x in _safe_list(manifest.get("host_permissions"))][:20]
    apis = [str(x) for x in _safe_list(storage.get("apis"))[:10]] + [str(x) for x in _safe_list(network.get("apis"))[:10]]
    behaviors = [str(x) for x in _safe_list(vf.get("behavior_tags"))][:20]

    status = "success"
    if _safe_dict(rag_fingerprint_result).get("status") == "error" or _safe_dict(rag_rerank_result).get("status") == "error":
        status = "error"

    return {
        "status": status,
        "summary": _clip_text(
            _safe_dict(rag_rerank_result).get("message")
            or f"top_patterns={len(top_patterns)} behaviors={len(behaviors)}",
            260,
        ),
        "top_patterns": top_patterns,
        "fingerprint_summary": {
            "permissions": permissions,
            "apis": apis[:20],
            "hosts": hosts,
            "behaviors": behaviors,
        },
    }


def infer_recommended_decision(payload: dict) -> str:
    overall = _safe_dict(payload.get("overall"))
    weighted_decision = str(overall.get("recommended_decision", "")).strip().lower()
    if weighted_decision in {"review", "reject"}:
        return weighted_decision

    overall = _safe_dict(payload.get("overall"))
    risk = normalize_risk_level(overall.get("risk_level"))

    if risk in {"CRITICAL", "HIGH", "MEDIUM"}:
        return "review"

    dynamic = _safe_dict(payload.get("dynamic_analysis"))
    dynamic_risk = normalize_risk_level(dynamic.get("risk_level"))
    if dynamic_risk in {"CRITICAL", "HIGH", "MEDIUM"}:
        return "review"

    statuses = [
        _safe_dict(payload.get("static_analysis")).get("status"),
        _safe_dict(payload.get("obfuscation_analysis")).get("status"),
        _safe_dict(payload.get("dynamic_analysis")).get("status"),
        _safe_dict(payload.get("rag_analysis")).get("status"),
    ]
    error_count = sum(1 for s in statuses if s == "error")
    if risk == "UNKNOWN" or error_count >= 2:
        return "review"

    return "review"


def _build_review_fields(payload: dict) -> tuple[list[str], list[str], list[str]]:
    reasons: list[str] = []
    blockers: list[str] = []
    actions: list[str] = []

    overall = _safe_dict(payload.get("overall"))
    risk_level = normalize_risk_level(overall.get("risk_level"))
    component_scores = _safe_dict(overall.get("component_scores"))
    weighted_factors = [str(x) for x in _safe_list(overall.get("risk_factors"))]
    weighted_review = [str(x) for x in _safe_list(overall.get("review_reasons"))]
    weighted_blockers = [str(x) for x in _safe_list(overall.get("approval_blockers"))]

    if risk_level in {"CRITICAL", "HIGH"}:
        blockers.append(f"overall risk level is {risk_level}")
        actions.append("Block publication and require security incident triage.")

    dynamic = _safe_dict(payload.get("dynamic_analysis"))
    runtime = _safe_dict(dynamic.get("runtime_evidence"))
    if int(runtime.get("external_posts", 0) or 0) > 0:
        reasons.append("dynamic analysis observed external POST requests")
        actions.append("Review outbound endpoints and payload contents before approval.")

    static = _safe_dict(payload.get("static_analysis"))
    if int(_safe_dict(static.get("severity_counts")).get("high", 0) or 0) > 0:
        reasons.append("static analysis contains high severity findings")

    obf = _safe_dict(payload.get("obfuscation_analysis"))
    if normalize_risk_level(obf.get("risk_level")) in {"HIGH", "MEDIUM"}:
        reasons.append("obfuscation analysis flagged suspicious patterns")
        actions.append("Perform manual reverse engineering on flagged files.")

    if component_scores:
        reasons.append("weighted scoring used dynamic-first risk model")
    reasons.extend(weighted_factors)
    reasons.extend(weighted_review)
    blockers.extend(weighted_blockers)

    if not reasons:
        reasons.append("no critical blockers detected from summarized signals")
    if not actions:
        actions.append("Proceed with standard approval checklist.")

    return reasons[:10], blockers[:10], actions[:10]


def _browser_to_program_type(browser: str) -> str:
    lowered = str(browser or "").strip().lower()
    mapping = {
        "chrome": "Chrome Extension",
        "edge": "Edge Extension",
        "firefox": "Firefox Extension",
        "opera": "Opera Extension",
    }
    return mapping.get(lowered, f"{browser} Extension" if browser else "Extension")


def build_web_payload(
    *,
    ext_id: str,
    ext_name: str,
    browser: str,
    version: str,
    file_name: str | None,
    static_result: dict,
    obfuscation_result: dict,
    dynamic_result: dict,
    rag_fingerprint_result: dict,
    rag_rerank_result: dict,
    final_risk_summary: dict,
    decision: str | None = None,
) -> dict:
    static_summary = summarize_static_result(static_result)
    obf_summary = summarize_obfuscation_result(obfuscation_result)
    dynamic_summary = summarize_dynamic_result(dynamic_result)
    rag_summary = summarize_rag_result(rag_fingerprint_result, rag_rerank_result)

    sev_counts = _extract_severity_counts(_safe_dict(final_risk_summary).get("scan_result"))
    weighted = _safe_dict(_safe_dict(final_risk_summary).get("weighted_risk"))

    if weighted:
        overall_level = normalize_risk_level(weighted.get("risk_level"))
        overall_score = _to_float(weighted.get("risk_score"), 0.0)
        weighted_decision = str(weighted.get("recommended_decision", "")).strip().lower()
        weighted_reason = str(weighted.get("decision_reason", "")).strip()
        weights = _safe_dict(weighted.get("weights"))
        component_scores = _safe_dict(weighted.get("component_scores"))
        weighted_risk_factors = [str(x) for x in _safe_list(weighted.get("risk_factors"))]
        weighted_review_reasons = [str(x) for x in _safe_list(weighted.get("review_reasons"))]
        weighted_blockers = [str(x) for x in _safe_list(weighted.get("approval_blockers"))]
    else:
        dynamic_risk = normalize_risk_level(dynamic_summary.get("risk_level"))
        if dynamic_risk in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
            overall_level = dynamic_risk
        else:
            if sev_counts["critical"] > 0:
                overall_level = "CRITICAL"
            elif sev_counts["high"] > 0:
                overall_level = "HIGH"
            elif sev_counts["medium"] > 0:
                overall_level = "MEDIUM"
            elif sev_counts["low"] > 0:
                overall_level = "LOW"
            else:
                overall_level = "UNKNOWN"
        overall_score = _to_float(_safe_dict(dynamic_result.get("final_risk") if isinstance(dynamic_result, dict) else {}).get("risk_score"), 0.0)
        weighted_decision = ""
        weighted_reason = ""
        weights = {}
        component_scores = {}
        weighted_risk_factors = []
        weighted_review_reasons = []
        weighted_blockers = []

    now_kst = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")

    payload = {
        "schema_version": "1.0",
        "payload_type": "extension_analysis_summary",
        "analysis_status": "completed",
        "generated_at": now_kst,
        "extension": {
            "extension_id": str(ext_id or ""),
            "name": str(ext_name or ""),
            "browser": str(browser or ""),
            "version": str(version or ""),
            "file_name": str(file_name or ""),
            "program_type": _browser_to_program_type(browser),
        },
        "overall": {
            "risk_level": overall_level,
            "risk_score": overall_score,
            "recommended_decision": "review",
            "decision_reason": weighted_reason,
            "summary": _clip_text(
                _safe_dict(dynamic_result.get("final_risk") if isinstance(dynamic_result, dict) else {}).get("reason")
                or dynamic_summary.get("summary")
                or "analysis completed",
                260,
            ),
            "severity_counts": sev_counts,
            "weights": weights,
            "component_scores": component_scores,
            "risk_factors": weighted_risk_factors,
            "review_reasons": weighted_review_reasons,
            "approval_blockers": weighted_blockers,
        },
        "static_analysis": static_summary,
        "obfuscation_analysis": obf_summary,
        "dynamic_analysis": dynamic_summary,
        "rag_analysis": rag_summary,
        "review": {
            "needs_human_review": True,
            "review_reasons": [],
            "approval_blockers": [],
            "recommended_actions": [],
        },
        "raw_refs": {
            "has_static_raw": bool(static_result),
            "has_obfuscation_raw": bool(obfuscation_result),
            "has_dynamic_raw": bool(dynamic_result),
            "has_rag_raw": bool(rag_fingerprint_result or rag_rerank_result),
        },
    }

    inferred = infer_recommended_decision(payload)
    final_decision = str(decision).strip().lower() if decision else inferred
    if final_decision == "reject":
        final_decision = "review"
    if final_decision != "review":
        final_decision = "review"

    payload["overall"]["recommended_decision"] = final_decision
    if not payload["overall"].get("decision_reason"):
        payload["overall"]["decision_reason"] = "ExtS3 policy determines final approval from the scan risk result."

    review_reasons, blockers, actions = _build_review_fields(payload)
    payload["review"]["needs_human_review"] = True
    payload["review"]["review_reasons"] = review_reasons
    payload["review"]["approval_blockers"] = blockers
    payload["review"]["recommended_actions"] = actions

    return payload
