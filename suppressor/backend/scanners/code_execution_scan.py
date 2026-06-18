import re
from collections import Counter
from typing import Any, Dict, List, Sequence, Tuple

try:
    from backend.scanners.common import add_finding
    from backend.scanners.manifest_behavior_scan import find_background_entries
except ModuleNotFoundError:
    from scanners.common import add_finding
    from scanners.manifest_behavior_scan import find_background_entries


# 동적 실행/문자열 복원 계열 패턴만 분리
EXECUTION_PATTERNS: Sequence[Tuple[str, str, str, str]] = (
    ("eval", r"\beval\s*\(", "high", "Dynamic code execution via eval"),
    ("Function", r"\bnew\s+Function\s*\(", "high", "Dynamic code execution via Function constructor"),
    ("atob", r"\batob\s*\(", "medium", "Runtime string decoding via atob"),
    ("fromCharCode", r"\bString\.fromCharCode\s*\(", "medium", "Character-code string reconstruction detected"),
)


# 서드파티 번들/라이브러리 파일은 오탐 완화를 위해 구분
def is_library_file(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if normalized.endswith(".min.js") or normalized.endswith("-min.js"):
        return True
    for marker in ("/lib/", "/libs/", "/vendor/", "/node_modules/", "/dist/"):
        if marker in normalized or normalized.startswith(marker[1:]):
            return True
    return False


# 룰셋/파서/에디터 계열 파일은 정상 확장에서도 동적 문자열 처리 패턴이 잦다.
def is_low_signal_execution_file(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if normalized.startswith("rulesets/"):
        return True
    for token in ("parser", "editor", "codemirror", "csstree", "jsonpath"):
        if token in normalized:
            return True
    return False


# 파일이 background인지 content script인지 문맥을 추정
def get_script_context(path: str, manifest: Dict[str, Any]) -> str:
    normalized = path.replace("\\", "/")
    background_entries = {item.replace("\\", "/") for item in find_background_entries(manifest)}
    if any(normalized.endswith(entry) for entry in background_entries):
        return "background"
    for content_script in manifest.get("content_scripts", []):
        if isinstance(content_script, dict):
            for script in content_script.get("js", []):
                if isinstance(script, str) and normalized.endswith(script.replace("\\", "/")):
                    return "content_script"
    return "unknown"


# 코드 실행 성격이 강한 정적 패턴을 스캔
def run_code_execution_scan(report: Dict[str, Any], source_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    manifest = report.get("manifest", {}) if isinstance(report.get("manifest"), dict) else {}
    findings: List[Dict[str, Any]] = []
    severity_counts: Counter = Counter()
    pattern_hits: Counter = Counter()

    for entry in source_entries:
        file_name = str(entry.get("file_name", ""))
        content = entry.get("content")
        relative_path = str(entry.get("relative_path", file_name))
        if not file_name.endswith(".js") or not isinstance(content, str):
            continue

        # 파일 문맥과 라이브러리 여부에 따라 심각도를 보정
        context = get_script_context(relative_path, manifest)
        library_file = is_library_file(relative_path)
        low_signal_file = is_low_signal_execution_file(relative_path)

        # eval, Function, atob 같은 실행/복원 패턴 탐지
        for rule_id, pattern, severity, title in EXECUTION_PATTERNS:
            if not re.search(pattern, content, re.IGNORECASE):
                continue
            adjusted_severity = "low" if library_file else severity
            if low_signal_file and adjusted_severity == "high":
                adjusted_severity = "medium"
            elif low_signal_file and adjusted_severity == "medium":
                adjusted_severity = "low"
            if context == "background" and rule_id in {"eval", "Function"}:
                adjusted_severity = "high"
            pattern_hits[rule_id] += 1
            add_finding(
                findings,
                severity_counts,
                adjusted_severity,
                "code_execution",
                rule_id,
                title,
                {
                    "file": relative_path,
                    "context": context,
                    "library_file": library_file,
                    "low_signal_file": low_signal_file,
                    "pattern": pattern,
                },
                "Review whether this dynamic execution path is necessary and whether decoded content can be inspected.",
            )

    return {
        "scanner": "code_execution_scan",
        "summary": {
            "pattern_hits": dict(pattern_hits),
        },
        "findings": findings,
        "severity_counts": dict(severity_counts),
    }
