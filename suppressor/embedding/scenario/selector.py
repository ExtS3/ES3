from __future__ import annotations

from .config import DEFAULT_MIN_FINAL_SCORE


def _score_of(match: dict) -> float:
    try:
        return float(match.get("final_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _collect_strings(value) -> list[str]:
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


def _extract_static_evidence(vector_fingerprint: dict) -> dict:
    if not isinstance(vector_fingerprint, dict):
        return {
            "static_capability_score": 0.0,
            "session_payload_score": 0.0,
            "screenshot_evidence": [],
            "remote_control_evidence": [],
            "automation_helper_evidence": [],
            "all_strings": [],
        }
    manifest = vector_fingerprint.get("manifest_profile", {}) if isinstance(vector_fingerprint.get("manifest_profile", {}), dict) else {}
    all_strings = _collect_strings(vector_fingerprint)
    manifest_strings = _collect_strings(manifest)
    perms = " ".join(manifest_strings)
    remote_control_evidence: list[str] = []
    screenshot_evidence: list[str] = []
    automation_helper_evidence: list[str] = []
    session_payload_evidence: list[str] = []

    permission_tokens = ("debugger", "scripting", "tabs", "activetab", "offscreen")
    for token in permission_tokens:
        if token in perms:
            remote_control_evidence.append(token)
    if "<all_urls>" in perms:
        remote_control_evidence.append("<all_urls>")

    helper_tokens = [
        "click-helper",
        "fill-helper",
        "keyboard-helper",
        "form-submit-helper",
        "network-helper",
        "screenshot-helper",
        "web-fetcher-helper",
        "inject-bridge",
    ]
    for tok in helper_tokens:
        if any(tok in s for s in all_strings):
            automation_helper_evidence.append(tok)

    screenshot_tokens = [
        "chrome.tabs.capturevisibletab",
        "page.capturescreenshot",
        "chrome_screenshot",
        "screenshot-helper",
        "todataurl",
        "getdisplaymedia",
    ]
    for tok in screenshot_tokens:
        if any(tok in s for s in all_strings):
            screenshot_evidence.append(tok)

    # session payload evidence must be concrete (not storage permission alone)
    if any(tok in s for tok in ("localstorage", "sessionstorage", "document.cookie", "cookie") for s in all_strings):
        session_payload_evidence.append("storage_or_cookie_read")
    if any("json.stringify" in s and any(k in s for k in ("session", "token", "auth", "user_auth")) for s in all_strings):
        session_payload_evidence.append("session_payload_stringify")
    if any("runtime.sendmessage" in s for s in all_strings):
        session_payload_evidence.append("runtime_message_bridge")
    if any(("fetch" in s or "xmlhttprequest" in s) and "post" in s and any(k in s for k in ("session", "token", "auth", "user_auth")) for s in all_strings):
        session_payload_evidence.append("payload_post_send")

    static_capability_score = float(len(remote_control_evidence) + len(automation_helper_evidence)) / 12.0
    session_payload_score = float(len(session_payload_evidence)) / 4.0
    return {
        "static_capability_score": min(1.0, static_capability_score),
        "session_payload_score": min(1.0, session_payload_score),
        "screenshot_evidence": screenshot_evidence,
        "remote_control_evidence": remote_control_evidence,
        "automation_helper_evidence": automation_helper_evidence,
        "session_payload_evidence": session_payload_evidence,
        "all_strings": all_strings,
    }


def _score_breakdown(match: dict, vector_fingerprint: dict | None = None) -> dict:
    base = _score_of(match)
    if not isinstance(match, dict):
        return {
            "score": base,
            "static_capability_score": 0.0,
            "concrete_api_evidence": [],
            "dynamic_evidence_score": 0.0,
            "negative_penalties": [],
            "candidate_only": True,
        }
    pattern = str(match.get("pattern_name", "")).lower()
    e = _extract_static_evidence(vector_fingerprint or {})

    # broad behavior tags alone should not confirm session theft
    broad_tags = {"external_communication", "message_passing_bridge", "repeated_exfiltration", "session_theft_pattern", "credential_or_token_exfiltration_pattern"}
    vf_tags = set()
    if isinstance(vector_fingerprint, dict):
        tags = vector_fingerprint.get("behavior_tags", [])
        if isinstance(tags, list):
            vf_tags = {str(t) for t in tags}
    broad_only = bool(vf_tags) and vf_tags.issubset(broad_tags)

    static_capability_score = 0.0
    dynamic_evidence_score = 0.0
    concrete_api_evidence: list[str] = []
    negative_penalties: list[str] = []
    score = base

    # screenshot/capture candidates
    if "tabs_capture_visible_tab_exfiltration" in pattern or "page_screenshot_or_content_capture" in pattern:
        concrete_api_evidence.extend(e["screenshot_evidence"])
        static_capability_score += min(0.45, 0.12 * len(e["screenshot_evidence"]))
        static_capability_score += min(0.20, 0.05 * len(e["remote_control_evidence"]))
        if len(e["screenshot_evidence"]) >= 2:
            score += 0.35
        if len(e["screenshot_evidence"]) >= 1:
            score += 0.20

    # remote control candidates
    if "remote_browser_control_debugger_scripting" in pattern or "browser_automation_remote_control" in pattern:
        rc_count = len(e["remote_control_evidence"])
        helper_count = len(e["automation_helper_evidence"])
        concrete_api_evidence.extend(e["remote_control_evidence"])
        concrete_api_evidence.extend(e["automation_helper_evidence"])
        static_capability_score += min(0.50, 0.08 * rc_count) + min(0.30, 0.04 * helper_count)
        if rc_count >= 4:
            score += 0.30
        if helper_count >= 3:
            score += 0.20

    # session exfil candidates: require concrete payload evidence
    if "session_storage_exfiltration" in pattern or "session_theft" in pattern:
        concrete_api_evidence.extend(e["session_payload_evidence"])
        static_capability_score += min(0.30, 0.08 * len(e["session_payload_evidence"]))
        if len(e["session_payload_evidence"]) < 2:
            score -= 0.35
            negative_penalties.append("missing_storage_payload_evidence")
        if len(e["remote_control_evidence"]) >= 4:
            score -= 0.25
            negative_penalties.append("remote_control_profile_mismatch")
        if broad_only and len(e["session_payload_evidence"]) == 0:
            score -= 0.20
            negative_penalties.append("broad_tags_without_concrete_session_payload")

    if score < 0.0:
        score = 0.0
    if score > 1.0:
        score = 1.0

    return {
        "score": score,
        "static_capability_score": min(1.0, static_capability_score),
        "concrete_api_evidence": sorted(set(concrete_api_evidence)),
        "dynamic_evidence_score": dynamic_evidence_score,
        "negative_penalties": negative_penalties,
        "candidate_only": True,
    }


def select_candidate_matches(
    rerank_result: dict,
    vector_fingerprint: dict | None = None,
    min_final_score: float = DEFAULT_MIN_FINAL_SCORE,
    max_matches: int = 3,
) -> list[dict]:
    if not isinstance(rerank_result, dict):
        return []

    matches = rerank_result.get("reranked_matches", [])
    if not isinstance(matches, list):
        return []

    valid = [m for m in matches if isinstance(m, dict)]
    valid.sort(key=lambda m: _score_breakdown(m, vector_fingerprint=vector_fingerprint)["score"], reverse=True)

    selected: list[dict] = []
    seen_doc_refs: set[str] = set()
    for m in valid:
        breakdown = _score_breakdown(m, vector_fingerprint=vector_fingerprint)
        boosted = float(breakdown.get("score", 0.0))
        if boosted < float(min_final_score):
            continue
        doc_ref = m.get("doc_ref")
        if not isinstance(doc_ref, str) or not doc_ref.strip():
            continue
        if doc_ref in seen_doc_refs:
            continue
        seen_doc_refs.add(doc_ref)
        existing_evidence = m.get("concrete_api_evidence", [])
        if not isinstance(existing_evidence, list):
            existing_evidence = []
        existing_evidence = [str(x) for x in existing_evidence if isinstance(x, str)]
        enriched = dict(m)
        enriched["candidate_score"] = boosted
        enriched["static_capability_score"] = breakdown.get("static_capability_score", 0.0)
        enriched["concrete_api_evidence"] = existing_evidence if existing_evidence else breakdown.get("concrete_api_evidence", [])
        enriched["dynamic_evidence_score"] = breakdown.get("dynamic_evidence_score", 0.0)
        enriched["negative_penalties"] = breakdown.get("negative_penalties", [])
        enriched["candidate_only"] = bool(breakdown.get("candidate_only", True))
        selected.append(enriched)
        if len(selected) >= int(max_matches):
            break

    return selected


def select_best_match(
    rerank_result: dict,
    vector_fingerprint: dict | None = None,
    min_final_score: float = DEFAULT_MIN_FINAL_SCORE,
) -> dict | None:
    candidates = select_candidate_matches(
        rerank_result=rerank_result,
        vector_fingerprint=vector_fingerprint,
        min_final_score=min_final_score,
        max_matches=1,
    )
    return candidates[0] if candidates else None

