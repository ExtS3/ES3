from __future__ import annotations

ALLOWED_ACTIONS = [
    "load_extension",
    "verify_extension_loaded",
    "open_mock_page",
    "wait_for_page_load",
    "seed_dummy_local_storage",
    "seed_extension_uuid",
    "wait_for_extension_service_worker",
    "prepare_target_routes",
    "seed_target_local_storage_before_goto",
    "probe_content_script_execution",
    "simulate_dom_input_events",
    "click_extension_action",
    "submit_mock_form",
    "wait",
    "collect_network_requests",
    "collect_runtime_messages",
    "collect_storage_events",
    "collect_dom_events",
    "collect_timer_events",
    "cleanup_harness",
    "finish_analysis",
]

FORBIDDEN_ACTIONS = {
    "login_real_service",
    "collect_real_cookie",
    "collect_real_token",
    "collect_real_session",
    "send_to_real_external_server",
    "bypass_authentication",
    "exploit_real_target",
    "access_real_user_data",
}


def get_allowed_actions() -> list[str]:
    return list(ALLOWED_ACTIONS)


def is_allowed_action(action_name: str) -> bool:
    return action_name in ALLOWED_ACTIONS and action_name not in FORBIDDEN_ACTIONS


def _unsafe_target(target: str) -> bool:
    t = target.lower()
    if any(host in t for host in ("web.telegram.org", "accounts.google.com", "mail.google.com", "drive.google.com")):
        return False
    unsafe_keywords = ["real", "prod", "production", "facebook.com", "google.com", "x.com", "twitter.com"]
    return any(k in t for k in unsafe_keywords) and "mock" not in t and "localhost" not in t


def validate_agent_action(action: dict) -> tuple[bool, str]:
    if not isinstance(action, dict):
        return False, "action must be a dict"

    action_name = action.get("action")
    if not isinstance(action_name, str) or not action_name.strip():
        return False, "missing action field"

    if action_name in FORBIDDEN_ACTIONS:
        return False, f"forbidden action: {action_name}"

    if not is_allowed_action(action_name):
        return False, f"action not allowed: {action_name}"

    target = action.get("target")
    if isinstance(target, str) and target.strip() and _unsafe_target(target):
        return False, f"unsafe target detected: {target}"

    if action_name == "finish_analysis":
        fa = action.get("final_assessment")
        if not isinstance(fa, dict):
            action["final_assessment"] = {
                "scenario_matched": False,
                "confidence_score": 0.0,
                "matched_evidence": [],
                "missing_evidence": [],
                "safety_notes": [],
            }

    return True, "ok"
