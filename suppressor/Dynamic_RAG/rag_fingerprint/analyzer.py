import asyncio
import os
from pathlib import Path
from typing import Any

from .capability_mapper import load_capability_mapping, map_capabilities
from .code_scanner import aggregate_js_scans, scan_js_file
from .dnr_scanner import scan_dnr_rules
from .fingerprint_builder import build_fingerprint
from .flow_builder import build_predicted_flows
from .html_scanner import scan_html
from .loader import load_extension_source, prepare_output_dir
from .manifest_parser import build_manifest_profile, build_manifest_raw, parse_manifest
from .utils import iter_files, save_json


THIRD_PARTY_HINTS = ("jquery", "bootstrap", "lodash", "react", "vue", "angular")


def _norm_rel(root: Path, p: str | None) -> str | None:
    if p is None:
        return None
    raw = str(p).strip()
    if not raw:
        return None

    cut_idx = len(raw)
    q_idx = raw.find("?")
    h_idx = raw.find("#")
    if q_idx != -1:
        cut_idx = min(cut_idx, q_idx)
    if h_idx != -1:
        cut_idx = min(cut_idx, h_idx)
    raw = raw[:cut_idx]

    raw = raw.replace("\\", "/").lstrip("/")
    if not raw:
        return None

    norm = os.path.normpath(raw).replace("\\", "/")
    if norm in {"", "."}:
        return None
    if norm.startswith("../") or norm == "..":
        return None
    if any(part == ".." for part in norm.split("/")):
        return None
    if len(norm) >= 3 and norm[1] == ":" and norm[2] == "/":
        return None

    root_resolved = root.resolve()
    candidate = (root_resolved / Path(norm)).resolve()
    try:
        return candidate.relative_to(root_resolved).as_posix()
    except ValueError:
        return None


def _add_role(roles: dict[str, str], root: Path, path_value: str | None, role: str) -> None:
    rel = _norm_rel(root, path_value)
    if rel:
        roles[rel] = role


def _build_manifest_js_roles(root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for cs in manifest.get("content_scripts", []) or []:
        for js in cs.get("js", []) or []:
            _add_role(roles, root, js, "content_script")
    bg = manifest.get("background", {}) or {}
    if bg.get("service_worker"):
        _add_role(roles, root, bg.get("service_worker"), "background")
    for js in bg.get("scripts", []) or []:
        _add_role(roles, root, js, "background")
    return roles


def _html_role_for_path(root: Path, manifest: dict[str, Any], rel_html: str) -> str:
    if rel_html == (_norm_rel(root, (manifest.get("action") or {}).get("default_popup")) or ""):
        return "popup"
    if rel_html == (_norm_rel(root, (manifest.get("browser_action") or {}).get("default_popup")) or ""):
        return "popup"
    if rel_html == (_norm_rel(root, (manifest.get("page_action") or {}).get("default_popup")) or ""):
        return "popup"
    if rel_html == (_norm_rel(root, manifest.get("options_page")) or ""):
        return "options"
    if rel_html == (_norm_rel(root, ((manifest.get("options_ui") or {}).get("page"))) or ""):
        return "options"
    if rel_html == (_norm_rel(root, ((manifest.get("side_panel") or {}).get("default_path"))) or ""):
        return "side_panel"
    offscreen = manifest.get("offscreen")
    if rel_html == (_norm_rel(root, offscreen) or ""):
        return "offscreen"
    for key in ("offscreen_documents", "offscreen_document", "offscreen_pages", "offscreen_page"):
        value = manifest.get(key)
        if isinstance(value, str) and rel_html == (_norm_rel(root, value) or ""):
            return "offscreen"
        if isinstance(value, list):
            for item in value:
                if rel_html == (_norm_rel(root, item) or ""):
                    return "offscreen"
    return "extension_page"


def _classify_source(rel_js: str) -> tuple[str, bool]:
    rel = rel_js.replace("\\", "/").lower()
    name = Path(rel).name.lower()
    is_minified = name.endswith(".min.js")
    if "/vendor/" in f"/{rel}/" or rel.startswith("vendor/"):
        return "vendor", is_minified
    if rel.startswith("node_modules/") or "/node_modules/" in rel:
        return "third_party", is_minified
    if rel.startswith("lib/") or "/lib/" in rel:
        return "third_party", is_minified
    if any(h in rel for h in THIRD_PARTY_HINTS):
        return "third_party", is_minified
    if is_minified:
        return "third_party", is_minified
    return "first_party", is_minified


def _is_allowed_for_vector(scan: dict[str, Any], include_declared_third_party: bool) -> bool:
    source_class = scan.get("source_class", "first_party")
    role = scan.get("role", "unknown_script")
    if source_class == "first_party":
        return True
    if source_class in {"third_party", "vendor"} and include_declared_third_party and role in {"content_script", "background"}:
        return True
    return False


def analyze_extension_static(
    target,
    output_dir=None,
    include_declared_third_party=False,
):
    source = load_extension_source(str(target))
    try:
        manifest = parse_manifest(source.root)
        manifest_profile = build_manifest_profile(manifest)
        manifest_js_roles = _build_manifest_js_roles(source.root, manifest)

        js_files = iter_files(source.root, (".js", ".mjs", ".cjs"))
        html_files = iter_files(source.root, (".html", ".htm"))

        html_results = [scan_html(h) for h in html_files]
        html_script_roles: dict[str, str] = {}
        html_inline_roles: dict[str, str] = {}
        for hr in html_results:
            rel_html = str(Path(hr["file"]).resolve().relative_to(source.root.resolve()))
            page_role = _html_role_for_path(source.root, manifest, rel_html)
            for src in hr.get("scripts", []):
                js_rel = str((Path(rel_html).parent / src).as_posix())
                html_script_roles[js_rel] = page_role
            for idx, _ in enumerate(hr.get("inline_scripts", [])):
                html_inline_roles[f"{rel_html}::{idx}"] = page_role

        inline_scans = []
        for hr in html_results:
            rel_html = str(Path(hr["file"]).resolve().relative_to(source.root.resolve()))
            for idx, inline in enumerate(hr.get("inline_scripts", [])):
                tmp = source.root / f".__inline_{idx}.js"
                tmp.write_text(inline, encoding="utf-8")
                role = html_inline_roles.get(f"{rel_html}::{idx}", "extension_page")
                inline_scans.append(scan_js_file(tmp, role=role, source_class="first_party", is_minified=False))
                tmp.unlink(missing_ok=True)

        js_scans = []
        for p in js_files:
            rel = str(p.resolve().relative_to(source.root.resolve()))
            role = manifest_js_roles.get(rel) or html_script_roles.get(rel) or "unknown_script"
            source_class, is_minified = _classify_source(rel)
            js_scans.append(scan_js_file(p, role=role, source_class=source_class, is_minified=is_minified))
        js_scans.extend(inline_scans)
        agg_all = aggregate_js_scans(js_scans)
        vector_scans = [sc for sc in js_scans if _is_allowed_for_vector(sc, include_declared_third_party)]
        agg_vector = aggregate_js_scans(vector_scans)

        dnr = scan_dnr_rules(source.root, manifest)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        # analyzer.py 위치 기준으로 config 폴더 경로 계산 (상위로 두 번 이동 후 config 폴더)
        config_path = os.path.join(current_dir, "..", "config", "capability_mapping.json")

        mapping = load_capability_mapping(config_path)
        capabilities = map_capabilities(manifest, agg_vector.get("signals", []), mapping)
        vector_signals = set(agg_vector.get("signals", []))
        has_explicit_network_api = any(
            s in vector_signals
            for s in [
                "network.fetch",
                "network.xhr",
                "network.sendBeacon",
                "network.WebSocket",
                "network.EventSource",
                "network.jquery.ajax",
                "network.jquery.get",
                "network.jquery.post",
                "network.axios",
            ]
        )
        has_external_origin = bool(agg_vector.get("network", {}).get("external_origin_present", False))
        has_any_url_reference = bool(agg_vector.get("network", {}).get("has_any_url_reference", False))
        has_endpoint_keywords = bool(agg_vector.get("network", {}).get("endpoint_keywords", []))

        extra_caps = []
        if manifest_profile.get("host_access") == "targeted":
            extra_caps.append("targeted_page_access")
        if "document_start" in (manifest_profile.get("content_script_run_at") or []):
            extra_caps.append("early_document_injection")
        if any(s in agg_vector.get("signals", []) for s in ["storage.localStorage", "storage.sessionStorage"]):
            extra_caps.append("page_storage_access")
        if "background" in (manifest_profile.get("entrypoint_roles") or []):
            extra_caps.append("background_execution")
        if any(s in agg_vector.get("signals", []) for s in ["delayed_execution.setInterval", "delayed_execution.setTimeout"]):
            extra_caps.append("periodic_execution")
        capabilities = sorted(set(capabilities + extra_caps))

        if "external_network" in capabilities and not has_explicit_network_api:
            capabilities = [c for c in capabilities if c != "external_network"]
        if has_external_origin and has_endpoint_keywords and not has_explicit_network_api:
            capabilities = sorted(set(capabilities + ["external_endpoint_reference"]))
        if has_explicit_network_api and (has_external_origin or has_any_url_reference):
            capabilities = sorted(set(capabilities + ["external_network"]))

        if {
            "navigation.action.onClicked",
            "navigation.tabs.create",
            "navigation.runtime.getURL_html",
        }.issubset(vector_signals):
            roles = set(manifest_profile.get("entrypoint_roles", []))
            roles.add("extension_page")
            manifest_profile["entrypoint_roles"] = sorted(roles)

        flows = build_predicted_flows(manifest_profile, agg_vector, dnr)
        fingerprint = build_fingerprint(manifest_profile, capabilities, agg_vector, flows, dnr)
        entrypoints = []
        for sc in js_scans:
            entrypoints.append(
                {
                    "role": sc.get("role", "unknown_script"),
                    "path": sc.get("file", ""),
                    "source_class": sc.get("source_class", "first_party"),
                    "is_minified": bool(sc.get("is_minified", False)),
                }
            )
        excluded_files = [sc.get("file", "") for sc in js_scans if sc not in vector_scans]

        extracted = {
            "manifest_raw": build_manifest_raw(manifest),
            "entrypoints": entrypoints,
            "js_scan_aggregate": {"files": agg_all.get("files", []), "code_signals": {k: v for k, v in agg_all.items() if k != "files"}},
            "js_scan_vector_scope": {"files": agg_vector.get("files", []), "code_signals": {k: v for k, v in agg_vector.items() if k != "files"}},
            "vector_filtering": {
                "third_party_excluded_by_default": True,
                "include_declared_third_party": include_declared_third_party,
                "excluded_files": excluded_files,
            },
        }

        out_paths = {"extracted_code_features": None, "vector_fingerprint": None}
        if output_dir is not None:
            out = prepare_output_dir(str(output_dir))
            ex_path = out / "extracted_code_features.json"
            vec_path = out / "vector_fingerprint.json"
            save_json(ex_path, extracted)
            save_json(vec_path, fingerprint)
            out_paths = {
                "extracted_code_features": str(ex_path),
                "vector_fingerprint": str(vec_path),
            }

        return {
            "status": "ok",
            "target": str(target),
            "analysis_type": "static_rag_fingerprint",
            "extracted_code_features": extracted,
            "vector_fingerprint": fingerprint,
            "output_paths": out_paths,
        }
    finally:
        source.cleanup()


async def analyze_extension_with_ai(
    target,
    runner_mode="static",
    output_dir=None,
    include_declared_third_party=False,
    **kwargs,
):
    result = await asyncio.to_thread(
        analyze_extension_static,
        target,
        output_dir,
        include_declared_third_party,
    )
    result["runner_mode"] = runner_mode
    return result
