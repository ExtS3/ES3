from __future__ import annotations

import os
import threading
import time
import asyncio

from .action_schema import validate_agent_action
from .config import DEFAULT_MAX_DYNAMIC_ROUNDS
from .llm_client import call_llm
from .observation_schema import normalize_action_observation
from .prompt_builder import (
    build_agent_system_prompt,
    build_next_action_prompt_compact,
    build_repair_prompt_for_invalid_json,
)


def _default_final_assessment() -> dict:
    return {
        "scenario_matched": False,
        "confidence_score": 0.0,
        "matched_evidence": [],
        "missing_evidence": [],
        "safety_notes": [],
    }


def _bootstrap_actions(preferred_target_url: str) -> list[dict]:
    return [
        {"action": "load_extension", "target": "mock_or_localhost_only", "input": {}},
        {"action": "verify_extension_loaded", "target": "mock_or_localhost_only", "input": {}},
        {"action": "wait_for_extension_service_worker", "target": "mock_or_localhost_only", "input": {"timeout_ms": 5000}},
        {"action": "prepare_target_routes", "target": "mock_or_localhost_only", "input": {}},
        {"action": "seed_target_local_storage_before_goto", "target": "mock_or_localhost_only", "input": {}},
        {"action": "open_mock_page", "target": preferred_target_url, "input": {"url": preferred_target_url}},
        {"action": "wait_for_page_load", "target": preferred_target_url, "input": {"timeout_ms": 10000}},
        {"action": "probe_content_script_execution", "target": preferred_target_url, "input": {}},
        {"action": "simulate_dom_input_events", "target": preferred_target_url, "input": {}},
        {"action": "wait", "target": preferred_target_url, "input": {"ms": 3000}},
        {"action": "collect_runtime_messages", "target": preferred_target_url, "input": {}},
        {"action": "collect_storage_events", "target": preferred_target_url, "input": {}},
        {"action": "collect_timer_events", "target": preferred_target_url, "input": {}},
        {"action": "collect_network_requests", "target": preferred_target_url, "input": {}},
        {"action": "cleanup_harness", "target": "mock_or_localhost_only", "input": {}},
    ]


def run_llm_dynamic_analysis_agent(
    vector_fingerprint: dict,
    selected_match: dict,
    scenario_doc: str,
    execute_action,
    max_rounds: int = DEFAULT_MAX_DYNAMIC_ROUNDS,
    enable_llm: bool | None = None,
    preferred_target_url: str | None = None,
) -> dict:
    try:
        loop = asyncio.get_running_loop()
        diag = {"running_loop": True, "loop_id": id(loop), "loop_type": type(loop).__name__}
    except RuntimeError:
        diag = {"running_loop": False, "loop_id": None, "loop_type": None}
    print(
        f"[thread_diag] location=agent_start thread={threading.current_thread().name} "
        f"running_loop={diag['running_loop']} loop_id={diag['loop_id']}",
        flush=True,
    )
    history: list[dict] = []
    final_assessment = _default_final_assessment()
    notes: list[str] = []
    dynamic_timeout_sec = int(os.getenv("DYNAMIC_ANALYSIS_TIMEOUT_SEC", "60"))
    deadline = time.monotonic() + max(dynamic_timeout_sec, 1)
    max_rounds = max(1, min(int(max_rounds), 12))
    if isinstance(preferred_target_url, str) and preferred_target_url:
        for action in _bootstrap_actions(preferred_target_url):
            if time.monotonic() > deadline:
                return {
                    "status": "partial_error",
                    "selected_match": selected_match,
                    "actions_executed": history,
                    "final_assessment": final_assessment,
                    "error_type": "DynamicAnalysisTimeout",
                    "error": "Dynamic analysis exceeded timeout",
                    "notes": notes + ["dynamic analysis timeout during bootstrap"],
                }
            obs = execute_action(action)
            if isinstance(obs, dict):
                ex = obs.get("execution", {}) if isinstance(obs.get("execution", {}), dict) else {}
                ex["thread_diag_agent_start"] = {"thread": threading.current_thread().name, **diag}
                obs["execution"] = ex
                resolved = str(ex.get("expected_target_url") or ex.get("mock_server_url") or "")
                if resolved and action.get("action") in {
                    "open_mock_page",
                    "wait_for_page_load",
                    "probe_content_script_execution",
                    "simulate_dom_input_events",
                    "collect_runtime_messages",
                    "collect_network_requests",
                    "collect_storage_events",
                    "collect_timer_events",
                    "collect_dom_events",
                    "wait",
                }:
                    action = {**action, "target": resolved}
                    action_input = action.get("input", {})
                    if isinstance(action_input, dict):
                        action["input"] = {**action_input, "url": resolved} if "url" in action_input else dict(action_input)
            history.append(normalize_action_observation(action, obs))
        if history:
            last_exec = history[-1].get("observation", {}).get("execution", {}) if isinstance(history[-1], dict) else {}
            extension_attempted = bool(
                isinstance(last_exec, dict)
                and (
                    last_exec.get("extension_manifest_path")
                    or last_exec.get("extension_load_path")
                    or last_exec.get("extension_context_launched")
                )
            )
            if extension_attempted and isinstance(last_exec, dict) and not bool(last_exec.get("extension_loaded", False)):
                notes.extend(["extension_not_loaded", "service_worker_not_ready", "content_script_not_executed"])
                load_error = str(last_exec.get("extension_load_error", "extension_not_loaded"))
                if load_error == "manifest_not_found":
                    err_type = "ManifestNotFound"
                elif load_error == "headed_mode_requires_display_or_xvfb":
                    err_type = "HeadedModeUnavailable"
                elif load_error in {"service_worker_not_ready", "extension_service_worker_not_started_headless_mode_possible"}:
                    err_type = "ServiceWorkerNotReady"
                else:
                    err_type = "ExtensionLoadError"
                return {
                    "status": "partial_error",
                    "selected_match": selected_match,
                    "actions_executed": history,
                    "final_assessment": final_assessment,
                    "error_type": err_type,
                    "error": f"extension_not_loaded: {load_error}",
                    "notes": notes,
                }
        run_llm_after_bootstrap = str(os.getenv("DYNAMIC_AGENT_LLM_AFTER_BOOTSTRAP", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        if not run_llm_after_bootstrap and enable_llm is not True:
            return {
                "status": "ok",
                "selected_match": selected_match,
                "actions_executed": history,
                "final_assessment": final_assessment,
                "notes": notes + ["deterministic bootstrap completed; llm action loop skipped"],
            }

    for round_idx in range(1, int(max_rounds) + 1):
        if time.monotonic() > deadline:
            return {
                "status": "partial_error",
                "selected_match": selected_match,
                "actions_executed": history,
                "final_assessment": final_assessment,
                "error_type": "DynamicAnalysisTimeout",
                "error": "Dynamic analysis exceeded timeout",
                "notes": notes + ["dynamic analysis timeout"],
            }
        system_prompt = build_agent_system_prompt()
        prompt = build_next_action_prompt_compact(
            vector_fingerprint=vector_fingerprint,
            selected_match=selected_match,
            scenario_doc=scenario_doc,
            observation_history=history,
            round_index=round_idx,
            max_rounds=max_rounds,
        )
        print("[prompt_mode] mode=ollama_compact", flush=True)

        llm_action = call_llm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            enable_real_call=enable_llm,
        )

        if isinstance(llm_action, dict) and llm_action.get("parse_error"):
            repair_prompt = build_repair_prompt_for_invalid_json(
                raw_text=str(llm_action.get("raw_text", "")),
                parse_error=str(llm_action.get("parse_error", "")),
            )
            llm_action = call_llm(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": repair_prompt},
                ],
                enable_real_call=enable_llm,
            )

        valid, reason = validate_agent_action(llm_action)
        if not valid:
            return {
                "status": "error",
                "selected_match": selected_match,
                "actions_executed": history,
                "final_assessment": final_assessment,
                "notes": [f"invalid llm action: {reason}"],
            }

        action_name = llm_action.get("action")
        if action_name == "open_mock_page" and isinstance(preferred_target_url, str) and preferred_target_url:
            llm_action.setdefault("input", {})
            if isinstance(llm_action.get("input"), dict):
                llm_action["input"]["url"] = preferred_target_url
            llm_action["target"] = preferred_target_url

        if action_name == "finish_analysis":
            fa = llm_action.get("final_assessment")
            if isinstance(fa, dict):
                final_assessment = {
                    "scenario_matched": bool(fa.get("scenario_matched", False)),
                    "confidence_score": float(fa.get("confidence_score", 0.0) or 0.0),
                    "matched_evidence": fa.get("matched_evidence", []) if isinstance(fa.get("matched_evidence", []), list) else [],
                    "missing_evidence": fa.get("missing_evidence", []) if isinstance(fa.get("missing_evidence", []), list) else [],
                    "safety_notes": fa.get("safety_notes", []) if isinstance(fa.get("safety_notes", []), list) else [],
                }
            return {
                "status": "ok",
                "selected_match": selected_match,
                "actions_executed": history,
                "final_assessment": final_assessment,
                "notes": notes,
            }

        observation = execute_action(llm_action)
        row = normalize_action_observation(llm_action, observation)
        history.append(row)

        exec_info = row["observation"].get("execution", {})
        if (
            exec_info.get("real_service_used")
            or exec_info.get("real_secret_observed")
            or (
                exec_info.get("non_localhost_sensitive_transmission")
                and not (
                    exec_info.get("target_url_emulation_used")
                    and not exec_info.get("target_url_emulation_failed")
                    and not exec_info.get("real_service_used")
                )
            )
        ):
            notes.append("safety violation observed; stopping execution")
            final_assessment["safety_notes"].append("execution stopped due to safety violation")
            return {
                "status": "error",
                "selected_match": selected_match,
                "actions_executed": history,
                "final_assessment": final_assessment,
                "notes": notes,
            }

    return {
        "status": "max_rounds_reached",
        "selected_match": selected_match,
        "actions_executed": history,
        "final_assessment": final_assessment,
        "notes": ["maximum dynamic rounds reached before finish_analysis"],
    }
