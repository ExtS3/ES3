from typing import Any

from .utils import dedup_sorted


def _build_behavior_tags(manifest_profile: dict[str, Any], agg: dict[str, Any], flows: list[dict[str, Any]], dnr: dict[str, Any]) -> list[str]:
    tags = set()
    signals = set(agg.get("signals", []))
    if "document_start" in (manifest_profile.get("content_script_run_at") or []):
        tags.add("early_injection")
    if "storage.localStorage" in signals or "storage.sessionStorage" in signals:
        tags.add("page_storage_exfiltration")
    if "messaging.runtime.sendMessage" in signals:
        tags.add("message_passing_bridge")
    if any(
        s in signals
        for s in [
            "network.fetch",
            "network.xhr",
            "network.sendBeacon",
            "network.WebSocket",
            "network.EventSource",
            "network.jquery.ajax",
            "network.jquery.get",
            "network.jquery.post",
            "network.axios",
        ]
    ):
        tags.add("external_communication")
    if any((f.get("path") or [None])[0] == "extension_page" and f.get("sink") == "external_network" for f in flows):
        tags.add("extension_page_network_behavior")
    if any(f.get("trigger") == "form_submit" and f.get("sink") == "external_network" for f in flows):
        tags.add("form_submission_network")
    if any(f.get("sink") == "storage_write" for f in flows) or "storage.chrome.storage.local.set" in signals:
        tags.add("storage_persistence")
    if "delayed_execution.setInterval" in signals:
        tags.add("repeated_exfiltration")
    if any(k in agg.get("keywords", {}).get("storage", []) for k in ["session", "auth", "token", "user_auth"]):
        tags.add("session_theft_pattern")
        tags.add("credential_or_token_exfiltration_pattern")
    if any(a in dnr.get("action_types", []) for a in ["redirect", "modifyHeaders", "block"]):
        tags.add("request_modification")
    if "redirect" in dnr.get("action_types", []):
        tags.add("redirect_hijacking")
    return sorted(tags)


def build_capability_combinations(manifest_profile: dict[str, Any], caps: list[str], agg: dict[str, Any], dnr: dict[str, Any]) -> list[str]:
    combos = []
    host = manifest_profile.get("host_access")
    roles = set(manifest_profile.get("entrypoint_roles", []))
    run_ats = set(manifest_profile.get("content_script_run_at", []))
    signals = set(agg.get("signals", []))

    if host == "broad" and "content_script" in roles:
        combos.append("broad_page_access + content_script")
    if host == "targeted" and "document_start" in run_ats and "content_script" in roles:
        combos.append("targeted_page_access + document_start + content_script")
    if "content_script" in roles and "background" in roles and "message_bridge" in caps:
        combos.append("content_script + message_bridge + background")
    if any(s in signals for s in ["dom.event.submit", "dom.event.input"]) and "message_bridge" in caps and "external_network" in caps:
        combos.append("dom_access + message_bridge + external_network")
    if any(s in signals for s in ["storage.localStorage", "storage.sessionStorage"]) and "message_bridge" in caps and "external_network" in caps:
        combos.append("page_storage_access + message_bridge + external_network")
    if any(s in signals for s in ["delayed_execution.setInterval", "delayed_execution.setTimeout"]) and "external_network" in caps:
        combos.append("periodic_execution + external_network")
    if "request_rule_control" in caps and "redirect" in dnr.get("action_types", []):
        combos.append("request_rule_control + request_redirect")
    if "debugger_access" in caps and "tab_access" in caps:
        combos.append("debugger_access + tab_access")
    if "script_injection" in caps and host == "broad":
        combos.append("script_injection + broad_page_access")
    if "storage_access" in caps and "external_network" in caps:
        combos.append("storage_access + external_network")
    return dedup_sorted(combos)


def build_static_code_signals(manifest_profile: dict[str, Any], agg: dict[str, Any], dnr: dict[str, Any]) -> dict[str, Any]:
    signals = set(agg.get("signals", []))
    out: dict[str, Any] = {}
    storage_apis = []
    if "storage.chrome.storage.local" in signals:
        storage_apis.append("chrome.storage.local")
    if "storage.chrome.storage.sync" in signals:
        storage_apis.append("chrome.storage.sync")
    if "storage.chrome.storage.session" in signals:
        storage_apis.append("chrome.storage.session")
    if "storage.localStorage" in signals:
        storage_apis.append("localStorage")
    if "storage.sessionStorage" in signals:
        storage_apis.append("sessionStorage")
    if storage_apis:
        out["storage"] = {"apis": sorted(set(storage_apis)), "keywords": sorted(set(agg.get("keywords", {}).get("storage", [])))}

    dom_events = []
    if "dom.event.submit" in signals:
        dom_events.append("submit")
    if "dom.event.input" in signals:
        dom_events.append("input")
    dom_selectors = []
    if "dom.selector.password" in signals:
        dom_selectors.append("password_input")
    if "dom.selector.email" in signals:
        dom_selectors.append("email_input")
    if dom_events or dom_selectors:
        out["dom_input"] = {"events": sorted(set(dom_events)), "selectors": sorted(set(dom_selectors)), "keywords": sorted(set(agg.get("keywords", {}).get("dom", [])))}

    msg_apis = []
    if "messaging.runtime.sendMessage" in signals:
        msg_apis.append("runtime.sendMessage")
    if "messaging.runtime.onMessage" in signals:
        msg_apis.append("runtime.onMessage")
    if "messaging.tabs.sendMessage" in signals:
        msg_apis.append("tabs.sendMessage")
    if msg_apis:
        patterns = []
        role_flows = [f for f in (agg.get("derived_flows", []) or []) if "runtime_message" in (f.get("path") or [])]
        if any((f.get("path") or [None])[0] == "content_script" for f in role_flows):
            patterns.append("content_script_to_background")
        if any((f.get("path") or [None])[0] in {"extension_page", "popup", "options", "side_panel", "offscreen"} for f in role_flows):
            patterns.append("extension_page_to_background")
        if any((f.get("path") or [None])[0] == "unknown_script" for f in role_flows):
            patterns.append("unknown_script_to_background")
        out["messaging"] = {"apis": sorted(set(msg_apis)), "patterns": patterns, "message_actions": agg.get("keywords", {}).get("message_actions", [])}

    net_apis = []
    if "network.fetch" in signals:
        net_apis.append("fetch")
    if "network.xhr" in signals:
        net_apis.append("XMLHttpRequest")
    if "network.sendBeacon" in signals:
        net_apis.append("sendBeacon")
    if "network.WebSocket" in signals:
        net_apis.append("WebSocket")
    if "network.EventSource" in signals:
        net_apis.append("EventSource")
    if "network.jquery.ajax" in signals:
        net_apis.append("jquery.ajax")
    if "network.jquery.get" in signals:
        net_apis.append("jquery.get")
    if "network.jquery.post" in signals:
        net_apis.append("jquery.post")
    if "network.axios" in signals:
        net_apis.append("axios")
    external_origin_present = bool(agg.get("network", {}).get("external_origin_present", False))
    endpoint_keywords = agg.get("network", {}).get("endpoint_keywords", [])
    network_patterns = []
    if external_origin_present and not net_apis:
        network_patterns.append("external_endpoint_reference")
    if net_apis or external_origin_present or endpoint_keywords:
        out["network"] = {
            "apis": sorted(set(net_apis)),
            "patterns": sorted(set(network_patterns)),
            "external_origin_present": external_origin_present,
            "methods": agg.get("network", {}).get("methods", []),
            "endpoint_keywords": endpoint_keywords,
        }

    nav_apis = []
    if "navigation.tabs.create" in signals:
        nav_apis.append("tabs.create")
    if "navigation.tabs.update" in signals:
        nav_apis.append("tabs.update")
    if "navigation.location.href" in signals:
        nav_apis.append("location.href")
    nav_patterns = []
    if any(f.get("sink") == "extension_page_open" for f in agg.get("derived_flows", [])):
        nav_patterns.append("extension_page_open")
    if nav_apis or nav_patterns:
        out["navigation"] = {"apis": sorted(set(nav_apis)), "patterns": sorted(set(nav_patterns))}

    if any(s in signals for s in ["delayed_execution.setInterval", "delayed_execution.setTimeout"]):
        apis = []
        if "delayed_execution.setInterval" in signals:
            apis.append("setInterval")
        if "delayed_execution.setTimeout" in signals:
            apis.append("setTimeout")
        patterns = []
        if "storage.localStorage" in signals:
            patterns.append("periodic_session_collection")
        if "network.fetch" in signals or "network.xhr" in signals or "network.sendBeacon" in signals:
            patterns.append("repeated_transmission")
        out["delayed_execution"] = {
            "apis": sorted(set(apis)),
            "patterns": sorted(set(patterns)),
            "interval_category": (agg.get("interval_categories") or [None])[0],
        }

    if dnr.get("has_dnr"):
        out["request_modification"] = {
            "action_types": dnr.get("action_types", []),
        }

    return out


def build_fingerprint(manifest_profile: dict[str, Any], capabilities: list[str], agg: dict[str, Any], flows: list[dict[str, Any]], dnr: dict[str, Any]) -> dict[str, Any]:
    agg["derived_flows"] = flows
    tags = _build_behavior_tags(manifest_profile, agg, flows, dnr)
    combos = build_capability_combinations(manifest_profile, capabilities, agg, dnr)
    static_signals = build_static_code_signals(manifest_profile, agg, dnr)
    return {
        "manifest_profile": manifest_profile,
        "capability_profile": dedup_sorted(capabilities),
        "capability_combinations": combos,
        "static_code_signals": static_signals,
        "predicted_flows": flows,
        "behavior_tags": tags,
    }
