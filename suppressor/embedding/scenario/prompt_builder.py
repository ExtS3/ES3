from __future__ import annotations

import json
import logging
import re
from typing import Any

from .action_schema import get_allowed_actions

logger = logging.getLogger(__name__)

CRITICAL_CAPABILITY_PRIORITY = [
    "broad_page_access",
    "early_document_injection",
    "page_storage_access",
    "storage_access",
    "external_network",
    "message_bridge",
    "background_execution",
    "periodic_execution",
    "dom_access",
    "temporary_tab_access",
]

CRITICAL_BEHAVIOR_TAGS = [
    "credential_or_token_exfiltration_pattern",
    "session_theft_pattern",
    "page_storage_exfiltration",
    "repeated_exfiltration",
    "external_communication",
    "message_passing_bridge",
    "early_injection",
    "form_submission_network",
]

ACTION_PURPOSES = {
    "load_extension": "Load unpacked extension for controlled analysis.",
    "open_mock_page": "Open mock/localhost page to trigger extension behaviors safely.",
    "seed_dummy_local_storage": "Insert harmless localStorage/session test values.",
    "seed_extension_uuid": "Seed deterministic extension UUID-related state.",
    "wait_for_extension_service_worker": "Wait until extension service worker is ready.",
    "prepare_target_routes": "Prepare local route interception for safe observation.",
    "seed_target_local_storage_before_goto": "Seed target page storage before navigation.",
    "click_extension_action": "Trigger extension action UI interaction.",
    "submit_mock_form": "Submit mock form to stimulate content script/network path.",
    "wait": "Allow timers/background tasks to run for evidence collection.",
    "collect_network_requests": "Collect observed network requests.",
    "collect_runtime_messages": "Collect chrome runtime messaging events.",
    "collect_storage_events": "Collect storage read/write events.",
    "collect_dom_events": "Collect DOM event interactions.",
    "collect_timer_events": "Collect timer/interval behavior evidence.",
    "finish_analysis": "Finish analysis with final structured assessment.",
}


def build_agent_system_prompt() -> str:
    return (
        "You are a Chrome extension dynamic security analysis agent. "
        "Choose the next safe analysis action using only the provided evidence. "
        "Return JSON only."
    )


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _trim_list(values: list[Any], max_items: int) -> list[Any]:
    return values[: max(0, int(max_items))]


def _ranked_subset(values: list[str], priority: list[str], max_items: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for p in priority:
        if p in values and p not in seen:
            out.append(p)
            seen.add(p)
        if len(out) >= max_items:
            return out

    for v in values:
        if v not in seen:
            out.append(v)
            seen.add(v)
        if len(out) >= max_items:
            return out

    return out


def _summarize_manifest(vector_fingerprint: dict) -> dict:
    manifest = _safe_dict(vector_fingerprint.get("manifest_profile"))
    return {
        "manifest_version": manifest.get("manifest_version"),
        "host_access": manifest.get("host_access", manifest.get("host_permissions", [])),
        "background_type": manifest.get("background_type"),
        "entrypoint_roles": manifest.get("entrypoint_roles", []),
        "content_script_run_at": manifest.get("content_script_run_at", []),
    }


def _summarize_capabilities(vector_fingerprint: dict) -> list[str]:
    cp = _safe_dict(vector_fingerprint.get("capability_profile"))
    caps = [str(k) for k, v in cp.items() if bool(v)]
    return _ranked_subset(caps, CRITICAL_CAPABILITY_PRIORITY, 15)


def _flow_priority(flow: dict) -> tuple[int, int]:
    src = str(flow.get("source", "")).lower()
    sink = str(flow.get("sink", "")).lower()
    score = 0
    if sink == "external_network":
        score += 3
    if src in {"localstorage", "sessionstorage", "credential_input"}:
        score += 3
    if "credential" in src or "token" in src or "session" in src:
        score += 2
    return score, len(json.dumps(flow, ensure_ascii=False))


def _summarize_predicted_flows(vector_fingerprint: dict) -> list[dict]:
    raw = _safe_list(vector_fingerprint.get("predicted_flows"))
    flows = [f for f in raw if isinstance(f, dict)]
    prioritized = sorted(flows, key=_flow_priority, reverse=True)

    out: list[dict] = []
    for f in prioritized:
        out.append(
            {
                "source": str(f.get("source", "")),
                "path": str(f.get("path", "")),
                "sink": str(f.get("sink", "")),
                "confidence": f.get("confidence"),
            }
        )
        if len(out) >= 5:
            break
    return out


def _summarize_behavior_tags(vector_fingerprint: dict) -> list[str]:
    tags = [str(t) for t in _safe_list(vector_fingerprint.get("behavior_tags"))]
    return _ranked_subset(tags, CRITICAL_BEHAVIOR_TAGS, 15)


def _summarize_static_signals(vector_fingerprint: dict) -> dict:
    signals = _safe_dict(vector_fingerprint.get("static_code_signals"))
    storage = _safe_dict(signals.get("storage"))
    messaging = _safe_dict(signals.get("messaging"))
    network = _safe_dict(signals.get("network"))
    delayed = _safe_dict(signals.get("delayed_execution"))

    return {
        "storage": {
            "apis": _trim_list(_safe_list(storage.get("apis")), 30),
            "keywords_top10": _trim_list(_safe_list(storage.get("keywords")), 10),
        },
        "messaging": {
            "apis": _trim_list(_safe_list(messaging.get("apis")), 30),
            "patterns": _trim_list(_safe_list(messaging.get("patterns")), 20),
            "message_actions_top10": _trim_list(_safe_list(messaging.get("message_actions")), 10),
        },
        "network": {
            "apis": _trim_list(_safe_list(network.get("apis")), 30),
            "methods": _trim_list(_safe_list(network.get("methods")), 10),
            "endpoint_keywords_top10": _trim_list(_safe_list(network.get("endpoint_keywords")), 10),
            "external_origin_present": bool(network.get("external_origin_present", False)),
        },
        "delayed_execution": {
            "apis": _trim_list(_safe_list(delayed.get("apis")), 20),
            "patterns": _trim_list(_safe_list(delayed.get("patterns")), 20),
        },
    }


def _summarize_selected_match(selected_match: dict) -> dict:
    payload = _safe_dict(selected_match.get("payload"))
    pf = _safe_dict(payload.get("vector_fingerprint"))
    flows = _safe_list(pf.get("predicted_flows"))
    tags = _safe_list(pf.get("behavior_tags"))
    signals = _safe_dict(pf.get("static_code_signals"))

    matched_signals_count = 0
    for section in signals.values():
        if isinstance(section, dict):
            for v in section.values():
                if isinstance(v, list):
                    matched_signals_count += len(v)

    return {
        "pattern_name": selected_match.get("pattern_name", ""),
        "final_score": selected_match.get("final_score", 0.0),
        "doc_ref": selected_match.get("doc_ref", ""),
        "candidate_only": bool(selected_match.get("candidate_only", True)),
        "concrete_api_evidence": _trim_list(_safe_list(selected_match.get("concrete_api_evidence")), 20),
        "matched_behavior_tags": _trim_list([str(t) for t in tags], 15),
        "matched_flows_count": len(flows),
        "matched_signals_count": matched_signals_count,
    }


def _extract_scenario_sections(scenario_doc: str) -> dict:
    # Temporary heuristic parser; falls back to prefix truncation when headings are unclear.
    text = str(scenario_doc or "")
    if not text.strip():
        return {"summary": ""}

    key_map = {
        "goal": ["goal", "목적", "overview"],
        "required_evidence": ["required evidence", "evidence", "탐지 근거"],
        "allowed_actions": ["allowed actions", "actions"],
        "stop_condition": ["stop condition", "success criteria"],
        "safety_notes": ["safety notes", "안전"],
    }

    lines = text.splitlines()
    section_lines: dict[str, list[str]] = {k: [] for k in key_map}
    current_key: str | None = None

    for line in lines:
        low = line.strip().lower()
        if low.startswith("#"):
            current_key = None
            for k, words in key_map.items():
                if any(w in low for w in words):
                    current_key = k
                    break
            continue
        if current_key and line.strip():
            section_lines[current_key].append(line)

    extracted = {
        k: "\n".join(v).strip()[:1200] for k, v in section_lines.items() if "\n".join(v).strip()
    }

    if extracted:
        return extracted

    return {
        "summary": text[:2000],
        "note": "fallback_truncated_scenario_doc_no_heading_match",
    }


def _summarize_recent_observations(observation_history: list[dict]) -> dict:
    rows = [r for r in observation_history if isinstance(r, dict)]
    recent = rows[-5:]

    totals = {
        "network_requests": 0,
        "runtime_messages": 0,
        "storage_events": 0,
        "dom_events": 0,
        "timers": 0,
        "document_start_observed": False,
        "content_script_executed": False,
        "extension_loaded": False,
        "service_worker_ready": False,
        "external_post_count": 0,
        "localhost_post_count": 0,
        "save_session_post_count": 0,
        "runtime_save_session_message_count": 0,
        "route_matched_save_session_endpoint": 0,
        "target_local_storage_seeded_before_goto": False,
    }

    recent_actions: list[dict] = []
    last_error: dict | None = None

    for row in rows:
        action = _safe_dict(row.get("action"))
        obs = _safe_dict(row.get("observation"))
        ex = _safe_dict(obs.get("execution"))

        nreq = _safe_list(obs.get("network_requests"))
        rmsg = _safe_list(obs.get("runtime_messages"))
        sev = _safe_list(obs.get("storage_events"))
        dev = _safe_list(obs.get("dom_events"))
        tv = _safe_list(obs.get("timers"))

        totals["network_requests"] += len(nreq)
        totals["runtime_messages"] += len(rmsg)
        totals["storage_events"] += len(sev)
        totals["dom_events"] += len(dev)
        totals["timers"] += len(tv)

        totals["document_start_observed"] = totals["document_start_observed"] or bool(ex.get("document_start_observed", False))
        totals["content_script_executed"] = totals["content_script_executed"] or bool(ex.get("content_script_executed", False))
        totals["extension_loaded"] = totals["extension_loaded"] or bool(ex.get("extension_loaded", False))
        totals["service_worker_ready"] = totals["service_worker_ready"] or bool(ex.get("service_worker_ready", False))
        totals["target_local_storage_seeded_before_goto"] = totals["target_local_storage_seeded_before_goto"] or bool(
            ex.get("target_local_storage_seeded_before_goto", False)
        )
        totals["route_matched_save_session_endpoint"] += int(ex.get("route_matched_save_session_endpoint", 0) or 0)

        for req in nreq:
            if not isinstance(req, dict):
                continue
            method = str(req.get("method", "")).upper()
            url = str(req.get("url", "")).lower()
            if method == "POST":
                if "127.0.0.1" in url or "localhost" in url:
                    totals["localhost_post_count"] += 1
                else:
                    totals["external_post_count"] += 1
                if "save-session" in url or "save_session" in url:
                    totals["save_session_post_count"] += 1

        for msg in rmsg:
            txt = json.dumps(msg, ensure_ascii=False).lower() if isinstance(msg, (dict, list)) else str(msg).lower()
            if "save_session" in txt or "save-session" in txt:
                totals["runtime_save_session_message_count"] += 1

        if ex.get("dynamic_analysis_timeout"):
            last_error = {"error_type": "DynamicAnalysisTimeout", "error": "dynamic_analysis_timeout"}

    for row in recent:
        action = _safe_dict(row.get("action"))
        obs = _safe_dict(row.get("observation"))
        recent_actions.append(
            {
                "action": action.get("action", ""),
                "target": action.get("target", ""),
                "network_requests": len(_safe_list(obs.get("network_requests"))),
                "runtime_messages": len(_safe_list(obs.get("runtime_messages"))),
                "storage_events": len(_safe_list(obs.get("storage_events"))),
            }
        )

    return {
        "recent_actions": recent_actions,
        "observation_totals": totals,
        "last_error": last_error,
    }


def _summarize_allowed_actions() -> list[dict]:
    out: list[dict] = []
    for name in get_allowed_actions():
        if name == "finish_analysis":
            required = ["action", "reason", "final_assessment"]
        elif name in {"open_mock_page", "wait", "submit_mock_form"}:
            required = ["action", "target", "input", "reason"]
        else:
            required = ["action", "target", "input", "reason"]

        out.append(
            {
                "action": name,
                "required_fields": required,
                "purpose": ACTION_PURPOSES.get(name, "Perform a safe analysis step."),
            }
        )
    return out


def _prompt_component_diag(components: dict[str, str], system_prompt: str, final_prompt: str) -> None:
    logger.info(
        "[prompt_component_diag] system_prompt_chars=%s fingerprint_chars=%s selected_match_chars=%s "
        "scenario_doc_chars=%s observation_history_chars=%s action_schema_chars=%s other_chars=%s total_chars=%s",
        len(system_prompt),
        len(components["fingerprint"]),
        len(components["selected_match"]),
        len(components["scenario_doc"]),
        len(components["observation_history"]),
        len(components["allowed_actions"]),
        len(components["other"]),
        len(final_prompt),
    )


def build_next_action_prompt_compact(
    vector_fingerprint: dict,
    selected_match: dict,
    scenario_doc: str,
    observation_history: list[dict],
    round_index: int,
    max_rounds: int,
) -> str:
    manifest_summary = _summarize_manifest(vector_fingerprint)
    capability_summary = _summarize_capabilities(vector_fingerprint)
    flows_summary = _summarize_predicted_flows(vector_fingerprint)
    behavior_tags = _summarize_behavior_tags(vector_fingerprint)
    static_signals = _summarize_static_signals(vector_fingerprint)
    selected_match_summary = _summarize_selected_match(selected_match)
    scenario_sections = _extract_scenario_sections(scenario_doc)
    obs_summary = _summarize_recent_observations(observation_history)
    allowed_actions_summary = _summarize_allowed_actions()

    static_security_summary = {
        "manifest": manifest_summary,
        "capability_profile_top": capability_summary,
        "behavior_tags_top": behavior_tags,
        "static_code_signals": static_signals,
        "round": f"{round_index}/{max_rounds}",
    }

    target_scenario = {
        "pattern_name": selected_match_summary.get("pattern_name", ""),
        "doc_ref": selected_match_summary.get("doc_ref", ""),
        "score": selected_match_summary.get("final_score", 0.0),
    }

    components = {
        "fingerprint": json.dumps(static_security_summary, ensure_ascii=False),
        "predicted_flows": json.dumps(flows_summary, ensure_ascii=False),
        "selected_match": json.dumps(selected_match_summary, ensure_ascii=False),
        "scenario_doc": json.dumps(scenario_sections, ensure_ascii=False),
        "observation_history": json.dumps(obs_summary, ensure_ascii=False),
        "allowed_actions": json.dumps(allowed_actions_summary, ensure_ascii=False),
        "other": "[Task]/[Output JSON] scaffolding",
    }

    prompt = (
        "[Task]\n"
        "Decide the next dynamic analysis action or finish analysis.\n\n"
        "[Target Scenario]\n"
        f"{json.dumps(target_scenario, ensure_ascii=False)}\n\n"
        "[Static Security Summary]\n"
        f"{components['fingerprint']}\n\n"
        "[Predicted Flows]\n"
        f"{components['predicted_flows']}\n\n"
        "[Selected Match]\n"
        f"{components['selected_match']}\n\n"
        "[Scenario Evidence Requirements]\n"
        f"{components['scenario_doc']}\n\n"
        "[Recent Observations]\n"
        f"{components['observation_history']}\n\n"
        "[Allowed Actions]\n"
        f"{components['allowed_actions']}\n\n"
        "[Output JSON]\n"
        "Return exactly one JSON object.\n"
        "No markdown.\n"
        "No explanation outside JSON.\n\n"
        "Action output:\n"
        "{\n"
        "  \"action\": \"string\",\n"
        "  \"target\": \"string\",\n"
        "  \"reason\": \"string\"\n"
        "}\n\n"
        "Finish output:\n"
        "{\n"
        "  \"action\": \"finish_analysis\",\n"
        "  \"target\": \"\",\n"
        "  \"reason\": \"string\",\n"
        "  \"final_assessment\": {\n"
        "    \"scenario_matched\": false,\n"
        "    \"confidence_score\": 0.0,\n"
        "    \"matched_evidence\": [],\n"
        "    \"missing_evidence\": [],\n"
        "    \"safety_notes\": []\n"
        "  }\n"
        "}\n"
    )

    if len(prompt) > 8000:
        static_security_summary["static_code_signals"]["storage"]["apis"] = _trim_list(
            _safe_list(static_security_summary["static_code_signals"]["storage"].get("apis")), 15
        )
        static_security_summary["static_code_signals"]["messaging"]["apis"] = _trim_list(
            _safe_list(static_security_summary["static_code_signals"]["messaging"].get("apis")), 15
        )
        static_security_summary["static_code_signals"]["network"]["apis"] = _trim_list(
            _safe_list(static_security_summary["static_code_signals"]["network"].get("apis")), 15
        )
        static_security_summary["static_code_signals"]["delayed_execution"]["apis"] = _trim_list(
            _safe_list(static_security_summary["static_code_signals"]["delayed_execution"].get("apis")), 10
        )
        scenario_sections = {
            k: (v[:800] if isinstance(v, str) else v) for k, v in scenario_sections.items()
        }
        obs_summary["recent_actions"] = _trim_list(_safe_list(obs_summary.get("recent_actions")), 3)
        components["fingerprint"] = json.dumps(static_security_summary, ensure_ascii=False)
        components["scenario_doc"] = json.dumps(scenario_sections, ensure_ascii=False)
        components["observation_history"] = json.dumps(obs_summary, ensure_ascii=False)
        prompt = (
            "[Task]\n"
            "Decide the next dynamic analysis action or finish analysis.\n\n"
            "[Target Scenario]\n"
            f"{json.dumps(target_scenario, ensure_ascii=False)}\n\n"
            "[Static Security Summary]\n"
            f"{components['fingerprint']}\n\n"
            "[Predicted Flows]\n"
            f"{components['predicted_flows']}\n\n"
            "[Selected Match]\n"
            f"{components['selected_match']}\n\n"
            "[Scenario Evidence Requirements]\n"
            f"{components['scenario_doc']}\n\n"
            "[Recent Observations]\n"
            f"{components['observation_history']}\n\n"
            "[Allowed Actions]\n"
            f"{components['allowed_actions']}\n\n"
            "[Output JSON]\n"
            "Return exactly one JSON object.\n"
            "No markdown.\n"
            "No explanation outside JSON.\n\n"
            "Action output:\n"
            "{\n"
            "  \"action\": \"string\",\n"
            "  \"target\": \"string\",\n"
            "  \"reason\": \"string\"\n"
            "}\n\n"
            "Finish output:\n"
            "{\n"
            "  \"action\": \"finish_analysis\",\n"
            "  \"target\": \"\",\n"
            "  \"reason\": \"string\",\n"
            "  \"final_assessment\": {\n"
            "    \"scenario_matched\": false,\n"
            "    \"confidence_score\": 0.0,\n"
            "    \"matched_evidence\": [],\n"
            "    \"missing_evidence\": [],\n"
            "    \"safety_notes\": []\n"
            "  }\n"
            "}\n"
        )

    _prompt_component_diag(components, build_agent_system_prompt(), prompt)
    return prompt


def build_repair_prompt_for_invalid_json(raw_text: str, parse_error: str) -> str:
    trimmed = str(raw_text or "")[:1200]
    err = str(parse_error or "")[:300]
    return (
        "Previous response was not valid JSON for the action schema.\n"
        "Return exactly one valid JSON object now.\n"
        "No markdown. No extra text.\n"
        f"Parse error: {err}\n"
        "Invalid response excerpt:\n"
        f"{trimmed}\n\n"
        "Valid formats:\n"
        "1) Action:\n"
        "{\"action\":\"string\",\"target\":\"string\",\"reason\":\"string\",\"input\":{}}\n"
        "2) Finish:\n"
        "{\"action\":\"finish_analysis\",\"target\":\"\",\"reason\":\"string\",\"final_assessment\":{\"scenario_matched\":false,\"confidence_score\":0.0,\"matched_evidence\":[],\"missing_evidence\":[],\"safety_notes\":[]}}\n"
    )


def build_next_action_prompt(
    vector_fingerprint: dict,
    selected_match: dict,
    scenario_doc: str,
    observation_history: list[dict],
    round_index: int,
    max_rounds: int,
) -> str:
    # Legacy full prompt retained for reference/testing only.
    allowed = get_allowed_actions()
    match_summary = {
        "pattern_name": selected_match.get("pattern_name"),
        "final_score": selected_match.get("final_score"),
        "doc_ref": selected_match.get("doc_ref"),
        "rerank_breakdown": selected_match.get("rerank_breakdown", {}),
    }

    return (
        "Task: choose the next safe dynamic-analysis action OR finish_analysis if evidence is sufficient.\n"
        "Rules:\n"
        "- No real-service login\n"
        "- No real token/cookie/session/password collection\n"
        "- No real external C2 transmission\n"
        "- Use dummy data only\n"
        "- You may emulate target login domains only via mock_profile.target_url, but NEVER access real services\n"
        "- Output JSON only. Never output code blocks, Python, shell, or system commands\n"
        "- JSON only\n\n"
        f"Round: {round_index}/{max_rounds}\n\n"
        "Vector fingerprint:\n"
        f"{json.dumps(vector_fingerprint, ensure_ascii=False)}\n\n"
        "Selected match:\n"
        f"{json.dumps(match_summary, ensure_ascii=False)}\n\n"
        "Scenario document:\n"
        f"{scenario_doc}\n\n"
        "Observation history:\n"
        f"{json.dumps(observation_history, ensure_ascii=False)}\n\n"
        "Allowed actions:\n"
        f"{json.dumps(allowed, ensure_ascii=False)}\n\n"
        "Output schema for normal action:\n"
        "{\n"
        "  \"action\": \"open_mock_page\",\n"
        "  \"target\": \"mock_or_localhost_only\",\n"
        "  \"input\": {\n"
        "    \"mock_profile\": {\n"
        "      \"target_url\": \"https://web.telegram.org/k/\",\n"
        "      \"local_storage\": {},\n"
        "      \"session_storage\": {},\n"
        "      \"dom\": {\"title\": \"\", \"inputs\": [], \"forms\": [], \"buttons\": []},\n"
        "      \"events\": [],\n"
        "      \"wait_ms\": 5000\n"
        "    }\n"
        "  },\n"
        "  \"reason\": \"\",\n"
        "  \"expected_observation\": \"\"\n"
        "}\n\n"
        "Output schema for finish:\n"
        "{\n"
        "  \"action\": \"finish_analysis\",\n"
        "  \"reason\": \"\",\n"
        "  \"final_assessment\": {\n"
        "    \"scenario_matched\": true,\n"
        "    \"confidence_score\": 0.0,\n"
        "    \"matched_evidence\": [],\n"
        "    \"missing_evidence\": [],\n"
        "    \"safety_notes\": []\n"
        "  }\n"
        "}\n"
    )
