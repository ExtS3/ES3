from vscode_analysis.decision import decide


def test_critical_suggests_reject_and_review():
    d = decide({"critical": 2, "high": 0, "medium": 0, "low": 0})
    assert d["decision"] == "review"
    assert d["suggest_reject"] is True


def test_high_medium_only_is_review_no_reject():
    d = decide({"critical": 0, "high": 1, "medium": 3, "low": 0})
    assert d["decision"] == "review"
    assert d["suggest_reject"] is False


def test_no_findings_is_review_not_approve():
    d = decide({"critical": 0, "high": 0, "medium": 0, "low": 0})
    assert d["decision"] == "review"
    assert d["suggest_reject"] is False
    # 자동 approve 절대 없음
    assert d["decision"] != "approve"


def test_error_status_is_review_failclosed():
    d = decide({"critical": 0, "high": 0, "medium": 0, "low": 0}, status="error")
    assert d["decision"] == "review"
    assert d["suggest_reject"] is False
