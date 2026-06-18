from pathlib import Path
from typing import Any

from .utils import FingerprintError, load_json

BROAD_PATTERNS = {"<all_urls>", "*://*/*", "http://*/*", "https://*/*"}


def parse_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FingerprintError(f"manifest.json not found in extension: {root}")
    manifest = load_json(manifest_path)
    return manifest


def classify_host_access(manifest: dict[str, Any]) -> str:
    host_perms = manifest.get("host_permissions", []) or []
    cs_matches = []
    for cs in manifest.get("content_scripts", []) or []:
        cs_matches.extend(cs.get("matches", []) or [])
    combined = set(host_perms + cs_matches)
    if not combined:
        return "none"
    if combined.intersection(BROAD_PATTERNS):
        return "broad"
    targeted = [m for m in combined if isinstance(m, str) and m.startswith("https://") and m.count("/") >= 2]
    if targeted and len(combined) == len(targeted):
        return "targeted"
    return "limited"


def build_manifest_profile(manifest: dict[str, Any]) -> dict[str, Any]:
    entrypoints = set()
    bg = manifest.get("background", {}) or {}
    if bg.get("service_worker") or bg.get("scripts"):
        entrypoints.add("background")
    if manifest.get("content_scripts"):
        entrypoints.add("content_script")
    if (manifest.get("action") or {}).get("default_popup") or (manifest.get("browser_action") or {}).get("default_popup") or (manifest.get("page_action") or {}).get("default_popup"):
        entrypoints.add("popup")
    if manifest.get("options_page") or (manifest.get("options_ui") or {}).get("page"):
        entrypoints.add("options")
    if (manifest.get("side_panel") or {}).get("default_path"):
        entrypoints.add("side_panel")
    if manifest.get("devtools_page"):
        entrypoints.add("devtools")
    if manifest.get("declarative_net_request", {}).get("rule_resources"):
        entrypoints.add("ruleset")

    run_ats = []
    for cs in manifest.get("content_scripts", []) or []:
        if cs.get("run_at"):
            run_ats.append(cs.get("run_at"))

    if bg.get("service_worker"):
        bg_type = "service_worker"
    elif bg.get("scripts"):
        bg_type = "script"
    else:
        bg_type = "none"

    return {
        "manifest_version": manifest.get("manifest_version"),
        "host_access": classify_host_access(manifest),
        "background_type": bg_type,
        "entrypoint_roles": sorted(entrypoints),
        "content_script_run_at": sorted(set(run_ats)),
    }


def build_manifest_raw(manifest: dict[str, Any]) -> dict[str, Any]:
    bg = manifest.get("background", {}) or {}
    bg_files = []
    bg_type = "none"
    if bg.get("service_worker"):
        bg_type = "service_worker"
        bg_files.append(bg.get("service_worker"))
    elif bg.get("scripts"):
        bg_files.extend(bg.get("scripts") or [])
        bg_type = "persistent_background" if bg.get("persistent") else "background_script"

    content_scripts = []
    for cs in manifest.get("content_scripts", []) or []:
        content_scripts.append(
            {
                "matches": cs.get("matches", []) or [],
                "js": cs.get("js", []) or [],
                "run_at": cs.get("run_at", ""),
                "all_frames": bool(cs.get("all_frames", False)),
            }
        )

    ui_entrypoints = []
    for p in [
        (manifest.get("action") or {}).get("default_popup"),
        (manifest.get("browser_action") or {}).get("default_popup"),
        (manifest.get("page_action") or {}).get("default_popup"),
        manifest.get("options_page"),
        ((manifest.get("options_ui") or {}).get("page")),
        ((manifest.get("side_panel") or {}).get("default_path")),
        manifest.get("devtools_page"),
    ]:
        if p:
            ui_entrypoints.append(p)

    return {
        "manifest_version": manifest.get("manifest_version"),
        "permissions": manifest.get("permissions", []) or [],
        "optional_permissions": manifest.get("optional_permissions", []) or [],
        "host_permissions": manifest.get("host_permissions", []) or [],
        "background": {"type": bg_type, "files": bg_files},
        "content_scripts": content_scripts,
        "ui_entrypoints": sorted(set(ui_entrypoints)),
        "chrome_url_overrides": manifest.get("chrome_url_overrides", {}) or {},
        "web_accessible_resources": manifest.get("web_accessible_resources", []) or [],
        "declarative_net_request": {"rule_resources": (manifest.get("declarative_net_request", {}) or {}).get("rule_resources", []) or []},
    }
