from __future__ import annotations


def normalize_observations(observations: dict | None) -> dict:
    src = observations if isinstance(observations, dict) else {}
    execution_src = src.get("execution", {}) if isinstance(src.get("execution", {}), dict) else {}

    return {
        "network_requests": src.get("network_requests", []) if isinstance(src.get("network_requests", []), list) else [],
        "runtime_messages": src.get("runtime_messages", []) if isinstance(src.get("runtime_messages", []), list) else [],
        "storage_events": src.get("storage_events", []) if isinstance(src.get("storage_events", []), list) else [],
        "dom_events": src.get("dom_events", []) if isinstance(src.get("dom_events", []), list) else [],
        "timers": src.get("timers", []) if isinstance(src.get("timers", []), list) else [],
        "execution": {
            "document_start_observed": bool(execution_src.get("document_start_observed", False)),
            "mock_target_used": bool(execution_src.get("mock_target_used", True)),
            "real_service_used": bool(execution_src.get("real_service_used", False)),
            "real_secret_observed": bool(execution_src.get("real_secret_observed", False)),
            "non_localhost_sensitive_transmission": bool(execution_src.get("non_localhost_sensitive_transmission", False)),
            "actual_page_url": str(execution_src.get("actual_page_url", "")),
            "expected_target_url": str(execution_src.get("expected_target_url", "")),
            "target_url_emulation_used": bool(execution_src.get("target_url_emulation_used", False)),
            "target_url_emulation_failed": bool(execution_src.get("target_url_emulation_failed", False)),
            "target_url_emulation_error": str(execution_src.get("target_url_emulation_error", "")),
            "target_url_emulation_enabled": bool(execution_src.get("target_url_emulation_enabled", False)),
            "original_mock_server_url": str(execution_src.get("original_mock_server_url", "")),
            "emulated_target_url": str(execution_src.get("emulated_target_url", "")),
            "selected_content_script_match": str(execution_src.get("selected_content_script_match", "")),
            "target_host_mapped_to_local": bool(execution_src.get("target_host_mapped_to_local", False)),
            "manifest_content_script_matches": (
                execution_src.get("manifest_content_script_matches", [])
                if isinstance(execution_src.get("manifest_content_script_matches", []), list)
                else []
            ),
            "manifest_mismatch_reason": str(execution_src.get("manifest_mismatch_reason", "")),
            "manifest_match_actual_page_url": bool(execution_src.get("manifest_match_actual_page_url", False)),
            "route_registered_web_telegram": bool(execution_src.get("route_registered_web_telegram", False)),
            "route_matched_web_telegram_count": int(execution_src.get("route_matched_web_telegram_count", 0) or 0),
            "route_registered_save_session_endpoint": bool(execution_src.get("route_registered_save_session_endpoint", False)),
            "route_matched_save_session_endpoint": int(execution_src.get("route_matched_save_session_endpoint", 0) or 0),
            "content_script_executed": bool(execution_src.get("content_script_executed", False)),
            "content_script_execution_source": str(execution_src.get("content_script_execution_source", "")),
            "content_script_run_at_observed": bool(execution_src.get("content_script_run_at_observed", False)),
            "target_local_storage_seeded_before_goto": bool(execution_src.get("target_local_storage_seeded_before_goto", False)),
            "seed_extension_uuid_attempted": bool(execution_src.get("seed_extension_uuid_attempted", False)),
            "seed_extension_uuid_success": bool(execution_src.get("seed_extension_uuid_success", False)),
            "seed_extension_uuid_error": str(execution_src.get("seed_extension_uuid_error", "")),
            "service_worker_ready_before_uuid_seed": bool(execution_src.get("service_worker_ready_before_uuid_seed", False)),
            "extension_loaded": bool(execution_src.get("extension_loaded", False)),
            "extension_id": str(execution_src.get("extension_id", "")),
            "extension_background_type": str(execution_src.get("extension_background_type", "")),
            "service_worker_count": int(execution_src.get("service_worker_count", 0) or 0),
            "service_worker_url": str(execution_src.get("service_worker_url", "")),
            "service_worker_ready": bool(execution_src.get("service_worker_ready", False)),
            "extension_manifest_matches": execution_src.get("extension_manifest_matches", [])
            if isinstance(execution_src.get("extension_manifest_matches", []), list)
            else [],
            "extension_manifest_content_scripts": int(execution_src.get("extension_manifest_content_scripts", 0) or 0),
            "extension_content_script_files": execution_src.get("extension_content_script_files", [])
            if isinstance(execution_src.get("extension_content_script_files", []), list)
            else [],
            "content_script_probe_method": str(execution_src.get("content_script_probe_method", "")),
            "content_script_files_expected": execution_src.get("content_script_files_expected", [])
            if isinstance(execution_src.get("content_script_files_expected", []), list)
            else [],
            "content_script_files_observed": execution_src.get("content_script_files_observed", [])
            if isinstance(execution_src.get("content_script_files_observed", []), list)
            else [],
            "manifest_match_target_url": bool(execution_src.get("manifest_match_target_url", False)),
            "manifest_match_patterns": execution_src.get("manifest_match_patterns", [])
            if isinstance(execution_src.get("manifest_match_patterns", []), list)
            else [],
            "manifest_match_error": str(execution_src.get("manifest_match_error", "")),
            "extension_target_original": str(execution_src.get("extension_target_original", "")),
            "extension_unpacked_dir": str(execution_src.get("extension_unpacked_dir", "")),
            "extension_load_path": str(execution_src.get("extension_load_path", "")),
            "extension_manifest_path": str(execution_src.get("extension_manifest_path", "")),
            "extension_manifest_exists": bool(execution_src.get("extension_manifest_exists", False)),
            "extension_context_launched": bool(execution_src.get("extension_context_launched", False)),
            "extension_load_error": str(execution_src.get("extension_load_error", "")),
            "extension_load_warning": str(execution_src.get("extension_load_warning", "")),
            "browser_launch_args_sanitized": execution_src.get("browser_launch_args_sanitized", [])
            if isinstance(execution_src.get("browser_launch_args_sanitized", []), list)
            else [],
            "used_launch_persistent_context": bool(execution_src.get("used_launch_persistent_context", False)),
            "headless": bool(execution_src.get("headless", False)),
            "headless_source": str(execution_src.get("headless_source", "")),
            "dynamic_harness_headless_env": str(execution_src.get("dynamic_harness_headless_env", "")),
            "display_env": str(execution_src.get("display_env", "")),
            "xvfb_available": bool(execution_src.get("xvfb_available", False)),
            "headed_supported": bool(execution_src.get("headed_supported", False)),
            "service_worker_wait_timeout_ms": int(execution_src.get("service_worker_wait_timeout_ms", 0) or 0),
            "service_worker_urls": execution_src.get("service_worker_urls", [])
            if isinstance(execution_src.get("service_worker_urls", []), list)
            else [],
            "launch_args_removed": execution_src.get("launch_args_removed", [])
            if isinstance(execution_src.get("launch_args_removed", []), list)
            else [],
            "cleanup_started": bool(execution_src.get("cleanup_started", False)),
            "cleanup_completed": bool(execution_src.get("cleanup_completed", False)),
            "cleanup_error": str(execution_src.get("cleanup_error", "")),
            "cleanup_closed_context": bool(execution_src.get("cleanup_closed_context", False)),
            "cleanup_stopped_playwright": bool(execution_src.get("cleanup_stopped_playwright", False)),
            "cleanup_removed_user_data_dir": bool(execution_src.get("cleanup_removed_user_data_dir", False)),
            "cleanup_removed_unpacked_dir": bool(execution_src.get("cleanup_removed_unpacked_dir", False)),
            "cleanup_removed_user_data_dir_not_applicable": bool(execution_src.get("cleanup_removed_user_data_dir_not_applicable", False)),
            "cleanup_removed_unpacked_dir_not_applicable": bool(execution_src.get("cleanup_removed_unpacked_dir_not_applicable", False)),
            "real_network_used": bool(execution_src.get("real_network_used", False)),
            "intercepted_by_harness": bool(execution_src.get("intercepted_by_harness", False)),
            "external_request_attempted": bool(execution_src.get("external_request_attempted", False)),
            "external_request_blocked": bool(execution_src.get("external_request_blocked", False)),
            "external_request_count": int(execution_src.get("external_request_count", 0) or 0),
            "blocked_external_request_count": int(execution_src.get("blocked_external_request_count", 0) or 0),
            "blocked_external_requests": execution_src.get("blocked_external_requests", [])
            if isinstance(execution_src.get("blocked_external_requests", []), list)
            else [],
            "external_request_failed": bool(execution_src.get("external_request_failed", False)),
            "external_request_block_source": str(execution_src.get("external_request_block_source", "")),
            "external_request_outcome": str(execution_src.get("external_request_outcome", "")),
            "unsafe_request_url": str(execution_src.get("unsafe_request_url", "")),
            "unsafe_request_host": str(execution_src.get("unsafe_request_host", "")),
            "content_script_not_executed_reason": str(execution_src.get("content_script_not_executed_reason", "")),
            "content_script_probe_warning": str(execution_src.get("content_script_probe_warning", "")),
            "content_script_probe_error": str(execution_src.get("content_script_probe_error", "")),
            "content_script_dom_marker_found": bool(execution_src.get("content_script_dom_marker_found", False)),
            "content_script_probe_timeout_ms": int(execution_src.get("content_script_probe_timeout_ms", 0) or 0),
            "content_script_console_logs": (
                execution_src.get("content_script_console_logs", [])
                if isinstance(execution_src.get("content_script_console_logs", []), list)
                else []
            ),
            "content_script_page_errors": (
                execution_src.get("content_script_page_errors", [])
                if isinstance(execution_src.get("content_script_page_errors", []), list)
                else []
            ),
            "manifest_content_script_js": (
                execution_src.get("manifest_content_script_js", [])
                if isinstance(execution_src.get("manifest_content_script_js", []), list)
                else []
            ),
            "manifest_content_script_run_at": str(execution_src.get("manifest_content_script_run_at", "")),
            "manifest_content_script_exclude_matches": (
                execution_src.get("manifest_content_script_exclude_matches", [])
                if isinstance(execution_src.get("manifest_content_script_exclude_matches", []), list)
                else []
            ),
            "manifest_content_script_include_globs": (
                execution_src.get("manifest_content_script_include_globs", [])
                if isinstance(execution_src.get("manifest_content_script_include_globs", []), list)
                else []
            ),
            "manifest_content_script_exclude_globs": (
                execution_src.get("manifest_content_script_exclude_globs", [])
                if isinstance(execution_src.get("manifest_content_script_exclude_globs", []), list)
                else []
            ),
            "manifest_content_script_all_frames": bool(execution_src.get("manifest_content_script_all_frames", False)),
            "manifest_permissions": (
                execution_src.get("manifest_permissions", [])
                if isinstance(execution_src.get("manifest_permissions", []), list)
                else []
            ),
            "manifest_host_permissions": (
                execution_src.get("manifest_host_permissions", [])
                if isinstance(execution_src.get("manifest_host_permissions", []), list)
                else []
            ),
            "selected_content_script_files": (
                execution_src.get("selected_content_script_files", [])
                if isinstance(execution_src.get("selected_content_script_files", []), list)
                else []
            ),
            "manifest_injection_eligible": bool(execution_src.get("manifest_injection_eligible", False)),
            "manifest_injection_block_reason": str(execution_src.get("manifest_injection_block_reason", "")),
            "manifest_match_expected_url": bool(execution_src.get("manifest_match_expected_url", False)),
            "content_script_file_exists": bool(execution_src.get("content_script_file_exists", False)),
            "content_script_file_checks": (
                execution_src.get("content_script_file_checks", [])
                if isinstance(execution_src.get("content_script_file_checks", []), list)
                else []
            ),
            "content_script_request_seen": bool(execution_src.get("content_script_request_seen", False)),
            "content_script_request_url": str(execution_src.get("content_script_request_url", "")),
            "content_script_request_resource_type": str(execution_src.get("content_script_request_resource_type", "")),
            "extension_script_requests": (
                execution_src.get("extension_script_requests", [])
                if isinstance(execution_src.get("extension_script_requests", []), list)
                else []
            ),
            "isolated_world_context_seen": bool(execution_src.get("isolated_world_context_seen", False)),
            "isolated_world_contexts": (
                execution_src.get("isolated_world_contexts", [])
                if isinstance(execution_src.get("isolated_world_contexts", []), list)
                else []
            ),
            "content_script_isolated_world_detected": bool(execution_src.get("content_script_isolated_world_detected", False)),
            "manifest_patched_for_dynamic_analysis": bool(execution_src.get("manifest_patched_for_dynamic_analysis", False)),
            "manifest_original_content_script_matches": (
                execution_src.get("manifest_original_content_script_matches", [])
                if isinstance(execution_src.get("manifest_original_content_script_matches", []), list)
                else []
            ),
            "manifest_patched_content_script_matches": (
                execution_src.get("manifest_patched_content_script_matches", [])
                if isinstance(execution_src.get("manifest_patched_content_script_matches", []), list)
                else []
            ),
            "page_load_error": str(execution_src.get("page_load_error", "")),
            "page_load_started": bool(execution_src.get("page_load_started", False)),
            "page_load_completed": bool(execution_src.get("page_load_completed", False)),
            "open_mock_page_attempted": bool(execution_src.get("open_mock_page_attempted", False)),
            "open_mock_page_succeeded": bool(execution_src.get("open_mock_page_succeeded", False)),
            "content_script_probe_attempted": bool(execution_src.get("content_script_probe_attempted", False)),
            "page_response_status": execution_src.get("page_response_status"),
            "page_load_warning": str(execution_src.get("page_load_warning", "")),
            "goto_called": bool(execution_src.get("goto_called", False)),
            "goto_completed": bool(execution_src.get("goto_completed", False)),
            "wait_for_load_state_called": bool(execution_src.get("wait_for_load_state_called", False)),
            "wait_for_load_state_completed": bool(execution_src.get("wait_for_load_state_completed", False)),
            "wait_for_load_state_error": str(execution_src.get("wait_for_load_state_error", "")),
            "mock_server_check_attempted": bool(execution_src.get("mock_server_check_attempted", False)),
            "mock_server_autostart_enabled": bool(execution_src.get("mock_server_autostart_enabled", False)),
            "mock_server_autostarted": bool(execution_src.get("mock_server_autostarted", False)),
            "mock_server_host": str(execution_src.get("mock_server_host", "")),
            "mock_server_port": int(execution_src.get("mock_server_port", 0) or 0),
            "mock_server_url": str(execution_src.get("mock_server_url", "")),
            "mock_server_reachable": bool(execution_src.get("mock_server_reachable", False)),
            "mock_server_status_code": execution_src.get("mock_server_status_code"),
            "mock_server_error": str(execution_src.get("mock_server_error", "")),
            "mock_server_stopped": bool(execution_src.get("mock_server_stopped", False)),
            "mock_server_stop_error": str(execution_src.get("mock_server_stop_error", "")),
            "dynamic_analysis_timeout": bool(execution_src.get("dynamic_analysis_timeout", False)),
            "playwright_worker_thread_name": str(execution_src.get("playwright_worker_thread_name", "")),
            "playwright_worker_started": bool(execution_src.get("playwright_worker_started", False)),
            "playwright_worker_running_loop": bool(execution_src.get("playwright_worker_running_loop", False)),
            "playwright_worker_shutdown_completed": bool(execution_src.get("playwright_worker_shutdown_completed", False)),
            "thread_diag_ensure_context": execution_src.get("thread_diag_ensure_context", {})
            if isinstance(execution_src.get("thread_diag_ensure_context", {}), dict)
            else {},
            "thread_diag_agent_start": execution_src.get("thread_diag_agent_start", {})
            if isinstance(execution_src.get("thread_diag_agent_start", {}), dict)
            else {},
        },
    }


def _build_action_result(action: dict, observation: dict | None) -> dict:
    action_name = action.get("action", "") if isinstance(action, dict) else ""
    obs = observation if isinstance(observation, dict) else {}
    ex = obs.get("execution", {}) if isinstance(obs.get("execution", {}), dict) else {}
    target = (
        str(ex.get("expected_target_url", "") or action.get("target", "") or "")
        if isinstance(action, dict) else ""
    )
    if action_name == "open_mock_page":
        attempted = bool(ex.get("open_mock_page_attempted", False))
        succeeded = bool(ex.get("open_mock_page_succeeded", False))
        error = str(ex.get("page_load_error", "") or "")
        if attempted and not succeeded and not error:
            if not ex.get("goto_called"):
                error = "page_navigation_not_called"
            elif not ex.get("goto_completed"):
                error = ex.get("content_script_not_executed_reason", "goto_not_completed") or "goto_not_completed"
    elif action_name == "wait_for_page_load":
        attempted = bool(ex.get("wait_for_load_state_called", False))
        succeeded = bool(ex.get("wait_for_load_state_completed", False))
        error = str(ex.get("wait_for_load_state_error", "") or "")
    elif action_name == "probe_content_script_execution":
        attempted = bool(ex.get("content_script_probe_attempted", False))
        succeeded = bool(ex.get("content_script_executed", False))
        error = str(ex.get("content_script_not_executed_reason", "") or "")
    else:
        attempted = bool(ex) or bool(obs.get("network_requests")) or True
        succeeded = not bool(ex.get("extension_load_error", "")) if action_name == "load_extension" else True
        error = str(ex.get("extension_load_error", "") or "") if action_name == "load_extension" else ""
    return {
        "action": action_name,
        "target": target,
        "attempted": attempted,
        "succeeded": succeeded,
        "error": error,
    }


def normalize_action_observation(action: dict, observation: dict | None) -> dict:
    return {
        "action": action if isinstance(action, dict) else {},
        "observation": normalize_observations(observation),
        "action_result": _build_action_result(action if isinstance(action, dict) else {}, observation),
    }
