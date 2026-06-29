import re
from collections import Counter
from typing import Any, Dict, List, Sequence, Tuple

try:
    from backend.scanners.common import add_finding
    from backend.scanners.code_execution_scan import is_library_file, get_script_context
except ModuleNotFoundError:
    from scanners.common import add_finding
    from scanners.code_execution_scan import is_library_file, get_script_context


# 페이지에 코드를 주입하는 패턴 (악성 확장의 페이로드 전달 경로)
INJECTION_PATTERNS: Sequence[Tuple[str, str, str, str]] = (
    (
        "inject_remote_script",
        r"createElement\s*\(\s*['\"]script['\"]\s*\)[\s\S]{0,300}\.src\s*=",
        "high",
        "Remote script injected into page via dynamically created <script> element",
    ),
    (
        "inject_inline_script",
        r"createElement\s*\(\s*['\"]script['\"]\s*\)[\s\S]{0,300}\.(?:text|textContent|innerText|innerHTML)\s*=",
        "high",
        "Inline code injected into page via dynamically created <script> element",
    ),
    (
        "create_script_element",
        r"createElement\s*\(\s*['\"]script['\"]\s*\)",
        "medium",
        "Dynamic <script> element creation (possible page injection)",
    ),
)


# 특정 조건에서만 동작해 탐지를 회피하는 패턴 (time-bomb / 호스트 게이팅)
EVASION_PATTERNS: Sequence[Tuple[str, str, str, str]] = (
    (
        "host_conditional_exec",
        r"location\.(?:hostname|host)\s*(?:={2,3}|!={1,2}|\.(?:includes|indexOf|match|startsWith|endsWith|search)\s*\()",
        "medium",
        "Host-conditional execution (runs only on a specific site)",
    ),
    (
        "time_conditional_exec",
        r"\.(?:getHours|getDay|getDate|getMonth|getUTCHours|getUTCDay|getUTCDate)\s*\(\s*\)",
        "low",
        "Time-conditional execution (possible time-bomb trigger)",
    ),
)


# 숨겨진 코드 주입과 조건부 회피를 함께 탐지한다.
# 둘이 같은 파일에서 동시에 나타나면(주입 + 회피) 악성 가능성이 크게 높아진다.
def run_evasion_injection_scan(report: Dict[str, Any], source_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
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

        context = get_script_context(relative_path, manifest)
        library_file = is_library_file(relative_path)

        injection_severities: List[str] = []
        evasion_hit = False

        # 주입 패턴과 회피 패턴을 한 번에 훑으며 카테고리별 발생 여부를 추적
        for group, kind in ((INJECTION_PATTERNS, "injection"), (EVASION_PATTERNS, "evasion")):
            for rule_id, pattern, severity, title in group:
                if not re.search(pattern, content, re.IGNORECASE):
                    continue
                adjusted_severity = "low" if library_file else severity
                pattern_hits[rule_id] += 1
                if kind == "injection":
                    injection_severities.append(adjusted_severity)
                else:
                    evasion_hit = True
                add_finding(
                    findings,
                    severity_counts,
                    adjusted_severity,
                    "evasion_injection",
                    rule_id,
                    title,
                    {
                        "file": relative_path,
                        "context": context,
                        "library_file": library_file,
                        "pattern": pattern,
                    },
                    "Confirm whether this conditional code injection is part of legitimate functionality or hidden malicious behavior.",
                )

        # 스모킹 건: 같은 파일에서 코드 주입과 조건부 회피가 동시에 발생
        if injection_severities and evasion_hit:
            if library_file:
                combined_severity = "low"
            elif "high" in injection_severities:
                combined_severity = "critical"
            else:
                combined_severity = "high"
            pattern_hits["evasive_injection"] += 1
            add_finding(
                findings,
                severity_counts,
                combined_severity,
                "evasion_injection",
                "evasive_injection",
                "Evasive code injection: hidden script injection gated by a host/time condition",
                {
                    "file": relative_path,
                    "context": context,
                    "library_file": library_file,
                },
                "Treat as high-risk: a script is injected only under a specific site/time condition, a common detection-evasion technique.",
            )

    return {
        "scanner": "evasion_injection_scan",
        "summary": {
            "pattern_hits": dict(pattern_hits),
        },
        "findings": findings,
        "severity_counts": dict(severity_counts),
    }
