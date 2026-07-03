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
    (
        "trusted_types_bypass",
        r"trustedTypes\s*\.\s*createPolicy\s*\([\s\S]{0,300}createScript",
        "high",
        "Trusted Types policy that launders arbitrary strings into executable script (CSP bypass)",
    ),
)


# 원격 데이터 수신 신호. 단독으로는 finding을 만들지 않고(fetch는 정상 확장에도 흔함,
# 단독 보고는 code_navigation_scan 담당) 인라인 주입과의 결합 판정에만 사용한다.
REMOTE_FETCH_REGEX = re.compile(r"\bfetch\s*\(|\bXMLHttpRequest\b", re.IGNORECASE)

# 원격에서 받은 문자열이 페이지에서 코드로 실행될 수 있는 주입 계열 rule_id
INLINE_EXEC_RULES = frozenset({"inject_inline_script", "trusted_types_bypass"})


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
        injection_rules_hit: List[str] = []
        evasion_hit = False
        fetch_hit = bool(REMOTE_FETCH_REGEX.search(content))

        # 주입 패턴과 회피 패턴을 한 번에 훑으며 카테고리별 발생 여부를 추적
        for group, kind in ((INJECTION_PATTERNS, "injection"), (EVASION_PATTERNS, "evasion")):
            for rule_id, pattern, severity, title in group:
                if not re.search(pattern, content, re.IGNORECASE):
                    continue
                adjusted_severity = "low" if library_file else severity
                pattern_hits[rule_id] += 1
                if kind == "injection":
                    injection_severities.append(adjusted_severity)
                    injection_rules_hit.append(rule_id)
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

        # 스모킹 건 2: 원격 수신(fetch/XHR)과 인라인 코드 주입이 같은 파일에 공존.
        # 서버 응답이 페이지에서 실행 코드가 될 수 있는 원격 제어 주입 경로
        # (예: BadBlocker — Adblock for YouTube가 24시간마다 받아오는 config의
        # scripletsRules를 trustedTypes로 세탁해 <script>로 주입).
        if fetch_hit and INLINE_EXEC_RULES.intersection(injection_rules_hit):
            combined_severity = "low" if library_file else "critical"
            pattern_hits["remote_config_injection"] += 1
            add_finding(
                findings,
                severity_counts,
                combined_severity,
                "evasion_injection",
                "remote_config_injection",
                "Remote-controlled code injection: remotely fetched data can be executed as page script",
                {
                    "file": relative_path,
                    "context": context,
                    "library_file": library_file,
                },
                "Treat as high-risk: the file both fetches remote data and injects inline script, so a server-side change alone could execute arbitrary code in pages.",
            )

    return {
        "scanner": "evasion_injection_scan",
        "summary": {
            "pattern_hits": dict(pattern_hits),
        },
        "findings": findings,
        "severity_counts": dict(severity_counts),
    }
