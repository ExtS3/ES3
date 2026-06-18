from pathlib import Path

DEFAULT_MIN_FINAL_SCORE = 0.35
DEFAULT_MAX_DYNAMIC_ROUNDS = 8

SCENARIO_DOC_BASE_DIR = str(Path(__file__).resolve().parent.parent)

SCORING_WEIGHTS = {
    "rerank_final_score": 0.30,
    "scenario_evidence_score": 0.55,
    "llm_assessment_score": 0.15,
}
