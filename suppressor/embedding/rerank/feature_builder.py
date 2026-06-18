from __future__ import annotations

from typing import Any


_SIGNAL_SECTIONS = [
    "network",
    "storage",
    "messaging",
    "dom_input",
    "delayed_execution",
    "navigation",
    "request_modification",
    "dynamic_execution",
    "debugger",
    "file_clipboard",
]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _dedup_sorted_str(items: list[Any]) -> list[str]:
    out = {str(x).strip() for x in items if str(x).strip()}
    return sorted(out)


def _normalize_combo(combo: Any) -> str:
    if combo is None:
        return ""
    if isinstance(combo, str):
        raw_parts = combo.split("+")
    elif isinstance(combo, (list, tuple, set)):
        raw_parts = list(combo)
    else:
        raw_parts = [combo]

    parts = sorted({str(p).strip() for p in raw_parts if str(p).strip()})
    return "|".join(parts)


def _flow_to_string(flow: Any) -> str:
    if not isinstance(flow, dict):
        return ""
    trigger = str(flow.get("trigger", "")).strip()
    source = str(flow.get("source", "")).strip()
    sink = str(flow.get("sink", "")).strip()
    path_vals = _as_list(flow.get("path", []))
    path = "|".join(str(x).strip() for x in path_vals if str(x).strip())
    return f"trigger={trigger}|source={source}|path={path}|sink={sink}"


def _flatten_network(signals: dict[str, Any], out: set[str]) -> None:
    for api in _as_list(signals.get("apis")):
        api_s = str(api).strip()
        if api_s:
            out.add(f"network.{api_s}")

    if bool(signals.get("external_origin_present")):
        out.add("network.external_origin_present")

    for method in _as_list(signals.get("methods")):
        method_s = str(method).strip()
        if method_s:
            out.add(f"network.method.{method_s}")

    for keyword in _as_list(signals.get("endpoint_keywords")):
        k = str(keyword).strip()
        if k:
            out.add(f"network.endpoint.{k}")

    for pattern in _as_list(signals.get("patterns")):
        p = str(pattern).strip()
        if p:
            out.add(f"network.pattern.{p}")


def _flatten_storage(signals: dict[str, Any], out: set[str]) -> None:
    for api in _as_list(signals.get("apis")):
        api_s = str(api).strip()
        if api_s:
            out.add(f"storage.{api_s}")

    for keyword in _as_list(signals.get("keywords")):
        k = str(keyword).strip()
        if k:
            out.add(f"storage.keyword.{k}")


def _flatten_messaging(signals: dict[str, Any], out: set[str]) -> None:
    for api in _as_list(signals.get("apis")):
        api_s = str(api).strip()
        if api_s:
            out.add(f"messaging.{api_s}")

    for pattern in _as_list(signals.get("patterns")):
        p = str(pattern).strip()
        if p:
            out.add(f"messaging.pattern.{p}")

    for action in _as_list(signals.get("message_actions")):
        a = str(action).strip()
        if a:
            out.add(f"messaging.action.{a}")


def _flatten_dom_input(signals: dict[str, Any], out: set[str]) -> None:
    for event in _as_list(signals.get("events")):
        e = str(event).strip()
        if e:
            out.add(f"dom_input.event.{e}")

    for selector in _as_list(signals.get("selectors")):
        s = str(selector).strip()
        if s:
            out.add(f"dom_input.selector.{s}")

    for keyword in _as_list(signals.get("keywords")):
        k = str(keyword).strip()
        if k:
            out.add(f"dom_input.keyword.{k}")


def _flatten_delayed_execution(signals: dict[str, Any], out: set[str]) -> None:
    for api in _as_list(signals.get("apis")):
        api_s = str(api).strip()
        if api_s:
            out.add(f"delayed_execution.{api_s}")

    for pattern in _as_list(signals.get("patterns")):
        p = str(pattern).strip()
        if p:
            out.add(f"delayed_execution.pattern.{p}")

    for cat in _as_list(signals.get("interval_categories")):
        c = str(cat).strip()
        if c:
            out.add(f"delayed_execution.interval_category.{c}")


def _flatten_simple(section_name: str, signals: dict[str, Any], out: set[str]) -> None:
    for api in _as_list(signals.get("apis")):
        api_s = str(api).strip()
        if api_s:
            out.add(f"{section_name}.{api_s}")

    for pattern in _as_list(signals.get("patterns")):
        p = str(pattern).strip()
        if p:
            out.add(f"{section_name}.pattern.{p}")


def _flatten_debugger(signals: dict[str, Any], out: set[str]) -> None:
    for api in _as_list(signals.get("apis")):
        api_s = str(api).strip()
        if api_s:
            out.add(f"debugger.{api_s}")


def _flatten_file_clipboard(signals: dict[str, Any], out: set[str]) -> None:
    for api in _as_list(signals.get("apis")):
        api_s = str(api).strip()
        if api_s:
            out.add(f"file_clipboard.{api_s}")

    for event in _as_list(signals.get("events")):
        e = str(event).strip()
        if e:
            out.add(f"file_clipboard.event.{e}")


def build_rerank_features(vector_fingerprint: dict) -> dict:
    fp = vector_fingerprint if isinstance(vector_fingerprint, dict) else {}

    capability_set = _dedup_sorted_str(_as_list(fp.get("capability_profile", [])))

    combo_set = {
        _normalize_combo(combo)
        for combo in _as_list(fp.get("capability_combinations", []))
    }
    capability_combo_set = sorted({c for c in combo_set if c})

    flow_set = {
        _flow_to_string(flow) for flow in _as_list(fp.get("predicted_flows", []))
    }
    flow_set_list = sorted({f for f in flow_set if f})

    behavior_tag_set = _dedup_sorted_str(_as_list(fp.get("behavior_tags", [])))

    signal_set: set[str] = set()
    static_signals = fp.get("static_code_signals", {})
    if isinstance(static_signals, dict):
        for section in _SIGNAL_SECTIONS:
            if section not in static_signals:
                continue
            section_data = static_signals.get(section)
            if not isinstance(section_data, dict):
                continue
            if section == "network":
                _flatten_network(section_data, signal_set)
            elif section == "storage":
                _flatten_storage(section_data, signal_set)
            elif section == "messaging":
                _flatten_messaging(section_data, signal_set)
            elif section == "dom_input":
                _flatten_dom_input(section_data, signal_set)
            elif section == "delayed_execution":
                _flatten_delayed_execution(section_data, signal_set)
            elif section in {"navigation", "request_modification", "dynamic_execution"}:
                _flatten_simple(section, section_data, signal_set)
            elif section == "debugger":
                _flatten_debugger(section_data, signal_set)
            elif section == "file_clipboard":
                _flatten_file_clipboard(section_data, signal_set)

    return {
        "capability_set": capability_set,
        "capability_combo_set": capability_combo_set,
        "flow_set": flow_set_list,
        "behavior_tag_set": behavior_tag_set,
        "signal_set": sorted(signal_set),
    }
