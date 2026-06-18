from __future__ import annotations

import json


def _pick_event_fields(ev: dict) -> dict:
    if not isinstance(ev, dict):
        return {}
    out = {}
    for k in (
        "storage_area",
        "operation",
        "key",
        "method",
        "url_category",
        "endpoint_keywords",
        "body_contains_dummy_secret",
        "intercepted_by_harness",
    ):
        if k in ev:
            out[k] = ev.get(k)
    return out


def dedupe_events(events: list[dict], max_sample: int = 2) -> tuple[int, list[dict]]:
    if not isinstance(events, list):
        return 0, []
    total = len(events)
    seen: set[tuple] = set()
    sample: list[dict] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        sig = (
            str(ev.get("storage_area", "")),
            str(ev.get("operation", "")),
            str(ev.get("key", "")),
            str(ev.get("method", "")),
            str(ev.get("url_category", "")),
            tuple(sorted(str(x) for x in (ev.get("endpoint_keywords", []) if isinstance(ev.get("endpoint_keywords", []), list) else []))),
        )
        if sig in seen:
            continue
        seen.add(sig)
        if len(sample) < max_sample:
            sample.append(_pick_event_fields(ev))
    return total, sample


def compact_observation(observation: dict) -> dict:
    if not isinstance(observation, dict):
        return {}
    obs = dict(observation)
    keys = ["network_requests", "runtime_messages", "storage_events", "dom_events", "timers"]
    for k in keys:
        total, sample = dedupe_events(obs.get(k, []), max_sample=2)
        summary = {"total": total, "sample": sample}
        if k == "network_requests":
            # richer network debug summary
            summary["sample"] = []
            seen = set()
            for req in obs.get(k, []):
                if not isinstance(req, dict):
                    continue
                sig = (
                    str(req.get("method", "")),
                    str(req.get("url", "")),
                    str(req.get("url_host", "")),
                    str(req.get("url_path", "")),
                )
                if sig in seen:
                    continue
                seen.add(sig)
                summary["sample"].append(
                    {
                        "method": req.get("method"),
                        "url": req.get("url"),
                        "url_host": req.get("url_host"),
                        "url_path": req.get("url_path"),
                        "resource_type": req.get("resource_type"),
                        "is_mock_receiver": req.get("is_mock_receiver"),
                        "is_save_session_endpoint": req.get("is_save_session_endpoint"),
                        "fulfilled_by_harness": req.get("fulfilled_by_harness"),
                        "aborted_by_harness": req.get("aborted_by_harness"),
                        "is_target_url_emulation": req.get("is_target_url_emulation"),
                        "real_network_used": req.get("real_network_used"),
                        "intercepted_by_harness": req.get("intercepted_by_harness"),
                        "post_data_preview": req.get("post_data_preview"),
                        "body_contains_dummy_secret": req.get("body_contains_dummy_secret"),
                    }
                )
                if len(summary["sample"]) >= 2:
                    break
        if k == "storage_events":
            unique_keys_all = []
            for item in obs.get(k, []):
                if isinstance(item, dict) and item.get("key"):
                    unique_keys_all.append(str(item["key"]))
            unique_keys_sorted = sorted(set(unique_keys_all))
            summary["unique_key_count"] = len(unique_keys_sorted)
            summary["unique_keys"] = unique_keys_sorted[:20]
        obs[f"{k}_summary"] = summary
        obs.pop(k, None)
    return obs


def compact_agent_result(agent_result: dict) -> dict:
    if not isinstance(agent_result, dict):
        return {}
    actions = agent_result.get("actions_executed", [])
    actions_count = len(actions) if isinstance(actions, list) else 0
    observation_totals = {
        "network_requests": 0,
        "runtime_messages": 0,
        "storage_events": 0,
        "dom_events": 0,
        "timers": 0,
        "document_start_observed": False,
        "mock_target_used": True,
        "real_service_used": False,
        "content_script_executed": False,
        "seed_extension_uuid_success": False,
        "seed_extension_uuid_error": "",
        "route_matched_save_session_endpoint": 0,
        "target_local_storage_seeded_before_goto": False,
        "actual_page_url": "",
        "expected_target_url": "",
        "extension_loaded": False,
        "extension_id": "",
        "service_worker_ready": False,
        "service_worker_url": "",
        "manifest_match_target_url": True,
        "content_script_probe_method": "",
        "content_script_files_expected": [],
        "content_script_files_observed": [],
        "extension_target_original": "",
        "extension_unpacked_dir": "",
        "extension_load_path": "",
        "extension_manifest_path": "",
        "extension_manifest_exists": False,
        "extension_context_launched": False,
        "extension_load_error": "",
        "extension_load_warning": "",
        "browser_launch_args_sanitized": [],
        "used_launch_persistent_context": False,
        "headless": False,
        "headless_source": "",
        "dynamic_harness_headless_env": "",
        "display_env": "",
        "xvfb_available": False,
        "headed_supported": False,
        "launch_args_removed": [],
        "service_worker_wait_timeout_ms": 0,
        "service_worker_count": 0,
        "service_worker_urls": [],
        "cleanup_started": False,
        "cleanup_completed": False,
        "cleanup_error": "",
        "cleanup_closed_context": False,
        "cleanup_stopped_playwright": False,
        "cleanup_removed_user_data_dir": False,
        "cleanup_removed_unpacked_dir": False,
        "cleanup_removed_user_data_dir_not_applicable": False,
        "cleanup_removed_unpacked_dir_not_applicable": False,
        "real_network_used": False,
        "intercepted_by_harness": False,
        "external_request_attempted": False,
        "external_request_blocked": False,
        "external_request_count": 0,
        "blocked_external_request_count": 0,
        "blocked_external_requests": [],
        "external_request_failed": False,
        "external_request_block_source": "",
        "external_request_outcome": "",
        "unsafe_request_url": "",
        "unsafe_request_host": "",
        "content_script_not_executed_reason": "",
        "content_script_probe_warning": "",
        "page_load_error": "",
        "page_load_started": False,
        "page_load_completed": False,
        "open_mock_page_attempted": False,
        "open_mock_page_succeeded": False,
        "content_script_probe_attempted": False,
        "page_response_status": None,
        "page_load_warning": "",
        "goto_called": False,
        "goto_completed": False,
        "wait_for_load_state_called": False,
        "wait_for_load_state_completed": False,
        "wait_for_load_state_error": "",
        "mock_server_check_attempted": False,
        "mock_server_autostart_enabled": False,
        "mock_server_autostarted": False,
        "mock_server_host": "",
        "mock_server_port": 0,
        "mock_server_url": "",
        "mock_server_reachable": False,
        "mock_server_status_code": None,
        "mock_server_error": "",
        "mock_server_stopped": False,
        "mock_server_stop_error": "",
        "dynamic_analysis_timeout": False,
        "playwright_worker_thread_name": "",
        "playwright_worker_started": False,
        "playwright_worker_running_loop": False,
        "playwright_worker_shutdown_completed": False,
    }
    recent_actions: list[dict] = []
    if isinstance(actions, list):
        save_session_post_count = 0
        localhost_post_count = 0
        external_post_count = 0
        extension_resource_request_count = 0
        web_telegram_request_count = 0
        runtime_save_session_message_count = 0
        seen_network_requests: set[tuple] = set()
        for row in actions:
            if not isinstance(row, dict):
                continue
            obs = row.get("observation", {})
            if not isinstance(obs, dict):
                continue
            for k in ("runtime_messages", "storage_events", "dom_events", "timers"):
                observation_totals[k] += len(obs.get(k, [])) if isinstance(obs.get(k, []), list) else 0
            for msg in obs.get("runtime_messages", []) if isinstance(obs.get("runtime_messages", []), list) else []:
                if isinstance(msg, dict) and str(msg.get("action", "")).lower() == "save_session":
                    runtime_save_session_message_count += 1
            for req in obs.get("network_requests", []) if isinstance(obs.get("network_requests", []), list) else []:
                if not isinstance(req, dict):
                    continue
                method = str(req.get("method", "")).upper()
                host = str(req.get("url_host", "")).lower()
                path = str(req.get("url_path", "")).lower()
                rtype = str(req.get("resource_type", "")).lower()
                sig = (
                    method,
                    str(req.get("url", "")),
                    str(req.get("post_data_preview", "")),
                    rtype,
                )
                if sig in seen_network_requests:
                    continue
                seen_network_requests.add(sig)
                observation_totals["network_requests"] += 1
                if method == "POST" and "save_session.php" in path:
                    save_session_post_count += 1
                if method == "POST" and str(req.get("url_category", "")).lower() == "localhost":
                    localhost_post_count += 1
                if method == "POST" and str(req.get("url_category", "")).lower() == "external":
                    external_post_count += 1
                if host.startswith("chrome-extension") or rtype in {"script", "serviceworker"}:
                    extension_resource_request_count += 1
                if "web.telegram.org" in host:
                    web_telegram_request_count += 1
            ex = obs.get("execution", {})
            if isinstance(ex, dict):
                observation_totals["document_start_observed"] = observation_totals["document_start_observed"] or bool(
                    ex.get("document_start_observed", False)
                )
                observation_totals["mock_target_used"] = observation_totals["mock_target_used"] and bool(ex.get("mock_target_used", True))
                observation_totals["real_service_used"] = observation_totals["real_service_used"] or bool(ex.get("real_service_used", False))
                observation_totals["content_script_executed"] = observation_totals["content_script_executed"] or bool(
                    ex.get("content_script_executed", False)
                )
                observation_totals["seed_extension_uuid_success"] = observation_totals["seed_extension_uuid_success"] or bool(
                    ex.get("seed_extension_uuid_success", False)
                )
                if not observation_totals.get("seed_extension_uuid_error"):
                    observation_totals["seed_extension_uuid_error"] = str(ex.get("seed_extension_uuid_error", "") or "")
                observation_totals["route_matched_save_session_endpoint"] = max(
                    int(observation_totals["route_matched_save_session_endpoint"]),
                    int(ex.get("route_matched_save_session_endpoint", 0) or 0),
                )
                observation_totals["target_local_storage_seeded_before_goto"] = observation_totals["target_local_storage_seeded_before_goto"] or bool(
                    ex.get("target_local_storage_seeded_before_goto", False)
                )
                if not observation_totals.get("actual_page_url"):
                    observation_totals["actual_page_url"] = str(ex.get("actual_page_url", "") or "")
                if not observation_totals.get("expected_target_url"):
                    observation_totals["expected_target_url"] = str(ex.get("expected_target_url", "") or "")
                observation_totals["extension_loaded"] = observation_totals["extension_loaded"] or bool(ex.get("extension_loaded", False))
                if not observation_totals.get("extension_id"):
                    observation_totals["extension_id"] = str(ex.get("extension_id", "") or "")
                observation_totals["service_worker_ready"] = observation_totals["service_worker_ready"] or bool(ex.get("service_worker_ready", False))
                if not observation_totals.get("service_worker_url"):
                    observation_totals["service_worker_url"] = str(ex.get("service_worker_url", "") or "")
                observation_totals["manifest_match_target_url"] = observation_totals["manifest_match_target_url"] or bool(
                    ex.get("manifest_match_target_url", False)
                )
                if not observation_totals.get("content_script_probe_method"):
                    observation_totals["content_script_probe_method"] = str(ex.get("content_script_probe_method", "") or "")
                if not observation_totals.get("content_script_files_expected"):
                    observation_totals["content_script_files_expected"] = (
                        ex.get("content_script_files_expected", [])
                        if isinstance(ex.get("content_script_files_expected", []), list)
                        else []
                    )
                observed = ex.get("content_script_files_observed", [])
                if isinstance(observed, list):
                    merged = set(observation_totals.get("content_script_files_observed", []) or [])
                    merged.update(str(x) for x in observed)
                    observation_totals["content_script_files_observed"] = sorted(merged)
                for k in (
                    "extension_target_original",
                    "extension_unpacked_dir",
                    "extension_load_path",
                    "extension_manifest_path",
                    "extension_load_error",
                    "extension_load_warning",
                    "cleanup_error",
                    "unsafe_request_url",
                    "unsafe_request_host",
                    "page_load_error",
                    "mock_server_error",
                    "mock_server_host",
                    "mock_server_url",
                    "mock_server_stop_error",
                    "external_request_block_source",
                    "external_request_outcome",
                    "content_script_probe_warning",
                    "page_load_warning",
                    "wait_for_load_state_error",
                ):
                    if not observation_totals.get(k):
                        observation_totals[k] = str(ex.get(k, "") or "")
                reason = str(ex.get("content_script_not_executed_reason", "") or "")
                if reason and (
                    not observation_totals.get("content_script_not_executed_reason")
                    or observation_totals.get("content_script_not_executed_reason") == "page_not_loaded"
                ):
                    observation_totals["content_script_not_executed_reason"] = reason
                for k in (
                    "extension_manifest_exists",
                    "extension_context_launched",
                    "used_launch_persistent_context",
                    "xvfb_available",
                    "headed_supported",
                    "cleanup_started",
                    "cleanup_completed",
                    "cleanup_closed_context",
                    "cleanup_stopped_playwright",
                    "cleanup_removed_user_data_dir",
                    "cleanup_removed_unpacked_dir",
                    "cleanup_removed_user_data_dir_not_applicable",
                    "cleanup_removed_unpacked_dir_not_applicable",
                    "real_network_used",
                    "intercepted_by_harness",
                    "external_request_attempted",
                    "external_request_blocked",
                    "external_request_failed",
                    "page_load_started",
                    "page_load_completed",
                    "open_mock_page_attempted",
                    "open_mock_page_succeeded",
                    "content_script_probe_attempted",
                    "goto_called",
                    "goto_completed",
                    "wait_for_load_state_called",
                    "wait_for_load_state_completed",
                    "mock_server_check_attempted",
                    "mock_server_autostart_enabled",
                    "mock_server_autostarted",
                    "mock_server_reachable",
                    "mock_server_stopped",
                    "dynamic_analysis_timeout",
                ):
                    observation_totals[k] = bool(observation_totals.get(k, False)) or bool(ex.get(k, False))
                for k in ("page_response_status", "mock_server_status_code", "mock_server_port"):
                    if (observation_totals.get(k) in {None, 0}) and ex.get(k) is not None:
                        observation_totals[k] = ex.get(k)
                for k in ("external_request_count", "blocked_external_request_count"):
                    observation_totals[k] = max(
                        int(observation_totals.get(k, 0) or 0),
                        int(ex.get(k, 0) or 0),
                    )
                blocked = ex.get("blocked_external_requests", [])
                if isinstance(blocked, list):
                    prev = observation_totals.get("blocked_external_requests", [])
                    if not isinstance(prev, list):
                        prev = []
                    for item in blocked:
                        if item not in prev and len(prev) < 20:
                            prev.append(item)
                    observation_totals["blocked_external_requests"] = prev
                for k in ("headless_source", "dynamic_harness_headless_env", "display_env"):
                    if not observation_totals.get(k):
                        observation_totals[k] = str(ex.get(k, "") or "")
                if ex.get("headless_source") or ex.get("dynamic_harness_headless_env") or ex.get("extension_context_launched"):
                    observation_totals["headless"] = bool(ex.get("headless", False))
                if not observation_totals.get("browser_launch_args_sanitized"):
                    observation_totals["browser_launch_args_sanitized"] = (
                        ex.get("browser_launch_args_sanitized", [])
                        if isinstance(ex.get("browser_launch_args_sanitized", []), list)
                        else []
                    )
                if not observation_totals.get("launch_args_removed"):
                    observation_totals["launch_args_removed"] = (
                        ex.get("launch_args_removed", [])
                        if isinstance(ex.get("launch_args_removed", []), list)
                        else []
                    )
                observation_totals["service_worker_wait_timeout_ms"] = max(
                    int(observation_totals.get("service_worker_wait_timeout_ms", 0) or 0),
                    int(ex.get("service_worker_wait_timeout_ms", 0) or 0),
                )
                observation_totals["service_worker_count"] = max(
                    int(observation_totals.get("service_worker_count", 0) or 0),
                    int(ex.get("service_worker_count", 0) or 0),
                )
                sw_urls = ex.get("service_worker_urls", [])
                if isinstance(sw_urls, list):
                    merged_sw = set(observation_totals.get("service_worker_urls", []) or [])
                    merged_sw.update(str(x) for x in sw_urls)
                    observation_totals["service_worker_urls"] = sorted(merged_sw)
                if not observation_totals.get("playwright_worker_thread_name"):
                    observation_totals["playwright_worker_thread_name"] = str(ex.get("playwright_worker_thread_name", "") or "")
                observation_totals["playwright_worker_started"] = observation_totals["playwright_worker_started"] or bool(
                    ex.get("playwright_worker_started", False)
                )
                observation_totals["playwright_worker_running_loop"] = observation_totals["playwright_worker_running_loop"] or bool(
                    ex.get("playwright_worker_running_loop", False)
                )
                observation_totals["playwright_worker_shutdown_completed"] = observation_totals["playwright_worker_shutdown_completed"] or bool(
                    ex.get("playwright_worker_shutdown_completed", False)
                )
        if observation_totals.get("extension_loaded") and observation_totals.get("service_worker_ready"):
            if observation_totals.get("extension_load_error"):
                observation_totals["extension_load_warning"] = observation_totals.get("extension_load_warning") or observation_totals.get("extension_load_error")
            observation_totals["extension_load_error"] = ""
        observation_totals["save_session_post_count"] = save_session_post_count
        observation_totals["localhost_post_count"] = localhost_post_count
        observation_totals["external_post_count"] = external_post_count
        observation_totals["extension_resource_request_count"] = extension_resource_request_count
        observation_totals["web_telegram_request_count"] = web_telegram_request_count
        observation_totals["runtime_save_session_message_count"] = runtime_save_session_message_count

        key_action_names = {
            "open_mock_page",
            "wait_for_page_load",
            "probe_content_script_execution",
        }
        seen_recent = set()
        for row in actions:
            if not isinstance(row, dict):
                continue
            action = row.get("action", {})
            action_name = action.get("action") if isinstance(action, dict) else None
            if action_name not in key_action_names or action_name in seen_recent:
                continue
            ar = row.get("action_result", {}) if isinstance(row.get("action_result"), dict) else {}
            recent_actions.append(
                {
                    "action": action_name,
                    "target": (observation_totals.get("expected_target_url") or action.get("target")) if isinstance(action, dict) else None,
                    "attempted": bool(ar.get("attempted", True)),
                    "succeeded": bool(ar.get("succeeded", False)),
                    "error": str(ar.get("error", "") or ""),
                }
            )
            seen_recent.add(action_name)
        for row in actions[-3:]:
            if not isinstance(row, dict):
                continue
            action = row.get("action", {})
            action_name = action.get("action") if isinstance(action, dict) else None
            sig = (action_name, action.get("target") if isinstance(action, dict) else None)
            if any((r.get("action"), r.get("target")) == sig for r in recent_actions):
                continue
            ar = row.get("action_result", {}) if isinstance(row.get("action_result"), dict) else {}
            recent_actions.append(
                {
                    "action": action_name,
                    "target": (observation_totals.get("expected_target_url") or action.get("target")) if isinstance(action, dict) else None,
                    "attempted": bool(ar.get("attempted", True)),
                    "succeeded": bool(ar.get("succeeded", False)),
                    "error": str(ar.get("error", "") or ""),
                }
            )
        recent_actions = recent_actions[-8:]
    return {
        "status": agent_result.get("status"),
        "final_assessment": agent_result.get("final_assessment", {}),
        "actions_count": actions_count,
        "observation_totals": observation_totals,
        "recent_actions": recent_actions,
        "error": agent_result.get("error"),
        "error_type": agent_result.get("error_type"),
        "dynamic_analysis_timeout": bool(agent_result.get("error_type") == "DynamicAnalysisTimeout"),
    }


def _compact_selected_match(match: dict) -> dict:
    if not isinstance(match, dict):
        return {}
    payload = match.get("payload", {}) if isinstance(match.get("payload", {}), dict) else {}
    vf = payload.get("vector_fingerprint", {}) if isinstance(payload.get("vector_fingerprint", {}), dict) else {}
    behavior_tags = vf.get("behavior_tags", []) if isinstance(vf.get("behavior_tags", []), list) else []
    predicted_flows = vf.get("predicted_flows", []) if isinstance(vf.get("predicted_flows", []), list) else []
    static_signals = vf.get("static_code_signals", {}) if isinstance(vf.get("static_code_signals", {}), dict) else {}
    signals_count = sum(len(v) for v in static_signals.values() if isinstance(v, dict))
    return {
        "pattern_name": match.get("pattern_name") or payload.get("pattern_name"),
        "doc_ref": match.get("doc_ref") or payload.get("doc_ref"),
        "vector_similarity": match.get("vector_similarity", match.get("score", match.get("similarity"))),
        "final_score": match.get("final_score"),
        "static_capability_score": match.get("static_capability_score", 0.0),
        "concrete_api_evidence": match.get("concrete_api_evidence", []),
        "dynamic_evidence_score": match.get("dynamic_evidence_score", 0.0),
        "negative_penalties": match.get("negative_penalties", []),
        "candidate_only": bool(match.get("candidate_only", True)),
        "matched_behavior_tags": behavior_tags[:10],
        "matched_flows_count": len(predicted_flows),
        "matched_signals_count": signals_count,
    }


def _compact_scenario_result(row: dict) -> dict:
    if not isinstance(row, dict):
        return {}
    out = {
        "pattern_name": row.get("pattern_name"),
        "doc_ref": row.get("doc_ref"),
        "rerank_final_score": row.get("rerank_final_score"),
        "static_evidence_score": row.get("static_evidence_score"),
        "scenario_evidence_score": row.get("scenario_evidence_score"),
        "dynamic_evidence_score": row.get("dynamic_evidence_score"),
        "llm_assessment_score": row.get("llm_assessment_score"),
        "final_dynamic_rag_score": row.get("final_dynamic_rag_score"),
        "concrete_api_evidence": row.get("concrete_api_evidence", []),
        "negative_penalties": row.get("negative_penalties", []),
        "evidence_score": row.get("evidence_score", {}),
        "behavior_tags": row.get("behavior_tags", []),
        "match_status": row.get("match_status", "candidate_only"),
        "scenario_matched": bool(row.get("scenario_matched", False)),
        "candidate_only": bool(row.get("candidate_only", not bool(row.get("scenario_matched", False)))),
        "external_request_attempted": bool(row.get("external_request_attempted", False)),
        "external_request_blocked": bool(row.get("external_request_blocked", False)),
        "real_network_used": bool(row.get("real_network_used", False)),
        "intercepted_by_harness": bool(row.get("intercepted_by_harness", False)),
        "agent_result": compact_agent_result(row.get("agent_result", {})),
    }
    ar = out.get("agent_result", {}) if isinstance(out.get("agent_result", {}), dict) else {}
    totals = ar.get("observation_totals", {}) if isinstance(ar.get("observation_totals", {}), dict) else {}
    for k in (
        "save_session_post_count",
        "localhost_post_count",
        "external_post_count",
        "extension_resource_request_count",
        "web_telegram_request_count",
        "runtime_save_session_message_count",
        "content_script_executed",
        "seed_extension_uuid_success",
        "seed_extension_uuid_error",
        "route_matched_save_session_endpoint",
        "target_local_storage_seeded_before_goto",
        "actual_page_url",
        "expected_target_url",
        "extension_loaded",
        "extension_id",
        "service_worker_ready",
        "service_worker_url",
        "manifest_match_target_url",
        "content_script_probe_method",
        "content_script_files_expected",
        "content_script_files_observed",
        "extension_target_original",
        "extension_unpacked_dir",
        "extension_load_path",
        "extension_manifest_path",
        "extension_manifest_exists",
        "extension_context_launched",
        "extension_load_error",
        "extension_load_warning",
        "browser_launch_args_sanitized",
        "used_launch_persistent_context",
        "headless",
        "headless_source",
        "dynamic_harness_headless_env",
        "display_env",
        "xvfb_available",
        "headed_supported",
        "service_worker_wait_timeout_ms",
        "service_worker_count",
        "service_worker_urls",
        "launch_args_removed",
        "cleanup_started",
        "cleanup_completed",
        "cleanup_error",
        "cleanup_closed_context",
        "cleanup_stopped_playwright",
        "cleanup_removed_user_data_dir",
        "cleanup_removed_unpacked_dir",
        "cleanup_removed_user_data_dir_not_applicable",
        "cleanup_removed_unpacked_dir_not_applicable",
        "real_network_used",
        "intercepted_by_harness",
        "external_request_attempted",
        "external_request_blocked",
        "external_request_count",
        "blocked_external_request_count",
        "blocked_external_requests",
        "external_request_failed",
        "external_request_block_source",
        "external_request_outcome",
        "unsafe_request_url",
        "unsafe_request_host",
        "content_script_not_executed_reason",
        "content_script_probe_warning",
        "page_load_error",
        "page_load_started",
        "page_load_completed",
        "open_mock_page_attempted",
        "open_mock_page_succeeded",
        "content_script_probe_attempted",
        "page_response_status",
        "page_load_warning",
        "goto_called",
        "goto_completed",
        "wait_for_load_state_called",
        "wait_for_load_state_completed",
        "wait_for_load_state_error",
        "mock_server_check_attempted",
        "mock_server_autostart_enabled",
        "mock_server_autostarted",
        "mock_server_host",
        "mock_server_port",
        "mock_server_url",
        "mock_server_reachable",
        "mock_server_status_code",
        "mock_server_error",
        "mock_server_stopped",
        "mock_server_stop_error",
        "dynamic_analysis_timeout",
        "playwright_worker_thread_name",
        "playwright_worker_started",
        "playwright_worker_running_loop",
        "playwright_worker_shutdown_completed",
    ):
        if k in totals:
            out[k] = totals.get(k)
    if row.get("error") is not None:
        out["error"] = row.get("error")
    if row.get("error_type") is not None:
        out["error_type"] = row.get("error_type")
    if row.get("traceback_tail") is not None:
        out["traceback_tail"] = row.get("traceback_tail")
    if "risk_factors" in row:
        out["risk_factors"] = row.get("risk_factors")
    return out


def _compact_final_risk(final_risk: dict) -> dict:
    if not isinstance(final_risk, dict):
        return {}
    top = final_risk.get("top_scenario", {}) if isinstance(final_risk.get("top_scenario", {}), dict) else {}
    top_summary = {
        "pattern_name": top.get("pattern_name"),
        "doc_ref": top.get("doc_ref"),
        "rerank_final_score": top.get("rerank_final_score"),
        "scenario_evidence_score": top.get("scenario_evidence_score"),
        "llm_assessment_score": top.get("llm_assessment_score"),
        "final_dynamic_rag_score": top.get("final_dynamic_rag_score"),
    }
    rerank_top = (
        final_risk.get("rerank_top_scenario", {})
        if isinstance(final_risk.get("rerank_top_scenario", {}), dict)
        else {}
    )
    rerank_top_summary = {
        "pattern_name": rerank_top.get("pattern_name"),
        "doc_ref": rerank_top.get("doc_ref"),
        "rerank_final_score": rerank_top.get("rerank_final_score"),
        "concrete_api_evidence": rerank_top.get("concrete_api_evidence", []),
    }
    dynamic_top = (
        final_risk.get("dynamic_top_scenario", {})
        if isinstance(final_risk.get("dynamic_top_scenario", {}), dict)
        else top
    )
    dynamic_top_summary = {
        "pattern_name": dynamic_top.get("pattern_name"),
        "doc_ref": dynamic_top.get("doc_ref"),
        "rerank_final_score": dynamic_top.get("rerank_final_score"),
        "scenario_evidence_score": dynamic_top.get("scenario_evidence_score"),
        "llm_assessment_score": dynamic_top.get("llm_assessment_score"),
        "final_dynamic_rag_score": dynamic_top.get("final_dynamic_rag_score"),
    }
    out = {
        "risk_level": final_risk.get("risk_level"),
        "risk_score": final_risk.get("risk_score"),
        "reason": final_risk.get("reason"),
        "matched_scenarios": final_risk.get("matched_scenarios", []),
        "candidate_scenarios": final_risk.get("candidate_scenarios", []),
        "vector_candidate_scenarios": final_risk.get("vector_candidate_scenarios", []),
        "risk_factors": final_risk.get("risk_factors", []),
        "risk_escalation": final_risk.get("risk_escalation", {}),
        "missing_evidence": final_risk.get("missing_evidence", []),
        "safety_violation": final_risk.get("safety_violation", False),
        "external_request_attempted": final_risk.get("external_request_attempted", False),
        "external_request_blocked": final_risk.get("external_request_blocked", False),
        "real_network_used": final_risk.get("real_network_used", False),
        "intercepted_by_harness": final_risk.get("intercepted_by_harness", False),
        "top_scenario_summary": top_summary,
        "rerank_top_scenario_summary": rerank_top_summary,
        "dynamic_top_scenario_summary": dynamic_top_summary,
    }
    if "error_summary" in final_risk:
        out["error_summary"] = final_risk.get("error_summary")
    return out


def compact_dynamic_rag_result(result: dict) -> dict:
    if not isinstance(result, dict):
        return {}
    selected_matches = result.get("selected_matches", [])
    scenario_results = result.get("scenario_results", [])
    return {
        "status": result.get("status"),
        "final_risk": _compact_final_risk(result.get("final_risk", {})),
        "selected_matches_summary": [
            _compact_selected_match(m) for m in selected_matches if isinstance(m, dict)
        ] if isinstance(selected_matches, list) else [],
        "scenario_results_summary": [
            _compact_scenario_result(s) for s in scenario_results if isinstance(s, dict)
        ] if isinstance(scenario_results, list) else [],
        "notes": result.get("notes", []),
    }


def compact_result_json_line(compact_result: dict) -> str:
    return json.dumps(compact_result, ensure_ascii=False, separators=(",", ":"))


def compact_result_one_line_summary(compact_result: dict) -> str:
    if not isinstance(compact_result, dict):
        return "Dynamic RAG summary: unavailable"
    fr = compact_result.get("final_risk", {}) if isinstance(compact_result.get("final_risk", {}), dict) else {}
    top = fr.get("top_scenario_summary", {}) if isinstance(fr.get("top_scenario_summary", {}), dict) else {}
    scenarios = compact_result.get("scenario_results_summary", [])
    first = scenarios[0] if isinstance(scenarios, list) and scenarios and isinstance(scenarios[0], dict) else {}
    ar = first.get("agent_result", {}) if isinstance(first.get("agent_result", {}), dict) else {}
    totals = ar.get("observation_totals", {}) if isinstance(ar.get("observation_totals", {}), dict) else {}
    return (
        "Dynamic RAG summary: "
        f"risk={fr.get('risk_level')} "
        f"score={fr.get('risk_score')} "
        f"scenario={top.get('pattern_name')} "
        f"evidence={first.get('scenario_evidence_score')} "
        f"actions={ar.get('actions_count')} "
        f"storage_events={totals.get('storage_events', 0)} "
        f"network_requests={totals.get('network_requests', 0)} "
        f"runtime_messages={totals.get('runtime_messages', 0)}"
    )
