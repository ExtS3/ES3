#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_zip_or_dir(target: Path) -> Tuple[Path, Optional[Path]]:
    if target.is_dir():
        return target.resolve(), None
    if zipfile.is_zipfile(target):
        temp_dir = Path(tempfile.mkdtemp(prefix="practical_obf_"))
        with zipfile.ZipFile(target, "r") as zf:
            zf.extractall(temp_dir)
        return temp_dir, temp_dir
    raise ValueError("입력은 ZIP 파일 또는 디렉터리여야 합니다.")


def _cleanup_temp_dir(temp_dir: Optional[Path]) -> None:
    if temp_dir and temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def _find_manifest(root: Path) -> Optional[Path]:
    direct = root / "manifest.json"
    if direct.exists():
        return direct
    for p in root.rglob("manifest.json"):
        return p
    return None


def _load_manifest(path: Optional[Path]) -> Dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def _program_type_from_manifest(manifest: Dict) -> str:
    return "Firefox Extension" if "browser_specific_settings" in manifest else "Chrome Extension"


def _js_like_files(root: Path) -> List[Path]:
    exts = {".js", ".mjs", ".cjs"}
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts]


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _shannon_entropy(data: str) -> float:
    if not data:
        return 0.0
    counter = Counter(data)
    total = len(data)
    return -sum((n / total) * math.log2(n / total) for n in counter.values())


HIGH_RISK_PERMS = {
    "<all_urls>", "scripting", "cookies", "webRequest", "webRequestBlocking",
    "tabs", "activeTab", "clipboardRead", "clipboardWrite", "debugger",
    "declarativeNetRequest", "declarativeNetRequestWithHostAccess",
}

KNOWN_FILE_LIBS = {
    "underscore-min.js": "underscore",
    "underscore.js": "underscore",
    "underscore.string.min.js": "underscore.string",
    "knockout-3.5.1.js": "knockout",
    "knockout.js": "knockout",
    "knockout-secure-binding.min.js": "knockout-secure-binding",
    "jquery.min.js": "jquery",
    "bootstrap.min.js": "bootstrap",
}

KNOWN_LIB_HEADERS = [
    ("underscore", re.compile(r'Underscore(?:\.js)?\s+1\.', re.I)),
    ("knockout", re.compile(r'Knockout JavaScript library v3\.', re.I)),
    ("knockout-secure-binding", re.compile(r'knockout-secure-binding', re.I)),
    ("underscore.string", re.compile(r'underscore\.string', re.I)),
]

MINIFIER_HINTS = [
    ("terser", re.compile(r'/\*[\s!]*Terser\b', re.I)),
    ("uglifyjs", re.compile(r'/\*[\s!]*UglifyJS\b', re.I)),
    ("webpack", re.compile(r'__webpack_require__|webpackChunk\w+\s*=')),
    ("rollup", re.compile(r'rollupPluginBabelHelpers|createCommonjsModule')),
    ("esbuild", re.compile(r'//\s*esbuild|__toCommonJS|__copyProps', re.I)),
    ("swc", re.compile(r'@swc/helpers|_interop_require_default', re.I)),
    ("vite", re.compile(r'vitePreload|__vite__')),
    ("parcel", re.compile(r'parcelRequire\s*=')),
    ("source_map", re.compile(r'//#\s*sourceMappingURL=', re.I)),
    ("license", re.compile(r'License:\s*MIT|may be freely distributed under the MIT license', re.I)),
]

SAFE_RUNTIME_PATTERNS = [
    ("function_return_this", re.compile(r'Function\s*\(\s*["\']return this["\']\s*\)\s*\(\s*\)', re.I)),
    ("indirect_eval_this", re.compile(r'\(\s*0\s*,\s*eval\s*\)\s*\(\s*["\']this["\']\s*\)', re.I)),
]

PAT = {
    "hex_vars": re.compile(r'\b_0x[0-9a-f]{3,8}\b', re.I),
    "hex_indexing": re.compile(r'\b(?:_0x[0-9a-f]{3,8}|[_$a-zA-Z][_$a-zA-Z0-9]{0,20})\s*\[\s*0x[0-9a-f]+\s*\]', re.I),
    "while_true": re.compile(r'while\s*\(\s*(?:!!\[\]|true)\s*\)', re.I),
    "array_ops": re.compile(r'(?:push|shift|splice|unshift)\s*\('),
    "large_string_array": re.compile(r'\[\s*["\'][^"\']{0,120}["\']\s*(?:,\s*["\'][^"\']{0,120}["\']\s*){19,}\]'),
    "eval_atob": re.compile(r'eval\s*\(\s*atob\s*\(', re.I),
    "function_atob": re.compile(r'(?:new\s+)?Function\s*\(\s*atob\s*\(', re.I),
    "new_function": re.compile(r'\bnew\s+Function\s*\(', re.I),
    "eval": re.compile(r'\beval\s*\(', re.I),
    "bracket_eval": re.compile(r'(?:window|self|globalThis|this)\s*\[\s*["\']eval["\']\s*\]', re.I),
    "executeScript_sink": re.compile(r'chrome\.scripting\.executeScript\s*\(|chrome\.tabs\.executeScript\s*\('),
    "importScripts_sink": re.compile(r'\bimportScripts\s*\('),
    "xor_decoder": re.compile(r'charCodeAt\s*\([^)]*\)\s*\^\s*\w+|String\.fromCharCode\s*\([^)]*\^', re.I),
    "jsfuck_like": re.compile(r'^(?:[\[\]\(\)!+\s]){80,}$', re.M),
    "aaencode_like": re.compile(r'[゚ω]{3,}|[ｦ-ﾟ]{5,}'),
    "fetch": re.compile(r'\bfetch\s*\('),
    "xhr": re.compile(r'\bXMLHttpRequest\b'),
    "ws": re.compile(r'\bWebSocket\s*\('),
    "cookie": re.compile(r'\bdocument\.cookie\b'),
    "localStorage": re.compile(r'\blocalStorage\b'),
    "sessionStorage": re.compile(r'\bsessionStorage\b'),
    "clipboard": re.compile(r'\bnavigator\.clipboard\b|clipboard(Read|Write)', re.I),
}


def _collect_manifest_context(manifest: Dict) -> Dict:
    background = manifest.get("background") or {}
    content_scripts = manifest.get("content_scripts") or []
    permissions = list(manifest.get("permissions") or [])
    host_permissions = list(manifest.get("host_permissions") or [])
    optional_permissions = list(manifest.get("optional_permissions") or [])
    optional_host_permissions = list(manifest.get("optional_host_permissions") or [])

    bg_files: List[str] = []
    if isinstance(background, dict):
        sw = background.get("service_worker")
        if sw:
            bg_files.append(str(sw).replace("\\", "/").lstrip("/"))
        for s in background.get("scripts", []) or []:
            bg_files.append(str(s).replace("\\", "/").lstrip("/"))

    cs_files: List[str] = []
    for item in content_scripts:
        if isinstance(item, dict):
            for s in item.get("js", []) or []:
                cs_files.append(str(s).replace("\\", "/").lstrip("/"))

    return {
        "permissions": permissions,
        "host_permissions": host_permissions,
        "optional_permissions": optional_permissions,
        "optional_host_permissions": optional_host_permissions,
        "background_files": bg_files,
        "content_script_files": cs_files,
    }


def _analyze_file(path: Path, root: Path, manifest_ctx: Dict) -> Dict:
    rel_path = _rel(path, root)
    text = _safe_read_text(path)
    filename = path.name.lower()

    lines = text.splitlines() or [text]
    max_line_length = max((len(x) for x in lines), default=0)
    whitespace_ratio = sum(1 for ch in text if ch.isspace()) / max(len(text), 1)

    var_names = re.findall(r'\b(?:var|let|const)\s+([_$a-zA-Z][_$a-zA-Z0-9]*)', text)
    identifier_entropy = _shannon_entropy("".join(var_names)) if var_names else 0.0

    minify_signals: List[str] = []
    suspicious_signals: List[str] = []
    ignored_signals: List[str] = []
    reasons: List[str] = []

    if filename.endswith(".min.js"):
        minify_signals.append("filename:.min.js")
    if filename in KNOWN_FILE_LIBS:
        minify_signals.append(f"known_library_file:{KNOWN_FILE_LIBS[filename]}")
    for name, pat in KNOWN_LIB_HEADERS:
        if pat.search(text[:4000]):
            minify_signals.append(f"known_library_header:{name}")
    for name, pat in MINIFIER_HINTS:
        if pat.search(text[:20000]):
            minify_signals.append(f"minifier:{name}")
    if max_line_length > 4000 and whitespace_ratio < 0.12:
        minify_signals.append("long_single_line_bundle_like")
    if var_names and identifier_entropy < 3.5 and not PAT["hex_vars"].search(text):
        minify_signals.append("low_identifier_entropy")

    # safe runtime patterns
    for name, pat in SAFE_RUNTIME_PATTERNS:
        if pat.search(text):
            ignored_signals.append(name)

    # strong obfuscation core only
    hex_vars = PAT["hex_vars"].findall(text)
    if len(hex_vars) >= 5:
        suspicious_signals.append(f"hex_vars:{len(hex_vars)}")

    hex_index = PAT["hex_indexing"].findall(text)
    if len(hex_index) >= 3:
        suspicious_signals.append(f"hex_indexing:{len(hex_index)}")

    if PAT["eval_atob"].search(text):
        suspicious_signals.append("eval_atob")
    if PAT["function_atob"].search(text):
        suspicious_signals.append("function_atob")
    if PAT["xor_decoder"].search(text):
        suspicious_signals.append("xor_decoder")
    if PAT["jsfuck_like"].search(text):
        suspicious_signals.append("jsfuck_like")
    if PAT["aaencode_like"].search(text):
        suspicious_signals.append("aaencode_like")
    if PAT["executeScript_sink"].search(text):
        suspicious_signals.append("executeScript_sink")
    if PAT["importScripts_sink"].search(text):
        suspicious_signals.append("importScripts_sink")

    # rotation: only if while(...) + array ops + obf context
    has_while = bool(PAT["while_true"].search(text))
    has_ops = bool(PAT["array_ops"].search(text))
    has_large_array = bool(PAT["large_string_array"].search(text))
    has_obf_context = len(hex_vars) >= 3 or len(hex_index) >= 2 or has_large_array
    if has_while and has_ops and has_obf_context:
        suspicious_signals.append("rotation_decoder_pattern")
    elif has_ops:
        ignored_signals.append("array_ops_only")

    # weak runtime only with strong context
    has_strong_core = any(
        s.startswith(("hex_vars:", "hex_indexing:")) or s in {
            "eval_atob", "function_atob", "xor_decoder", "jsfuck_like",
            "aaencode_like", "executeScript_sink", "importScripts_sink",
            "rotation_decoder_pattern"
        }
        for s in suspicious_signals
    )

    if PAT["new_function"].search(text):
        if "function_return_this" in ignored_signals:
            ignored_signals.append("new_function(global_object_pattern)")
        elif has_strong_core:
            suspicious_signals.append("new_function_with_obf_context")
        else:
            ignored_signals.append("new_function(standalone)")

    if PAT["eval"].search(text):
        if "indirect_eval_this" in ignored_signals:
            ignored_signals.append("eval(global_object_pattern)")
        elif has_strong_core:
            suspicious_signals.append("eval_with_obf_context")
        else:
            ignored_signals.append("eval(standalone)")

    if PAT["bracket_eval"].search(text):
        if has_strong_core:
            suspicious_signals.append("bracket_eval_with_obf_context")
        else:
            ignored_signals.append("bracket_eval(standalone)")

    external_hits: List[str] = []
    if PAT["fetch"].search(text):
        external_hits.append("fetch")
    if PAT["xhr"].search(text):
        external_hits.append("XMLHttpRequest")
    if PAT["ws"].search(text):
        external_hits.append("WebSocket")

    sensitive_hits: List[str] = []
    if PAT["cookie"].search(text):
        sensitive_hits.append("document.cookie")
    if PAT["localStorage"].search(text):
        sensitive_hits.append("localStorage")
    if PAT["sessionStorage"].search(text):
        sensitive_hits.append("sessionStorage")
    if PAT["clipboard"].search(text):
        sensitive_hits.append("clipboard")

    perms = set(manifest_ctx["permissions"]) | set(manifest_ctx["host_permissions"]) | set(manifest_ctx["optional_permissions"]) | set(manifest_ctx["optional_host_permissions"])
    matched_perms = sorted(p for p in perms if p in HIGH_RISK_PERMS or p.startswith("http://") or p.startswith("https://"))

    is_background = rel_path in set(manifest_ctx["background_files"]) or filename in {"background.js", "worker.js", "service_worker.js"}
    is_content = rel_path in set(manifest_ctx["content_script_files"]) or filename in {"content.js", "content_script.js", "inject.js"}

    strong_legit = sum(1 for s in minify_signals if s.startswith(("filename:", "known_library_file:", "known_library_header:", "minifier:"))) >= 1
    very_strong_legit = sum(1 for s in minify_signals if s.startswith(("filename:", "known_library_file:", "known_library_header:", "minifier:"))) >= 2

    hard_bad_combo = any(x in suspicious_signals for x in ["eval_atob", "function_atob", "executeScript_sink", "importScripts_sink"]) and (external_hits or matched_perms)
    strong_obf_count = len([
        x for x in suspicious_signals if x.startswith(("hex_vars:", "hex_indexing:")) or x in {
            "eval_atob", "function_atob", "xor_decoder", "jsfuck_like", "aaencode_like",
            "executeScript_sink", "importScripts_sink", "rotation_decoder_pattern",
            "new_function_with_obf_context", "eval_with_obf_context", "bracket_eval_with_obf_context",
        }
    ])

    if hard_bad_combo or "jsfuck_like" in suspicious_signals or "aaencode_like" in suspicious_signals:
        verdict = "likely_malicious_obfuscation"
        reasons.append("강한 난독화/실행 패턴이 외부 통신 또는 특수 패밀리와 결합됨")
    elif very_strong_legit and strong_obf_count == 0:
        verdict = "benign_minify"
        reasons.append("정상 라이브러리/빌드 흔적이 강하고 강한 난독화 핵심이 없음")
    elif very_strong_legit and strong_obf_count == 1:
        verdict = "benign_minify"
        reasons.append("정상 라이브러리/빌드 흔적이 강하고 의심 신호가 단일 핵심에 그침")
    elif strong_obf_count >= 2:
        verdict = "suspicious_obfuscation"
        reasons.append("난독화 핵심 신호가 여러 개 동시에 관찰됨")
    elif strong_legit and strong_obf_count == 0:
        verdict = "benign_minify"
        reasons.append("정상 build/minify 결과물로 보임")
    elif suspicious_signals and not strong_legit:
        verdict = "suspicious_obfuscation"
        reasons.append("정상 흔적보다 강한 이상 신호가 두드러짐")
    else:
        verdict = "readable_script"
        reasons.append("읽기 가능한 일반 스크립트/번들로 보임")

    if is_background:
        reasons.append("background/service worker 맥락")
    if is_content:
        reasons.append("content script 맥락")
    if matched_perms:
        reasons.append(f"고위험 권한/호스트: {', '.join(matched_perms[:6])}")
    if external_hits:
        reasons.append(f"외부 통신 신호: {', '.join(sorted(set(external_hits)))}")
    if sensitive_hits:
        reasons.append(f"민감 접근 신호: {', '.join(sorted(set(sensitive_hits)))}")
    if minify_signals:
        reasons.append(f"정상 흔적: {', '.join(minify_signals[:8])}")
    if suspicious_signals:
        reasons.append(f"의심 흔적: {', '.join(suspicious_signals[:8])}")
    if ignored_signals:
        reasons.append(f"무시된 패턴: {', '.join(ignored_signals[:8])}")

    return {
        "path": rel_path,
        "result": verdict,
        "reasons": reasons,
        "details": {
            "minify_signals": minify_signals,
            "suspicious_signals": suspicious_signals,
            "ignored_signals": ignored_signals,
            "external_signals": sorted(set(external_hits)),
            "sensitive_signals": sorted(set(sensitive_hits)),
            "matched_high_risk_permissions": matched_perms,
            "is_background_file": is_background,
            "is_content_script_file": is_content,
            "line_count": len(lines),
            "max_line_length": max_line_length,
            "identifier_entropy": round(identifier_entropy, 3),
        },
    }


def _severity_from_summary(summary: Dict[str, int]) -> Tuple[str, List[str]]:
    reasons: List[str] = []

    if summary.get("likely_malicious_obfuscation", 0) > 0:
        reasons.append("likely_malicious_obfuscation 파일이 1개 이상 존재")
        return "Critical", reasons

    if summary.get("suspicious_obfuscation", 0) >= 2:
        reasons.append("suspicious_obfuscation 파일이 2개 이상 존재")
        return "High", reasons

    if summary.get("suspicious_obfuscation", 0) == 1:
        reasons.append("suspicious_obfuscation 파일이 1개 존재")
        return "Medium", reasons

    if summary.get("benign_minify", 0) > 0 or summary.get("readable_script", 0) > 0:
        reasons.append("악성/의심 난독화 없이 정상 minify 또는 readable script만 존재")
        return "Low", reasons

    reasons.append("분석 대상 JS가 없거나 유의미한 신호가 없음")
    return "Low", reasons


class PracticalScanner:
    def run(self, target: Path) -> Dict:
        root, temp_dir = _extract_zip_or_dir(target)
        try:
            manifest = _load_manifest(_find_manifest(root))
            manifest_ctx = _collect_manifest_context(manifest)

            files_out: List[Dict] = []
            summary = {
                "benign_minify": 0,
                "readable_script": 0,
                "suspicious_obfuscation": 0,
                "likely_malicious_obfuscation": 0,
            }

            for path in _js_like_files(root):
                item = _analyze_file(path, root, manifest_ctx)
                files_out.append(item)
                summary[item["result"]] = summary.get(item["result"], 0) + 1

            # sort: malicious first, then suspicious, then benign/readable, keep path order inside
            order = {
                "likely_malicious_obfuscation": 0,
                "suspicious_obfuscation": 1,
                "benign_minify": 2,
                "readable_script": 3,
            }
            files_out.sort(key=lambda x: (order.get(x["result"], 9), x["path"]))

            if summary["likely_malicious_obfuscation"] > 0:
                overall = "likely_malicious_obfuscation"
            elif summary["suspicious_obfuscation"] > 0:
                overall = "suspicious_obfuscation_present"
            elif summary["benign_minify"] > 0:
                overall = "mostly_benign_minify"
            else:
                overall = "mostly_readable_script"

            # compact human-friendly log
            scan_log = []
            for item in files_out:
                scan_log.append({
                    "path": item["path"],
                    "result": item["result"],
                    "reasons": item["reasons"],
                })

            severity, severity_reasons = _severity_from_summary(summary)

            return {
                "program_name": manifest.get("name", target.stem if target.is_file() else target.name),
                "program_type": _program_type_from_manifest(manifest),
                "overall_verdict": overall,
                "final_severity": severity,
                "final_severity_reasons": severity_reasons,
                "summary": summary,
                "scan_log": scan_log,
                "files": files_out,
            }
        finally:
            _cleanup_temp_dir(temp_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Practical minify vs obfuscation scanner")
    parser.add_argument("target", help="확장 프로그램 ZIP 또는 디렉터리")
    parser.add_argument("--output", help="JSON 출력 파일 경로 (생략 시 자동 생성)")
    args = parser.parse_args()

    target_path = Path(args.target)
    result = PracticalScanner().run(target_path)
    payload = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
    else:
        base_name = target_path.stem if target_path.is_file() else target_path.name
        output_path = Path(f"{base_name}_scan_result.json")

    output_path.write_text(payload, encoding="utf-8")
    print(str(output_path.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
