"""
web_payload에서 LLM 프롬프트에 필요한 핵심 필드를 추출합니다.
4개 위험 그룹 기준으로 정리: 권한/접근, 코드/난독화, 동적 행동, 유사 패턴
"""
from typing import Any, Dict, List


def _get(d: Dict, *keys, default=None) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _trim(lst: Any, max_items: int = 5, max_len: int = 80) -> List[str]:
    if not isinstance(lst, list):
        return []
    result = []
    for item in lst[:max_items]:
        if isinstance(item, dict):
            text = item.get("name") or item.get("title") or item.get("description") or str(item)
        else:
            text = str(item)
        result.append(text[:max_len])
    return result


def extract_for_llm(web_payload: dict) -> dict:
    ext     = web_payload.get("extension", {}) or {}
    overall = web_payload.get("overall", {}) or {}
    static_a  = web_payload.get("static_analysis", {}) or {}
    dynamic_a = web_payload.get("dynamic_analysis", {}) or {}
    obf_a     = web_payload.get("obfuscation_analysis", {}) or {}
    rag_a     = web_payload.get("rag_analysis", {}) or {}
    review    = web_payload.get("review", {}) or {}
    comp      = overall.get("component_scores", {}) or {}

    # static key_findings를 "[심각도] 내용" 형태로 변환
    raw_findings = static_a.get("key_findings") or []
    static_findings = []
    for f in raw_findings[:5]:
        if isinstance(f, dict):
            sev  = f.get("severity", "?")
            desc = f.get("title") or f.get("description") or f.get("message") or str(f)
            static_findings.append(f"[{sev}] {desc[:70]}")
        else:
            static_findings.append(str(f)[:80])

    return {
        # 기본 정보
        "name":    ext.get("name", "unknown"),
        "id":      ext.get("extension_id", "unknown"),
        "browser": ext.get("browser", "unknown"),
        "version": ext.get("version", "unknown"),

        # 종합 위험도
        "risk_level": overall.get("risk_level", "UNKNOWN"),
        "risk_score": float(overall.get("risk_score", 0.0)),

        # 컴포넌트 점수
        "d_score": float(_get(comp, "dynamic",    "score",      default=0.0)),
        "d_level": str(_get(comp, "dynamic",    "risk_level", default="?")),
        "s_score": float(_get(comp, "static",     "score",      default=0.0)),
        "s_level": str(_get(comp, "static",     "risk_level", default="?")),
        "o_score": float(_get(comp, "obfuscation","score",      default=0.0)),
        "o_level": str(_get(comp, "obfuscation","risk_level", default="?")),

        # [그룹1] 권한/접근
        "permissions":    _trim(static_a.get("permissions"), 10),
        "suspicious_apis": _trim(static_a.get("suspicious_apis"), 8),
        "external_domains": _trim(static_a.get("external_domains"), 5),

        # [그룹2] 코드/난독화
        "static_findings": static_findings,
        "obf_indicators":  _trim(obf_a.get("key_indicators"), 5),
        "obf_files":       _trim(obf_a.get("obfuscated_files"), 3),

        # [그룹3] 동적 행동
        "runtime":          dynamic_a.get("runtime_evidence", {}) or {},
        "matched_scenarios": _trim(dynamic_a.get("matched_scenarios"), 5),
        "observations":      _trim(dynamic_a.get("key_observations"), 4),

        # [그룹4] 유사 패턴
        "top_patterns": _trim(rag_a.get("top_patterns"), 3),

        # 판단 근거
        "risk_factors":   _trim(overall.get("risk_factors"), 5),
        "review_reasons": _trim(
            overall.get("review_reasons") or review.get("review_reasons"), 5
        ),
        "blockers": _trim(
            overall.get("approval_blockers") or review.get("approval_blockers"), 3
        ),
    }
