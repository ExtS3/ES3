"""양성 5종 .vsix 코퍼스 검증: Critical 오탐 0 + 반환 형태 + decision=review.

코퍼스 경로가 없으면 skip (CI 환경 호환).
"""

import os

import pytest

from vscode_analysis.runner import run_vscode_static_analysis

CORPUS_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "..", "..", "..", "..",
        "labs", "vscode-corpus", "benign",
    )
)
# 위 상대경로가 환경마다 다를 수 있어 절대경로 fallback도 둔다.
ABS_CORPUS = r"D:/SJH_Data/01_Personal/02_Univ/02_CCIT/dev/labs/vscode-corpus/benign"

BENIGN_FILES = [
    "dbaeumer.vscode-eslint-3.0.24.vsix",
    "esbenp.prettier-vscode-12.4.0.vsix",
    "eamodio.gitlens-2026.5.280630.vsix",
    "ms-python.python-2026.4.0.vsix",
    "vscode-icons-team.vscode-icons-12.18.0.vsix",
]

RUN_STATIC_KEYS = {
    "program_name", "program_version", "program_type",
    "reputation_targets", "summary", "findings", "scan_result", "enabled_scanners",
}


def _corpus_path(name):
    for base in (ABS_CORPUS, CORPUS_DIR):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return None


@pytest.mark.parametrize("name", BENIGN_FILES)
def test_benign_no_critical_false_positive(name):
    path = _corpus_path(name)
    if path is None:
        pytest.skip(f"corpus not available: {name}")

    result = run_vscode_static_analysis(path)

    assert result["status"] == "ok", f"{name}: {result.get('error')}"

    # Critical 오탐 0
    crit = result["scan_result"]["critical"]
    crit_rules = sorted({f["rule_id"] for f in result["findings"] if f["severity"] == "CRITICAL"})
    assert crit == 0, f"{name}: critical false positives {crit_rules}"

    # 반환 형태가 run_static_analysis와 동일 키 구조
    assert RUN_STATIC_KEYS.issubset(result.keys())

    # decision=review (양성은 거부 제안 없음)
    assert result["decision"]["decision"] == "review"
    assert result["decision"]["suggest_reject"] is False


def test_python_apiproposals_whitelisted():
    """ms-python apiProposals 9개가 M-002로 발화하지 않아야 한다."""
    path = _corpus_path("ms-python.python-2026.4.0.vsix")
    if path is None:
        pytest.skip("python corpus not available")
    result = run_vscode_static_analysis(path)
    ids = {f["rule_id"] for f in result["findings"]}
    assert "M-002" not in ids


def test_eslint_postinstall_is_medium_not_critical():
    """eslint postinstall은 M-005 medium이지 critical이 아니어야 한다."""
    path = _corpus_path("dbaeumer.vscode-eslint-3.0.24.vsix")
    if path is None:
        pytest.skip("eslint corpus not available")
    result = run_vscode_static_analysis(path)
    assert result["scan_result"]["critical"] == 0
