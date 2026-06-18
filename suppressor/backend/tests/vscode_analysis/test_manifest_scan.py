"""M-001, M-002, M-004, M-005, M-006 positive/negative."""

from vscode_analysis.manifest_scan import scan_manifest


def _ids(findings):
    return {f["rule_id"] for f in findings}


# --- M-001 ---
def test_m001_positive_wildcard_activation():
    findings, _ = scan_manifest({"activationEvents": ["*"], "extensionKind": ["ui"]})
    assert "M-001" in _ids(findings)


def test_m001_negative_specific_activation():
    findings, _ = scan_manifest({"activationEvents": ["onLanguage:python"], "extensionKind": ["ui"]})
    assert "M-001" not in _ids(findings)


# --- M-002 ---
def test_m002_positive_third_party_proposals():
    findings, counts = scan_manifest({
        "publisher": "some-3rd-party",
        "enabledApiProposals": ["terminalDataWriteEvent"],
        "extensionKind": ["ui"],
    })
    assert "M-002" in _ids(findings)
    assert counts["high"] >= 1


def test_m002_negative_whitelisted_publisher():
    # ms-python apiProposals 9개 -> 화이트리스트로 면제 (코퍼스 가정)
    findings, _ = scan_manifest({
        "publisher": "ms-python",
        "enabledApiProposals": ["a", "b", "c", "d", "e", "f", "g", "h", "i"],
        "extensionKind": ["ui"],
    })
    assert "M-002" not in _ids(findings)


def test_m002_negative_no_proposals():
    findings, _ = scan_manifest({"publisher": "x", "enabledApiProposals": [], "extensionKind": ["ui"]})
    assert "M-002" not in _ids(findings)


# --- M-004 ---
def test_m004_positive_missing_kind():
    findings, _ = scan_manifest({"name": "x"})
    assert "M-004" in _ids(findings)


def test_m004_positive_workspace_kind():
    findings, _ = scan_manifest({"extensionKind": ["workspace"]})
    assert "M-004" in _ids(findings)


def test_m004_negative_ui_only():
    findings, _ = scan_manifest({"extensionKind": ["ui"]})
    assert "M-004" not in _ids(findings)


# --- M-005 ---
def test_m005_positive_postinstall():
    findings, counts = scan_manifest({
        "scripts": {"postinstall": "node ./build/bin/all.js install"},
        "extensionKind": ["ui"],
    })
    assert "M-005" in _ids(findings)
    # eslint postinstall은 medium이지 critical 아님
    assert counts["medium"] >= 1
    assert counts["critical"] == 0


def test_m005_negative_no_install_hook():
    findings, _ = scan_manifest({"scripts": {"build": "tsc"}, "extensionKind": ["ui"]})
    assert "M-005" not in _ids(findings)


# --- M-006 ---
def test_m006_positive_extension_pack():
    findings, _ = scan_manifest({"extensionPack": ["ms-python.pylance"], "extensionKind": ["ui"]})
    assert "M-006" in _ids(findings)


def test_m006_negative_empty_pack():
    findings, _ = scan_manifest({"extensionPack": [], "extensionKind": ["ui"]})
    assert "M-006" not in _ids(findings)
