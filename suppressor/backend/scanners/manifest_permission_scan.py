import json
import os
from collections import Counter
from typing import Any, Dict, List, Set, Tuple

try:
    from backend.scanners.common import add_finding, ensure_dict
except ModuleNotFoundError:
    from scanners.common import add_finding, ensure_dict


# 권한 위험도는 정적 분석의 1차 핵심 지표
HIGH_RISK_PERMISSIONS = {
    "tabs",
    "cookies",
    "webRequest",
    "webRequestBlocking",
    "debugger",
    "management",
    "proxy",
    "nativeMessaging",
    "history",
    "downloads",
    "clipboardRead",
    "clipboardWrite",
    "scripting",
}
CRITICAL_PERMISSIONS = {"debugger", "proxy", "nativeMessaging", "management", "webRequestBlocking"}

EXTANALYSIS_RISK_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "none": "low",
}
RISK_LABEL_KO = {
    "critical": "치명",
    "high": "높음",
    "medium": "보통",
    "low": "낮음",
    "none": "정보",
}


# ExtAnalysis 권한 DB를 참고 데이터로만 로드
def load_extanalysis_permission_db() -> Dict[str, Dict[str, Any]]:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    db_path = os.path.join(project_root, "ExtAnalysis", "db", "permissions.json")
    if not os.path.exists(db_path):
        return {}
    try:
        with open(db_path, encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# 권한 이름과 선언 위치를 함께 수집
def extract_permission_sources(manifest: Dict[str, Any]) -> Dict[str, List[str]]:
    sources: Dict[str, List[str]] = {}
    for key in ("permissions", "optional_permissions"):
        value = manifest.get(key, [])
        if not isinstance(value, list):
            continue
        for item in value:
            if not item:
                continue
            name = str(item)
            sources.setdefault(name, [])
            if key not in sources[name]:
                sources[name].append(key)
    return sources


# 호스트 권한도 선언 위치와 함께 수집
def extract_host_permission_sources(manifest: Dict[str, Any]) -> Dict[str, List[str]]:
    hosts: Dict[str, List[str]] = {}
    for key in ("host_permissions", "optional_host_permissions"):
        value = manifest.get(key, [])
        if not isinstance(value, list):
            continue
        for item in value:
            if not item:
                continue
            host = str(item)
            hosts.setdefault(host, [])
            if key not in hosts[host]:
                hosts[host].append(key)
    for item in manifest.get("permissions", []):
        if isinstance(item, str) and (item.startswith("http://") or item.startswith("https://") or "://*/*" in item):
            hosts.setdefault(item, [])
            if "permissions" not in hosts[item]:
                hosts[item].append("permissions")
    for script in manifest.get("content_scripts", []):
        if isinstance(script, dict):
            for match in script.get("matches", []):
                if match:
                    host = str(match)
                    hosts.setdefault(host, [])
                    if "content_scripts.matches" not in hosts[host]:
                        hosts[host].append("content_scripts.matches")
    return hosts


def _split_declared_items(source_map: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
    required = sorted(name for name, sources in source_map.items() if any(src in {"permissions", "host_permissions"} for src in sources))
    optional = sorted(name for name, sources in source_map.items() if any(src in {"optional_permissions", "optional_host_permissions"} for src in sources))
    return required, optional


# 권한과 호스트 범위만 전담하는 스캐너
def run_manifest_permission_scan(report: Dict[str, Any]) -> Dict[str, Any]:
    manifest = ensure_dict(report.get("manifest", {}), "manifest")
    findings: List[Dict[str, Any]] = []
    severity_counts: Counter = Counter()
    permission_db = load_extanalysis_permission_db()

    # 선언 권한과 실제 접근 가능한 호스트 범위를 먼저 계산
    permission_sources = extract_permission_sources(manifest)
    host_permission_sources = extract_host_permission_sources(manifest)
    permissions = set(permission_sources.keys())
    host_permissions = set(host_permission_sources.keys())
    required_permissions, optional_permissions = _split_declared_items(permission_sources)
    required_hosts, optional_hosts = _split_declared_items(host_permission_sources)
    critical_permissions = sorted(permission for permission in permissions if permission in CRITICAL_PERMISSIONS)
    high_risk_permissions = sorted(permission for permission in permissions if permission in HIGH_RISK_PERMISSIONS)
    db_scored_permissions = []
    wildcard_hosts = sorted(
        host for host in host_permissions if "<all_urls>" in host or "://*/*" in host or host.startswith("*://")
    )

    # ExtAnalysis 권한 DB 기준으로 설명/기본 위험도를 보조 정보로 생성
    for permission in sorted(permissions):
        meta = permission_db.get(permission)
        if not isinstance(meta, dict):
            continue
        db_scored_permissions.append(
            {
                "name": permission,
                "risk": str(meta.get("risk", "none")).lower(),
                "warning": meta.get("warning", "none"),
                "description": meta.get("description", ""),
                "sources": permission_sources.get(permission, []),
            }
        )

    ext_critical_permissions = sorted(
        item["name"] for item in db_scored_permissions
        if item["risk"] == "critical" and item["name"] not in critical_permissions
    )
    ext_high_permissions = sorted(
        item["name"] for item in db_scored_permissions
        if item["risk"] == "high" and item["name"] not in high_risk_permissions and item["name"] not in critical_permissions
    )
    ext_medium_permissions = sorted(
        item["name"] for item in db_scored_permissions
        if item["risk"] == "medium"
        and item["name"] not in high_risk_permissions
        and item["name"] not in critical_permissions
    )
    adblocker_like_profile = (
        "declarativeNetRequest" in permissions
        and wildcard_hosts == ["<all_urls>"]
        and not critical_permissions
        and set(permissions).issubset({"activeTab", "declarativeNetRequest", "scripting", "storage"})
    )

    # 즉시 차단 후보가 되는 권한
    if critical_permissions:
        add_finding(
            findings,
            severity_counts,
            "critical",
            "manifest_permissions",
            "critical_permissions",
            "Critical extension permissions declared",
            {"permissions": critical_permissions},
            "Block or require manual approval before allowing the package.",
        )
    # 민감 데이터 접근/브라우저 제어 가능성이 높은 권한
    if high_risk_permissions:
        high_risk_severity = "medium" if adblocker_like_profile else "high"
        add_finding(
            findings,
            severity_counts,
            high_risk_severity,
            "manifest_permissions",
            "high_risk_permissions",
            "High-risk extension permissions detected",
            {"permissions": high_risk_permissions},
            "Validate why the extension needs these permissions and whether the scope can be reduced.",
        )
    # ExtAnalysis DB가 높게 보는 권한도 보조 시그널로 반영
    if ext_critical_permissions:
        add_finding(
            findings,
            severity_counts,
            "critical",
            "manifest_permissions",
            "extanalysis_critical_permissions",
            "ExtAnalysis 기준 위험 권한 감지",
            {"permissions": ext_critical_permissions},
            "기본 권한 DB 상 치명적으로 분류되는 권한이므로 사용 목적을 강하게 검증해야 합니다.",
        )
    if ext_high_permissions:
        ext_high_severity = "medium" if adblocker_like_profile else "high"
        add_finding(
            findings,
            severity_counts,
            ext_high_severity,
            "manifest_permissions",
            "extanalysis_high_permissions",
            "ExtAnalysis 기준 고위험 권한 감지",
            {"permissions": ext_high_permissions},
            "기본 권한 DB 상 고위험 권한으로 분류되므로 기능적 필요성을 검토해야 합니다.",
        )
    if ext_medium_permissions:
        add_finding(
            findings,
            severity_counts,
            "medium",
            "manifest_permissions",
            "extanalysis_medium_permissions",
            "ExtAnalysis 기준 주의 권한 감지",
            {"permissions": ext_medium_permissions},
            "기본 권한 DB 상 주의가 필요한 권한이므로 선언 범위를 확인해야 합니다.",
        )
    # optional_permissions는 설치 후 권한 확장 가능성이 있어 별도 표시
    if optional_permissions:
        add_finding(
            findings,
            severity_counts,
            "medium",
            "manifest_permissions",
            "optional_permissions_present",
            "선택 권한(optional_permissions) 존재",
            {"permissions": optional_permissions},
            "기본 설치 시점에는 비활성일 수 있지만 이후 사용자 승인으로 권한이 확대될 수 있습니다.",
        )
    # 전체 웹 또는 매우 넓은 범위를 읽을 수 있는 경우
    if wildcard_hosts:
        add_finding(
            findings,
            severity_counts,
            "medium" if adblocker_like_profile else ("critical" if len(wildcard_hosts) >= 2 else "high"),
            "manifest_permissions",
            "wildcard_host_permissions",
            "Broad host access detected",
            {"host_permissions": wildcard_hosts},
            "Restrict host access to known, owned service domains wherever possible.",
        )
    # optional_host_permissions도 별도 경고
    if optional_hosts:
        add_finding(
            findings,
            severity_counts,
            "high" if any("<all_urls>" in host or "://*/*" in host for host in optional_hosts) else "medium",
            "manifest_permissions",
            "optional_host_permissions_present",
            "선택 호스트 권한(optional_host_permissions) 존재",
            {"host_permissions": optional_hosts},
            "설치 후점에 외부 사이트 접근 범위가 확장될 수 있으므로 요청 시점과 기능 흐름을 확인해야 합니다.",
        )

    return {
        "scanner": "manifest_permission_scan",
        "summary": {
            "permissions": sorted(permissions),
            "host_permissions": sorted(host_permissions),
            "required_permissions": required_permissions,
            "optional_permissions": optional_permissions,
            "required_host_permissions": required_hosts,
            "optional_host_permissions": optional_hosts,
            "permission_sources": permission_sources,
            "host_permission_sources": host_permission_sources,
            "wildcard_hosts": wildcard_hosts,
            "adblocker_like_profile": adblocker_like_profile,
            "permission_details": db_scored_permissions,
        },
        "findings": findings,
        "severity_counts": dict(severity_counts),
    }
