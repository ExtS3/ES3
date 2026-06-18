from typing import Any


def build_predicted_flows(manifest_profile: dict[str, Any], agg: dict[str, Any], dnr: dict[str, Any]) -> list[dict[str, Any]]:
    flows: list[dict[str, Any]] = []
    signals = set(agg.get("signals", []))
    by_role = {k: set(v) for k, v in (agg.get("by_role_signals", {}) or {}).items()}
    by_role_keywords = agg.get("by_role_keywords", {}) or {}
    bg_signals = by_role.get("background", set())
    sender_roles = []
    for role, role_signals in by_role.items():
        if "messaging.runtime.sendMessage" in role_signals:
            sender_roles.append(role)
    has_bg_listener = "messaging.runtime.onMessage" in bg_signals
    has_bg_network = any(s in bg_signals for s in ["network.fetch", "network.xhr", "network.sendBeacon"])

    if (
        "document_start" in (manifest_profile.get("content_script_run_at") or [])
        and "content_script" in by_role
        and "storage.localStorage" in by_role.get("content_script", set())
        and "messaging.runtime.sendMessage" in by_role.get("content_script", set())
        and has_bg_listener
        and has_bg_network
    ):
        flows.append(
            {
                "trigger": "document_start",
                "source": "page_local_storage",
                "path": ["content_script", "runtime_message", "background"],
                "sink": "external_network",
            }
        )

    if any(s in signals for s in ["delayed_execution.setInterval", "delayed_execution.setTimeout"]) and (
        any(s in signals for s in ["network.fetch", "network.xhr", "network.sendBeacon"]) or has_bg_network
    ):
        timer_sender = "content_script" if "content_script" in sender_roles else (sender_roles[0] if sender_roles else None)
        flows.append(
            {
                "trigger": "timer",
                "source": "page_local_storage" if "storage.localStorage" in signals else "unknown",
                "path": [timer_sender, "runtime_message", "background"] if timer_sender and has_bg_listener else ["background"],
                "sink": "external_network",
            }
        )

    if (
        any(s in signals for s in ["dom.event.submit", "dom.selector.password", "dom.selector.email"])
        and sender_roles
        and has_bg_listener
        and has_bg_network
    ):
        sender = "content_script" if "content_script" in sender_roles else sender_roles[0]
        flows.append(
            {
                "trigger": "form_submit",
                "source": "credential_input",
                "path": [sender, "runtime_message", "background"],
                "sink": "external_network",
            }
        )

    if has_bg_listener and has_bg_network:
        preferred_order = ["content_script", "extension_page", "popup", "options", "side_panel", "offscreen", "unknown_script"]
        for role in preferred_order:
            if role not in sender_roles:
                continue
            if role == "content_script":
                continue
            flows.append(
                {
                    "trigger": "page_visit",
                    "source": "unknown",
                    "path": [role, "runtime_message", "background"],
                    "sink": "external_network",
                }
            )

    extension_roles = ["extension_page", "popup", "options", "side_panel", "offscreen"]
    for role in extension_roles:
        rs = by_role.get(role, set())
        if not rs:
            continue
        has_submit = "dom.event.submit" in rs
        has_network = any(
            s in rs
            for s in ["network.fetch", "network.xhr", "network.sendBeacon", "network.jquery.ajax", "network.jquery.get", "network.jquery.post", "network.axios"]
        )
        if has_submit and has_network:
            flows.append(
                {
                    "trigger": "form_submit",
                    "source": "form_input",
                    "path": ["extension_page"],
                    "sink": "external_network",
                }
            )

        msg_actions = set((by_role_keywords.get(role, {}) or {}).get("message_actions", []))
        if "messaging.runtime.sendMessage" in rs and "saveApp" in msg_actions and has_bg_listener and "storage.chrome.storage.local.set" in bg_signals:
            flows.append(
                {
                    "trigger": "form_submit_success",
                    "source": "form_state",
                    "path": ["extension_page", "runtime_message", "background"],
                    "sink": "storage_write",
                }
            )

    if {"navigation.action.onClicked", "navigation.tabs.create", "navigation.runtime.getURL_html"}.issubset(bg_signals):
        flows.append(
            {
                "trigger": "action_click",
                "source": "extension_action",
                "path": ["background"],
                "sink": "extension_page_open",
            }
        )

    if any(a in dnr.get("action_types", []) for a in ["redirect", "modifyHeaders", "block"]):
        if "redirect" in dnr.get("action_types", []):
            sink = "redirect"
        elif "modifyHeaders" in dnr.get("action_types", []):
            sink = "header_modification"
        else:
            sink = "request_modification"
        flows.append(
            {
                "trigger": "request_event",
                "source": "web_request",
                "path": ["dnr_ruleset"],
                "sink": sink,
            }
        )

    return flows
