from collections import Counter
from typing import Any, Dict, List

try:
    from backend.scanners.common import add_finding, ensure_dict
except ModuleNotFoundError:
    from scanners.common import add_finding, ensure_dict


# background/service worker 엔트리만 별도로 추출
def find_background_entries(manifest: Dict[str, Any]) -> List[str]:
    entries: List[str] = []
    background = manifest.get("background")
    if not isinstance(background, dict):
        return entries
    scripts = background.get("scripts")
    if isinstance(scripts, list):
        entries.extend(str(item) for item in scripts if item)
    service_worker = background.get("service_worker")
    if service_worker:
        entries.append(str(service_worker))
    return entries


# manifest의 동작/노출 성격을 보는 스캐너
def run_manifest_behavior_scan(report: Dict[str, Any]) -> Dict[str, Any]:
    manifest = ensure_dict(report.get("manifest", {}), "manifest")
    findings: List[Dict[str, Any]] = []
    severity_counts: Counter = Counter()

    # 브라우저 기본 페이지를 덮어쓰는지 확인
    overrides = manifest.get("chrome_url_overrides")
    if overrides:
        add_finding(
            findings,
            severity_counts,
            "medium",
            "manifest_behavior",
            "chrome_url_overrides",
            "Chrome page override configured",
            {"chrome_url_overrides": overrides},
            "Review whether browser page override behavior is necessary and user-visible.",
        )

    # 외부 홈페이지 링크 보유 여부
    homepage_url = manifest.get("homepage_url")
    if homepage_url:
        add_finding(
            findings,
            severity_counts,
            "low",
            "manifest_behavior",
            "homepage_url",
            "External homepage URL declared",
            {"homepage_url": homepage_url},
            "Confirm the destination is legitimate and vendor-controlled.",
        )

    # 외부 웹페이지/확장이 메시지를 보낼 수 있는지 확인
    externally_connectable = manifest.get("externally_connectable")
    if externally_connectable:
        add_finding(
            findings,
            severity_counts,
            "high",
            "manifest_behavior",
            "externally_connectable",
            "External message surface exposed",
            {"externally_connectable": externally_connectable},
            "Audit which sites or extensions can interact with this package.",
        )

    # 웹 페이지에 노출되는 리소스가 있는지 확인
    web_accessible = manifest.get("web_accessible_resources")
    if web_accessible:
        add_finding(
            findings,
            severity_counts,
            "medium",
            "manifest_behavior",
            "web_accessible_resources",
            "Web-accessible resources exposed",
            {"web_accessible_resources": web_accessible},
            "Verify exposed assets cannot be abused by arbitrary pages.",
        )

    # 백그라운드에서 지속 실행되는 진입점 확인
    background_entries = find_background_entries(manifest)
    if background_entries:
        add_finding(
            findings,
            severity_counts,
            "low",
            "manifest_behavior",
            "background_execution",
            "Background execution entrypoints present",
            {"background_entries": background_entries},
            "Review background/service worker scripts for privileged logic.",
        )

    return {
        "scanner": "manifest_behavior_scan",
        "summary": {
            "background_entries": background_entries,
            "chrome_url_overrides": overrides or {},
            "externally_connectable": externally_connectable,
            "web_accessible_resources": web_accessible,
        },
        "findings": findings,
        "severity_counts": dict(severity_counts),
    }
