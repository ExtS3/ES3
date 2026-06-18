import re
from pathlib import Path
from typing import Any

from .utils import read_text_safe

PATTERNS = {
    "network.fetch": re.compile(r"\bfetch\s*\("),
    "network.xhr": re.compile(r"\bXMLHttpRequest\b"),
    "network.sendBeacon": re.compile(r"sendBeacon\s*\("),
    "network.WebSocket": re.compile(r"\bWebSocket\s*\("),
    "network.EventSource": re.compile(r"\bEventSource\s*\("),
    "network.jquery.ajax": re.compile(r"(?:jQuery|\$)\.ajax\s*\("),
    "network.jquery.get": re.compile(r"\$\.get\s*\("),
    "network.jquery.post": re.compile(r"\$\.post\s*\("),
    "network.axios": re.compile(r"\baxios(?:\s*\(|\.(?:get|post)\s*\()"),
    "messaging.runtime.sendMessage": re.compile(r"(?:chrome\.)?runtime\.sendMessage\s*\("),
    "messaging.runtime.onMessage": re.compile(r"(?:chrome\.)?runtime\.onMessage"),
    "messaging.tabs.sendMessage": re.compile(r"(?:chrome\.)?tabs\.sendMessage\s*\("),
    "storage.localStorage": re.compile(r"\blocalStorage\b"),
    "storage.sessionStorage": re.compile(r"\bsessionStorage\b"),
    "storage.chrome.storage.local": re.compile(r"chrome\.storage\.local"),
    "storage.chrome.storage.sync": re.compile(r"chrome\.storage\.sync"),
    "storage.chrome.storage.session": re.compile(r"chrome\.storage\.session"),
    "delayed_execution.setInterval": re.compile(r"\bsetInterval\s*\("),
    "delayed_execution.setTimeout": re.compile(r"\bsetTimeout\s*\("),
    "navigation.tabs.update": re.compile(r"(?:chrome\.)?tabs\.update\s*\("),
    "navigation.tabs.create": re.compile(r"(?:chrome\.)?tabs\.create\s*\("),
    "navigation.location.href": re.compile(r"location\.href\s*="),
    "navigation.action.onClicked": re.compile(r"chrome\.action\.onClicked"),
    "navigation.runtime.getURL_html": re.compile(r"(?:chrome\.)?runtime\.getURL\s*\(\s*['\"][^'\"]+\.html['\"]\s*\)"),
    "storage.chrome.storage.local.set": re.compile(r"chrome\.storage\.local\.set\s*\("),
    "dynamic.eval": re.compile(r"\beval\s*\("),
    "dynamic.new_function": re.compile(r"new\s+Function\s*\("),
    "dynamic.importScripts": re.compile(r"\bimportScripts\s*\("),
    "dom.event.submit": re.compile(r"addEventListener\s*\(\s*['\"]submit['\"]"),
    "dom.event.input": re.compile(r"addEventListener\s*\(\s*['\"]input['\"]"),
    "dom.selector.password": re.compile(r"input\[type=['\"]password['\"]\]", re.I),
    "dom.selector.email": re.compile(r"input\[type=['\"]email['\"]\]", re.I),
}

KEYWORDS = ["api", "config", "collect", "track", "sync", "update", "rule", "campaign", "save", "session", "token"]
STORAGE_KEYWORDS = ["token", "config", "settings", "rule", "flag", "uid", "session", "auth", "user_auth", "user_id"]
DOM_KEYWORDS = ["password", "email", "login", "username", "credential", "auth", "token", "session", "user_auth", "user_id"]

URL_RE = re.compile(r"https?://[^\"'\s)]+", re.I)
METHOD_RE = re.compile(r"\b(GET|POST)\b")
INTERVAL_NUM_RE = re.compile(r"setInterval\s*\([^,]+,\s*(\d+)")
ASSIGN_METHOD_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\.method\s*=\s*['\"]([A-Za-z]+)['\"]", re.I)
ASSIGN_URL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\.url\s*=\s*['\"](https?://[^'\"]+)['\"]", re.I)
JQUERY_AJAX_VAR_RE = re.compile(r"(?:jQuery|\$)\.ajax\s*\(\s*([A-Za-z_$][\w$]*)\s*\)")


def classify_interval(code: str) -> str | None:
    vals = [int(v) for v in INTERVAL_NUM_RE.findall(code)]
    if not vals:
        return None
    smallest = min(vals)
    if smallest <= 60000:
        return "short_periodic"
    if smallest <= 3600000:
        return "medium_periodic"
    return "long_periodic"


def scan_js_file(path: Path, role: str = "unknown_script", source_class: str = "first_party", is_minified: bool = False) -> dict[str, Any]:
    text = read_text_safe(path)
    if text is None:
        return {"file": str(path), "role": role, "source_class": source_class, "is_minified": is_minified, "skipped": True}

    signals: list[str] = []
    for k, p in PATTERNS.items():
        if p.search(text):
            signals.append(k)

    urls = URL_RE.findall(text)
    external_origin_present = any(not u.startswith("http://127.0.0.1") and not u.startswith("http://localhost") for u in urls)
    has_any_url_reference = bool(urls)

    methods = set(METHOD_RE.findall(text))
    assigned_methods: dict[str, str] = {v: m.upper() for v, m in ASSIGN_METHOD_RE.findall(text)}
    assigned_urls: dict[str, str] = {v: u for v, u in ASSIGN_URL_RE.findall(text)}
    ajax_vars = JQUERY_AJAX_VAR_RE.findall(text)
    for var in ajax_vars:
        if var in assigned_methods:
            methods.add(assigned_methods[var])
        if var in assigned_urls:
            urls.append(assigned_urls[var])
            has_any_url_reference = True
            if not assigned_urls[var].startswith("http://127.0.0.1") and not assigned_urls[var].startswith("http://localhost"):
                external_origin_present = True

    if "network.jquery.get" in signals:
        methods.add("GET")
    if "network.jquery.post" in signals:
        methods.add("POST")
    if "network.axios" in signals:
        if re.search(r"\baxios\.post\s*\(", text):
            methods.add("POST")
        if re.search(r"\baxios\.get\s*\(", text):
            methods.add("GET")

    endpoint_keywords = sorted({kw for kw in KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", text, re.I)})
    methods = sorted(methods)
    storage_keywords = sorted({kw for kw in STORAGE_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", text, re.I)})
    dom_keywords = sorted({kw for kw in DOM_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", text, re.I)})
    message_actions = sorted(set(re.findall(r"action\s*:\s*['\"]([A-Za-z0-9_]+)['\"]", text)))

    return {
        "file": str(path),
        "role": role,
        "source_class": source_class,
        "is_minified": is_minified,
        "signals": sorted(set(signals)),
        "network": {
            "external_origin_present": external_origin_present,
            "has_any_url_reference": has_any_url_reference,
            "methods": methods,
            "endpoint_keywords": endpoint_keywords,
        },
        "keywords": {
            "storage": storage_keywords,
            "dom": dom_keywords,
            "message_actions": message_actions,
        },
        "interval_category": classify_interval(text),
    }


def aggregate_js_scans(scans: list[dict[str, Any]]) -> dict[str, Any]:
    all_signals = sorted({s for sc in scans for s in sc.get("signals", [])})
    external = any(sc.get("network", {}).get("external_origin_present") for sc in scans)
    any_url_reference = any(sc.get("network", {}).get("has_any_url_reference") for sc in scans)
    methods = sorted({m for sc in scans for m in sc.get("network", {}).get("methods", [])})
    endpoint_keywords = sorted({k for sc in scans for k in sc.get("network", {}).get("endpoint_keywords", [])})
    storage_keywords = sorted({k for sc in scans for k in sc.get("keywords", {}).get("storage", [])})
    dom_keywords = sorted({k for sc in scans for k in sc.get("keywords", {}).get("dom", [])})
    msg_actions = sorted({k for sc in scans for k in sc.get("keywords", {}).get("message_actions", [])})
    interval_categories = sorted({c for sc in scans if sc.get("interval_category") for c in [sc.get("interval_category")]})
    by_role_signals: dict[str, list[str]] = {}
    by_role_keywords: dict[str, dict[str, list[str]]] = {}
    for sc in scans:
        role = sc.get("role", "unknown_script")
        by_role_signals.setdefault(role, [])
        by_role_signals[role].extend(sc.get("signals", []))
        by_role_keywords.setdefault(role, {"storage": [], "dom": [], "message_actions": []})
        by_role_keywords[role]["storage"].extend(sc.get("keywords", {}).get("storage", []))
        by_role_keywords[role]["dom"].extend(sc.get("keywords", {}).get("dom", []))
        by_role_keywords[role]["message_actions"].extend(sc.get("keywords", {}).get("message_actions", []))
    by_role_signals = {k: sorted(set(v)) for k, v in by_role_signals.items()}
    by_role_keywords = {
        role: {k: sorted(set(v)) for k, v in kw.items()}
        for role, kw in by_role_keywords.items()
    }
    return {
        "signals": all_signals,
        "network": {
            "external_origin_present": external,
            "has_any_url_reference": any_url_reference,
            "methods": methods,
            "endpoint_keywords": endpoint_keywords,
        },
        "keywords": {
            "storage": storage_keywords,
            "dom": dom_keywords,
            "message_actions": msg_actions,
        },
        "interval_categories": interval_categories,
        "by_role_signals": by_role_signals,
        "by_role_keywords": by_role_keywords,
        "files": scans,
    }
