from __future__ import annotations

from .observation_schema import normalize_observations


def _is_emulated_target_safe_request(request: dict, execution: dict) -> bool:
    if not isinstance(request, dict):
        return False
    host = str(request.get("url_host", "")).lower()
    is_target_emulation = bool(request.get("is_target_url_emulation"))
    return (
        host in {"web.telegram.org", "accounts.google.com", "mail.google.com", "drive.google.com"}
        and is_target_emulation
        and bool(execution.get("mock_target_used", False))
        and not bool(execution.get("real_service_used", False))
        and bool(request.get("intercepted_by_harness"))
        and bool(request.get("fulfilled_by_harness"))
        and not bool(request.get("real_network_used"))
    )


def _first_actionable_unsafe_request(obs: dict) -> dict | None:
    execution = obs.get("execution", {}) if isinstance(obs.get("execution", {}), dict) else {}
    for req in obs.get("network_requests", []):
        if not isinstance(req, dict):
            continue
        if _is_emulated_target_safe_request(req, execution):
            continue
        if bool(req.get("real_network_used")) and not bool(req.get("intercepted_by_harness")):
            return req
        if str(req.get("url_category", "")).lower() == "external" and bool(req.get("real_network_used")):
            return req
    return None


# Boolean execution keys that should be OR-accumulated across all actions.
# Once any action observation marks these True, the combined result is True.
# This prevents a stale False from an early action (e.g., load_extension before Chrome
# confirms the extension is loaded) from masking a later True value.
_OR_ACCUMULATE_BOOL_KEYS: frozenset[str] = frozenset({
    "extension_loaded",
    "extension_context_launched",
    "service_worker_ready",
    "content_script_executed",
    "content_script_run_at_observed",
    "content_script_request_seen",
    "content_script_probe_attempted",
    "content_script_dom_marker_found",
    "content_script_isolated_world_detected",
    "isolated_world_context_seen",
    "manifest_match_target_url",
    "manifest_match_actual_page_url",
    "target_url_emulation_used",
    "target_local_storage_seeded_before_goto",
    "seed_extension_uuid_success",
    "page_load_completed",
    "open_mock_page_succeeded",
    "external_request_attempted",
    "external_request_blocked",
    "intercepted_by_harness",
    "cleanup_completed",
    "manifest_injection_eligible",
})


def collect_observations_from_agent_result(agent_result: dict) -> dict:
    if not isinstance(agent_result, dict):
        return normalize_observations(None)

    combined = {
        "network_requests": [],
        "runtime_messages": [],
        "storage_events": [],
        "dom_events": [],
        "timers": [],
        "execution": {
            "document_start_observed": False,
            "mock_target_used": True,
            "real_service_used": False,
            "real_secret_observed": False,
            "non_localhost_sensitive_transmission": False,
        },
    }

    for item in agent_result.get("actions_executed", []) if isinstance(agent_result.get("actions_executed", []), list) else []:
        if not isinstance(item, dict):
            continue
        obs = normalize_observations(item.get("observation"))
        combined["network_requests"].extend(obs["network_requests"])
        combined["runtime_messages"].extend(obs["runtime_messages"])
        combined["storage_events"].extend(obs["storage_events"])
        combined["dom_events"].extend(obs["dom_events"])
        combined["timers"].extend(obs["timers"])

        ex = obs["execution"]
        combined["execution"]["document_start_observed"] = combined["execution"]["document_start_observed"] or ex.get("document_start_observed", False)
        combined["execution"]["mock_target_used"] = combined["execution"]["mock_target_used"] and ex.get("mock_target_used", True)
        combined["execution"]["real_service_used"] = combined["execution"]["real_service_used"] or ex.get("real_service_used", False)
        combined["execution"]["real_secret_observed"] = combined["execution"]["real_secret_observed"] or ex.get("real_secret_observed", False)
        combined["execution"]["non_localhost_sensitive_transmission"] = (
            combined["execution"]["non_localhost_sensitive_transmission"] or ex.get("non_localhost_sensitive_transmission", False)
        )
        for key, value in ex.items():
            if key in combined["execution"]:
                # OR-accumulate boolean flags that can transition False→True across actions.
                if key in _OR_ACCUMULATE_BOOL_KEYS and isinstance(value, bool) and value:
                    combined["execution"][key] = True
                elif isinstance(value, int) and isinstance(combined["execution"].get(key), int):
                    combined["execution"][key] = max(combined["execution"][key], value)
                elif isinstance(value, str) and value and not combined["execution"].get(key):
                    combined["execution"][key] = value
                continue
            if isinstance(value, bool):
                combined["execution"][key] = bool(combined["execution"].get(key, False)) or value
            elif isinstance(value, int):
                combined["execution"][key] = max(int(combined["execution"].get(key, 0) or 0), value)
            elif isinstance(value, list):
                prev = combined["execution"].get(key, [])
                if not isinstance(prev, list):
                    prev = []
                combined["execution"][key] = prev + [v for v in value if v not in prev]
            elif value and not combined["execution"].get(key):
                combined["execution"][key] = value

    cex = combined["execution"]
    # Normalize stale error strings when the extension is confirmed loaded.
    if cex.get("extension_loaded") and cex.get("service_worker_ready"):
        cex["extension_load_error"] = ""
    # Normalize stale content-script failure fields when execution is confirmed.
    if cex.get("content_script_executed"):
        cex["content_script_not_executed_reason"] = ""
        cex["content_script_probe_attempted"] = True
    # Infer content_script_executed from runtime/storage evidence as a belt-and-suspenders check.
    # If the extension produced messages or storage events, the content script must have run.
    if not cex.get("content_script_executed") and (combined["runtime_messages"] or combined["storage_events"]):
        cex["content_script_executed"] = True
        cex["content_script_execution_inferred"] = True
        if not cex.get("content_script_probe_method"):
            cex["content_script_probe_method"] = "runtime_message_and_storage_event_inference"
        cex["content_script_not_executed_reason"] = ""
        cex["content_script_probe_attempted"] = True

    return combined


def score_scenario_evidence(
    vector_fingerprint: dict,
    selected_match: dict,
    llm_agent_result: dict | None,
    observations: dict | None,
) -> dict:
    obs = normalize_observations(observations) if observations is not None else None
    if obs is None and llm_agent_result is not None:
        obs = collect_observations_from_agent_result(llm_agent_result)

    if obs is None:
        return {
            "status": "no_observations",
            "scenario_evidence_score": 0.0,
            "matched_evidence": [],
            "missing_evidence": [],
            "safety_violation": False,
            "notes": ["No observations were provided."],
        }

    ex = obs["execution"]
    extension_load_attempted = bool(
        ex.get("extension_manifest_path")
        or ex.get("extension_load_path")
        or ex.get("extension_context_launched")
    )
    has_runtime_evidence = bool(obs["runtime_messages"]) or bool(obs["storage_events"]) or bool(obs["timers"])
    if extension_load_attempted and not bool(ex.get("extension_loaded", True)) and not has_runtime_evidence:
        return {
            "status": "ok",
            "scenario_evidence_score": 0.0,
            "matched_evidence": [],
            "missing_evidence": ["extension_not_loaded", "service_worker_not_ready", "content_script_not_executed"],
            "safety_violation": False,
            "notes": ["Extension did not load; dynamic runtime evidence collection was limited."],
        }
    unsafe_req = _first_actionable_unsafe_request(obs)
    if ex.get("real_service_used") or ex.get("real_secret_observed") or (ex.get("non_localhost_sensitive_transmission") and unsafe_req is not None) or unsafe_req is not None:
        req = unsafe_req or {}
        result = {
            "status": "safety_violation",
            "scenario_evidence_score": 0.0,
            "matched_evidence": [],
            "missing_evidence": ["safety_constraints_violated"],
            "safety_violation": True,
            "safety_violation_source": "unsafe_external_request" if unsafe_req is not None else "execution_safety_signal",
            "unsafe_request_url": req.get("url", ""),
            "unsafe_request_host": req.get("url_host", ""),
            "real_network_used": bool(req.get("real_network_used", False)),
            "intercepted_by_harness": bool(req.get("intercepted_by_harness", False)),
            "is_target_url_emulation": bool(req.get("is_target_url_emulation", False)),
            "notes": ["Unsafe execution signal detected."],
        }
        result.update(_external_attempt_summary(obs))
        result["safety_violation"] = True
        result["safety_violation_source"] = "unsafe_external_request" if unsafe_req is not None else "execution_safety_signal"
        return result

    pattern_name = (
        str(selected_match.get("pattern_name", "")).lower()
        if isinstance(selected_match, dict)
        else ""
    )
    if "session_storage" in pattern_name or "session_theft" in pattern_name:
        return _score_session_exfiltration(obs)
    if "proxy" in pattern_name or "vpn" in pattern_name:
        return _score_proxy_vpn_pattern(obs, vector_fingerprint)
    return _score_generic(obs, vector_fingerprint)


def _score_session_exfiltration(obs: dict) -> dict:
    ex = obs["execution"]
    matched = []
    missing = []

    if bool(ex.get("content_script_executed", False)):
        matched.append("content_script_execution")
    else:
        missing.append("content_script_execution")

    if ex.get("document_start_observed"):
        matched.append("early_injection")
    else:
        missing.append("early_injection")

    storage_ok = any(
        isinstance(s, dict)
        and str(s.get("storage_area", "")).lower() == "localstorage"
        and str(s.get("operation", "")).lower() == "read"
        and any(str(k).lower() in {"session", "auth", "user_id"} for k in s.get("keywords", []))
        for s in obs["storage_events"]
    )
    if storage_ok:
        matched.append("page_storage_exfiltration")
    else:
        missing.append("page_storage_exfiltration")

    msg_bridge = any(
        isinstance(m, dict) and (
            m.get("direction") == "content_script_to_background"
            or str(m.get("action", "")).lower() == "save_session"
        )
        for m in obs["runtime_messages"]
    )
    if msg_bridge:
        matched.append("message_passing_bridge")
    else:
        missing.append("message_passing_bridge")

    localhost_post = any(
        isinstance(n, dict)
        and str(n.get("url_category", "")).lower() == "localhost"
        and str(n.get("method", "")).upper() == "POST"
        for n in obs["network_requests"]
    )
    external_blocked = bool(ex.get("external_request_blocked", False)) or bool(ex.get("external_request_attempted", False))
    if localhost_post or external_blocked:
        matched.append("external_communication")
    else:
        missing.append("external_communication")

    has_timer = any(isinstance(t, dict) and str(t.get("api", "")) in {"setInterval", "setTimeout", "chrome.alarms"} for t in obs["timers"])
    runtime_save_session_count = sum(
        1
        for m in obs["runtime_messages"]
        if isinstance(m, dict) and str(m.get("action", "")).lower() == "save_session"
    )
    save_session_post_count = sum(
        1
        for n in obs["network_requests"]
        if isinstance(n, dict) and str(n.get("method", "")).upper() == "POST" and bool(n.get("is_save_session_endpoint"))
    )
    external_post_count = sum(
        1
        for n in obs["network_requests"]
        if isinstance(n, dict) and str(n.get("method", "")).upper() == "POST" and str(n.get("url_category", "")).lower() == "external"
    )
    sensitive_storage_reads = sum(
        1
        for s in obs["storage_events"]
        if isinstance(s, dict)
        and str(s.get("storage_area", "")).lower() == "localstorage"
        and str(s.get("operation", "")).lower() == "read"
        and any(str(k).lower() in {"session", "auth", "user_id", "token"} for k in s.get("keywords", []))
    )
    has_bridge_or_external = msg_bridge or localhost_post or external_blocked or external_post_count > 0
    repeated_evidence = (
        has_timer
        or save_session_post_count >= 2
        or external_post_count >= 2
        or runtime_save_session_count >= 2
        or (sensitive_storage_reads >= 2 and has_bridge_or_external)
    )
    if repeated_evidence:
        matched.append("repeated_exfiltration")
    else:
        missing.append("repeated_exfiltration")

    dummy_in_network = any(isinstance(n, dict) and bool(n.get("body_contains_dummy_secret", False)) for n in obs["network_requests"])
    dummy_in_message = any(isinstance(m, dict) and bool(m.get("contains_dummy_secret", False)) for m in obs["runtime_messages"])
    if dummy_in_network or dummy_in_message:
        matched.append("credential_or_token_exfiltration_pattern")
    else:
        missing.append("credential_or_token_exfiltration_pattern")

    score = len(matched) / 7.0
    result = {
        "status": "ok",
        "scenario_evidence_score": score,
        "matched_evidence": matched,
        "missing_evidence": missing,
        "safety_violation": False,
        "notes": [f"Matched {len(matched)} of 7 checks.", "target-url emulation traffic is excluded from safety violation when intercepted by harness."],
    }
    result.update(_external_attempt_summary(obs))
    return result


def _score_proxy_vpn_pattern(obs: dict, vector_fingerprint: dict) -> dict:
    # VPN/proxy 계열은 패턴이 다양한 편이라 범용 평가를 사용한다.
    return _score_generic(obs, vector_fingerprint)


def _score_generic(obs: dict, vector_fingerprint: dict) -> dict:
    matched = []
    missing = []
    ex = obs.get("execution", {}) if isinstance(obs.get("execution", {}), dict) else {}

    content_script_ok = bool(ex.get("content_script_executed", False))
    if content_script_ok:
        matched.append("content_script_execution")
    else:
        missing.append("content_script_execution")

    has_input_change = any(
        isinstance(d, dict) and str(d.get("event", "")).lower() == "input_change_simulated"
        for d in obs["dom_events"]
    )
    if has_input_change and content_script_ok:
        matched.append("input_change_event")
    else:
        missing.append("input_change_event")

    has_external_net = any(
        isinstance(n, dict) and str(n.get("url_category", "")).lower() == "external"
        for n in obs["network_requests"]
    ) or bool(ex.get("external_request_blocked", False)) or bool(ex.get("external_request_attempted", False))
    if has_external_net:
        matched.append("external_communication")
    else:
        missing.append("external_communication")

    has_bridge = any(isinstance(m, dict) for m in obs["runtime_messages"])
    if has_bridge:
        matched.append("message_passing_bridge")
    else:
        missing.append("message_passing_bridge")

    has_storage = bool(obs["storage_events"])
    if has_storage:
        matched.append("storage_access")
    else:
        missing.append("storage_access")

    has_timer = any(isinstance(t, dict) for t in obs["timers"])
    if has_timer:
        matched.append("periodic_execution")
    else:
        missing.append("periodic_execution")

    total_observed = (
        len(obs["network_requests"])
        + len(obs["runtime_messages"])
        + len(obs["storage_events"])
        + len(obs["dom_events"])
        + len(obs["timers"])
    )
    if total_observed == 0:
        score = 0.0
    else:
        score = len(matched) / max(len(matched) + len(missing), 1)

    result = {
        "status": "ok",
        "scenario_evidence_score": score,
        "matched_evidence": matched,
        "missing_evidence": missing,
        "safety_violation": False,
        "notes": [f"Generic scorer (dynamic-only): matched {len(matched)} of {len(matched) + len(missing)}"],
    }
    result.update(_external_attempt_summary(obs))
    return result


def _external_attempt_summary(obs: dict) -> dict:
    ex = obs.get("execution", {}) if isinstance(obs.get("execution", {}), dict) else {}
    external_requests = [
        req
        for req in obs.get("network_requests", [])
        if isinstance(req, dict) and str(req.get("url_category", "")).lower() == "external"
    ]
    blocked = [
        req
        for req in external_requests
        if bool(req.get("intercepted_by_harness")) and (bool(req.get("fulfilled_by_harness")) or bool(req.get("aborted_by_harness")))
    ]
    real = [req for req in external_requests if bool(req.get("real_network_used")) and not bool(req.get("intercepted_by_harness"))]
    first = (real or blocked or external_requests or [{}])[0]
    return {
        "external_request_attempted": bool(external_requests) or bool(ex.get("external_request_attempted", False)),
        "external_request_blocked": bool(blocked) or bool(ex.get("external_request_blocked", False)),
        "external_request_count": int(ex.get("external_request_count", len(external_requests)) or len(external_requests)),
        "blocked_external_request_count": int(ex.get("blocked_external_request_count", len(blocked)) or len(blocked)),
        "blocked_external_requests": ex.get("blocked_external_requests", [])
        if isinstance(ex.get("blocked_external_requests", []), list)
        else [],
        "real_network_used": bool(real) or bool(ex.get("real_network_used", False)),
        "intercepted_by_harness": bool(blocked) or bool(ex.get("intercepted_by_harness", False)),
        "unsafe_request_url": str(first.get("url", "") or ex.get("unsafe_request_url", "")),
        "unsafe_request_host": str(first.get("url_host", "") or ex.get("unsafe_request_host", "")),
    }
