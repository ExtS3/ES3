"""VSCode 전용 판정 (설계 §6).

- Critical >= 1            -> 거부 제안 + review
- High/Medium만 (findings) -> review
- 무 findings              -> review (Tier1: 자동 approve 없음)
- 분석 실패 (status=error) -> review (fail-closed)

자동 approve는 절대 생성하지 않는다.
"""

from typing import Any, Dict


def decide(severity_counts: Dict[str, int], status: str = "ok") -> Dict[str, Any]:
    """severity_counts(critical/high/medium/low)와 status를 받아 판정 dict 반환."""
    counts = severity_counts or {}
    critical = int(counts.get("critical", 0))

    if status == "error":
        return {
            "decision": "review",
            "suggest_reject": False,
            "reason": "분석 실패 — 수동 검토 필요 (fail-closed)",
        }

    if critical >= 1:
        return {
            "decision": "review",
            "suggest_reject": True,
            "reason": f"Critical 룰 {critical}건 발화 — 거부 권장 + 수동 검토",
        }

    return {
        "decision": "review",
        "suggest_reject": False,
        "reason": "수동 검토 필요 (Tier1 자동 승인 없음)",
    }
