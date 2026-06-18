from __future__ import annotations

import os
from typing import Any

DEFAULT_RISK_WEIGHTS = {
    "dynamic": 0.65,
    "static": 0.20,
    "obfuscation": 0.15,
}

SEVERITY_SCORE = {
    "LOW": 0.20,
    "MEDIUM": 0.45,
    "HIGH": 0.75,
    "CRITICAL": 0.95,
    "UNKNOWN": 0.50,
}

_LEVEL_ORDER = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "CRITICAL": 3,
    "UNKNOWN": -1,
}


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _normalize_risk_level(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    low = str(value).strip().lower()
    mapping = {
        "critical": "CRITICAL",
        "high": "HIGH",
        "medium": "MEDIUM",
        "low": "LOW",
        "unknown": "UNKNOWN",
        "inconclusive": "UNKNOWN",
        "치명": "CRITICAL",
        "높음": "HIGH",
        "보통": "MEDIUM",
        "낮음": "LOW",
    }
    return mapping.get(low, "UNKNOWN")


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _env_weights() -> dict[str, float]:
    keys = {
        "dynamic": "RISK_WEIGHT_DYNAMIC",
        "static": "RISK_WEIGHT_STATIC",
        "obfuscation": "RISK_WEIGHT_OBFUSCATION",
    }
    parsed: dict[str, float] = {}
    for k, env in keys.items():
        raw = os.getenv(env)
        if raw is None:
            return dict(DEFAULT_RISK_WEIGHTS)
        try:
            parsed[k] = float(raw)
        except (TypeError, ValueError):
            return dict(DEFAULT_RISK_WEIGHTS)

    if any(v < 0 for v in parsed.values()):
        return dict(DEFAULT_RISK_WEIGHTS)

    s = sum(parsed.values())
    if abs(s - 1.0) > 1e-6:
        return dict(DEFAULT_RISK_WEIGHTS)

    return parsed


def _level_from_score(score: float) -> str:
    s = _clamp01(score)
    if s < 0.30:
        return "LOW"
    if s < 0.55:
        return "MEDIUM"
    if s < 0.80:
        return "HIGH"
    return "CRITICAL"


def _max_level(a: str, b: str) -> str:
    if _LEVEL_ORDER.get(a, -1) >= _LEVEL_ORDER.get(b, -1):
        return a
    return b


def _extract_dynamic(dynamic_result: dict) -> dict:
    d = _safe_dict(dynamic_result)
    status = str(d.get("status", "skipped"))

    final_risk = _safe_dict(d.get("final_risk"))
    lvl = _normalize_risk_level(
        final_risk.get("risk_level")
        or d.get("risk_level")
        or d.get("overall_risk")
        or "UNKNOWN"
    )

    score_raw = final_risk.get("risk_score")
    if score_raw is None:
        score_raw = d.get("risk_score")

    if score_raw is None:
        score = SEVERITY_SCORE.get(lvl, 0.5)
    else:
        score = _clamp01(_to_float(score_raw, SEVERITY_SCORE.get(lvl, 0.5)))

    risk_factors = [str(x) for x in _safe_list(final_risk.get("risk_factors"))]
    reason = str(final_risk.get("reason") or d.get("message") or "")

    return {
        "status": status,
        "risk_level": lvl,
        "score": score,
        "reason": reason,
        "risk_factors": risk_factors,
    }


def _extract_static(static_result: dict) -> dict:
    root = _safe_dict(static_result)
    status = str(root.get("status", "skipped"))

    analysis = _safe_dict(root.get("static_analysis"))
    scan = _safe_dict(analysis.get("scan_result"))

    critical = int(scan.get("critical", 0) or 0)
    high = int(scan.get("high", 0) or 0)
    medium = int(scan.get("medium", 0) or 0)
    low = int(scan.get("low", 0) or 0)

    if status in {"error", "skipped"}:
        lvl = "UNKNOWN"
        score = SEVERITY_SCORE["UNKNOWN"]
    else:
        if critical >= 1:
            lvl = "CRITICAL"
        elif high >= 1:
            lvl = "HIGH"
        elif medium >= 1:
            lvl = "MEDIUM"
        elif low >= 1:
            lvl = "LOW"
        else:
            lvl = "LOW"

        score = min(1.0, critical * 0.95 + high * 0.45 + medium * 0.20 + low * 0.05)

    return {
        "status": status,
        "risk_level": lvl,
        "score": _clamp01(score),
        "reason": f"critical={critical} high={high} medium={medium} low={low}",
        "counts": {"critical": critical, "high": high, "medium": medium, "low": low},
    }


def _extract_obf(obfuscation_result: dict) -> dict:
    d = _safe_dict(obfuscation_result)
    status = str(d.get("status", "skipped"))

    declared = (
        d.get("result_risk")
        or d.get("final_severity")
        or d.get("overall_risk")
        or d.get("recommended_risk")
        or d.get("risk_level")
    )

    files = _safe_list(d.get("files"))
    summary = _safe_dict(d.get("summary"))
    packed_or_minified = bool(d.get("packed_or_minified", False))
    if not packed_or_minified:
        packed_or_minified = any(str(_safe_dict(f).get("verdict", "")).lower() == "minified_or_bundled" for f in files)

    suspicious_cnt = 0
    likely_malicious_cnt = 0
    minified_cnt = 0
    for row in files:
        rr = _safe_dict(row)
        verdict = str(rr.get("verdict", "")).lower()
        if verdict == "likely_malicious_obfuscation":
            likely_malicious_cnt += 1
        elif verdict == "suspicious_obfuscation":
            suspicious_cnt += 1
        elif verdict == "minified_or_bundled":
            minified_cnt += 1

    if not declared:
        overall = str(d.get("overall", "")).lower()
        if "likely_malicious" in overall:
            declared = "HIGH"
        elif "suspicious" in overall:
            declared = "MEDIUM"

    if status in {"error", "skipped"}:
        lvl = "UNKNOWN"
    else:
        lvl = _normalize_risk_level(declared) if declared else "UNKNOWN"
        if lvl == "UNKNOWN":
            if likely_malicious_cnt >= 1:
                lvl = "HIGH"
            elif suspicious_cnt >= 2:
                lvl = "MEDIUM"
            elif suspicious_cnt == 1:
                lvl = "MEDIUM"
            elif packed_or_minified or minified_cnt > 0:
                lvl = "LOW"
            else:
                lvl = "LOW"

    score = SEVERITY_SCORE.get(lvl, 0.5)
    if lvl == "MEDIUM":
        score = min(0.65, score + suspicious_cnt * 0.05)
    if lvl == "HIGH":
        score = min(0.9, score + likely_malicious_cnt * 0.05)

    return {
        "status": status,
        "risk_level": lvl,
        "score": _clamp01(score),
        "reason": f"likely_malicious={likely_malicious_cnt} suspicious={suspicious_cnt} minified={minified_cnt}",
        "stats": {
            "likely_malicious": likely_malicious_cnt,
            "suspicious": suspicious_cnt,
            "minified": minified_cnt,
            "packed_or_minified": packed_or_minified,
        },
    }


def _contains_exfiltration_factor(dynamic_factors: list[str]) -> bool:
    target = " ".join([f.lower() for f in dynamic_factors])
    keywords = ["external_post", "credential", "session", "cookie", "storage", "exfil"]
    return any(k in target for k in keywords)


def calculate_weighted_final_risk(
    *,
    static_result: dict,
    obfuscation_result: dict,
    dynamic_result: dict,
    rag_rerank_result: dict | None = None,
) -> dict:
    weights = _env_weights()

    dynamic = _extract_dynamic(dynamic_result)
    static = _extract_static(static_result)
    obf = _extract_obf(obfuscation_result)

    component_scores = {
        "dynamic": {
            "status": dynamic["status"],
            "risk_level": dynamic["risk_level"],
            "score": dynamic["score"],
            "weight": weights["dynamic"],
            "weighted_score": dynamic["score"] * weights["dynamic"],
            "reason": dynamic["reason"],
        },
        "static": {
            "status": static["status"],
            "risk_level": static["risk_level"],
            "score": static["score"],
            "weight": weights["static"],
            "weighted_score": static["score"] * weights["static"],
            "reason": static["reason"],
        },
        "obfuscation": {
            "status": obf["status"],
            "risk_level": obf["risk_level"],
            "score": obf["score"],
            "weight": weights["obfuscation"],
            "weighted_score": obf["score"] * weights["obfuscation"],
            "reason": obf["reason"],
        },
    }

    weighted_score = sum(x["weighted_score"] for x in component_scores.values())
    weighted_score = _clamp01(weighted_score)
    risk_level = _level_from_score(weighted_score)

    # escalation rules
    static_counts = static.get("counts", {})
    if dynamic["risk_level"] in {"HIGH", "CRITICAL"}:
        risk_level = _max_level(risk_level, dynamic["risk_level"])

    if int(static_counts.get("critical", 0) or 0) >= 1:
        risk_level = _max_level(risk_level, "HIGH")

    if int(static_counts.get("high", 0) or 0) >= 2 and obf["risk_level"] in {"MEDIUM", "HIGH", "CRITICAL"}:
        risk_level = _max_level(risk_level, "HIGH")

    if obf["risk_level"] in {"HIGH", "CRITICAL"} and dynamic["risk_level"] in {"MEDIUM", "HIGH", "CRITICAL"}:
        risk_level = _max_level(risk_level, "HIGH")

    statuses = [dynamic["status"], static["status"], obf["status"]]
    error_or_skipped = sum(1 for s in statuses if s in {"error", "skipped"})

    if error_or_skipped >= 2 and risk_level == "LOW":
        risk_level = "UNKNOWN"

    review_reasons: list[str] = []
    blockers: list[str] = []
    risk_factors: list[str] = []

    if dynamic["risk_factors"]:
        risk_factors.extend(dynamic["risk_factors"])

    if dynamic["status"] in {"error", "skipped"} and (
        static["risk_level"] in {"MEDIUM", "HIGH", "CRITICAL"}
        or obf["risk_level"] in {"MEDIUM", "HIGH", "CRITICAL"}
    ):
        review_reasons.append("dynamic analysis unavailable while static/obfuscation indicate medium+ risk")

    if _contains_exfiltration_factor(dynamic.get("risk_factors", [])):
        review_reasons.append("dynamic risk factors include possible exfiltration signals")

    if int(static_counts.get("critical", 0) or 0) >= 1:
        blockers.append("static analysis contains at least one CRITICAL finding")

    if risk_level in {"HIGH", "CRITICAL"}:
        blockers.append(f"final weighted risk level is {risk_level}")

    # Suppressor only reports scan risk. ExtS3 applies operational approval policy.
    recommended = "review"

    if dynamic["status"] in {"error", "skipped"} and (
        static["risk_level"] in {"MEDIUM", "HIGH", "CRITICAL"}
        or obf["risk_level"] in {"MEDIUM", "HIGH", "CRITICAL"}
    ):
        recommended = "review"

    if error_or_skipped >= 2:
        recommended = "review"

    if risk_level == "LOW":
        decision_reason = "No strong dynamic or corroborated static/obfuscation risk indicators were detected; ExtS3 policy determines final approval."
    else:
        decision_reason = "Risk signals or analysis uncertainty require human review before approval."

    return {
        "risk_level": risk_level,
        "risk_score": weighted_score,
        "recommended_decision": recommended,
        "decision_reason": decision_reason,
        "weights": weights,
        "component_scores": component_scores,
        "risk_factors": risk_factors[:30],
        "review_reasons": review_reasons[:20],
        "approval_blockers": blockers[:20],
    }
