from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from typing import Any

from .feature_builder import build_rerank_features
from .scorer import compare_rerank_features


def _as_candidates(compare_result: Any) -> list[dict[str, Any]]:
    if isinstance(compare_result, dict):
        matches = compare_result.get("matches")
        if isinstance(matches, list):
            return [m for m in matches if isinstance(m, dict)]
        return [compare_result]
    if isinstance(compare_result, list):
        return [m for m in compare_result if isinstance(m, dict)]
    return []


def _is_probably_fingerprint(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    keys = {
        "capability_profile",
        "capability_combinations",
        "predicted_flows",
        "behavior_tags",
        "static_code_signals",
    }
    return bool(keys & set(obj.keys()))


def _extract_fingerprint(candidate: dict[str, Any]) -> dict[str, Any] | None:
    def _unwrap_vf(vf: Any) -> dict[str, Any] | None:
        cur = vf
        for _ in range(3):
            if not isinstance(cur, dict):
                return None
            if _is_probably_fingerprint(cur):
                return cur
            if "vector_fingerprint" in cur and isinstance(cur.get("vector_fingerprint"), dict):
                cur = cur["vector_fingerprint"]
                continue
            return None
        return cur if isinstance(cur, dict) and _is_probably_fingerprint(cur) else None

    payload = candidate.get("payload")
    if isinstance(payload, dict):
        if isinstance(payload.get("vector_fingerprint"), dict):
            unwrapped = _unwrap_vf(payload["vector_fingerprint"])
            if isinstance(unwrapped, dict):
                return unwrapped
        if isinstance(payload.get("fingerprint"), dict):
            unwrapped = _unwrap_vf(payload["fingerprint"])
            if isinstance(unwrapped, dict):
                return unwrapped

    if isinstance(candidate.get("vector_fingerprint"), dict):
        unwrapped = _unwrap_vf(candidate["vector_fingerprint"])
        if isinstance(unwrapped, dict):
            return unwrapped
    if isinstance(candidate.get("fingerprint"), dict):
        unwrapped = _unwrap_vf(candidate["fingerprint"])
        if isinstance(unwrapped, dict):
            return unwrapped

    # Fallback: compareDB legacy shape may store fingerprint in `document`
    document = candidate.get("document")
    if isinstance(document, dict) and _is_probably_fingerprint(document):
        return document
    if isinstance(document, str):
        try:
            parsed = json.loads(document)
            unwrapped = _unwrap_vf(parsed)
            if isinstance(unwrapped, dict):
                return unwrapped
        except Exception:
            pass

    if _is_probably_fingerprint(candidate):
        return candidate

    return None


def _extract_score(candidate: dict[str, Any]) -> float:
    for key in ("score", "similarity", "vector_similarity"):
        if key in candidate:
            try:
                return float(candidate.get(key) or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _collect_strings(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value.lower())
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(_collect_strings(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_collect_strings(v))
    return out


def _resolve_extension_root(extension_target: str | None) -> tuple[str | None, str | None]:
    if not isinstance(extension_target, str) or not extension_target.strip():
        return None, None
    p = extension_target
    if not os.path.exists(p):
        return None, None
    if os.path.isdir(p):
        return p, None
    low = p.lower()
    if low.endswith(".zip"):
        td = tempfile.mkdtemp(prefix="rerank_ext_")
        try:
            with zipfile.ZipFile(p, "r") as zf:
                zf.extractall(td)
            manifest_path = None
            for root, _dirs, files in os.walk(td):
                if "manifest.json" in files:
                    manifest_path = os.path.join(root, "manifest.json")
                    break
            if manifest_path:
                return os.path.dirname(manifest_path), td
            return td, td
        except Exception:
            shutil.rmtree(td, ignore_errors=True)
            return None, None
    return None, None


def _scan_extension_static_evidence(extension_target: str | None) -> dict[str, Any]:
    root, tmp_dir = _resolve_extension_root(extension_target)
    if root is None:
        return {
            "unpacked_root": None,
            "scanned_files": 0,
            "scanned_js_json_files": 0,
            "concrete_static_evidence": [],
            "notes": ["extension_target_unavailable_or_unresolvable"],
        }
    hits: set[str] = set()
    weak_hits: set[str] = set()
    scanned_files = 0
    scanned_js_json_files = 0
    manifest_capabilities = {
        "permissions": [],
        "host_permissions": [],
        "content_script_matches": [],
        "background_scripts": [],
        "background_service_worker": None,
    }
    filename_tokens = [
        "screenshot-helper.js",
        "click-helper.js",
        "fill-helper.js",
        "keyboard-helper.js",
        "form-submit-helper.js",
        "network-helper.js",
        "web-fetcher-helper.js",
        "inject-bridge.js",
    ]
    content_tokens = [
        "chrome.tabs.capturevisibletab",
        "capturevisibletab",
        "chrome_screenshot",
        "page.capturescreenshot",
        "chrome.debugger",
        "chrome.scripting.executescript",
        "debugger.sendcommand",
        "document.body.innertext",
        "document.body.innerhtml",
        "document.documentelement.outerhtml",
        "document.queryselector",
        "document.queryselectorall",
        "textcontent",
        "innertext",
        "page_content",
        "extractcontent",
        "scrape",
        "crawler",
        "dom snapshot",
        "html capture",
        "localstorage",
        "sessionstorage",
        "chrome.storage.session",
        "chrome.cookies",
        "clearallcookies",
        "save_session",
        "save_session.php",
        "get_session.php",
        "get_sessions.php",
        "set_session_changed",
        "tg.cloudapi.stream",
        "web.telegram.org",
        "chrome.runtime.sendmessage",
        "runtime.sendmessage",
        "chrome.runtime.onmessage",
        "runtime.onmessage",
    ]
    weak_content_tokens = [
        "offscreen",
        "activetab",
        "tabs",
        "<all_urls>",
    ]
    try:
        for cur_root, _dirs, files in os.walk(root):
            _dirs[:] = [d for d in _dirs if d not in {"__MACOSX", ".git", "node_modules", ".cache", "dist"}]
            for fn in files:
                scanned_files += 1
                fn_low = fn.lower()
                rel = os.path.relpath(os.path.join(cur_root, fn), root).replace("\\", "/")
                for tok in filename_tokens:
                    if tok in fn_low or tok in rel.lower():
                        hits.add(tok)
                if not (fn_low.endswith(".js") or fn_low.endswith(".json")):
                    continue
                scanned_js_json_files += 1
                fpath = os.path.join(cur_root, fn)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as rf:
                        raw = rf.read()
                        text = raw.lower()
                    for tok in content_tokens:
                        if tok in text:
                            hits.add(tok)
                    for tok in weak_content_tokens:
                        if tok in text:
                            weak_hits.add(tok)
                    if fn_low == "manifest.json":
                        try:
                            manifest_obj = json.loads(raw)
                        except Exception:
                            manifest_obj = {}
                        if isinstance(manifest_obj, dict):
                            perms = manifest_obj.get("permissions", [])
                            host_perms = manifest_obj.get("host_permissions", [])
                            cs = manifest_obj.get("content_scripts", [])
                            bg = manifest_obj.get("background", {})
                            if isinstance(perms, list):
                                manifest_capabilities["permissions"] = sorted(
                                    {str(x) for x in perms if isinstance(x, (str, int, float))}
                                )
                            if isinstance(host_perms, list):
                                manifest_capabilities["host_permissions"] = sorted(
                                    {str(x) for x in host_perms if isinstance(x, (str, int, float))}
                                )
                            if isinstance(cs, list):
                                matches: set[str] = set()
                                for row in cs:
                                    if not isinstance(row, dict):
                                        continue
                                    ms = row.get("matches", [])
                                    if isinstance(ms, list):
                                        matches.update(str(x) for x in ms if isinstance(x, (str, int, float)))
                                manifest_capabilities["content_script_matches"] = sorted(matches)
                            if isinstance(bg, dict):
                                scripts = bg.get("scripts", [])
                                sw = bg.get("service_worker")
                                if isinstance(scripts, list):
                                    manifest_capabilities["background_scripts"] = sorted(
                                        {str(x) for x in scripts if isinstance(x, (str, int, float))}
                                    )
                                if isinstance(sw, (str, int, float)):
                                    manifest_capabilities["background_service_worker"] = str(sw)
                except Exception:
                    continue
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    notes: list[str] = []
    if not hits:
        notes.append("no_concrete_static_evidence_found_in_scanned_files")
    return {
        "unpacked_root": root,
        "scanned_files": scanned_files,
        "scanned_js_json_files": scanned_js_json_files,
        "concrete_static_evidence": sorted(hits),
        "weak_capability_evidence": sorted(weak_hits),
        "manifest_capabilities": manifest_capabilities,
        "notes": notes,
    }


def _extract_concrete_evidence(query_fingerprint: dict[str, Any], extension_target: str | None = None) -> dict[str, Any]:
    txt = " ".join(_collect_strings(query_fingerprint))
    scan_info = _scan_extension_static_evidence(extension_target)
    file_hits = scan_info.get("concrete_static_evidence", []) if isinstance(scan_info.get("concrete_static_evidence", []), list) else []
    weak_hits = scan_info.get("weak_capability_evidence", []) if isinstance(scan_info.get("weak_capability_evidence", []), list) else []
    txt += " " + " ".join(str(x).lower() for x in file_hits)
    screenshot_keys = [
        "chrome.tabs.capturevisibletab",
        "tabs.capturevisibletab",
        "capturevisibletab",
        "chrome_screenshot",
        "screenshot-helper.js",
        "screenshot-helper",
        "page.capturescreenshot",
        "tabcapture",
        "desktopcapture",
        "takescreenshot",
        "capturescreenshot",
        "browser_screenshot",
        "page_screenshot",
        "todataurl",
    ]
    page_content_keys = [
        "document.body.innertext",
        "document.body.textcontent",
        "document.body.innerhtml",
        "document.documentelement.outerhtml",
        "document.queryselector",
        "document.queryselectorall",
        "textcontent",
        "innertext",
        "getelementbyid",
        "getelementsbyclassname",
        "getelementsbytagname",
        "email body selector",
        "message body selector",
        "inbox",
        "message list",
        "email subject",
        "email body",
        "compose textarea",
        "input listener",
        "change listener",
        "submit listener",
    ]
    dom_tampering_keys = [
        "innerhtml =",
        "outerhtml =",
        "insertadjacenthtml",
        "appendchild",
        "removechild",
        "replacechild",
        "element.remove()",
        "classlist.add",
        "classlist.remove",
        "style.display =",
        "value =",
        "setattribute",
        "dispatchevent",
        "click()",
        "submit()",
        "form.submit()",
        "mutationobserver",
        "remote response inserted into dom",
    ]
    remote_keys = [
        "chrome.debugger",
        "debugger.sendcommand",
        "chrome.scripting.executescript",
        "scripting.executescript",
        "click-helper.js",
        "fill-helper.js",
        "keyboard-helper.js",
        "form-submit-helper.js",
        "network-helper.js",
        "web-fetcher-helper.js",
        "inject-bridge.js",
    ]
    session_read_keys = [
        "localstorage",
        "localstorage.getitem",
        "localstorage.setitem",
        "localstorage.clear",
        "sessionstorage",
        "sessionstorage.getitem",
        "chrome.storage.session",
        "document.cookie",
        "chrome.cookies",
        "clearallcookies",
        "storage_or_cookie_read",
    ]
    session_send_keys = [
        "save_session",
        "save_session.php",
        "get_session.php",
        "get_sessions.php",
        "tg.cloudapi.stream",
        "set_session_changed",
        "payload_post_send",
        "session payload",
        "token payload",
        "cookie payload",
        "xmlhttprequest post session",
        "fetch post session",
    ]
    session_bridge_keys = [
        "chrome.runtime.sendmessage",
        "runtime.sendmessage",
        "chrome.runtime.onmessage",
        "runtime.onmessage",
    ]
    session_origin_keys = [
        "web.telegram.org",
    ]
    generic_api_keys = ["fetch", "runtime.sendmessage", "xmlhttprequest"]
    weak_keys = ["offscreen", "activetab", "tabs", "<all_urls>"]
    fingerprint_keys = [
        "navigator.useragent",
        "navigator.language",
        "navigator.languages",
        "navigator.platform",
        "navigator.hardwareconcurrency",
        "navigator.devicememory",
        "screen.width",
        "screen.height",
        "screen.availwidth",
        "screen.availheight",
        "resolvedoptions().timezone",
        "timezone",
        "canvas fingerprint",
        "webgl fingerprint",
    ]

    screenshot_evidence = [k for k in screenshot_keys if k in txt]
    page_content_evidence = [k for k in page_content_keys if k in txt]
    dom_tampering_evidence = [k for k in dom_tampering_keys if k in txt]
    remote_evidence = [k for k in remote_keys if k in txt]
    session_read_evidence = [k for k in session_read_keys if k in txt]
    session_send_evidence = [k for k in session_send_keys if k in txt]
    session_bridge_evidence = [k for k in session_bridge_keys if k in txt]
    session_origin_evidence = [k for k in session_origin_keys if k in txt]
    fingerprint_evidence = [k for k in fingerprint_keys if k in txt]
    generic_api_evidence = [k for k in generic_api_keys if k in txt]
    weak_capability_evidence = [k for k in weak_keys if k in txt]
    weak_capability_evidence.extend([str(x).lower() for x in weak_hits])
    return {
        "screenshot_evidence": sorted(set(screenshot_evidence)),
        "page_content_evidence": sorted(set(page_content_evidence)),
        "dom_tampering_evidence": sorted(set(dom_tampering_evidence)),
        "remote_control_evidence": sorted(set(remote_evidence)),
        "session_read_evidence": sorted(set(session_read_evidence)),
        "session_send_evidence": sorted(set(session_send_evidence)),
        "session_bridge_evidence": sorted(set(session_bridge_evidence)),
        "session_origin_evidence": sorted(set(session_origin_evidence)),
        "fingerprinting_evidence": sorted(set(fingerprint_evidence)),
        "generic_api_evidence": sorted(set(generic_api_evidence)),
        "concrete_static_evidence": sorted(set(file_hits)),
        "weak_capability_evidence": sorted(set(weak_capability_evidence)),
        "manifest_capabilities": scan_info.get("manifest_capabilities", {}),
        "scan_info": scan_info,
    }


def _scenario_evidence_adjustment(pattern_name: str, evidence: dict[str, Any]) -> dict[str, Any]:
    p = str(pattern_name or "").lower()
    screenshot = evidence.get("screenshot_evidence", []) if isinstance(evidence.get("screenshot_evidence", []), list) else []
    page_content = evidence.get("page_content_evidence", []) if isinstance(evidence.get("page_content_evidence", []), list) else []
    dom_tampering = evidence.get("dom_tampering_evidence", []) if isinstance(evidence.get("dom_tampering_evidence", []), list) else []
    remote = evidence.get("remote_control_evidence", []) if isinstance(evidence.get("remote_control_evidence", []), list) else []
    weak = evidence.get("weak_capability_evidence", []) if isinstance(evidence.get("weak_capability_evidence", []), list) else []
    session_read = evidence.get("session_read_evidence", []) if isinstance(evidence.get("session_read_evidence", []), list) else []
    session_send = evidence.get("session_send_evidence", []) if isinstance(evidence.get("session_send_evidence", []), list) else []
    session_bridge = evidence.get("session_bridge_evidence", []) if isinstance(evidence.get("session_bridge_evidence", []), list) else []
    session_origin = evidence.get("session_origin_evidence", []) if isinstance(evidence.get("session_origin_evidence", []), list) else []
    fingerprinting = evidence.get("fingerprinting_evidence", []) if isinstance(evidence.get("fingerprinting_evidence", []), list) else []

    static_capability_score = 0.0
    concrete_api_evidence_score = 0.0
    concrete_api_evidence: list[str] = []
    negative_penalties: list[str] = []
    rerank_reason_parts: list[str] = []

    # screenshot capture scenario requires real capture evidence
    if "tabs_capture_visible_tab_exfiltration" in p:
        concrete_api_evidence.extend(screenshot)
        if any(k in screenshot for k in ("chrome.tabs.capturevisibletab", "capturevisibletab")):
            concrete_api_evidence_score += 0.35
            rerank_reason_parts.append("capture_visible_tab_detected")
        if "screenshot-helper.js" in screenshot or "screenshot-helper" in screenshot:
            concrete_api_evidence_score += 0.25
            rerank_reason_parts.append("screenshot_helper_detected")
        if "chrome_screenshot" in screenshot:
            concrete_api_evidence_score += 0.30
            rerank_reason_parts.append("chrome_screenshot_detected")
        if "page.capturescreenshot" in screenshot:
            concrete_api_evidence_score += 0.20
            rerank_reason_parts.append("strong_screenshot_api_match")
        if screenshot:
            static_capability_score += min(0.30, 0.08 * len(screenshot))
    # page screenshot/content capture scenario is narrowed to visual screenshot evidence only
    if "page_screenshot_or_content_capture" in p:
        concrete_api_evidence.extend(screenshot)
        if screenshot:
            static_capability_score += min(0.35, 0.07 * len(screenshot))

    # DOM content surveillance scenarios
    if any(k in p for k in ("webmail_dom_surveillance_collection", "input_change_event_collection", "dom_content_collection")):
        concrete_api_evidence.extend(page_content)
        if page_content:
            concrete_api_evidence_score += min(0.30, 0.06 * len(page_content))
            static_capability_score += min(0.25, 0.05 * len(page_content))
            rerank_reason_parts.append("dom_content_collection_detected")

    # DOM tampering scenarios
    if any(k in p for k in ("webmail_dom_content_tampering", "c2_response_dom_innerhtml_injection", "remote_dom_event_content_manipulation")):
        concrete_api_evidence.extend(dom_tampering)
        if dom_tampering:
            concrete_api_evidence_score += min(0.35, 0.07 * len(dom_tampering))
            static_capability_score += min(0.25, 0.05 * len(dom_tampering))
            rerank_reason_parts.append("dom_tampering_detected")

    # remote control / automation scenarios
    if any(k in p for k in ("remote_browser_control", "browser_automation", "debugger", "scripting", "automation")):
        concrete_api_evidence.extend(remote)
        required_combo = (
            ("chrome.debugger" in remote)
            and ("chrome.scripting.executescript" in remote or "scripting.executescript" in remote or "debugger.sendcommand" in remote)
            and any(x in remote for x in ("click-helper.js", "fill-helper.js", "keyboard-helper.js", "form-submit-helper.js", "inject-bridge.js", "web-fetcher-helper.js", "network-helper.js"))
        )
        if required_combo:
            concrete_api_evidence_score += 0.35
            rerank_reason_parts.append("debugger_scripting_tabs_combo")
        helper_hits = [x for x in remote if x.endswith("-helper.js") or "inject-bridge.js" in x]
        if len(helper_hits) >= 3:
            static_capability_score += 0.20
            rerank_reason_parts.append("automation_helpers_detected")
        static_capability_score += min(0.20, 0.03 * len(remote))

    # fingerprinting scenario only when true fingerprint fields exist
    if "browser_fingerprinting_environment_collection" in p or "fingerprinting" in p:
        concrete_api_evidence.extend(fingerprinting)
        if len(fingerprinting) >= 2:
            concrete_api_evidence_score += min(0.20, 0.06 * len(fingerprinting))
            rerank_reason_parts.append("fingerprinting_fields_detected")
        else:
            negative_penalties.append("insufficient_fingerprinting_fields")
            concrete_api_evidence_score -= 0.20
        if screenshot or remote:
            negative_penalties.append("screenshot_or_remote_control_not_fingerprinting")
            concrete_api_evidence_score -= 0.15

    # session exfiltration penalties when concrete payload evidence missing
    if "session_storage_exfiltration" in p or "session_theft" in p:
        concrete_api_evidence.extend(session_read)
        concrete_api_evidence.extend(session_send)
        concrete_api_evidence.extend(session_bridge)
        concrete_api_evidence.extend(session_origin)
        has_page_storage = any(
            k in session_read
            for k in (
                "localstorage",
                "localstorage.getitem",
                "localstorage.setitem",
                "localstorage.clear",
                "sessionstorage",
                "sessionstorage.getitem",
                "document.cookie",
            )
        )
        has_save_endpoint = any(k in session_send for k in ("save_session.php", "tg.cloudapi.stream"))
        has_session_endpoint = any(k in session_send for k in ("save_session.php", "get_session.php", "get_sessions.php"))
        has_save_action = "save_session" in session_send
        has_message_bridge = bool(session_bridge)
        has_session_payload = bool(session_read) and bool(session_send)
        has_session_theft_structure = bool(
            (has_page_storage and has_message_bridge and (has_save_endpoint or has_session_endpoint))
            or (has_save_endpoint and has_save_action and has_message_bridge)
            or (has_page_storage and has_save_action and has_session_origin)
        )
        if has_session_theft_structure:
            concrete_api_evidence_score += 0.08
            static_capability_score += min(0.12, 0.03 * len(set(session_read + session_send + session_bridge + session_origin)))
            rerank_reason_parts.append("session_theft_structural_evidence")
        elif not has_session_payload:
            negative_penalties.append("missing_session_payload_read_send_evidence")
            concrete_api_evidence_score -= 0.30
        if screenshot or len(remote) >= 4:
            negative_penalties.append("strong_non_session_profile_detected")
            concrete_api_evidence_score -= 0.25

    return {
        "static_capability_score": static_capability_score,
        "concrete_api_evidence": sorted(set(concrete_api_evidence)),
        "weak_capability_evidence": sorted(set(weak)),
        "concrete_api_evidence_score": concrete_api_evidence_score,
        "negative_penalties": negative_penalties,
        "rerank_reason": ", ".join(rerank_reason_parts) if rerank_reason_parts else "vector_similarity_dominant",
    }


def rerank_compare_result(
    query_fingerprint: dict,
    compare_result,
    min_final_score: float = 0.0,
    extension_target: str | None = None,
) -> dict:
    query_rerank_features = build_rerank_features(query_fingerprint)
    concrete_evidence = _extract_concrete_evidence(
        query_fingerprint if isinstance(query_fingerprint, dict) else {},
        extension_target=extension_target,
    )
    scan_info = concrete_evidence.get("scan_info", {}) if isinstance(concrete_evidence.get("scan_info", {}), dict) else {}
    print(f"[rerank_evidence] extension_target={extension_target}", flush=True)
    print(f"[rerank_evidence] unpacked_root={scan_info.get('unpacked_root')}", flush=True)
    print(f"[rerank_evidence] scanned_files={scan_info.get('scanned_files', 0)}", flush=True)
    print(f"[rerank_evidence] scanned_js_json_files={scan_info.get('scanned_js_json_files', 0)}", flush=True)
    print(f"[rerank_evidence] concrete_static_evidence={concrete_evidence.get('concrete_static_evidence', [])}", flush=True)
    if scan_info.get("notes"):
        print(f"[rerank_evidence] notes={scan_info.get('notes')}", flush=True)
    candidates = _as_candidates(compare_result)

    reranked_matches: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for idx, candidate in enumerate(candidates):
        candidate_id = candidate.get("id") if isinstance(candidate.get("id"), str) else f"candidate_{idx}"
        candidate_fp = _extract_fingerprint(candidate)
        if candidate_fp is None:
            skipped.append(
                {
                    "id": candidate_id,
                    "reason": "missing vector_fingerprint in candidate payload",
                }
            )
            continue

        candidate_features = build_rerank_features(candidate_fp)
        vector_similarity = _extract_score(candidate)

        breakdown = compare_rerank_features(
            query_features=query_rerank_features,
            candidate_features=candidate_features,
            vector_similarity=vector_similarity,
        )

        base_score = float(breakdown.get("final_score", 0.0))
        payload = candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
        pattern_name = payload.get("pattern_name") or candidate.get("pattern_name")
        adj = _scenario_evidence_adjustment(str(pattern_name or ""), concrete_evidence)
        static_capability_score = float(adj.get("static_capability_score", 0.0) or 0.0)
        concrete_api_evidence_score = float(adj.get("concrete_api_evidence_score", 0.0) or 0.0)
        concrete_api_evidence = adj.get("concrete_api_evidence", []) if isinstance(adj.get("concrete_api_evidence", []), list) else []
        if not concrete_api_evidence and concrete_evidence.get("concrete_static_evidence"):
            concrete_api_evidence = list(concrete_evidence.get("concrete_static_evidence", []))[:6]
            adj["rerank_reason"] = f"{adj.get('rerank_reason', 'vector_similarity_dominant')}, concrete_static_evidence_context"
        negative_penalty = 0.10 * len(adj.get("negative_penalties", []))
        # final evidence-aware score
        final_score = base_score + static_capability_score + concrete_api_evidence_score - negative_penalty
        if final_score < 0.0:
            final_score = 0.0
        if final_score > 1.0:
            final_score = 1.0
        if final_score < float(min_final_score):
            continue

        reranked_matches.append(
            {
                "id": candidate_id,
                "vector_similarity": vector_similarity,
                "final_score": final_score,
                "static_capability_score": static_capability_score,
                "concrete_api_evidence": concrete_api_evidence,
                "concrete_api_evidence_score": concrete_api_evidence_score,
                "negative_penalties": adj.get("negative_penalties", []),
                "rerank_reason": adj.get("rerank_reason", ""),
                "rerank_breakdown": {
                    **breakdown,
                    "base_final_score": base_score,
                    "static_capability_score": static_capability_score,
                    "concrete_api_evidence": concrete_api_evidence,
                    "concrete_api_evidence_score": concrete_api_evidence_score,
                    "negative_penalties": adj.get("negative_penalties", []),
                    "rerank_reason": adj.get("rerank_reason", ""),
                },
                "doc_ref": payload.get("doc_ref") or candidate.get("doc_ref"),
                "pattern_name": payload.get("pattern_name") or candidate.get("pattern_name"),
                "payload": payload,
            }
        )

    # force-inject screenshot/remote-control candidates when concrete evidence is strong
    evidence_injected_candidates: list[str] = []
    has_screenshot = bool(concrete_evidence.get("screenshot_evidence")) or bool(concrete_evidence.get("page_content_evidence"))
    has_remote = bool(concrete_evidence.get("remote_control_evidence"))
    forced_patterns: list[str] = []
    if has_screenshot:
        forced_patterns.extend(["tabs_capture_visible_tab_exfiltration", "page_screenshot_or_content_capture"])
    if has_remote:
        forced_patterns.extend(["browser_automation_remote_control", "remote_browser_control_debugger_scripting"])
    existing_patterns = {str(m.get("pattern_name")) for m in reranked_matches if isinstance(m, dict)}
    if forced_patterns:
        for ptn in forced_patterns:
            if ptn in existing_patterns:
                continue
            evidence_injected_candidates.append(ptn)
            reranked_matches.append(
                {
                    "id": f"forced_{ptn}",
                    "vector_similarity": 0.0,
                    "final_score": 0.42,
                    "static_capability_score": 0.20,
                    "concrete_api_evidence": sorted(
                        set(concrete_evidence.get("screenshot_evidence", []) + concrete_evidence.get("page_content_evidence", []) + concrete_evidence.get("remote_control_evidence", []))
                    ),
                    "concrete_api_evidence_score": 0.15,
                    "negative_penalties": [],
                    "rerank_reason": "evidence_injected_candidate",
                    "rerank_breakdown": {
                        "base_final_score": 0.0,
                        "static_capability_score": 0.20,
                        "concrete_api_evidence": sorted(
                            set(concrete_evidence.get("screenshot_evidence", []) + concrete_evidence.get("page_content_evidence", []) + concrete_evidence.get("remote_control_evidence", []))
                        ),
                        "concrete_api_evidence_score": 0.15,
                        "negative_penalties": [],
                        "rerank_reason": "evidence_injected_candidate",
                    },
                    "doc_ref": f"scenario_docs/{ptn}.md",
                    "pattern_name": ptn,
                    "payload": {"pattern_name": ptn, "doc_ref": f"scenario_docs/{ptn}.md"},
                    "candidate_only": True,
                    "threshold_passed": True,
                }
            )

    reranked_matches.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
    # Prefer rows with concrete evidence first, then score.
    reranked_matches.sort(
        key=lambda x: (
            1 if isinstance(x.get("concrete_api_evidence", []), list) and len(x.get("concrete_api_evidence", [])) > 0 else 0,
            float(x.get("final_score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    selected_candidates = reranked_matches[:3]
    top_candidate_patterns = [m.get("pattern_name") for m in selected_candidates if isinstance(m, dict)]
    print(f"[rerank_evidence] evidence_injected_candidates={evidence_injected_candidates}", flush=True)
    vector_sorted = sorted(
        [
            {
                "pattern_name": (c.get("payload", {}) or {}).get("pattern_name") or c.get("pattern_name"),
                "vector_similarity": _extract_score(c),
            }
            for c in candidates
        ],
        key=lambda x: float(x.get("vector_similarity", 0.0) or 0.0),
        reverse=True,
    )

    return {
        "query_rerank_features": query_rerank_features,
        "vector_top_pattern": vector_sorted[0]["pattern_name"] if vector_sorted else None,
        "vector_top_score": float(vector_sorted[0]["vector_similarity"] or 0.0) if vector_sorted else 0.0,
        "evidence_rerank_top_pattern": reranked_matches[0]["pattern_name"] if reranked_matches else None,
        "evidence_rerank_top_score": float(reranked_matches[0]["final_score"] or 0.0) if reranked_matches else 0.0,
        "top_candidate_patterns": top_candidate_patterns,
        "selected_candidates": selected_candidates,
        "evidence_injected_candidates": evidence_injected_candidates,
        "concrete_static_evidence": concrete_evidence.get("concrete_static_evidence", []),
        "weak_capability_evidence": concrete_evidence.get("weak_capability_evidence", []),
        "manifest_capabilities": concrete_evidence.get("manifest_capabilities", {}),
        "reranked_matches": reranked_matches,
        "skipped": skipped,
    }
