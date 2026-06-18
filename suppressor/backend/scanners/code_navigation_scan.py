import re
from collections import Counter
from urllib.parse import urlparse
from typing import Any, Dict, List, Sequence, Tuple

try:
    from backend.scanners.common import add_finding
    from backend.scanners.manifest_behavior_scan import find_background_entries
except ModuleNotFoundError:
    from scanners.common import add_finding
    from scanners.manifest_behavior_scan import find_background_entries


# 외부 페이지 열기/탭 생성/네트워크 요청 계열 패턴만 분리
NAVIGATION_PATTERNS: Sequence[Tuple[str, str, str, str]] = (
    ("chrome.runtime.setUninstallURL", r"chrome\.runtime\.setUninstallURL\s*\(", "high", "Uninstall callback URL detected"),
    ("chrome.tabs.create", r"chrome\.tabs\.create\s*\(", "medium", "Programmatic tab creation detected"),
    ("window.open", r"\bwindow\.open\s*\(", "medium", "Popup or navigation control detected"),
    ("fetch", r"\bfetch\s*\(", "medium", "Network request via fetch"),
    ("XMLHttpRequest", r"\bXMLHttpRequest\b", "medium", "Network request via XMLHttpRequest"),
)
URL_RE = re.compile(r"https?://[^\s'\"<>)]+", re.IGNORECASE)
ACTIVE_URL_RULES: Sequence[Tuple[str, str]] = (
    ("fetch", r"\bfetch\s*\([^)]*https?://"),
    ("xmlhttprequest", r"\bXMLHttpRequest\b"),
    ("websocket", r"\bWebSocket\s*\([^)]*wss?://"),
    ("send_beacon", r"\bnavigator\.sendBeacon\s*\([^)]*https?://"),
    ("window_open", r"\bwindow\.open\s*\([^)]*https?://"),
    ("location_redirect", r"(?:window\.)?location\.(?:href|assign|replace)\s*(?:=|\()"),
    ("tabs_create", r"chrome\.tabs\.create\s*\([^)]*url"),
    ("script_src", r"createElement\s*\(\s*['\"]script['\"]\s*\)[\s\S]{0,300}\.src\s*="),
    ("iframe_src", r"<iframe[^>]+src=['\"]https?://"),
)
PASSIVE_URL_HINTS: Sequence[str] = (
    "developer.chrome.com",
    "clients2.google.com/service/update2/crx",
    "schemas.microsoft.com",
)
RESERVED_TEST_DOMAINS = {
    "example.com",
    "www.example.com",
    "example.org",
    "www.example.org",
    "example.net",
    "www.example.net",
}
DOCUMENTATION_HOSTS = {
    "github.com",
    "www.github.com",
    "w3.org",
    "www.w3.org",
    "tools.ietf.org",
    "developer.apple.com",
    "developers.google.com",
    "bugs.webkit.org",
    "codemirror.net",
    "searchfox.org",
    "goessner.net",
    "mathiasbynens.be",
    "mths.be",
    "reddit.com",
    "www.reddit.com",
    "jsperf.com",
    "www.cse.yorku.ca",
    "w3c.github.io",
    "www.jsdelivr.com",
    "stackoverflow.com",
    "www.stackoverflow.com",
    "json.org",
    "www.json.org",
    "opensource.org",
    "www.opensource.org",
}


def is_invalid_reputation_target(url: str, hostname: str) -> bool:
    lowered = url.lower()
    if not hostname:
        return True
    if "${" in url or "`" in url:
        return True
    if hostname.endswith(".invalid"):
        return True
    return False


# 서드파티 번들/라이브러리 파일은 오탐 완화를 위해 구분
def is_library_file(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if normalized.endswith(".min.js") or normalized.endswith("-min.js"):
        return True
    for marker in ("/lib/", "/libs/", "/vendor/", "/node_modules/", "/dist/"):
        if marker in normalized or normalized.startswith(marker[1:]):
            return True
    return False


def is_low_signal_navigation_file(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if normalized.startswith("rulesets/"):
        return True
    for token in ("parser", "editor", "debug", "fetch", "codemirror", "csstree"):
        if token in normalized:
            return True
    return False


# JS 파일이 어떤 실행 문맥에서 쓰이는지 추정
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


def classify_urls_in_content(relative_path: str, content: str) -> List[Dict[str, Any]]:
    # URL 문자열을 실제 통신/이동 문맥인지 기준으로 분류
    classifications: List[Dict[str, Any]] = []
    seen = set()

    for match in URL_RE.finditer(content):
        url = match.group(0)
        if url in seen:
            continue
        seen.add(url)

        snippet = content[max(0, match.start() - 120): min(len(content), match.end() + 180)]
        lowered_snippet = snippet.lower()
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        context_type = "UNKNOWN"
        source_kind = "raw_reference"
        should_reputation_check = True

        if is_invalid_reputation_target(url, hostname):
            context_type = "PASSIVE_REFERENCE"
            source_kind = "invalid_or_template_url"
            should_reputation_check = False
            classifications.append(
                {
                    "url": url,
                    "file": relative_path,
                    "context_type": context_type,
                    "source_kind": source_kind,
                    "should_reputation_check": should_reputation_check,
                }
            )
            continue

        for kind, pattern in ACTIVE_URL_RULES:
            if re.search(pattern, snippet, re.IGNORECASE):
                context_type = "ACTIVE_NETWORK"
                source_kind = kind
                should_reputation_check = True
                break

        if hostname in DOCUMENTATION_HOSTS:
            context_type = "PASSIVE_REFERENCE"
            source_kind = "documentation_host"
            should_reputation_check = False

        if context_type == "UNKNOWN":
            if hostname in RESERVED_TEST_DOMAINS:
                context_type = "PASSIVE_REFERENCE"
                source_kind = "reserved_test_domain"
                should_reputation_check = False
            elif any(hint in url.lower() for hint in PASSIVE_URL_HINTS):
                context_type = "PASSIVE_REFERENCE"
                source_kind = "known_reference"
                should_reputation_check = False
            elif relative_path.lower().endswith(".json"):
                context_type = "PASSIVE_REFERENCE"
                source_kind = "json_reference"
                should_reputation_check = False
            elif any(token in lowered_snippet for token in ("schema", "docs", "readme", "license", "issue", "comment", "discussion", "manual", "forum", "kb/")):
                context_type = "PASSIVE_REFERENCE"
                source_kind = "documentation_reference"
                should_reputation_check = False
            elif any(token in lowered_snippet for token in ("icon", "font", "image", ".css", ".png", ".jpg", ".svg")):
                context_type = "STATIC_RESOURCE"
                source_kind = "static_resource"
                should_reputation_check = False

        classifications.append(
            {
                "url": url,
                "file": relative_path,
                "context_type": context_type,
                "source_kind": source_kind,
                "should_reputation_check": should_reputation_check,
            }
        )

    return classifications


# 설치/제거/탭 열기/외부 요청 같은 행위성 패턴을 스캔
def run_code_navigation_scan(report: Dict[str, Any], source_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    manifest = report.get("manifest", {}) if isinstance(report.get("manifest"), dict) else {}
    findings: List[Dict[str, Any]] = []
    severity_counts: Counter = Counter()
    pattern_hits: Counter = Counter()
    classified_urls: List[Dict[str, Any]] = []

    for entry in source_entries:
        file_name = str(entry.get("file_name", ""))
        content = entry.get("content")
        relative_path = str(entry.get("relative_path", file_name))
        if not file_name.endswith(".js") or not isinstance(content, str):
            continue

        # 문맥과 라이브러리 여부를 같이 봐서 과도한 오탐을 줄임
        context = get_script_context(relative_path, manifest)
        library_file = is_library_file(relative_path)
        low_signal_file = is_low_signal_navigation_file(relative_path)
        classified_urls.extend(classify_urls_in_content(relative_path, content))

        # 외부 페이지 이동/탭 생성/통신 패턴 탐지
        for rule_id, pattern, severity, title in NAVIGATION_PATTERNS:
            if not re.search(pattern, content, re.IGNORECASE):
                continue
            adjusted_severity = "low" if library_file else severity
            if low_signal_file and adjusted_severity == "medium":
                adjusted_severity = "low"
            if context == "background" and rule_id == "chrome.runtime.setUninstallURL":
                adjusted_severity = "high"
            pattern_hits[rule_id] += 1
            add_finding(
                findings,
                severity_counts,
                adjusted_severity,
                "code_navigation",
                rule_id,
                title,
                {
                    "file": relative_path,
                    "context": context,
                    "library_file": library_file,
                    "low_signal_file": low_signal_file,
                    "pattern": pattern,
                },
                "Check whether the navigation or outbound request is necessary and tied to legitimate UX or service logic.",
            )

    reputation_targets = sorted(
        {item["url"] for item in classified_urls if item["should_reputation_check"]}
    )
    active_urls = [item for item in classified_urls if item["context_type"] == "ACTIVE_NETWORK"]
    passive_urls = [item for item in classified_urls if item["context_type"] == "PASSIVE_REFERENCE"]
    static_resource_urls = [item for item in classified_urls if item["context_type"] == "STATIC_RESOURCE"]
    unknown_urls = [item for item in classified_urls if item["context_type"] == "UNKNOWN"]

    return {
        "scanner": "code_navigation_scan",
        "summary": {
            "pattern_hits": dict(pattern_hits),
            "reputation_targets": reputation_targets,
            "url_contexts": {
                "active_network": active_urls,
                "passive_reference": passive_urls,
                "static_resource": static_resource_urls,
                "unknown": unknown_urls,
            },
        },
        "findings": findings,
        "severity_counts": dict(severity_counts),
    }
