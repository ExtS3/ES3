from __future__ import annotations

import asyncio
import json
import threading
import traceback
from datetime import datetime
from pathlib import Path

from .compact import compact_dynamic_rag_result
from .config import (
    DEFAULT_MAX_DYNAMIC_ROUNDS,
    DEFAULT_MIN_FINAL_SCORE,
    SCENARIO_DOC_BASE_DIR,
    SCORING_WEIGHTS,
)
from .dynamic_agent import run_llm_dynamic_analysis_agent
from .evidence_scorer import score_scenario_evidence
from .loader import load_scenario_doc
from .risk_classifier import CRITICAL_TAGS, HIGH_TAGS, MEDIUM_TAGS, classify_final_risk
from .selector import select_candidate_matches


def _clamp_01(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def resolve_dynamic_target_url(vector_fingerprint: dict) -> str | None:
    if not isinstance(vector_fingerprint, dict):
        return "http://127.0.0.1:8080/mock/index.html"
    manifest = vector_fingerprint.get("manifest_profile", {}) if isinstance(vector_fingerprint.get("manifest_profile", {}), dict) else {}
    values: list[str] = []
    cs = manifest.get("content_scripts", [])
    if isinstance(cs, list):
        for item in cs:
            if not isinstance(item, dict):
                continue
            m = item.get("matches", [])
            if isinstance(m, list):
                values.extend([str(x) for x in m])
            elif isinstance(m, str):
                values.append(m)
    for key in ("content_scripts_matches", "matches", "host_permissions", "host_access", "permissions_hint"):
        raw = manifest.get(key)
        if isinstance(raw, list):
            values.extend([str(x) for x in raw])
        elif isinstance(raw, str):
            values.append(raw)
    for token in values:
        low = str(token).lower().strip()
        if low == "<all_urls>" or "<all_urls>" in low:
            return "http://127.0.0.1:8080/mock/index.html"
    # manifest matches 우선: 실제 명시된 origin이면 그 origin의 루트로
    for token in values:
        low = str(token).lower()
        if low.startswith("https://"):
            cleaned = str(token).replace("*", "").rstrip("/")
            return cleaned if cleaned else "http://127.0.0.1:8080/mock/index.html"
    # host_permissions가 와일드카드/불명확하면 중립 mock URL
    return "http://127.0.0.1:8080/mock/index.html"


def _build_scenario_result(match: dict, agent_result: dict, evidence: dict) -> dict:
    rerank_final = _clamp_01(match.get("final_score", 0.0))
    static_evidence_score = _clamp_01(
        float(match.get("static_capability_score", 0.0) or 0.0)
        + float(match.get("concrete_api_evidence_score", 0.0) or 0.0)
    )
    scenario_evidence = _clamp_01(evidence.get("scenario_evidence_score", 0.0))
    dynamic_evidence_score = scenario_evidence
    llm_assessment = _clamp_01(agent_result.get("final_assessment", {}).get("confidence_score", 0.0) if isinstance(agent_result, dict) else 0.0)

    final_dynamic_rag_score = (
        rerank_final * SCORING_WEIGHTS["rerank_final_score"]
        + scenario_evidence * SCORING_WEIGHTS["scenario_evidence_score"]
        + llm_assessment * SCORING_WEIGHTS["llm_assessment_score"]
    )
    if dynamic_evidence_score == 0.0:
        final_dynamic_rag_score = min(final_dynamic_rag_score, 0.30)

    agent_status = str(agent_result.get("status", "")).lower() if isinstance(agent_result, dict) else ""
    agent_error = agent_result.get("error") if isinstance(agent_result, dict) else None
    scenario_error = None
    if agent_status in {"error", "partial_error"}:
        scenario_error = str(agent_error or "dynamic agent returned error status without explicit error message")
    matched_evidence = evidence.get("matched_evidence", []) if isinstance(evidence.get("matched_evidence", []), list) else []
    agent_claimed = bool(agent_result.get("final_assessment", {}).get("scenario_matched", False)) if isinstance(agent_result, dict) else False
    evidence_confirmed = bool(scenario_evidence >= 0.6 and matched_evidence)
    agent_claimed = agent_claimed or evidence_confirmed
    scenario_matched = bool(scenario_evidence > 0.0 and matched_evidence and agent_claimed and not scenario_error)
    match_status = "matched" if scenario_matched else "candidate_only"

    return {
        "pattern_name": match.get("pattern_name", ""),
        "doc_ref": match.get("doc_ref", ""),
        "rerank_final_score": rerank_final,
        "static_evidence_score": static_evidence_score,
        "scenario_evidence_score": scenario_evidence,
        "dynamic_evidence_score": dynamic_evidence_score,
        "llm_assessment_score": llm_assessment,
        "final_dynamic_rag_score": final_dynamic_rag_score,
        "concrete_api_evidence": match.get("concrete_api_evidence", []) if isinstance(match.get("concrete_api_evidence", []), list) else [],
        "negative_penalties": match.get("negative_penalties", []) if isinstance(match.get("negative_penalties", []), list) else [],
        "agent_result": agent_result,
        "evidence_score": evidence,
        "behavior_tags": match.get("payload", {}).get("vector_fingerprint", {}).get("behavior_tags", [])
        if isinstance(match.get("payload", {}), dict)
        else [],
        "safety_violation": bool(evidence.get("safety_violation", False)),
        "scenario_matched": scenario_matched,
        "candidate_only": not scenario_matched,
        "external_request_attempted": bool(evidence.get("external_request_attempted", False)),
        "external_request_blocked": bool(evidence.get("external_request_blocked", False)),
        "real_network_used": bool(evidence.get("real_network_used", False)),
        "intercepted_by_harness": bool(evidence.get("intercepted_by_harness", False)),
        "match_status": match_status,
        "error": scenario_error,
        "error_type": "DynamicAgentError" if scenario_error else None,
        "traceback_tail": [scenario_error] if scenario_error else None,
    }


def _classify_risk_from_fingerprint_only(vector_fingerprint: dict) -> dict:
    if not isinstance(vector_fingerprint, dict):
        return {"risk_level": "LOW", "risk_score": 0.0, "reason": "Empty fingerprint"}

    tags = {str(t) for t in vector_fingerprint.get("behavior_tags", [])}
    signals = vector_fingerprint.get("static_code_signals", {})
    manifest = vector_fingerprint.get("manifest_profile", {})

    concrete_static_evidence = vector_fingerprint.get("concrete_static_evidence", [])
    if not isinstance(concrete_static_evidence, list):
        concrete_static_evidence = []
    has_concrete_static = len(concrete_static_evidence) >= 2

    if tags & CRITICAL_TAGS:
        corroboration_count = _count_corroboration_signals(signals, manifest, tags)
        if corroboration_count >= 5 and has_concrete_static:
            return {
                "risk_level": "HIGH",
                "risk_score": 0.65,
                "reason": "Strong static corroboration present, but dynamic confirmation is absent.",
                "matched_tags": sorted(tags & CRITICAL_TAGS),
                "corroboration_count": corroboration_count,
                "risk_factors": ["static_critical_tags_strong_corroboration"],
            }
        elif corroboration_count >= 3:
            return {
                "risk_level": "MEDIUM",
                "risk_score": 0.45,
                "reason": "Critical behavior tags with moderate corroborating signals (no dynamic confirmation)",
                "matched_tags": sorted(tags & CRITICAL_TAGS),
                "corroboration_count": corroboration_count,
                "risk_factors": ["static_critical_tags_moderate_corroboration"],
            }
        else:
            return {
                "risk_level": "LOW",
                "risk_score": 0.20,
                "reason": "Critical behavior tags but insufficient corroborating signals (no dynamic confirmation)",
                "matched_tags": sorted(tags & CRITICAL_TAGS),
                "corroboration_count": corroboration_count,
                "risk_factors": ["static_critical_tags_weak_corroboration"],
            }
    matched_high = tags & HIGH_TAGS
    if matched_high:
        corroboration_count = _count_corroboration_signals(signals, manifest, tags)
        if corroboration_count >= 2:
            return {
                "risk_level": "MEDIUM",
                "risk_score": 0.40,
                "reason": "High-risk behavior tags with corroborating signals (no dynamic confirmation)",
                "matched_tags": sorted(matched_high),
                "corroboration_count": corroboration_count,
                "risk_factors": ["static_high_tags_with_corroboration"],
            }
        return {
            "risk_level": "LOW",
            "risk_score": 0.20,
            "reason": "High-risk behavior tag present but insufficient corroborating signals",
            "matched_tags": sorted(matched_high),
            "corroboration_count": corroboration_count,
            "risk_factors": ["static_high_tags_insufficient_corroboration"],
        }
    if tags & MEDIUM_TAGS:
        return {
            "risk_level": "LOW",
            "risk_score": 0.15,
            "reason": "Only medium-risk behavior tags in static fingerprint",
            "risk_factors": ["static_medium_tags_only"],
        }
    return {
        "risk_level": "LOW",
        "risk_score": 0.1,
        "reason": "No high-risk tags in static fingerprint",
        "risk_factors": [],
    }


def _count_corroboration_signals(
    signals: dict,
    manifest: dict,
    tags: set[str],
) -> int:
    count = 0

    storage = signals.get("storage", {}) if isinstance(signals, dict) else {}
    network = signals.get("network", {}) if isinstance(signals, dict) else {}
    delayed = signals.get("delayed_execution", {}) if isinstance(signals, dict) else {}

    storage_keywords = {str(k).lower() for k in storage.get("keywords", [])}
    sensitive_storage = {"token", "auth", "session", "password", "credential", "secret", "key"}
    if storage_keywords & sensitive_storage:
        count += 1

    endpoint_keywords = {str(k).lower() for k in network.get("endpoint_keywords", [])}
    sensitive_endpoints = {"token", "auth", "session", "login", "credential", "secret"}
    if endpoint_keywords & sensitive_endpoints:
        count += 1

    delayed_apis = {str(a) for a in delayed.get("apis", [])}
    if "setInterval" in delayed_apis:
        count += 1

    delayed_patterns = {str(p) for p in delayed.get("patterns", [])}
    if "repeated_transmission" in delayed_patterns or "periodic_session_collection" in delayed_patterns:
        count += 1

    run_at = manifest.get("content_script_run_at", [])
    if isinstance(run_at, list) and "document_start" in run_at:
        count += 1

    exfil_tags = {"repeated_exfiltration", "page_storage_exfiltration", "credential_or_token_exfiltration_pattern"}
    if tags & exfil_tags:
        count += 1

    return count


def _has_screenshot_or_automation_static_evidence(vector_fingerprint: dict) -> bool:
    if not isinstance(vector_fingerprint, dict):
        return False
    txt = " ".join(_collect_strings(vector_fingerprint))
    keys = (
        "chrome.tabs.capturevisibletab",
        "page.capturescreenshot",
        "chrome_screenshot",
        "screenshot-helper",
        "debugger",
        "scripting.executescript",
        "click-helper",
        "fill-helper",
        "keyboard-helper",
        "form-submit-helper",
        "web-fetcher-helper",
        "network-helper",
        "offscreen",
    )
    return any(k in txt for k in keys)


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


def run_multi_scenario_dynamic_rag_analysis(
    vector_fingerprint: dict,
    rerank_result: dict,
    execute_action,
    scenario_base_dir: str = SCENARIO_DOC_BASE_DIR,
    min_final_score: float = DEFAULT_MIN_FINAL_SCORE,
    max_matches: int = 3,
    max_rounds: int = DEFAULT_MAX_DYNAMIC_ROUNDS,
    enable_llm: bool | None = None,
    save_outputs: bool = False,
    output_dir: str = "outputs",
    response_mode: str = "compact",
    target_url: str | None = None,
) -> dict:
    try:
        loop = asyncio.get_running_loop()
        diag = {"running_loop": True, "loop_id": id(loop), "loop_type": type(loop).__name__}
    except RuntimeError:
        diag = {"running_loop": False, "loop_id": None, "loop_type": None}
    print(
        f"[thread_diag] location=pipeline_start thread={threading.current_thread().name} "
        f"running_loop={diag['running_loop']} loop_id={diag['loop_id']}",
        flush=True,
    )
    # rerank_result 타입 방어: list 또는 reranked_matches 키 없는 dict 처리
    if isinstance(rerank_result, list):
        rerank_result = {"reranked_matches": rerank_result}
    elif isinstance(rerank_result, dict) and "reranked_matches" not in rerank_result:
        inner = rerank_result.get("matches") or rerank_result.get("results") or []
        rerank_result = {**rerank_result, "reranked_matches": inner if isinstance(inner, list) else []}

    matches = select_candidate_matches(
        rerank_result=rerank_result,
        vector_fingerprint=vector_fingerprint,
        min_final_score=min_final_score,
        max_matches=max_matches,
    )

    if not matches:
        top_score = 0.0
        rows = rerank_result.get("reranked_matches", []) if isinstance(rerank_result, dict) else []
        selected_candidates = rerank_result.get("selected_candidates", []) if isinstance(rerank_result, dict) else []
        top_candidate_patterns = rerank_result.get("top_candidate_patterns", []) if isinstance(rerank_result, dict) else []
        if isinstance(rows, list) and rows:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                try:
                    top_score = max(top_score, float(row.get("final_score", 0.0) or 0.0))
                except (TypeError, ValueError):
                    continue
        candidate_rows: list[dict] = []
        if isinstance(selected_candidates, list) and selected_candidates:
            candidate_rows = [c for c in selected_candidates if isinstance(c, dict)]
        elif isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ev = row.get("concrete_api_evidence", [])
                if isinstance(ev, list) and ev:
                    candidate_rows.append(row)
                if len(candidate_rows) >= int(max_matches):
                    break
        fallback_risk = _classify_risk_from_fingerprint_only(vector_fingerprint)
        candidate_names = []
        if isinstance(top_candidate_patterns, list) and top_candidate_patterns:
            candidate_names = [str(x) for x in top_candidate_patterns if isinstance(x, str) and str(x).strip()]
        if not candidate_names:
            candidate_names = [
                str(c.get("pattern_name"))
                for c in candidate_rows
                if isinstance(c.get("pattern_name"), str) and str(c.get("pattern_name")).strip()
            ]
        result = {
            "status": "candidate_only" if candidate_rows else "no_match",
            "selected_matches": candidate_rows,
            "scenario_results": [],
            "final_risk": fallback_risk,
            "notes": [
                "No scenario matched threshold",
                f"Top rerank score was {top_score:.4f}, threshold was {float(min_final_score):.4f}",
            ],
        }
        # no_match/candidate_only without dynamic run: use static-only fallback policy
        rerank_concrete_static = rerank_result.get("concrete_static_evidence", []) if isinstance(rerank_result, dict) else []
        rerank_injected = rerank_result.get("evidence_injected_candidates", []) if isinstance(rerank_result, dict) else []
        manifest_caps = rerank_result.get("manifest_capabilities", {}) if isinstance(rerank_result, dict) else {}
        if not isinstance(rerank_concrete_static, list):
            rerank_concrete_static = []
        if not isinstance(rerank_injected, list):
            rerank_injected = []
        concrete_candidate_names = []
        vector_only_names = []
        for row in (selected_candidates if isinstance(selected_candidates, list) else []):
            if not isinstance(row, dict):
                continue
            name = str(row.get("pattern_name", "")).strip()
            if not name:
                continue
            ev = row.get("concrete_api_evidence", [])
            has_concrete = isinstance(ev, list) and len(ev) > 0
            if has_concrete:
                concrete_candidate_names.append(name)
            else:
                vector_only_names.append(name)
        static_candidate_present = bool(concrete_candidate_names) or bool(rerank_concrete_static) or bool(rerank_injected)
        screenshot_or_automation_static = _has_screenshot_or_automation_static_evidence(vector_fingerprint)
        if static_candidate_present:
            fallback_level = "MEDIUM"
            fallback_score = 0.45
            fallback_reason = (
                "Strong static screenshot/browser automation evidence was found, but dynamic reproduction evidence was not observed."
                if screenshot_or_automation_static
                else "Strong static evidence was found, but dynamic reproduction evidence was not observed."
            )
            fallback_factors = (
                ["candidate_only_static_match", "zero_dynamic_evidence", "screenshot_capture_api_detected", "browser_automation_api_detected"]
                if screenshot_or_automation_static
                else ["candidate_only_static_match", "zero_dynamic_evidence"]
            )
        else:
            fallback_level = "LOW"
            fallback_score = 0.1
            fallback_reason = "No strong static candidate evidence and no dynamic reproduction evidence were observed."
            fallback_factors = ["no_scenario_match", "zero_dynamic_evidence"]
        result["final_risk"] = {
            "risk_level": fallback_level,
            "risk_score": fallback_score,
            "reason": fallback_reason,
            "matched_scenarios": [],
            "candidate_scenarios": concrete_candidate_names,
            "vector_candidate_scenarios": vector_only_names if vector_only_names else candidate_names,
            "risk_factors": fallback_factors,
            "missing_evidence": [],
            "safety_violation": False,
            "top_scenario": {},
        }
        compact = compact_dynamic_rag_result(result)
        result["compact_result"] = compact
        if save_outputs:
            _save_dynamic_rag_outputs(result, compact, output_dir)
        return _build_response_payload(result, compact, response_mode)

    scenario_results: list[dict] = []
    errors = 0

    for match in matches:
        try:
            doc_ref = match["doc_ref"]
            scenario_doc = load_scenario_doc(doc_ref, scenario_base_dir)

            agent_result = run_llm_dynamic_analysis_agent(
                vector_fingerprint=vector_fingerprint,
                selected_match=match,
                scenario_doc=scenario_doc,
                execute_action=execute_action,
                max_rounds=max_rounds,
                enable_llm=enable_llm,
                preferred_target_url=target_url or resolve_dynamic_target_url(vector_fingerprint),
            )

            evidence = score_scenario_evidence(
                vector_fingerprint=vector_fingerprint,
                selected_match=match,
                llm_agent_result=agent_result,
                observations=None,
            )

            scenario_results.append(_build_scenario_result(match, agent_result, evidence))
        except Exception as exc:
            errors += 1
            tb_lines = traceback.format_exc().splitlines()
            msg = str(exc)
            mapped_error_type = (
                "PlaywrightSyncInAsyncLoopError"
                if ("Playwright Sync API inside the asyncio loop" in msg or "sync_playwright inside running asyncio loop" in msg)
                else exc.__class__.__name__
            )
            scenario_results.append(
                {
                    "pattern_name": match.get("pattern_name", ""),
                    "doc_ref": match.get("doc_ref", ""),
                    "rerank_final_score": _clamp_01(match.get("final_score", 0.0)),
                    "concrete_api_evidence": (
                        match.get("concrete_api_evidence", [])
                        if isinstance(match.get("concrete_api_evidence", []), list)
                        else []
                    ),
                    "scenario_evidence_score": 0.0,
                    "llm_assessment_score": 0.0,
                    "final_dynamic_rag_score": 0.0,
                    "agent_result": {},
                    "evidence_score": {
                        "status": "no_observations",
                        "scenario_evidence_score": 0.0,
                        "matched_evidence": [],
                        "missing_evidence": [],
                        "safety_violation": False,
                        "notes": ["scenario execution failed"],
                    },
                    "behavior_tags": [],
                    "safety_violation": False,
                    "error": str(exc),
                    "error_type": mapped_error_type,
                    "traceback_tail": tb_lines[-20:],
                }
            )

    successful = [s for s in scenario_results if not s.get("error")]
    if not successful:
        status = "error"
    elif errors > 0:
        status = "partial_error"
    else:
        status = "ok"

    final_risk = classify_final_risk(
        successful if successful else scenario_results,
        vector_fingerprint=vector_fingerprint,
        static_context=rerank_result if isinstance(rerank_result, dict) else {},
    )
    # Keep rerank-top and dynamic-top scenario summaries separately to avoid confusion.
    rerank_top = max(matches, key=lambda m: _clamp_01(m.get("final_score", 0.0))) if matches else {}
    dynamic_top = final_risk.get("top_scenario", {}) if isinstance(final_risk.get("top_scenario", {}), dict) else {}
    if isinstance(final_risk, dict):
        final_risk["rerank_top_scenario"] = {
            "pattern_name": rerank_top.get("pattern_name"),
            "doc_ref": rerank_top.get("doc_ref"),
            "rerank_final_score": _clamp_01(rerank_top.get("final_score", 0.0)),
            "concrete_api_evidence": (
                rerank_top.get("concrete_api_evidence", [])
                if isinstance(rerank_top.get("concrete_api_evidence", []), list)
                else []
            ),
        } if isinstance(rerank_top, dict) and rerank_top else {}
        final_risk["dynamic_top_scenario"] = dynamic_top
    if status == "error":
        first_err = next((s for s in scenario_results if isinstance(s, dict) and s.get("error")), None)
        if isinstance(final_risk, dict) and isinstance(first_err, dict):
            final_risk["error_summary"] = {
                "scenario": first_err.get("pattern_name"),
                "error_type": first_err.get("error_type"),
                "error": first_err.get("error"),
                "traceback_tail": first_err.get("traceback_tail", []),
            }

    result = {
        "status": status,
        "selected_matches": matches,
        "scenario_results": scenario_results,
        "final_risk": final_risk,
        "notes": [],
    }
    compact = compact_dynamic_rag_result(result)
    result["compact_result"] = compact
    if save_outputs:
        _save_dynamic_rag_outputs(result, compact, output_dir)
    return _build_response_payload(result, compact, response_mode)


def run_dynamic_rag_analysis(
    vector_fingerprint: dict,
    rerank_result: dict,
    execute_action,
    scenario_base_dir: str = SCENARIO_DOC_BASE_DIR,
    min_final_score: float = DEFAULT_MIN_FINAL_SCORE,
    max_rounds: int = DEFAULT_MAX_DYNAMIC_ROUNDS,
    enable_llm: bool | None = None,
    save_outputs: bool = False,
    output_dir: str = "outputs",
    response_mode: str = "compact",
    target_url: str | None = None,
) -> dict:
    # rerank_result 타입 방어: list 또는 reranked_matches 키 없는 dict 처리
    if isinstance(rerank_result, list):
        rerank_result = {"reranked_matches": rerank_result}
    elif isinstance(rerank_result, dict) and "reranked_matches" not in rerank_result:
        inner = rerank_result.get("matches") or rerank_result.get("results") or []
        rerank_result = {**rerank_result, "reranked_matches": inner if isinstance(inner, list) else []}

    result = run_multi_scenario_dynamic_rag_analysis(
        vector_fingerprint=vector_fingerprint,
        rerank_result=rerank_result,
        execute_action=execute_action,
        scenario_base_dir=scenario_base_dir,
        min_final_score=min_final_score,
        max_matches=1,
        max_rounds=max_rounds,
        enable_llm=enable_llm,
        save_outputs=save_outputs,
        output_dir=output_dir,
        response_mode="full",
        target_url=target_url,
    )

    if result.get("status") in {"no_match", "candidate_only", "no_match_with_candidates"}:
        base = {
            "status": result.get("status"),
            "selected_match": None,
            "doc_ref": None,
            "scenario_doc_excerpt": "",
            "agent_result": None,
            "evidence_score": {"status": "no_observations", "scenario_evidence_score": 0.0},
            "final_dynamic_rag_score": None,
            "compact_result": result.get("compact_result", {}),
            "notes": result.get("notes", []),
        }
        return _build_response_payload(base, base.get("compact_result", {}), response_mode)

    first = result.get("scenario_results", [None])[0]
    if not isinstance(first, dict):
        return {
            "status": "error",
            "selected_match": None,
            "doc_ref": None,
            "scenario_doc_excerpt": "",
            "agent_result": None,
            "evidence_score": {"status": "no_observations", "scenario_evidence_score": 0.0},
            "final_dynamic_rag_score": None,
            "notes": ["No scenario result available"],
        }

    selected_match = result.get("selected_matches", [None])[0] if result.get("selected_matches") else None
    doc_ref = first.get("doc_ref")

    base = {
        "status": first.get("agent_result", {}).get("status", result.get("status", "ok")),
        "selected_match": selected_match,
        "doc_ref": doc_ref,
        "scenario_doc_excerpt": "",
        "agent_result": first.get("agent_result", {}),
        "evidence_score": first.get("evidence_score", {}),
        "final_dynamic_rag_score": first.get("final_dynamic_rag_score"),
        "compact_result": result.get("compact_result", {}),
        "notes": result.get("notes", []),
    }
    return _build_response_payload(base, base.get("compact_result", {}), response_mode)


def generate_scenario_plan_from_rerank(*args, **kwargs):
    return run_dynamic_rag_analysis(*args, **kwargs)


def _save_dynamic_rag_outputs(full_result: dict, compact_result: dict, output_dir: str) -> None:
    try:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        full_path = out_dir / f"dynamic_rag_full_{ts}.json"
        compact_path = out_dir / f"dynamic_rag_compact_{ts}.json"
        with full_path.open("w", encoding="utf-8") as f:
            json.dump(full_result, f, ensure_ascii=False, indent=2)
        with compact_path.open("w", encoding="utf-8") as f:
            json.dump(compact_result, f, ensure_ascii=False, indent=2)
    except Exception:
        return


def _build_response_payload(full_result: dict, compact_result: dict, response_mode: str) -> dict:
    mode = str(response_mode or "compact").lower()
    if mode in {"compact", "summary"}:
        return compact_result if isinstance(compact_result, dict) else {"status": full_result.get("status"), "notes": full_result.get("notes", [])}
    if mode in {"both"}:
        out = dict(full_result)
        out["compact_result"] = compact_result
        return out
    return full_result
