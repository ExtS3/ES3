from pathlib import Path
from typing import Any

from .utils import load_json


def load_capability_mapping(path: str | Path) -> dict[str, Any]:
    return load_json(path)


def map_capabilities(manifest: dict[str, Any], signal_keys: list[str], mapping: dict[str, Any]) -> list[str]:
    out = set()
    perm_map = mapping.get("permission_to_capability", {})
    host_map = mapping.get("host_permission_to_capability", {})
    entrypoint_map = mapping.get("entrypoint_to_capability", {})
    api_map = mapping.get("api_to_capability", {})

    perms = set((manifest.get("permissions") or []) + (manifest.get("optional_permissions") or []))
    for p in perms:
        for cap in perm_map.get(p, []):
            out.add(cap)

    hosts = set((manifest.get("host_permissions") or []))
    for cs in manifest.get("content_scripts", []) or []:
        hosts.update(cs.get("matches", []) or [])
    for h in hosts:
        if h in host_map:
            out.update(host_map.get(h, []))
        elif h:
            out.update(host_map.get("specific_domain", []))

    bg = manifest.get("background", {}) or {}
    roles = set()
    if manifest.get("content_scripts"):
        roles.add("content_script")
    if bg.get("service_worker") or bg.get("scripts"):
        roles.add("background")
    if bg.get("service_worker"):
        roles.add("service_worker")
    if (manifest.get("action") or {}).get("default_popup") or (manifest.get("browser_action") or {}).get("default_popup") or (manifest.get("page_action") or {}).get("default_popup"):
        roles.add("popup")
    if manifest.get("options_page") or (manifest.get("options_ui") or {}).get("page"):
        roles.add("options")
    if (manifest.get("side_panel") or {}).get("default_path"):
        roles.add("side_panel")
    if manifest.get("declarative_net_request", {}).get("rule_resources"):
        roles.add("declarative_net_request_ruleset")
    for r in roles:
        out.update(entrypoint_map.get(r, []))

    api_candidates = set()
    for s in signal_keys:
        if s.startswith("network.fetch"):
            api_candidates.add("fetch")
        if s.startswith("network.xhr"):
            api_candidates.add("XMLHttpRequest")
        if s.startswith("network.sendBeacon"):
            api_candidates.add("sendBeacon")
        if s.startswith("network.WebSocket"):
            api_candidates.add("WebSocket")
        if s.startswith("network.EventSource"):
            api_candidates.add("EventSource")
        if s.startswith("network.jquery.ajax"):
            api_candidates.add("jquery.ajax")
        if s.startswith("network.jquery.get"):
            api_candidates.add("jquery.get")
        if s.startswith("network.jquery.post"):
            api_candidates.add("jquery.post")
        if s.startswith("network.axios"):
            api_candidates.add("axios")
        if s.startswith("messaging.runtime.sendMessage"):
            api_candidates.add("runtime.sendMessage")
        if s.startswith("messaging.runtime.onMessage"):
            api_candidates.add("runtime.onMessage")
        if s.startswith("messaging.tabs.sendMessage"):
            api_candidates.add("tabs.sendMessage")
        if s.startswith("dynamic.eval"):
            api_candidates.add("eval")
        if s.startswith("dynamic.new_function"):
            api_candidates.add("new Function")
        if s.startswith("dynamic.importScripts"):
            api_candidates.add("importScripts")
        if s.startswith("storage.chrome.storage.local"):
            api_candidates.add("chrome.storage.local")
        if s.startswith("storage.localStorage"):
            api_candidates.add("localStorage")
        if s.startswith("navigation.tabs.update"):
            api_candidates.add("tabs.update")
        if s.startswith("navigation.tabs.create"):
            api_candidates.add("tabs.create")
        if s.startswith("navigation.location.href"):
            api_candidates.add("location.href")

    for api in api_candidates:
        for cap in api_map.get(api, []):
            out.add(cap)

    return sorted(out)
