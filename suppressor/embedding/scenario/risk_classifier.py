from __future__ import annotations

from typing import Any

from .compact import compact_agent_result

CRITICAL_TAGS = {
    "session_theft_pattern",
    "credential_or_token_exfiltration_pattern",
    "credential_interception",
    "data_exfiltration",
    "debugger_abuse",
    "dynamic_execution",
}

HIGH_TAGS = {
    "page_storage_exfiltration",
    "form_submission_network",
    "request_modification",
    "redirect_hijacking",
    "repeated_exfiltration",
    "persistent_connection",
}

MEDIUM_TAGS = {
    "external_communication",
    "message_passing_bridge",
    "storage_persistence",
    "extension_page_network_behavior",
}


def _clamp01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


SESSION_KEYWORDS = {"session", "token", "auth", "user_auth", "user_id", "credential"}
SESSION_ACTION_KEYWORDS = {"save_session", "set_uuid", "clear_session"}
LOGIN_SERVICE_DOMAINS = {"web.telegram.org", "accounts.google.com", "mail.google.com"}


def _collect_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value.lower())
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(_collect_strings(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_collect_strings(v))
    return out


def _contains_any_keyword(values: list[str], keywords: set[str]) -> bool:
    for v in values:
        for k in keywords:
            if k in v:
                return True
    return False


def compute_high_risk_behavior_flags(
    scenario_result: dict,
    vector_fingerprint: dict | None = None,
) -> dict:
    evidence = scenario_result.get("evidence_score", {}) if isinstance(scenario_result, dict) else {}
    agent_result = scenario_result.get("agent_result", {}) if isinstance(scenario_result, dict) else {}
    final_assessment = (
        agent_result.get("final_assessment", {})
        if isinstance(agent_result, dict) and isinstance(agent_result.get("final_assessment", {}), dict)
        else {}
    )
    observations: dict = {
        "network_requests": [],
        "runtime_messages": [],
        "storage_events": [],
        "timers": [],
        "execution": {},
    }
    for item in agent_result.get("actions_executed", []) if isinstance(agent_result, dict) else []:
        if not isinstance(item, dict):
            continue
        obs = item.get("observation", {})
        if not isinstance(obs, dict):
            continue
        for k in ("network_requests", "runtime_messages", "storage_events", "timers"):
            if isinstance(obs.get(k), list):
                observations[k].extend(obs[k])
        ex = obs.get("execution", {})
        if isinstance(ex, dict):
            observations["execution"].update(ex)

    vf = vector_fingerprint if isinstance(vector_fingerprint, dict) else {}
    signals = vf.get("static_code_signals", {}) if isinstance(vf.get("static_code_signals", {}), dict) else {}
    manifest = vf.get("manifest_profile", {}) if isinstance(vf.get("manifest_profile", {}), dict) else {}
    predicted_flows = vf.get("predicted_flows", []) if isinstance(vf.get("predicted_flows", []), list) else []
    matched_evidence = evidence.get("matched_evidence", []) if isinstance(evidence.get("matched_evidence", []), list) else []
    missing_evidence = evidence.get("missing_evidence", []) if isinstance(evidence.get("missing_evidence", []), list) else []

    storage_strings = _collect_strings(signals.get("storage", {})) + _collect_strings(observations.get("storage_events", []))
    network_strings = _collect_strings(signals.get("network", {})) + _collect_strings(observations.get("network_requests", []))
    message_strings = _collect_strings(signals.get("messaging", {})) + _collect_strings(observations.get("runtime_messages", []))
    timer_strings = _collect_strings(signals.get("delayed_execution", {})) + _collect_strings(observations.get("timers", []))
    manifest_strings = _collect_strings(manifest)
    flow_strings = _collect_strings(predicted_flows)

    dynamic_external_post = any(
        isinstance(n, dict)
        and str(n.get("method", "")).upper() == "POST"
        and str(n.get("url_category", "")).lower() == "external"
        for n in observations.get("network_requests", [])
    )
    static_external_post = bool(signals.get("network", {}).get("external_origin_present")) and (
        _contains_any_keyword(network_strings, {"post", "fetch", "xmlhttprequest"})
    )
    dynamic_bridge = any(
        isinstance(m, dict) and str(m.get("direction", "")).lower() == "content_script_to_background"
        for m in observations.get("runtime_messages", [])
    )
    static_bridge = _contains_any_keyword(message_strings, {"content_script_to_background", "runtime.sendmessage", "runtime.onmessage"})

    periodic_dynamic = any(
        isinstance(t, dict) and str(t.get("api", "")) in {"setInterval", "setTimeout", "chrome.alarms"}
        for t in observations.get("timers", [])
    )
    periodic_static = _contains_any_keyword(timer_strings, {"setinterval", "settimeout", "periodic_session_collection", "repeated_transmission"})

    targeted_login_domain = any(domain in s for s in (manifest_strings + flow_strings) for domain in LOGIN_SERVICE_DOMAINS)
    session_action_detected = _contains_any_keyword(message_strings, SESSION_ACTION_KEYWORDS)

    session_storage_access = (
        _contains_any_keyword(storage_strings, {"localstorage", "sessionstorage", "chrome.storage"})
        or "page_storage_exfiltration" in matched_evidence
    )
    credential_keyword_detected = _contains_any_keyword(storage_strings + message_strings + network_strings, SESSION_KEYWORDS)

    document_start = bool(observations.get("execution", {}).get("document_start_observed")) or _contains_any_keyword(
        manifest_strings, {"document_start", "early_document_injection"}
    )

    message_bridge = dynamic_bridge or static_bridge or "message_passing_bridge" in matched_evidence
    external_post = dynamic_external_post or static_external_post or "external_communication" in matched_evidence
    periodic_execution = periodic_dynamic or periodic_static or "repeated_exfiltration" in matched_evidence

    agent_claimed_match = bool(final_assessment.get("scenario_matched"))
    actual_runtime_messages = len(observations.get("runtime_messages", []))
    actual_network_requests = len(observations.get("network_requests", []))
    actual_storage_events = len(observations.get("storage_events", []))
    actual_timer_events = len(observations.get("timers", []))
    document_start_observed = bool(observations.get("execution", {}).get("document_start_observed"))

    no_runtime_observation = (
        actual_runtime_messages == 0
        and actual_network_requests == 0
        and actual_storage_events == 0
        and actual_timer_events == 0
    )
    document_start_not_observed = not document_start_observed
    observation_gap = agent_claimed_match and no_runtime_observation and document_start_not_observed
    observation_totals = {
        "network_requests": actual_network_requests,
        "runtime_messages": actual_runtime_messages,
        "storage_events": actual_storage_events,
        "dom_events": 0,
        "timers": actual_timer_events,
        "document_start_observed": document_start_observed,
        "mock_target_used": bool(observations.get("execution", {}).get("mock_target_used")),
        "real_service_used": bool(observations.get("execution", {}).get("real_service_used")),
    }

    core_flags = {
        "a_early_injection": document_start,
        "b_storage_access": session_storage_access,
        "c_session_keywords": credential_keyword_detected,
        "d_message_bridge": message_bridge,
        "e_external_post_or_fetch": external_post,
        "f_periodic_execution": periodic_execution,
        "g_session_action_message": session_action_detected,
        "h_targeted_login_domain": targeted_login_domain,
    }
    core_count = sum(1 for v in core_flags.values() if v)
    environment_limited = (
        bool(observations.get("execution", {}).get("mock_target_used"))
        and not bool(observations.get("execution", {}).get("real_service_used"))
        and observation_gap
        and (bool(targeted_login_domain) or bool(session_storage_access and credential_keyword_detected and external_post and message_bridge))
    )

    risk_factors = []
    if session_storage_access:
        risk_factors.append("session_storage_access")
    if credential_keyword_detected:
        risk_factors.append("credential_keyword_detected")
    if message_bridge:
        risk_factors.append("message_bridge_detected")
    if external_post:
        risk_factors.append("external_post_detected")
    if periodic_execution:
        risk_factors.append("periodic_execution_detected")
    if targeted_login_domain:
        risk_factors.append("targeted_login_domain")
    if document_start:
        risk_factors.append("document_start_or_early_injection")
    if session_action_detected:
        risk_factors.append("session_action_message_detected")
    if observation_gap:
        risk_factors.append("observation_gap")

    return {
        "core_flags": core_flags,
        "core_count": core_count,
        "session_storage_access": session_storage_access,
        "credential_keyword_detected": credential_keyword_detected,
        "message_bridge_detected": message_bridge,
        "external_post_detected": external_post,
        "periodic_execution_detected": periodic_execution,
        "targeted_login_domain": targeted_login_domain,
        "environment_limited": environment_limited,
        "observation_totals": observation_totals,
        "observation_gap": {
            "agent_claimed_match": agent_claimed_match,
            "actual_runtime_messages": actual_runtime_messages,
            "actual_network_requests": actual_network_requests,
            "actual_storage_events": actual_storage_events,
            "actual_timer_events": actual_timer_events,
            "document_start_observed": document_start_observed,
            "reason": (
                "LLM/agent marked scenario as matched based on planned actions, but harness observations did not capture the expected runtime evidence."
                if observation_gap
                else ""
            ),
        },
        "risk_factors": risk_factors,
    }


def is_high_confidence_session_exfiltration(flags: dict, safety_violation: bool) -> bool:
    if safety_violation:
        return False
    if not isinstance(flags, dict):
        return False
    session_data_evidence = bool(flags.get("session_storage_access")) and bool(flags.get("credential_keyword_detected"))
    bridge_or_external = bool(flags.get("message_bridge_detected")) or bool(flags.get("external_post_detected"))
    execution_context = bool(flags.get("periodic_execution_detected")) or bool(flags.get("targeted_login_domain")) or bool(
        flags.get("core_flags", {}).get("a_early_injection")
    )
    return bool(flags.get("core_count", 0) >= 4 and session_data_evidence and bridge_or_external and execution_context)


def classify_final_risk(
    scenario_results: list[dict],
    vector_fingerprint: dict | None = None,
    static_context: dict | None = None,
) -> dict:
    static_context = static_context if isinstance(static_context, dict) else {}

    def _observation_totals(s: dict) -> dict:
        actions = s.get("agent_result", {}).get("actions_executed", []) if isinstance(s.get("agent_result", {}), dict) else []
        totals = {
            "network_requests": 0,
            "runtime_messages": 0,
            "storage_events": 0,
            "timers": 0,
            "dom_events": 0,
            "content_script_executed": False,
            "document_start_observed": False,
            "extension_loaded": False,
            "service_worker_ready": False,
            "extension_context_launched": False,
            "dynamic_analysis_timeout": False,
            "actions_count": len(actions) if isinstance(actions, list) else 0,
            "localhost_post_count": 0,
            "external_post_count": 0,
            "external_request_count": 0,
            "blocked_external_request_count": 0,
            "external_request_attempted": False,
            "external_request_blocked": False,
            "real_network_used": False,
            "intercepted_by_harness": False,
            "runtime_save_session_message_count": 0,
        }
        for item in actions if isinstance(actions, list) else []:
            obs = item.get("observation", {}) if isinstance(item, dict) else {}
            if not isinstance(obs, dict):
                continue
            for k in ("network_requests", "runtime_messages", "storage_events", "timers", "dom_events"):
                v = obs.get(k, [])
                if isinstance(v, list):
                    totals[k] += len(v)
            net = obs.get("network_requests", []) if isinstance(obs.get("network_requests", []), list) else []
            for n in net:
                if not isinstance(n, dict):
                    continue
                if str(n.get("method", "")).upper() == "POST":
                    cat = str(n.get("url_category", "")).lower()
                    if cat == "localhost":
                        totals["localhost_post_count"] += 1
                    elif cat == "external":
                        totals["external_post_count"] += 1
                if str(n.get("url_category", "")).lower() == "external":
                    totals["external_request_count"] += 1
                    totals["external_request_attempted"] = True
                    if bool(n.get("intercepted_by_harness")) and (bool(n.get("fulfilled_by_harness")) or bool(n.get("aborted_by_harness"))):
                        totals["blocked_external_request_count"] += 1
                        totals["external_request_blocked"] = True
                    if bool(n.get("real_network_used")) and not bool(n.get("intercepted_by_harness")):
                        totals["real_network_used"] = True
                    if bool(n.get("intercepted_by_harness")):
                        totals["intercepted_by_harness"] = True
            msgs = obs.get("runtime_messages", []) if isinstance(obs.get("runtime_messages", []), list) else []
            for m in msgs:
                if isinstance(m, dict) and str(m.get("action", "")).lower() == "save_session":
                    totals["runtime_save_session_message_count"] += 1
            ex = obs.get("execution", {}) if isinstance(obs.get("execution", {}), dict) else {}
            totals["content_script_executed"] = totals["content_script_executed"] or bool(ex.get("content_script_executed", False))
            totals["document_start_observed"] = totals["document_start_observed"] or bool(ex.get("document_start_observed", False))
            totals["extension_loaded"] = totals["extension_loaded"] or bool(ex.get("extension_loaded", False))
            totals["service_worker_ready"] = totals["service_worker_ready"] or bool(ex.get("service_worker_ready", False))
            totals["extension_context_launched"] = totals["extension_context_launched"] or bool(ex.get("extension_context_launched", False))
            totals["dynamic_analysis_timeout"] = totals["dynamic_analysis_timeout"] or bool(ex.get("dynamic_analysis_timeout", False))
            totals["external_request_attempted"] = totals["external_request_attempted"] or bool(ex.get("external_request_attempted", False))
            totals["external_request_blocked"] = totals["external_request_blocked"] or bool(ex.get("external_request_blocked", False))
            totals["real_network_used"] = totals["real_network_used"] or bool(ex.get("real_network_used", False))
            totals["intercepted_by_harness"] = totals["intercepted_by_harness"] or bool(ex.get("intercepted_by_harness", False))
            totals["external_request_count"] = max(int(totals["external_request_count"]), int(ex.get("external_request_count", 0) or 0))
            totals["blocked_external_request_count"] = max(
                int(totals["blocked_external_request_count"]),
                int(ex.get("blocked_external_request_count", 0) or 0),
            )
        ar = s.get("agent_result", {}) if isinstance(s.get("agent_result", {}), dict) else {}
        if str(ar.get("error_type", "")).lower() == "dynamicanalysistimeout":
            totals["dynamic_analysis_timeout"] = True
        return totals

    def _is_matched_scenario(s: dict) -> bool:
        if not isinstance(s, dict):
            return False
        ev = s.get("evidence_score", {}) if isinstance(s.get("evidence_score", {}), dict) else {}
        matched_evidence = ev.get("matched_evidence", []) if isinstance(ev.get("matched_evidence", []), list) else []
        score = float(s.get("scenario_evidence_score", 0.0) or 0.0)
        scenario_matched = bool(s.get("scenario_matched", False))
        if not scenario_matched:
            scenario_matched = bool(s.get("agent_result", {}).get("final_assessment", {}).get("scenario_matched", False)) if isinstance(s.get("agent_result", {}), dict) else False
        return bool(score > 0.0 and matched_evidence and scenario_matched)

    def _llm_failure_only(s: dict) -> bool:
        if not isinstance(s, dict):
            return False
        ar = s.get("agent_result", {}) if isinstance(s.get("agent_result", {}), dict) else {}
        status = str(ar.get("status", "")).lower()
        error_type = str(ar.get("error_type", "")).lower()
        row_error_type = str(s.get("error_type", "")).lower()
        explicit_status = status in {"llm_failed", "parse_error", "model_error"}
        explicit_types = {
            "llmcallerror",
            "llmtimeout",
            "llmparseerror",
            "llmassessmentmissing",
        }
        type_failed = error_type in explicit_types or row_error_type in explicit_types
        llm_error_flag = bool(ar.get("llm_error", False))
        return bool(explicit_status or type_failed or llm_error_flag)

    if not scenario_results:
        return {
            "risk_level": "LOW",
            "risk_score": 0.0,
            "reason": "No matched scenario results",
            "matched_scenarios": [],
            "candidate_scenarios": [],
            "vector_candidate_scenarios": [],
            "top_scenario": {},
            "risk_factors": [],
            "missing_evidence": [],
            "safety_violation": False,
        }

    valid = [s for s in scenario_results if isinstance(s, dict)]
    if not valid:
        return {
            "risk_level": "LOW",
            "risk_score": 0.0,
            "reason": "No valid scenario result entries",
            "matched_scenarios": [],
            "candidate_scenarios": [],
            "vector_candidate_scenarios": [],
            "top_scenario": {},
            "risk_factors": [],
            "missing_evidence": [],
            "safety_violation": False,
        }

    def _is_actionable_safety_violation(s: dict) -> bool:
        if not isinstance(s, dict):
            return False
        if not bool(s.get("safety_violation", False)):
            return False
        ev = s.get("evidence_score", {}) if isinstance(s.get("evidence_score", {}), dict) else {}
        if bool(ev.get("real_network_used", False)):
            return True
        if bool(ev.get("unsafe_request_host")) and not bool(ev.get("intercepted_by_harness", False)):
            return True
        if bool(ev.get("unsafe_request_url")) and not bool(ev.get("is_target_url_emulation", False)):
            return True
        if bool(ev.get("is_target_url_emulation", False)) and bool(ev.get("intercepted_by_harness", False)):
            return False
        return bool(s.get("safety_violation", False))

    actionable_safety_rows = [s for s in valid if _is_actionable_safety_violation(s)]
    any_safety = len(actionable_safety_rows) > 0
    top = max(valid, key=lambda x: float(x.get("final_dynamic_rag_score", 0.0) or 0.0))

    matched_rows = [s for s in valid if _is_matched_scenario(s)]
    matched_scenarios = [s.get("pattern_name") for s in matched_rows if s.get("pattern_name")]
    def _row_has_concrete_static_evidence(s: dict) -> bool:
        if not isinstance(s, dict):
            return False
        ev = s.get("concrete_api_evidence", [])
        if isinstance(ev, list) and len(ev) > 0:
            return True
        if float(s.get("static_evidence_score", 0.0) or 0.0) > 0.0:
            return True
        if float(s.get("static_capability_score", 0.0) or 0.0) > 0.0:
            return True
        return False

    concrete_candidate_rows = [s for s in valid if _row_has_concrete_static_evidence(s)]
    vector_candidate_rows = [s for s in valid if not _row_has_concrete_static_evidence(s)]
    candidate_scenarios = [s.get("pattern_name") for s in concrete_candidate_rows if s.get("pattern_name")]
    vector_candidate_scenarios = [s.get("pattern_name") for s in vector_candidate_rows if s.get("pattern_name")]
    missing_evidence: list[str] = []
    for s in valid:
        miss = s.get("evidence_score", {}).get("missing_evidence", []) if isinstance(s.get("evidence_score", {}), dict) else []
        if isinstance(miss, list):
            missing_evidence.extend([str(m) for m in miss])

    risk_factors: list[str] = []
    risk_escalation = {
        "high_confidence_session_exfiltration": False,
        "environment_limited": False,
        "observation_gap": {},
        "agent_failed": False,
        "agent_error": "",
        "static_agent_failed_gate": False,
        "mock_limited_static_gate": False,
        "reason": "",
    }

    if any_safety:
        first = actionable_safety_rows[0]
        first_ev = first.get("evidence_score", {}) if isinstance(first.get("evidence_score", {}), dict) else {}
        risk_level = "CRITICAL"
        reason = "Safety violation observed during dynamic analysis"
        risk_factors.append("safety_violation")
        risk_escalation.update(
            {
                "reason": reason,
                "safety_violation_source": str(first_ev.get("safety_violation_source", "unknown")),
                "unsafe_request_url": str(first_ev.get("unsafe_request_url", "")),
                "unsafe_request_host": str(first_ev.get("unsafe_request_host", "")),
                "real_network_used": bool(first_ev.get("real_network_used", False)),
                "intercepted_by_harness": bool(first_ev.get("intercepted_by_harness", False)),
                "is_target_url_emulation": bool(first_ev.get("is_target_url_emulation", False)),
            }
        )
        return {
            "risk_level": risk_level,
            "risk_score": 1.0,
            "reason": reason,
            "matched_scenarios": matched_scenarios,
            "candidate_scenarios": candidate_scenarios,
            "vector_candidate_scenarios": vector_candidate_scenarios,
            "top_scenario": {**top, "agent_result": compact_agent_result(top.get("agent_result", {}))} if isinstance(top, dict) else {},
            "risk_factors": risk_factors,
            "risk_escalation": risk_escalation,
            "missing_evidence": missing_evidence,
            "safety_violation": True,
            "external_request_attempted": bool(first_ev.get("external_request_attempted", False)),
            "external_request_blocked": bool(first_ev.get("external_request_blocked", False)),
            "real_network_used": bool(first_ev.get("real_network_used", False)),
            "intercepted_by_harness": bool(first_ev.get("intercepted_by_harness", False)),
        }

    llm_failure_rows = [s for s in valid if _llm_failure_only(s)]
    if llm_failure_rows and len(llm_failure_rows) == len(valid):
        return {
            "risk_level": "INCONCLUSIVE",
            "risk_score": 0.1,
            "reason": "LLM assessment failed, so risk could not be determined.",
            "matched_scenarios": [],
            "candidate_scenarios": candidate_scenarios,
            "vector_candidate_scenarios": vector_candidate_scenarios,
            "top_scenario": {**top, "agent_result": compact_agent_result(top.get("agent_result", {}))} if isinstance(top, dict) else {},
            "risk_factors": ["llm_assessment_failed"],
            "risk_escalation": risk_escalation,
            "missing_evidence": missing_evidence,
            "safety_violation": False,
        }

    def _is_screenshot_or_remote_pattern(name: str) -> bool:
        n = str(name or "").lower()
        return any(k in n for k in ("screenshot", "capture", "remote_browser_control", "browser_automation", "debugger_scripting"))

    context_concrete_static = static_context.get("concrete_static_evidence", [])
    context_injected = static_context.get("evidence_injected_candidates", [])
    context_manifest_caps = static_context.get("manifest_capabilities", {})
    if not isinstance(context_concrete_static, list):
        context_concrete_static = []
    if not isinstance(context_injected, list):
        context_injected = []
    if not isinstance(context_manifest_caps, dict):
        context_manifest_caps = {}

    perms = {str(x).lower() for x in (context_manifest_caps.get("permissions", []) if isinstance(context_manifest_caps.get("permissions", []), list) else [])}
    manifest_risky_combo = bool(
        ({"debugger", "scripting", "tabs"} <= perms)
        or ("tabcapture" in perms)
        or ("desktopcapture" in perms)
    )

    any_static_candidate = bool(concrete_candidate_rows) or bool(context_concrete_static) or bool(context_injected) or manifest_risky_combo
    attempted_rows = 0
    timeout_attempt = False
    for s in valid:
        totals = _observation_totals(s)
        ar = s.get("agent_result", {}) if isinstance(s.get("agent_result", {}), dict) else {}
        status = str(ar.get("status", "")).lower()
        attempted = bool(
            totals.get("actions_count", 0) > 0
            or totals.get("extension_loaded", False)
            or totals.get("service_worker_ready", False)
            or totals.get("extension_context_launched", False)
            or status in {"ok", "partial_error"}
            or totals.get("dynamic_analysis_timeout", False)
        )
        if attempted:
            attempted_rows += 1
        timeout_attempt = timeout_attempt or bool(totals.get("dynamic_analysis_timeout", False))
    dynamic_attempted = attempted_rows > 0
    aggregate = {
        "network_requests": 0,
        "runtime_messages": 0,
        "storage_events": 0,
        "timers": 0,
        "dom_events": 0,
        "localhost_post_count": 0,
        "external_post_count": 0,
        "external_request_count": 0,
        "blocked_external_request_count": 0,
        "external_request_attempted": False,
        "external_request_blocked": False,
        "real_network_used": False,
        "intercepted_by_harness": False,
        "runtime_save_session_message_count": 0,
        "content_script_executed": False,
        "document_start_observed": False,
        "extension_loaded": False,
        "service_worker_ready": False,
    }
    for s in valid:
        t = _observation_totals(s)
        for k in (
            "network_requests",
            "runtime_messages",
            "storage_events",
            "timers",
            "dom_events",
            "localhost_post_count",
            "external_post_count",
            "external_request_count",
            "blocked_external_request_count",
            "runtime_save_session_message_count",
        ):
            aggregate[k] += int(t.get(k, 0) or 0)
        aggregate["content_script_executed"] = aggregate["content_script_executed"] or bool(t.get("content_script_executed", False))
        aggregate["document_start_observed"] = aggregate["document_start_observed"] or bool(t.get("document_start_observed", False))
        aggregate["external_request_attempted"] = aggregate["external_request_attempted"] or bool(t.get("external_request_attempted", False))
        aggregate["external_request_blocked"] = aggregate["external_request_blocked"] or bool(t.get("external_request_blocked", False))
        aggregate["real_network_used"] = aggregate["real_network_used"] or bool(t.get("real_network_used", False))
        aggregate["intercepted_by_harness"] = aggregate["intercepted_by_harness"] or bool(t.get("intercepted_by_harness", False))
        aggregate["extension_loaded"] = aggregate["extension_loaded"] or bool(t.get("extension_loaded", False))
        aggregate["service_worker_ready"] = aggregate["service_worker_ready"] or bool(t.get("service_worker_ready", False))

    dynamic_evidence_count = (
        aggregate["network_requests"]
        + aggregate["runtime_messages"]
        + aggregate["storage_events"]
        + aggregate["timers"]
        + aggregate["dom_events"]
        + aggregate["localhost_post_count"]
        + aggregate["external_post_count"]
        + aggregate["runtime_save_session_message_count"]
    )
    has_dynamic_evidence = bool(
        dynamic_evidence_count > 0 or aggregate["content_script_executed"] or aggregate["document_start_observed"]
    )
    confirmed_dynamic_flow = any(
        bool(s.get("scenario_matched", False))
        and isinstance((s.get("evidence_score", {}) if isinstance(s.get("evidence_score", {}), dict) else {}).get("matched_evidence", []), list)
        and len((s.get("evidence_score", {}) if isinstance(s.get("evidence_score", {}), dict) else {}).get("matched_evidence", [])) > 0
        and float(s.get("scenario_evidence_score", 0.0) or 0.0) >= 0.6
        and has_dynamic_evidence
        for s in valid
    )

    any_screenshot_remote = any(_is_screenshot_or_remote_pattern(s.get("pattern_name")) for s in valid)
    if any_static_candidate and any("session" in str(s.get("pattern_name", "")).lower() for s in concrete_candidate_rows):
        risk_factors.append("session_static_candidate_detected")
    if any_static_candidate and any(
        "external_communication" in [str(x) for x in (s.get("behavior_tags", []) if isinstance(s.get("behavior_tags", []), list) else [])]
        for s in concrete_candidate_rows
    ):
        risk_factors.append("external_network_static_candidate_detected")
    if any_screenshot_remote:
        risk_factors.extend(
            [
                "screenshot_capture_api_detected",
                "browser_automation_api_detected",
                "debugger_permission_detected",
                "scripting_execute_script_detected",
                "broad_tab_access_detected",
            ]
        )

    if confirmed_dynamic_flow:
        risk_level = "CRITICAL"
        risk_score = 0.9
        reason = "Static and dynamic evidence jointly reproduced the core malicious behavior flow."
        risk_factors.extend(["confirmed_dynamic_flow", "multi_signal_corroboration", "scenario_matched", "critical_behavior_confirmed"])
    elif any_static_candidate and has_dynamic_evidence:
        any_scenario_evidence = any(float(s.get("scenario_evidence_score", 0.0) or 0.0) > 0.0 for s in valid)
        dynamic_failed = not aggregate["extension_loaded"] and not aggregate["service_worker_ready"]
        if dynamic_failed and not any_scenario_evidence and not aggregate["real_network_used"]:
            risk_level = "MEDIUM"
            risk_score = 0.45
            reason = (
                "Static risk evidence was found, but dynamic analysis failed to load the extension — "
                "observed signals are not attributable to extension behavior."
            )
            risk_factors.extend(["extension_load_failed", "dynamic_evidence_unreliable", "candidate_static_match"])
        else:
            risk_level = "HIGH"
            risk_score = 0.7
            reason = "Static risk evidence was found and partial dynamic behavior was observed, but the full scenario was not conclusively reproduced."
            risk_factors.extend(["partial_dynamic_evidence", "candidate_static_match", "dynamic_behavior_observed"])
            if aggregate["runtime_messages"] > 0:
                risk_factors.append("runtime_message_observed")
            if aggregate["network_requests"] > 0:
                risk_factors.append("network_request_observed")
            if aggregate["storage_events"] > 0:
                risk_factors.append("storage_event_observed")
            if aggregate["timers"] > 0:
                risk_factors.append("timer_event_observed")
            if aggregate["content_script_executed"]:
                risk_factors.append("content_script_executed")
            if aggregate["external_post_count"] > 0:
                risk_factors.append("external_communication_observed")
    elif any_static_candidate and dynamic_attempted and not has_dynamic_evidence:
        risk_level = "MEDIUM"
        risk_score = 0.45
        reason = "Static risk evidence was found, but no dynamic reproduction evidence was observed."
        if candidate_scenarios:
            risk_factors.append("candidate_only_static_match")
        risk_factors.extend(["zero_dynamic_evidence", "dynamic_collection_gap"])
        if timeout_attempt:
            reason = "Dynamic analysis was attempted but evidence collection was incomplete."
    elif (not any_static_candidate) and (not has_dynamic_evidence) and (not dynamic_attempted):
        risk_level = "LOW"
        risk_score = 0.15
        reason = "No concrete static evidence or dynamic behavior was observed."
        risk_factors.extend(["no_concrete_static_evidence", "zero_dynamic_evidence"])
    elif not any_static_candidate and not has_dynamic_evidence:
        risk_level = "LOW"
        risk_score = 0.1
        reason = "No meaningful static or dynamic risk evidence was observed."
        risk_factors.extend(["no_static_candidate", "zero_dynamic_evidence"])
    else:
        risk_level = "LOW"
        risk_score = 0.15
        reason = "No meaningful static or dynamic risk evidence was observed."
        risk_factors.extend(["no_static_candidate"])

    if risk_level in {"MEDIUM", "HIGH"}:
        matched_scenarios = []
    risk_escalation["reason"] = reason

    return {
        "risk_level": risk_level,
        "risk_score": risk_score,
        "reason": reason,
        "matched_scenarios": matched_scenarios,
        "candidate_scenarios": candidate_scenarios,
        "vector_candidate_scenarios": vector_candidate_scenarios,
        "top_scenario": {**top, "agent_result": compact_agent_result(top.get("agent_result", {}))} if isinstance(top, dict) else {},
        "risk_factors": sorted(set(risk_factors)),
        "risk_escalation": risk_escalation,
        "missing_evidence": missing_evidence,
        "safety_violation": False,
        "external_request_attempted": bool(aggregate["external_request_attempted"]),
        "external_request_blocked": bool(aggregate["external_request_blocked"]),
        "real_network_used": bool(aggregate["real_network_used"]),
        "intercepted_by_harness": bool(aggregate["intercepted_by_harness"]),
    }
