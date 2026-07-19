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

# Message-flow extraction. Trigger names are carried under several object keys
# (this corpus uses msg/evt heavily; action: is rare), so cover the common set.
MESSAGE_KEYS = "msg|evt|type|cmd|name|action"
# Constructed message literal, e.g. {msg:"startBgImageCapturingMessage"}. (key, name).
MESSAGE_LITERAL_KV_RE = re.compile(rf"({MESSAGE_KEYS})\s*:\s*['\"]([A-Za-z0-9_]+)['\"]")
# A message literal only counts as a *send* when it sits inside a sendMessage(...) call.
# Keys like type:/name: are generic (validation-schema literals use them heavily), so
# proximity to sendMessage is what separates real messages from schema noise.
SENDMESSAGE_RE = re.compile(r"sendMessage\s*\(")
_SEND_WINDOW = 120
# Dispatch comparison inside an onMessage handler, both orderings:
#   "X"===e.msg   and   e.msg==="X"
HANDLE_LEFT_RE = re.compile(rf"['\"]([A-Za-z0-9_]+)['\"]\s*===?\s*[A-Za-z_$][\w$]*\.({MESSAGE_KEYS})")
HANDLE_RIGHT_RE = re.compile(rf"[A-Za-z_$][\w$]*\.({MESSAGE_KEYS})\s*===?\s*['\"]([A-Za-z0-9_]+)['\"]")
# Privileged chrome.* APIs worth extracting as trigger-chain sinks. Single source of
# truth: the union of every scenario doc's `expected_api` — the SAME source the harness
# wraps for observation — so extraction and observation never drift. Derived lazily from
# the doc files (self-contained; no import of the heavy `embedding.scenario` package).
_SCENARIO_DOCS_DIR = Path(__file__).resolve().parents[2] / "embedding" / "scenario_docs"
_SENSITIVE_APIS_CACHE: dict | None = None
_SENSITIVE_API_RE_CACHE = None


def _parse_expected_api_frontmatter(text: str) -> list[str]:
    # Minimal, dependency-free mirror of embedding.scenario.loader.parse_expected_api,
    # duplicated here only to keep Dynamic_RAG decoupled from the embedding package.
    if not text.lstrip().startswith("---"):
        return []
    body = text.lstrip()
    end = body.find("\n---", 3)
    if end == -1:
        return []
    apis: list[str] = []
    in_block = False
    for line in body[3:end].splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.startswith("expected_api:"):
            inline = stripped[len("expected_api:"):].strip()
            if inline.startswith("[") and inline.endswith("]"):
                return [i.strip().strip("'\"") for i in inline[1:-1].split(",") if i.strip()]
            in_block = True
            continue
        if in_block:
            if stripped.startswith("- "):
                apis.append(stripped[2:].strip().strip("'\""))
            else:
                break
    return [a for a in apis if a]


def _get_sensitive_apis() -> tuple[dict, "re.Pattern"]:
    global _SENSITIVE_APIS_CACHE, _SENSITIVE_API_RE_CACHE
    if _SENSITIVE_APIS_CACHE is None:
        apis: dict[str, str] = {}
        if _SCENARIO_DOCS_DIR.is_dir():
            for md in sorted(_SCENARIO_DOCS_DIR.glob("*.md")):
                try:
                    text = md.read_text(encoding="utf-8")
                except Exception:
                    continue
                for canonical in _parse_expected_api_frontmatter(text):
                    method = canonical.rpartition(".")[2]
                    if method:
                        apis[method] = canonical
        _SENSITIVE_APIS_CACHE = apis
        _SENSITIVE_API_RE_CACHE = (
            re.compile(r"\b(" + "|".join(re.escape(k) for k in apis) + r")\s*\(") if apis else None
        )
    return _SENSITIVE_APIS_CACHE, _SENSITIVE_API_RE_CACHE
# How far past a handler-branch comparison to look for the branch body's API calls and
# re-sends. Minified single-statement branches keep the trigger literal and its body
# adjacent; the window is bounded and cut at the next branch to limit misattribution.
_HANDLE_WINDOW = 240
_BRANCH_CUT_RE = re.compile(r"\belse\s+if\b|\belse\s*\{")

# url_visit trigger detection: a navigation-event listener whose handler reaches a
# sensitive API means the API is gated on visiting a URL, not on a message. Best-effort;
# the host gate substring is heuristic (see _extract_url_visit_triggers).
NAV_EVENT_RE = re.compile(r"(?:chrome\.)?(?:tabs\.onUpdated|tabs\.onCreated|webNavigation\.\w+)\.addListener")
# Host/URL gate substring, taken from a suggestively-named const (TARGET/HOST/URL/DOMAIN)
# or a direct .includes("...") / .hostname==="..." literal.
_HOST_GATE_CONST_RE = re.compile(r"[A-Za-z_]*(?:TARGET|HOST|URL|DOMAIN)[A-Za-z_]*\s*=\s*['\"]([A-Za-z0-9.\-]+)['\"]")
_HOST_GATE_INCLUDES_RE = re.compile(r"\.(?:includes|indexOf|startsWith|endsWith)\(\s*['\"]([A-Za-z0-9.\-]+)['\"]")
_HOST_GATE_HOSTNAME_RE = re.compile(r"hostname[^;{]{0,40}?['\"]([A-Za-z0-9.\-]+)['\"]")
# How far past a navigation-listener registration to look for the sensitive API. Only
# an API inside the listener body counts — a same-file API in an unrelated handler
# (e.g. a message handler) must not be misattributed to the navigation trigger.
_NAV_WINDOW = 800


def _extract_url_visit_triggers(text: str) -> list[dict]:
    # A url_visit trigger = a sensitive API called from within a navigation-event
    # listener body. Proximity (API within _NAV_WINDOW after the addListener) is what
    # separates a real nav-gated call from an unrelated same-file call. The host gate
    # substring is heuristic and may be empty (then the stimulus cannot target a URL).
    sensitive_apis, sensitive_api_re = _get_sensitive_apis()
    if not sensitive_api_re:
        return []
    found: set[str] = set()
    for m in NAV_EVENT_RE.finditer(text):
        window = text[m.end(): m.end() + _NAV_WINDOW]
        for a in sensitive_api_re.findall(window):
            found.add(sensitive_apis[a])
    if not found:
        return []
    host_substring = ""
    for rx in (_HOST_GATE_INCLUDES_RE, _HOST_GATE_CONST_RE, _HOST_GATE_HOSTNAME_RE):
        m = rx.search(text)
        if m:
            host_substring = m.group(1)
            break
    return [{"target_api": api, "target_host_substring": host_substring} for api in sorted(found)]


def _messages_in_send_calls(text: str) -> set[tuple[str, str]]:
    # (key, name) literals that appear inside a sendMessage(...) argument window.
    out: set[tuple[str, str]] = set()
    for m in SENDMESSAGE_RE.finditer(text):
        window = text[m.end(): m.end() + _SEND_WINDOW]
        for k, n in MESSAGE_LITERAL_KV_RE.findall(window):
            out.add((k, n))
    return out


def _extract_message_flow(text: str) -> dict[str, Any]:
    # Sends: message literals actually passed to sendMessage (filters schema noise).
    constructed = sorted(_messages_in_send_calls(text))

    handles: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for m in list(HANDLE_LEFT_RE.finditer(text)) + list(HANDLE_RIGHT_RE.finditer(text)):
        if m.re is HANDLE_LEFT_RE:
            name, key = m.group(1), m.group(2)
        else:
            key, name = m.group(1), m.group(2)
        if (name, key) in seen:
            continue
        seen.add((name, key))
        # Branch body window, cut at the next else-if/else so a sibling branch's API is
        # not misattributed to this trigger.
        window = text[m.end(): m.end() + _HANDLE_WINDOW]
        cut = _BRANCH_CUT_RE.search(window)
        if cut:
            window = window[: cut.start()]
        sensitive_apis, sensitive_api_re = _get_sensitive_apis()
        apis = sorted({sensitive_apis[a] for a in sensitive_api_re.findall(window)}) if sensitive_api_re else []
        resends = sorted(_messages_in_send_calls(window))
        handles.append({"name": name, "key": key, "apis": apis, "resends": [{"key": k, "name": n} for k, n in resends]})

    # Vocabulary = names that actually participate in messaging (sent or handled),
    # not every {key:"..."} literal — keeps schema/type literals out of message_actions.
    names = sorted(
        {n for _, n in constructed}
        | {h["name"] for h in handles}
        | {rs["name"] for h in handles for rs in h["resends"]}
    )
    return {
        "names": names,
        "constructed": [{"key": k, "name": n} for k, n in constructed],
        "handles": handles,
    }


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
    message_flow = _extract_message_flow(text)
    # message_actions was previously the action:-only regex; it is now the full message
    # vocabulary (msg/evt/type/cmd/name/action). This is a superset, so existing
    # membership checks (e.g. flow_builder "saveApp" in message_actions) still hold.
    message_actions = message_flow["names"]

    return {
        "file": str(path),
        "role": role,
        "source_class": source_class,
        "is_minified": is_minified,
        "signals": sorted(set(signals)),
        "message_sends": message_flow["constructed"],
        "message_handles": message_flow["handles"],
        "url_visit_triggers": _extract_url_visit_triggers(text),
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
    # Message-flow graph across files, each node/edge tagged with the source file's role
    # (= the execution context) so trigger chains carry handler/dispatch context.
    handle_nodes: list[dict[str, Any]] = []
    send_contexts: dict[str, set[str]] = {}
    url_visit_triggers: list[dict[str, Any]] = []
    for sc in scans:
        role = sc.get("role", "unknown_script")
        for h in sc.get("message_handles", []) or []:
            handle_nodes.append({**h, "context": role})
        for s in sc.get("message_sends", []) or []:
            send_contexts.setdefault(s.get("name", ""), set()).add(role)
        for uv in sc.get("url_visit_triggers", []) or []:
            url_visit_triggers.append({**uv, "context": role})
    message_graph = {
        "handles": handle_nodes,
        "send_contexts": {k: sorted(v) for k, v in send_contexts.items() if k},
        "url_visit_triggers": url_visit_triggers,
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
        "message_graph": message_graph,
        "files": scans,
    }


def build_trigger_chains(agg: dict[str, Any]) -> list[dict[str, Any]]:
    """Reconstruct 'message -> ... -> sensitive API' chains from the message graph.

    A chain is anchored on a handler branch that reaches a sensitive API. It is then
    walked backwards through re-send edges (handler of Mprev re-sends the trigger
    message) to find the earliest entry message. Only literal, in-branch re-sends are
    followed; hops that go through a function call (e.g. an OCR helper) cannot be
    bridged statically and simply leave the entry at the nearest reconstructable node.
    """
    graph = agg.get("message_graph", {}) if isinstance(agg.get("message_graph", {}), dict) else {}
    handles = graph.get("handles", []) if isinstance(graph.get("handles", []), list) else []
    send_contexts = graph.get("send_contexts", {}) if isinstance(graph.get("send_contexts", {}), dict) else {}

    # Index: which handler (by trigger name) re-sends a given message name.
    resenders_of: dict[str, list[dict[str, Any]]] = {}
    for h in handles:
        for rs in h.get("resends", []) or []:
            resenders_of.setdefault(str(rs.get("name", "")), []).append(h)

    chains: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for h in handles:
        apis = h.get("apis", []) or []
        if not apis:
            continue
        trigger = str(h.get("name", ""))
        key = str(h.get("key", ""))
        handler_context = str(h.get("context", "unknown_script"))
        # Walk backwards over re-send edges to find the entry message.
        steps = [trigger]
        entry_message = trigger
        entry_context = handler_context
        cursor = trigger
        depth = 0
        visited = {trigger}
        while depth < 6:
            resenders = resenders_of.get(cursor, [])
            prev = next((r for r in resenders if str(r.get("name", "")) not in visited), None)
            if prev is None:
                break
            pname = str(prev.get("name", ""))
            steps.insert(0, pname)
            entry_message = pname
            entry_context = str(prev.get("context", "unknown_script"))
            visited.add(pname)
            cursor = pname
            depth += 1
        # dispatch_context = where the trigger message is constructed/sent from.
        dispatch_context = send_contexts.get(trigger, [])
        for api in apis:
            dedup = (trigger, api)
            if dedup in seen:
                continue
            seen.add(dedup)
            chains.append({
                "trigger_type": "message",
                "trigger_message": trigger,
                "trigger_key": key,
                "target_api": api,
                "handler_context": handler_context,
                "dispatch_context": dispatch_context,
                "chain_steps": list(steps),
                "entry_message": entry_message,
                "entry_context": entry_context,
            })

    # url_visit chains: sensitive API gated on a navigation event, stimulated by
    # navigating to a URL whose host contains target_host_substring (heuristic; may be
    # empty, in which case the stimulus layer cannot target a URL).
    uv_seen: set[tuple[str, str]] = set()
    for uv in graph.get("url_visit_triggers", []) if isinstance(graph.get("url_visit_triggers", []), list) else []:
        api = str(uv.get("target_api", ""))
        sub = str(uv.get("target_host_substring", ""))
        if not api or (api, sub) in uv_seen:
            continue
        uv_seen.add((api, sub))
        chains.append({
            "trigger_type": "url_visit",
            "target_api": api,
            "target_host_substring": sub,
            "handler_context": str(uv.get("context", "unknown_script")),
            "dispatch_context": ["url_visit"],
        })
    return sorted(chains, key=lambda c: (c.get("target_api", ""), c.get("trigger_type", ""), c.get("trigger_message", "")))
