from __future__ import annotations

import re
from typing import Any


DEFAULT_WEIGHTS = {
    "vector_similarity": 0.30,
    "capability_combo_containment": 0.25,
    "flow_match": 0.10,
    "behavior_tag_overlap": 0.25,
    "signal_overlap": 0.10,
}


def _to_set(features: dict[str, Any], key: str) -> set[str]:
    vals = features.get(key, []) if isinstance(features, dict) else []
    if not isinstance(vals, list):
        return set()
    return {str(x).strip() for x in vals if str(x).strip()}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _combo_tokens(combo: str) -> set[str]:
    return {p.strip() for p in re.split(r"[|+]", str(combo)) if p.strip()}


def compare_rerank_features(
    query_features: dict,
    candidate_features: dict,
    vector_similarity: float = 0.0,
    weights: dict | None = None,
) -> dict:
    w = dict(DEFAULT_WEIGHTS)
    if isinstance(weights, dict):
        for k, v in weights.items():
            try:
                w[k] = float(v)
            except (TypeError, ValueError):
                continue

    vector_similarity = float(vector_similarity or 0.0)

    query_cap = _to_set(query_features, "capability_set")
    cand_cap = _to_set(candidate_features, "capability_set")

    query_combos = _to_set(query_features, "capability_combo_set")
    cand_combos = _to_set(candidate_features, "capability_combo_set")

    query_flows = _to_set(query_features, "flow_set")
    cand_flows = _to_set(candidate_features, "flow_set")

    query_tags = _to_set(query_features, "behavior_tag_set")
    cand_tags = _to_set(candidate_features, "behavior_tag_set")

    query_signals = _to_set(query_features, "signal_set")
    cand_signals = _to_set(candidate_features, "signal_set")

    capability_overlap = _jaccard(query_cap, cand_cap)

    matched_combos: list[str] = []
    combo_containment = 0.0
    if cand_combos:
        query_combo_tokens = [_combo_tokens(qc) for qc in query_combos]
        for candidate_combo in sorted(cand_combos):
            c_tokens = _combo_tokens(candidate_combo)
            if c_tokens and any(c_tokens.issubset(q_tokens) for q_tokens in query_combo_tokens):
                matched_combos.append(candidate_combo)
        combo_containment = len(matched_combos) / len(cand_combos)

    matched_flows = sorted(cand_flows & query_flows)
    flow_match = (len(matched_flows) / len(cand_flows)) if cand_flows else 0.0

    matched_tags = sorted(cand_tags & query_tags)
    behavior_tag_overlap = _jaccard(query_tags, cand_tags)

    matched_signals = sorted(cand_signals & query_signals)
    signal_overlap = _jaccard(query_signals, cand_signals)

    final_score = (
        vector_similarity * w["vector_similarity"]
        + combo_containment * w["capability_combo_containment"]
        + flow_match * w["flow_match"]
        + behavior_tag_overlap * w["behavior_tag_overlap"]
        + signal_overlap * w["signal_overlap"]
    )

    return {
        "vector_similarity": vector_similarity,
        "capability_overlap": capability_overlap,
        "capability_combo_containment": combo_containment,
        "flow_match": flow_match,
        "behavior_tag_overlap": behavior_tag_overlap,
        "signal_overlap": signal_overlap,
        "final_score": final_score,
        "matched": {
            "capability_combos": matched_combos,
            "flows": matched_flows,
            "behavior_tags": matched_tags,
            "signals": matched_signals,
        },
    }
