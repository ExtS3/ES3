from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .observation_schema import normalize_observations

_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "mock.local", "::1"}
_EMULATED_PAGE_HOSTS = {"web.telegram.org", "accounts.google.com", "mail.google.com", "drive.google.com"}
_EMULATED_EXTERNAL_HOSTS = _EMULATED_PAGE_HOSTS | {"tg.cloudapi.stream"}
_ALLOWED_SCHEMES = {"chrome-extension", "data", "blob", "about", "devtools"}
_DUMMY_MARKERS = {
    "DUMMY_SESSION_VALUE",
    "DUMMY_AUTH_VALUE",
    "DUMMY_USER_ID",
    "dummy_session",
    "dummy_auth",
    "dummy_user_id",
}
_ENDPOINT_KEYWORDS = ["save_session", "session", "api", "collect", "sync", "token", "auth"]
DEFAULT_SERVICE_WORKER_TIMEOUT_MS = 10000


def parse_bool_env(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _loop_state() -> dict:
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        return {"running_loop": True, "loop_id": id(loop), "loop_type": type(loop).__name__}
    except RuntimeError:
        return {"running_loop": False, "loop_id": None, "loop_type": None}


def is_safe_target_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower()
    return host in _ALLOWED_HOSTS or host.endswith(".localhost")


def is_allowed_request(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    scheme = (p.scheme or "").lower()
    host = (p.hostname or "").lower()
    if scheme in _ALLOWED_SCHEMES:
        return True
    if host in _ALLOWED_HOSTS or host.endswith(".localhost"):
        return True
    return False


def is_emulated_target_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    return (p.hostname or "").lower() in _EMULATED_EXTERNAL_HOSTS


def extract_target_urls_from_fingerprint(vector_fingerprint: dict) -> list[str]:
    if not isinstance(vector_fingerprint, dict):
        return []
    manifest = vector_fingerprint.get("manifest_profile", {}) if isinstance(vector_fingerprint.get("manifest_profile", {}), dict) else {}
    raw = manifest.get("host_permissions", [])
    values = raw if isinstance(raw, list) else [raw] if isinstance(raw, str) else []
    out: list[str] = []
    for token in values:
        t = str(token).strip()
        if "web.telegram.org" in t:
            out.append("https://web.telegram.org/k/")
        elif t.startswith("https://"):
            out.append(t.replace("*", "").rstrip("/"))
    return sorted(set(out))


def extract_endpoint_keywords(url: str) -> list[str]:
    try:
        path = (urlparse(url).path or "").lower()
    except Exception:
        path = ""
    found = [kw for kw in _ENDPOINT_KEYWORDS if kw in path]
    return sorted(set(found))


def body_contains_dummy_secret(body: str | bytes | None) -> bool:
    if body is None:
        return False
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="ignore")
    else:
        text = str(body)
    low = text.lower()
    return any(m.lower() in low for m in _DUMMY_MARKERS)


def infer_timer_evidence(network_requests: list[dict]) -> list[dict]:
    posts = [
        r
        for r in network_requests
        if isinstance(r, dict)
        and str(r.get("url_category", "")).lower() == "localhost"
        and str(r.get("method", "")).upper() == "POST"
    ]
    if len(posts) >= 2:
        return [{"api": "setInterval", "interval_category": "short_periodic", "inferred_from_repeated_post": True}]
    return []


def build_network_evidence_from_request(url: str, method: str, post_data: str | bytes | None, intercepted_by_harness: bool) -> dict:
    try:
        scheme = (urlparse(url).scheme or "").lower()
    except Exception:
        scheme = ""
    if scheme == "chrome-extension":
        category = "extension"
    elif is_safe_target_url(url):
        category = "localhost"
    else:
        category = "external"
    return {
        "url_category": category,
        "method": str(method or "").upper(),
        "endpoint_keywords": extract_endpoint_keywords(url),
        "body_contains_dummy_secret": body_contains_dummy_secret(post_data),
        "timestamp": str(time.time()),
        "intercepted_by_harness": bool(intercepted_by_harness),
    }


def build_mock_page_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mock Page</title>
</head>
<body>
  <div id="app-root" data-mock="true">
    <form id="login-form" method="post" action="#">
      <input type="text" id="username" name="username" value="DUMMY_SESSION_VALUE" autocomplete="username">
      <input type="password" id="password" name="password" value="DUMMY_AUTH_VALUE" autocomplete="current-password">
      <textarea id="notes" name="notes">DUMMY_SESSION_VALUE</textarea>
      <button type="submit" id="submit-btn">Submit</button>
      <button type="button" id="action-btn">Action</button>
    </form>
    <div id="__ext_probe_marker"></div>
  </div>
  <script>
    try { localStorage.setItem("session", "DUMMY_SESSION_VALUE"); } catch(_) {}
    try { localStorage.setItem("auth_token", "DUMMY_AUTH_VALUE"); } catch(_) {}
    try { localStorage.setItem("user_id", "DUMMY_USER_ID"); } catch(_) {}
    try { localStorage.setItem("dummy_session", "DUMMY_SESSION_VALUE"); } catch(_) {}
    try { localStorage.setItem("dummy_auth", "DUMMY_AUTH_VALUE"); } catch(_) {}
    window.__mockPageReady = true;
  </script>
</body>
</html>
"""


def _request_fingerprint(url: str, method: str, post_data: str | bytes | None) -> str:
    if isinstance(post_data, bytes):
        body = post_data
    else:
        body = str(post_data or "").encode("utf-8", errors="ignore")
    h = hashlib.sha256()
    h.update(str(method or "").upper().encode("utf-8"))
    h.update(b"|")
    h.update(str(url or "").encode("utf-8"))
    h.update(b"|")
    h.update(body)
    return h.hexdigest()


def _safe_extract_zip_to_temp(zip_path: str) -> tuple[str, str]:
    tmpdir = tempfile.mkdtemp(prefix="ext_unzip_")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            target = Path(tmpdir, member).resolve()
            if not str(target).startswith(str(Path(tmpdir).resolve())):
                raise RuntimeError("Unsafe zip path traversal detected")
        zf.extractall(tmpdir)
    return tmpdir, find_extension_root(tmpdir)


def find_extension_root(path: str) -> str:
    p = Path(path)
    if p.is_dir() and (p / "manifest.json").is_file():
        return str(p)
    for m in p.rglob("manifest.json"):
        return str(m.parent)
    raise FileNotFoundError("manifest.json not found in extension target")


class _MockPageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = build_mock_page_html().encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.do_GET()

    def log_message(self, format, *args):
        return


class PlaywrightDynamicHarness:
    def __init__(
        self,
        extension_target: str,
        mock_page_url: str = "http://127.0.0.1:8080/mock/index.html",
        receiver_origin: str = "http://127.0.0.1:9999",
        user_data_dir: str | None = None,
        headless: bool = False,
        intercept_mock_receiver: bool = True,
        serve_mock_page: bool = True,
        preferred_target_url: str | None = None,
    ):
        self.extension_target = extension_target
        self.mock_page_url = mock_page_url
        self.receiver_origin = receiver_origin
        self.user_data_dir = user_data_dir
        env_headless = os.getenv("DYNAMIC_HARNESS_HEADLESS")
        self.dynamic_harness_headless_env = str(env_headless or "")
        if env_headless is None:
            self.headless = bool(headless)
            headless_source = "constructor"
        else:
            self.headless = parse_bool_env(env_headless, default=bool(headless))
            headless_source = "env"
        self.headless_source = headless_source
        self.intercept_mock_receiver = intercept_mock_receiver
        self.serve_mock_page = serve_mock_page
        self.preferred_target_url = preferred_target_url

        self._tmp_dirs: list[str] = []
        self._extension_root: str | None = None
        self._pw = None
        self._context = None
        self._page = None

        self._network_requests: list[dict] = []
        self._runtime_messages: list[dict] = []
        self._storage_events: list[dict] = []
        self._dom_events: list[dict] = []
        self._timers: list[dict] = []
        self._execution = {
            "document_start_observed": False,
            "mock_target_used": True,
            "real_service_used": False,
            "real_secret_observed": False,
            "non_localhost_sensitive_transmission": False,
            "actual_page_url": "",
            "expected_target_url": "",
            "target_url_emulation_used": False,
            "target_url_emulation_failed": False,
            "target_url_emulation_error": "",
            "target_url_emulation_enabled": False,
            "original_mock_server_url": "",
            "emulated_target_url": "",
            "selected_content_script_match": "",
            "target_host_mapped_to_local": False,
            "manifest_content_script_matches": [],
            "manifest_mismatch_reason": "",
            "manifest_match_actual_page_url": False,
            "route_registered_web_telegram": False,
            "route_matched_web_telegram_count": 0,
            "route_registered_save_session_endpoint": False,
            "route_matched_save_session_endpoint": 0,
            "content_script_executed": False,
            "content_script_execution_source": "",
            "content_script_run_at_observed": False,
            "target_local_storage_seeded_before_goto": False,
            "seed_extension_uuid_attempted": False,
            "seed_extension_uuid_success": False,
            "seed_extension_uuid_error": "",
            "service_worker_ready_before_uuid_seed": False,
            "extension_loaded": False,
            "extension_id": "",
            "extension_background_type": "",
            "service_worker_count": 0,
            "service_worker_url": "",
            "service_worker_ready": False,
            "extension_manifest_matches": [],
            "extension_manifest_content_scripts": 0,
            "extension_content_script_files": [],
            "content_script_probe_method": "",
            "content_script_files_expected": [],
            "content_script_files_observed": [],
            "manifest_match_target_url": False,
            "manifest_match_patterns": [],
            "manifest_match_error": "",
            "extension_target_original": str(extension_target),
            "extension_unpacked_dir": "",
            "extension_load_path": "",
            "extension_manifest_path": "",
            "extension_manifest_exists": False,
            "extension_context_launched": False,
            "extension_load_error": "",
            "extension_load_warning": "",
            "browser_launch_args_sanitized": [],
            "launch_args_removed": [],
            "used_launch_persistent_context": False,
            "headless": bool(self.headless),
            "headless_source": headless_source,
            "dynamic_harness_headless_env": str(env_headless or ""),
            "display_env": "",
            "xvfb_available": False,
            "headed_supported": False,
            "service_worker_wait_timeout_ms": int(os.getenv("SERVICE_WORKER_TIMEOUT_MS", str(DEFAULT_SERVICE_WORKER_TIMEOUT_MS))),
            "service_worker_urls": [],
            "cleanup_started": False,
            "cleanup_completed": False,
            "cleanup_error": "",
            "cleanup_closed_context": False,
            "cleanup_stopped_playwright": False,
            "cleanup_removed_user_data_dir": False,
            "cleanup_removed_unpacked_dir": False,
            "cleanup_removed_user_data_dir_not_applicable": False,
            "cleanup_removed_unpacked_dir_not_applicable": False,
            "real_network_used": False,
            "intercepted_by_harness": False,
            "external_request_attempted": False,
            "external_request_blocked": False,
            "external_request_count": 0,
            "blocked_external_request_count": 0,
            "blocked_external_requests": [],
            "external_request_failed": False,
            "external_request_block_source": "",
            "external_request_outcome": "",
            "unsafe_request_url": "",
            "unsafe_request_host": "",
            "content_script_not_executed_reason": "",
            "content_script_probe_warning": "",
            "content_script_probe_error": "",
            "content_script_dom_marker_found": False,
            "content_script_probe_timeout_ms": 0,
            "content_script_console_logs": [],
            "content_script_page_errors": [],
            "manifest_content_script_js": [],
            "manifest_content_script_run_at": "",
            "manifest_content_script_exclude_matches": [],
            "manifest_content_script_include_globs": [],
            "manifest_content_script_exclude_globs": [],
            "manifest_content_script_all_frames": False,
            "manifest_permissions": [],
            "manifest_host_permissions": [],
            "selected_content_script_files": [],
            "manifest_injection_eligible": False,
            "manifest_injection_block_reason": "",
            "manifest_match_expected_url": False,
            "content_script_file_exists": False,
            "content_script_file_checks": [],
            "content_script_request_seen": False,
            "content_script_request_url": "",
            "content_script_request_resource_type": "",
            "extension_script_requests": [],
            "isolated_world_context_seen": False,
            "isolated_world_contexts": [],
            "content_script_isolated_world_detected": False,
            "manifest_patched_for_dynamic_analysis": False,
            "manifest_original_content_script_matches": [],
            "manifest_patched_content_script_matches": [],
            "page_load_error": "",
            "page_load_started": False,
            "page_load_completed": False,
            "open_mock_page_attempted": False,
            "open_mock_page_succeeded": False,
            "content_script_probe_attempted": False,
            "page_response_status": None,
            "page_load_warning": "",
            "goto_called": False,
            "goto_completed": False,
            "wait_for_load_state_called": False,
            "wait_for_load_state_completed": False,
            "wait_for_load_state_error": "",
            "mock_server_check_attempted": False,
            "mock_server_autostart_enabled": parse_bool_env(os.getenv("DYNAMIC_MOCK_AUTOSTART"), default=True),
            "mock_server_autostarted": False,
            "mock_server_host": "",
            "mock_server_port": 0,
            "mock_server_url": "",
            "mock_server_reachable": False,
            "mock_server_status_code": None,
            "mock_server_error": "",
            "mock_server_stopped": False,
            "mock_server_stop_error": "",
            "dynamic_analysis_timeout": False,
            "thread_diag_ensure_context": {},
        }
        self._seen_requests: set[str] = set()
        self._request_index_by_fingerprint: dict[str, int] = {}
        self._post_count_by_endpoint: dict[str, int] = {}
        self._notes: list[str] = []
        self._routes_registered = False
        self._init_script_installed = False
        self._manifest: dict = {}
        self._mock_server = None
        self._mock_server_thread: threading.Thread | None = None
        self._emulated_target_host: str = ""
        self._console_logs: list[dict] = []
        self._page_errors: list[str] = []

    def _resolve_extension_root(self) -> str:
        t = self.extension_target
        self._execution["extension_target_original"] = str(t)
        if os.path.isfile(t) and t.lower().endswith(".zip"):
            tmp, root = _safe_extract_zip_to_temp(t)
            self._tmp_dirs.append(tmp)
            self._execution["extension_unpacked_dir"] = str(tmp)
            return root
        if os.path.isdir(t):
            return find_extension_root(t)
        raise FileNotFoundError(f"extension_target not found: {t}")

    def _load_manifest_metadata(self) -> None:
        self._manifest = {}
        if not self._extension_root:
            return
        manifest_path = Path(self._extension_root) / "manifest.json"
        self._execution["extension_load_path"] = str(self._extension_root or "")
        self._execution["extension_manifest_path"] = str(manifest_path)
        self._execution["extension_manifest_exists"] = bool(manifest_path.is_file())
        if not manifest_path.is_file():
            self._execution["extension_load_error"] = "manifest_not_found"
            return
        try:
            self._manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            self._manifest = {}
            self._execution["extension_load_error"] = "manifest_parse_error"
            return
        background = self._manifest.get("background", {}) if isinstance(self._manifest.get("background", {}), dict) else {}
        content_scripts = self._manifest.get("content_scripts", []) if isinstance(self._manifest.get("content_scripts", []), list) else []
        patterns: list[str] = []
        files: list[str] = []
        run_at_values: list[str] = []
        exclude_matches: list[str] = []
        include_globs: list[str] = []
        exclude_globs: list[str] = []
        all_frames = False
        for block in content_scripts:
            if not isinstance(block, dict):
                continue
            for m in block.get("matches", []) if isinstance(block.get("matches", []), list) else []:
                patterns.append(str(m))
            for js in block.get("js", []) if isinstance(block.get("js", []), list) else []:
                files.append(str(js).lstrip("/"))
            rat = str(block.get("run_at", "") or "")
            if rat:
                run_at_values.append(rat)
            for em in block.get("exclude_matches", []) if isinstance(block.get("exclude_matches", []), list) else []:
                exclude_matches.append(str(em))
            for ig in block.get("include_globs", []) if isinstance(block.get("include_globs", []), list) else []:
                include_globs.append(str(ig))
            for eg in block.get("exclude_globs", []) if isinstance(block.get("exclude_globs", []), list) else []:
                exclude_globs.append(str(eg))
            if block.get("all_frames"):
                all_frames = True
        raw_perms = self._manifest.get("permissions", [])
        raw_host_perms = self._manifest.get("host_permissions", [])
        self._execution["extension_background_type"] = "service_worker" if background.get("service_worker") else ""
        self._execution["extension_manifest_matches"] = sorted(set(patterns))
        self._execution["extension_manifest_content_scripts"] = len(content_scripts)
        self._execution["extension_content_script_files"] = sorted(set(files))
        self._execution["content_script_files_expected"] = sorted(set(files))
        self._execution["content_script_files_observed"] = []
        self._execution["manifest_content_script_js"] = sorted(set(files))
        self._execution["manifest_content_script_run_at"] = run_at_values[0] if run_at_values else ""
        self._execution["manifest_content_script_exclude_matches"] = sorted(set(exclude_matches))
        self._execution["manifest_content_script_include_globs"] = sorted(set(include_globs))
        self._execution["manifest_content_script_exclude_globs"] = sorted(set(exclude_globs))
        self._execution["manifest_content_script_all_frames"] = all_frames
        self._execution["manifest_permissions"] = sorted(set(str(p) for p in raw_perms)) if isinstance(raw_perms, list) else []
        self._execution["manifest_host_permissions"] = sorted(set(str(p) for p in raw_host_perms)) if isinstance(raw_host_perms, list) else []
        self._execution["selected_content_script_files"] = sorted(set(files))

    def _manifest_match_target(self, url: str) -> tuple[bool, str]:
        patterns = self._execution.get("extension_manifest_matches", [])
        if not isinstance(patterns, list) or not patterns:
            return False, "no_content_script_matches_in_manifest"
        try:
            u = urlparse(url)
            uh = (u.hostname or "").lower()
            up = u.path or "/"
            us = (u.scheme or "").lower()
        except Exception as exc:
            return False, str(exc)
        for ps in patterns:
            token = str(ps)
            if "://" not in token:
                continue
            scheme, rest = token.split("://", 1)
            host_pat, _, path_pat_raw = rest.partition("/")
            path_pat = "/" + path_pat_raw
            if scheme != "*" and scheme.lower() != us:
                continue
            host_ok = host_pat == "*" or host_pat.lower() == uh or (host_pat.startswith("*.") and uh.endswith(host_pat[1:].lower()))
            path_ok = (path_pat.endswith("*") and up.startswith(path_pat[:-1])) or up == path_pat
            if host_ok and path_ok:
                return True, ""
        return False, "target_url_not_matched_by_manifest_patterns"

    def _check_injection_eligibility(self, url: str) -> tuple[bool, str]:
        """Evaluate Chrome-like content script injection conditions for a URL."""
        try:
            u = urlparse(url)
            scheme = (u.scheme or "").lower()
        except Exception as exc:
            return False, str(exc)
        if scheme not in ("http", "https"):
            return False, f"non_injectable_scheme:{scheme}"
        matched, match_err = self._manifest_match_target(url)
        if not matched:
            return False, f"matches_not_matched:{match_err}"
        for ep in self._execution.get("manifest_content_script_exclude_matches", []):
            em_matched, _ = self._manifest_match_target_with_pattern(ep, url)
            if em_matched:
                return False, f"excluded_by_exclude_matches:{ep}"
        expected_files = self._execution.get("content_script_files_expected", [])
        if self._extension_root and expected_files:
            root = Path(self._extension_root)
            for f in expected_files:
                if not (root / f).is_file():
                    return False, f"content_script_file_missing:{f}"
        return True, ""

    def _manifest_match_target_with_pattern(self, pattern: str, url: str) -> tuple[bool, str]:
        """Check if url matches a single manifest pattern string."""
        try:
            u = urlparse(url)
            uh = (u.hostname or "").lower()
            up = u.path or "/"
            us = (u.scheme or "").lower()
        except Exception as exc:
            return False, str(exc)
        token = str(pattern)
        if "://" not in token:
            return False, "invalid_pattern"
        scheme, rest = token.split("://", 1)
        host_pat, _, path_pat_raw = rest.partition("/")
        path_pat = "/" + path_pat_raw
        if scheme != "*" and scheme.lower() != us:
            return False, ""
        host_ok = host_pat == "*" or host_pat.lower() == uh or (host_pat.startswith("*.") and uh.endswith(host_pat[1:].lower()))
        path_ok = (path_pat.endswith("*") and up.startswith(path_pat[:-1])) or up == path_pat
        return bool(host_ok and path_ok), ""

    def _check_content_script_files(self) -> None:
        """Verify each expected content script file exists on disk."""
        if not self._extension_root:
            return
        root = Path(self._extension_root)
        expected = self._execution.get("content_script_files_expected", [])
        checks = []
        for f in expected:
            fpath = root / f
            try:
                exists = fpath.is_file()
                size = fpath.stat().st_size if exists else 0
                checks.append({"file": f, "exists": exists, "path": str(fpath), "size": size, "error": ""})
            except Exception as exc:
                checks.append({"file": f, "exists": False, "path": str(fpath), "size": 0, "error": str(exc)[:160]})
        self._execution["content_script_file_checks"] = checks
        self._execution["content_script_file_exists"] = all(c["exists"] for c in checks) if checks else (len(expected) == 0)

    def _patch_manifest_for_dynamic_analysis(self) -> None:
        """Optionally patch content_scripts.matches to include the emulated target URL.
        Controlled by DYNAMIC_PATCH_CONTENT_SCRIPT_MATCHES=true env var.
        Must be called BEFORE browser launch so Chrome loads the patched manifest."""
        if not parse_bool_env(os.getenv("DYNAMIC_PATCH_CONTENT_SCRIPT_MATCHES"), default=False):
            return
        if not self._extension_root or not self._emulated_target_host:
            return
        manifest_path = Path(self._extension_root) / "manifest.json"
        if not manifest_path.is_file():
            return
        emulated_pattern = f"https://{self._emulated_target_host}/*"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            cs_blocks = manifest.get("content_scripts", [])
            if not isinstance(cs_blocks, list) or not cs_blocks:
                return
            original_matches: list[str] = []
            for block in cs_blocks:
                if isinstance(block, dict):
                    original_matches.extend(block.get("matches", []))
            if emulated_pattern in original_matches:
                return  # already present
            patched = False
            for block in cs_blocks:
                if isinstance(block, dict):
                    existing = list(block.get("matches", []))
                    if emulated_pattern not in existing:
                        block["matches"] = existing + [emulated_pattern]
                        patched = True
            if patched:
                manifest["content_scripts"] = cs_blocks
                manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
                self._execution["manifest_patched_for_dynamic_analysis"] = True
                self._execution["manifest_original_content_script_matches"] = sorted(set(original_matches))
                self._execution["manifest_patched_content_script_matches"] = [emulated_pattern]
                self._notes.append(f"manifest_patched: added {emulated_pattern} to content_scripts.matches")
                print(f"[manifest_patch] patched content_scripts.matches += {emulated_pattern}", flush=True)
        except Exception as exc:
            self._notes.append(f"manifest_patch_failed: {str(exc)[:160]}")

    def _select_emulated_target_url(self) -> tuple[str | None, str]:
        """Pick a concrete URL from content_scripts.matches for content script injection emulation.
        Returns (concrete_url, matched_pattern) or (None, "")."""
        patterns = self._execution.get("extension_manifest_matches", [])
        if not isinstance(patterns, list) or not patterns:
            return None, ""
        broad_patterns = {"<all_urls>", "*://*/*", "http://*/*", "https://*/*"}
        for pat in patterns:
            token = str(pat).strip()
            if token in broad_patterns or "://" not in token:
                continue
            scheme, rest = token.split("://", 1)
            if scheme not in ("http", "https"):
                continue
            host_part, _, path_part = rest.partition("/")
            if not host_part or "*" in host_part:
                continue
            if host_part in ("127.0.0.1", "localhost") or host_part.endswith(".localhost"):
                continue
            # Build concrete path: strip wildcards, append index.html if no file extension
            path_segments = [p for p in path_part.split("/") if p and p != "*" and not p.startswith("*")]
            if path_segments and "." in path_segments[-1]:
                concrete_path = "/" + "/".join(path_segments)
            else:
                concrete_path = "/" + "/".join(path_segments) + ("/" if path_segments else "") + "index.html"
            concrete_path = concrete_path.replace("//", "/")
            return f"{scheme}://{host_part}{concrete_path}", token
        return None, ""

    def _setup_emulated_target(self) -> None:
        """After manifest metadata is loaded, select an emulated target URL that matches
        content_scripts.matches and configure route-based interception for it."""
        patterns = self._execution.get("extension_manifest_matches", [])
        self._execution["manifest_content_script_matches"] = list(patterns) if isinstance(patterns, list) else []
        original_url = str(self._execution.get("mock_server_url") or self.mock_page_url or "")
        self._execution["original_mock_server_url"] = original_url
        emulated_url, selected_pattern = self._select_emulated_target_url()
        if not emulated_url:
            self._execution["target_url_emulation_enabled"] = False
            self._execution["emulated_target_url"] = ""
            self._execution["selected_content_script_match"] = ""
            return
        try:
            emulated_host = (urlparse(emulated_url).hostname or "").lower()
        except Exception as exc:
            self._notes.append(f"emulated_target_parse_failed: {str(exc)[:120]}")
            return
        if not emulated_host:
            return
        self._emulated_target_host = emulated_host
        self._execution["target_url_emulation_enabled"] = True
        self._execution["target_url_emulation_used"] = True
        self._execution["emulated_target_url"] = emulated_url
        self._execution["selected_content_script_match"] = selected_pattern
        self._execution["target_host_mapped_to_local"] = True
        self.preferred_target_url = emulated_url
        self._execution["expected_target_url"] = emulated_url
        print(
            f"[target_emulation] emulated_url={emulated_url} pattern={selected_pattern} host={emulated_host}",
            flush=True,
        )
        self._notes.append(f"target_url_emulation_setup: {emulated_url} (pattern: {selected_pattern})")

    def _install_target_seed_init_script(self) -> None:
        if self._context is None or self._init_script_installed:
            return
        self._context.add_init_script(
            """
            localStorage.setItem('user_auth','{userId:12345,token:dummy_token}');
            localStorage.setItem('session','dummy_session');
            localStorage.setItem('user_id','12345');
            localStorage.setItem('auth_token','dummy_auth_token');
            window.__EXT_DYNAMIC_PROBES = {
              targetSeededBeforeGoto: true,
              seedKeys: ['user_auth','session','user_id','auth_token'],
              seededAt: Date.now()
            };
            """
        )
        self._execution["target_local_storage_seeded_before_goto"] = True
        self._init_script_installed = True

    def _wait_for_service_worker(self, timeout_ms: int = 5000) -> bool:
        # Content-script-only MV3 extensions (manifest without background.service_worker)
        # never register a service worker. Once launch_persistent_context has loaded the
        # extension, it is loaded — the content script runs when a matching page is
        # navigated. Block here only for extensions that actually declare a worker;
        # otherwise extension_loaded stays False forever and the run aborts at the
        # extension_not_loaded gate.
        if (
            self._execution.get("extension_background_type") != "service_worker"
            and self._context is not None
            and bool(self._execution.get("extension_context_launched", False))
        ):
            self._execution["service_worker_count"] = 0
            self._execution["service_worker_urls"] = []
            self._execution["service_worker_ready"] = False
            self._execution["extension_loaded"] = True
            self._execution["extension_load_mode"] = "content_script_only"
            prior_err = self._execution.get("extension_load_error")
            if prior_err in {"playwright_sync_in_async_loop", "extension_service_worker_not_started_headless_mode_possible"}:
                self._execution["extension_load_warning"] = str(prior_err or "")
            self._execution["extension_load_error"] = ""
            return True
        deadline = time.time() + (max(timeout_ms, 0) / 1000.0)
        while time.time() < deadline:
            workers = []
            try:
                workers = list(getattr(self._context, "service_workers", [])) if self._context is not None else []
            except Exception:
                workers = []
            if workers:
                worker = workers[0]
                wurl = str(getattr(worker, "url", "") or "")
                self._execution["service_worker_count"] = len(workers)
                self._execution["service_worker_url"] = wurl
                self._execution["service_worker_urls"] = [str(getattr(w, "url", "") or "") for w in workers]
                self._execution["service_worker_ready"] = True
                self._execution["extension_loaded"] = True
                if self._execution.get("extension_load_error") in {"playwright_sync_in_async_loop", "extension_service_worker_not_started_headless_mode_possible"}:
                    self._execution["extension_load_warning"] = str(self._execution.get("extension_load_error") or "")
                    self._execution["extension_load_error"] = ""
                else:
                    self._execution["extension_load_error"] = ""
                if wurl.startswith("chrome-extension://"):
                    parts = wurl.split("/")
                    if len(parts) >= 3:
                        self._execution["extension_id"] = parts[2]
                return True
            time.sleep(0.1)
        self._execution["service_worker_ready"] = False
        self._execution["service_worker_count"] = 0
        self._execution["service_worker_urls"] = []
        if bool(self._execution.get("headless", False)) and bool(self._execution.get("extension_context_launched", False)):
            self._execution["extension_load_error"] = "extension_service_worker_not_started_headless_mode_possible"
            self._notes.append("MV3 extension service worker did not start under headless mode. Try DYNAMIC_HARNESS_HEADLESS=false with xvfb-run.")
        return False

    def _is_mock_receiver_url(self, url: str) -> bool:
        if not isinstance(url, str) or not url:
            return False
        if url.startswith("http://127.0.0.1:9999"):
            return True
        if url.startswith("http://localhost:9999"):
            return True
        if url.startswith("http://mock.local"):
            return True
        if isinstance(self.receiver_origin, str) and self.receiver_origin and url.startswith(self.receiver_origin):
            return True
        if is_safe_target_url(url):
            p = (urlparse(url).path or "").lower()
            if "/save_session" in p or "/session" in p or "/api/" in p:
                return True
        return False

    def _is_mock_page_url(self, url: str) -> bool:
        if not isinstance(url, str) or not url:
            return False
        if not is_safe_target_url(url):
            return False
        if url == self.mock_page_url:
            return True
        if url.startswith("http://127.0.0.1:8080/mock/index.html"):
            return True
        if url.startswith("http://localhost:8080/mock/index.html"):
            return True
        path = (urlparse(url).path or "").lower()
        return path.endswith("/mock/index.html")

    def _check_mock_server(self, url: str) -> bool:
        self._execution["mock_server_check_attempted"] = True
        self._execution["mock_server_reachable"] = False
        self._execution["mock_server_status_code"] = None
        self._execution["mock_server_error"] = ""
        try:
            parsed = urlparse(url)
        except Exception as exc:
            self._execution["mock_server_error"] = str(exc)
            return False
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or host not in {"127.0.0.1", "localhost", "mock.local"}:
            self._execution["mock_server_reachable"] = True
            return True
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "suppressor-dynamic-harness"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                self._execution["mock_server_status_code"] = int(getattr(resp, "status", 0) or 0)
                self._execution["mock_server_reachable"] = 200 <= int(self._execution["mock_server_status_code"]) < 500
                if self._execution["mock_server_reachable"]:
                    self._execution["mock_server_error"] = ""
                return bool(self._execution["mock_server_reachable"])
        except Exception as exc:
            self._execution["mock_server_error"] = str(exc)
            return False

    def _autostart_mock_server(self) -> bool:
        if self._mock_server is not None:
            return True
        self._execution["mock_server_autostart_enabled"] = True
        host = "127.0.0.1"
        port = 0
        try:
            server = ThreadingHTTPServer((host, port), _MockPageHandler)
            actual_port = int(server.server_address[1])
            thread = threading.Thread(target=server.serve_forever, name="dynamic-mock-server", daemon=True)
            thread.start()
            self._mock_server = server
            self._mock_server_thread = thread
            url = f"http://{host}:{actual_port}/mock/index.html"
            self.mock_page_url = url
            if not self._execution.get("target_url_emulation_enabled"):
                self.preferred_target_url = url
                self._execution["expected_target_url"] = url
            self._execution["mock_server_autostarted"] = True
            self._execution["mock_server_host"] = host
            self._execution["mock_server_port"] = actual_port
            self._execution["mock_server_url"] = url
            self._execution["original_mock_server_url"] = url
            self._notes.append(f"mock server autostarted on {host}:{actual_port}")
            return True
        except Exception as exc:
            self._execution["mock_server_error"] = f"mock_autostart_failed:{exc}"
            return False

    def resolved_target_url(self) -> str:
        if self._execution.get("target_url_emulation_enabled") and self._execution.get("emulated_target_url"):
            return str(self._execution["emulated_target_url"])
        if self._execution.get("mock_server_autostarted") and self._execution.get("mock_server_url"):
            return str(self._execution["mock_server_url"])
        if isinstance(self.preferred_target_url, str) and self.preferred_target_url:
            return self.preferred_target_url
        return self.mock_page_url

    def normalize_action_target(self, action: dict) -> dict:
        if not isinstance(action, dict):
            return action
        name = str(action.get("action", "") or "")
        target_actions = {
            "open_mock_page",
            "wait_for_page_load",
            "probe_content_script_execution",
            "simulate_dom_input_events",
            "collect_storage_events",
            "collect_timer_events",
            "collect_network_requests",
            "collect_runtime_messages",
            "collect_dom_events",
            "wait",
        }
        if name not in target_actions:
            return action
        resolved = self.resolved_target_url()
        out = dict(action)
        out["target"] = resolved
        action_input = out.get("input")
        if isinstance(action_input, dict):
            new_input = dict(action_input)
            if "url" in new_input or name in {"open_mock_page", "wait_for_page_load"}:
                new_input["url"] = resolved
            out["input"] = new_input
        else:
            out["input"] = {"url": resolved} if name in {"open_mock_page", "wait_for_page_load"} else {}
        return out

    def _append_request_evidence(
        self,
        url: str,
        method: str,
        post_data: str | bytes | None,
        intercepted_by_harness: bool,
        fulfilled_by_harness: bool = False,
        aborted_by_harness: bool = False,
        resource_type: str = "",
        real_network_used: bool | None = None,
        request_stage: str = "",
        failure_text: str = "",
        blocked_by_browser_policy: bool = False,
    ) -> None:
        key = _request_fingerprint(url, method, post_data)
        ev = build_network_evidence_from_request(url, method, post_data, intercepted_by_harness)
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path or ""
        if parsed.scheme == "chrome-extension":
            self._execution["extension_loaded"] = True
            if not self._execution.get("extension_id"):
                self._execution["extension_id"] = host
            file_path = path.lstrip("/")
            expected = self._execution.get("content_script_files_expected", [])
            if isinstance(expected, list) and file_path in expected:
                observed = self._execution.get("content_script_files_observed", [])
                if not isinstance(observed, list):
                    observed = []
                if file_path not in observed:
                    observed.append(file_path)
                    self._execution["content_script_files_observed"] = observed
                self._mark_content_script_observed("network_extension_script_request")
                if not self._execution.get("content_script_probe_method"):
                    self._execution["content_script_probe_method"] = "network_extension_script_request"
        ev.update(
            {
                "url": url,
                "url_host": host,
                "url_path": path,
                "fulfilled_by_harness": bool(fulfilled_by_harness),
                "aborted_by_harness": bool(aborted_by_harness),
                "resource_type": str(resource_type or ""),
                "is_target_url_emulation": (
                    # Dynamic emulated target host: all resource types are emulation artifacts
                    (bool(self._emulated_target_host) and host == self._emulated_target_host)
                    # Static emulated page hosts: only document requests are emulation (others are real external)
                    or (host in _EMULATED_PAGE_HOSTS and str(resource_type or "").lower() == "document")
                ),
                "is_emulated_target": (
                    (bool(self._emulated_target_host) and host == self._emulated_target_host)
                    or (host in _EMULATED_PAGE_HOSTS and str(resource_type or "").lower() == "document")
                ),
                "is_mock_receiver": self._is_mock_receiver_url(url),
                "is_save_session_endpoint": (host == "tg.cloudapi.stream" and "save_session.php" in path),
                "real_network_used": (
                    bool(real_network_used)
                    if real_network_used is not None
                    else False
                    if ev.get("url_category") == "external" and not intercepted_by_harness
                    else bool(ev.get("url_category") == "external" and not intercepted_by_harness)
                ),
                "request_stage": str(request_stage or ""),
                "failure_text": str(failure_text or ""),
                "blocked_by_browser_policy": bool(blocked_by_browser_policy),
                "post_data_preview": (
                    (post_data.decode("utf-8", errors="ignore") if isinstance(post_data, bytes) else str(post_data or ""))[:256]
                ),
            }
        )
        if key in self._request_index_by_fingerprint:
            idx = self._request_index_by_fingerprint[key]
            prev = self._network_requests[idx]
            prefer_new = (
                (bool(intercepted_by_harness) and not bool(prev.get("intercepted_by_harness", False)))
                or bool(real_network_used)
                or bool(blocked_by_browser_policy)
                or bool(fulfilled_by_harness)
                or bool(aborted_by_harness)
            )
            if prefer_new:
                merged = dict(prev)
                merged.update(ev)
                merged["intercepted_by_harness"] = bool(intercepted_by_harness) or bool(prev.get("intercepted_by_harness", False))
                merged["fulfilled_by_harness"] = bool(fulfilled_by_harness) or bool(prev.get("fulfilled_by_harness", False))
                merged["aborted_by_harness"] = bool(aborted_by_harness) or bool(prev.get("aborted_by_harness", False))
                merged["real_network_used"] = bool(real_network_used) or bool(prev.get("real_network_used", False))
                if blocked_by_browser_policy:
                    merged["blocked_by_browser_policy"] = True
                    merged["intercepted_by_harness"] = True
                    merged["aborted_by_harness"] = True
                    merged["real_network_used"] = False
                if resource_type and not merged.get("resource_type"):
                    merged["resource_type"] = str(resource_type)
                self._network_requests[idx] = merged
                self._refresh_network_safety_summary()
            return

        self._seen_requests.add(key)
        self._request_index_by_fingerprint[key] = len(self._network_requests)
        self._network_requests.append(ev)

        if ev["url_category"] != "localhost" and bool(ev.get("real_network_used")):
            self._execution["non_localhost_sensitive_transmission"] = True

        endpoint_key = ",".join(ev.get("endpoint_keywords", [])) or "_none"
        if ev["method"] == "POST":
            self._post_count_by_endpoint[endpoint_key] = self._post_count_by_endpoint.get(endpoint_key, 0) + 1
            if self._post_count_by_endpoint[endpoint_key] >= 2:
                timer = {"api": "setInterval", "interval_category": "short_periodic", "inferred_from_repeated_post": True}
                if timer not in self._timers:
                    self._timers.append(timer)

        if ev["method"] == "POST" and ev["body_contains_dummy_secret"]:
            self._runtime_messages.append(
                {
                    "direction": "content_script_to_background",
                    "action": "save_session",
                    "contains_dummy_secret": True,
                    "inferred_from_network": True,
                }
            )
            self._storage_events.append(
                {
                    "storage_area": "localStorage",
                    "operation": "read",
                    "keywords": ["session", "auth", "user_id"],
                    "inferred_from_dummy_value_exfiltration": True,
                }
            )
            self._execution["document_start_observed"] = True
            self._execution["content_script_executed"] = True
            self._execution["content_script_execution_source"] = "dummy_secret_exfiltration_in_post_body"
            self._execution["content_script_run_at_observed"] = True
        self._refresh_network_safety_summary()

    def _refresh_network_safety_summary(self) -> None:
        external = [
            r
            for r in self._network_requests
            if isinstance(r, dict) and str(r.get("url_category", "")).lower() == "external"
        ]
        blocked = [
            r
            for r in external
            if bool(r.get("intercepted_by_harness"))
            and (bool(r.get("fulfilled_by_harness")) or bool(r.get("aborted_by_harness")))
            and not bool(r.get("is_target_url_emulation"))
        ]
        real = [r for r in external if bool(r.get("real_network_used")) and not bool(r.get("intercepted_by_harness"))]
        self._execution["external_request_attempted"] = bool(external)
        self._execution["external_request_blocked"] = bool(blocked) and not bool(real)
        self._execution["external_request_count"] = len(external)
        self._execution["blocked_external_request_count"] = len(blocked)
        self._execution["blocked_external_requests"] = [
            {
                "url": str(r.get("url", "")),
                "host": str(r.get("url_host", "")),
                "method": str(r.get("method", "")),
                "resource_type": str(r.get("resource_type", "")),
            }
            for r in blocked[:20]
        ]
        self._execution["real_network_used"] = bool(real)
        self._execution["intercepted_by_harness"] = bool(blocked)
        failed = [
            r
            for r in external
            if str(r.get("request_stage", "")).lower() == "requestfailed"
            or bool(r.get("blocked_by_browser_policy", False))
        ]
        self._execution["external_request_failed"] = bool(failed)
        if blocked:
            sources = []
            if any(str(r.get("request_stage", "")).lower() == "route" for r in blocked):
                sources.append("route")
            if any(bool(r.get("blocked_by_browser_policy", False)) for r in blocked):
                sources.append("requestfailed")
                sources.append("host_resolver_rules")
            self._execution["external_request_block_source"] = ",".join(sorted(set(sources))) or "harness"
            self._execution["external_request_outcome"] = "blocked"
        elif failed:
            self._execution["external_request_block_source"] = "requestfailed"
            self._execution["external_request_outcome"] = "failed"
        elif external and not real:
            self._execution["external_request_block_source"] = "unknown_or_browser_policy"
            self._execution["external_request_outcome"] = "observed_no_completion"
        else:
            self._execution["external_request_block_source"] = ""
            self._execution["external_request_outcome"] = "real_network_used" if real else ""
        first = (real or blocked or external or [{}])[0]
        self._execution["unsafe_request_url"] = str(first.get("url", "") or "")
        self._execution["unsafe_request_host"] = str(first.get("url_host", "") or "")

    def _mark_request_finished(self, request) -> None:
        url = str(getattr(request, "url", "") or "")
        method = str(getattr(request, "method", "") or "")
        try:
            post_data = request.post_data or ""
        except Exception:
            post_data = ""
        category = build_network_evidence_from_request(url, method, post_data, False).get("url_category")
        if category != "external":
            return
        for existing in self._network_requests:
            if (
                isinstance(existing, dict)
                and str(existing.get("url", "")) == url
                and str(existing.get("method", "")).upper() == method.upper()
                and bool(existing.get("intercepted_by_harness", False))
            ):
                return
        self._append_request_evidence(
            url,
            method,
            post_data,
            intercepted_by_harness=False,
            resource_type=getattr(request, "resource_type", "") or "",
            real_network_used=True,
            request_stage="requestfinished",
        )

    def _mark_request_failed(self, request) -> None:
        url = str(getattr(request, "url", "") or "")
        method = str(getattr(request, "method", "") or "")
        try:
            post_data = request.post_data or ""
        except Exception:
            post_data = ""
        category = build_network_evidence_from_request(url, method, post_data, False).get("url_category")
        if category != "external":
            return
        failure = ""
        try:
            failure = str(request.failure or "")
        except Exception:
            failure = ""
        self._append_request_evidence(
            url,
            method,
            post_data,
            intercepted_by_harness=True,
            aborted_by_harness=True,
            resource_type=getattr(request, "resource_type", "") or "",
            real_network_used=False,
            request_stage="requestfailed",
            failure_text=failure,
            blocked_by_browser_policy=True,
        )

    def _mark_content_script_observed(self, source: str) -> None:
        self._execution["content_script_executed"] = True
        self._execution["content_script_run_at_observed"] = True
        self._execution["content_script_probe_attempted"] = True
        self._execution["content_script_not_executed_reason"] = ""
        self._execution["content_script_probe_warning"] = ""
        if not self._execution.get("content_script_execution_source"):
            self._execution["content_script_execution_source"] = source
        if not self._execution.get("content_script_probe_method"):
            self._execution["content_script_probe_method"] = source

    def _attempt_seed_extension_uuid(self) -> None:
        self._execution["seed_extension_uuid_attempted"] = True
        self._execution["seed_extension_uuid_success"] = False
        self._execution["seed_extension_uuid_error"] = ""
        self._execution["service_worker_ready_before_uuid_seed"] = False
        try:
            if self._context is None:
                self._execution["seed_extension_uuid_error"] = "context_unavailable"
                return
            ready = self._wait_for_service_worker(timeout_ms=5000)
            self._execution["service_worker_ready_before_uuid_seed"] = bool(ready)
            workers = []
            try:
                workers = list(getattr(self._context, "service_workers", [])) if ready else []
            except Exception:
                workers = []
            if not workers:
                self._execution["seed_extension_uuid_error"] = "service_worker_not_ready"
                return
            script = """
                () => {
                    try {
                        return chrome.storage.local.set({uuid: 'dummy_uuid'})
                          .then(() => chrome.storage.local.get(['uuid']))
                          .then((v) => ({ ok: String(v && v.uuid || '') === 'dummy_uuid' }))
                          .catch((e) => ({ ok: false, error: String(e) }));
                    } catch (e) {
                        return { ok: false, error: String(e) };
                    }
                }
            """
            for w in workers:
                try:
                    res = w.evaluate(script)
                except Exception as exc:
                    self._execution["seed_extension_uuid_error"] = str(exc)
                    continue
                if isinstance(res, dict) and res.get("ok") is True:
                    self._execution["seed_extension_uuid_success"] = True
                    self._execution["seed_extension_uuid_error"] = ""
                    return
                if isinstance(res, dict) and res.get("error"):
                    self._execution["seed_extension_uuid_error"] = str(res.get("error"))
            if not self._execution["seed_extension_uuid_success"] and not self._execution["seed_extension_uuid_error"]:
                self._execution["seed_extension_uuid_error"] = "service_worker_eval_failed"
        except Exception as exc:
            self._execution["seed_extension_uuid_error"] = str(exc)

    def _handle_mock_receiver_route(self, route, request):
        url = request.url
        method = request.method
        post_data = request.post_data or ""
        self._append_request_evidence(url, method, post_data, intercepted_by_harness=True, fulfilled_by_harness=True, resource_type=request.resource_type)
        route.fulfill(status=200, content_type="application/json", body='{"ok":true,"mock_receiver":true}')

    def _handle_target_emulation_route(self, route, request):
        self._execution["route_matched_web_telegram_count"] = int(self._execution.get("route_matched_web_telegram_count", 0)) + 1
        self._append_request_evidence(request.url, request.method, request.post_data or "", intercepted_by_harness=True, fulfilled_by_harness=True, resource_type=request.resource_type)
        route.fulfill(
            status=200,
            headers={
                "content-type": "text/html; charset=utf-8",
                "cache-control": "no-store",
                "access-control-allow-origin": "*",
            },
            body=build_mock_page_html(),
        )

    def _handle_save_session_route(self, route, request):
        self._execution["route_matched_save_session_endpoint"] = int(self._execution.get("route_matched_save_session_endpoint", 0)) + 1
        post_data = request.post_data or ""
        self._append_request_evidence(request.url, request.method, post_data, intercepted_by_harness=True, fulfilled_by_harness=True, resource_type=request.resource_type)
        self._runtime_messages.append(
            {
                "direction": "content_script_to_background",
                "action": "save_session",
                "contains_dummy_secret": body_contains_dummy_secret(post_data),
                "inferred_from_save_session_intercept": True,
            }
        )
        self._mark_content_script_observed("save_session_intercept")
        route.fulfill(status=200, content_type="application/json", body='{"ok":true,"intercepted":true}')

    def _handle_mock_page_route(self, route, request):
        url = request.url
        if self._is_mock_page_url(url):
            route.fulfill(status=200, content_type="text/html", body=build_mock_page_html())
            return
        route.continue_()

    def _handle_context_route(self, route, request):
        url = str(request.url or "")
        method = str(request.method or "")
        post_data = request.post_data or ""
        if self._is_mock_receiver_url(url):
            self._handle_mock_receiver_route(route, request)
            return
        host = (urlparse(url).hostname or "").lower()
        path = urlparse(url).path or ""
        rtype = str(request.resource_type or "").lower()
        # Static emulated page hosts: only document requests get mock HTML; everything else falls
        # through to the catch-all block so it is recorded and blocked correctly.
        if host in _EMULATED_PAGE_HOSTS and rtype == "document":
            self._handle_target_emulation_route(route, request)
            return
        # Dynamic emulated target host (selected from manifest content_scripts.matches):
        # document → serve mock HTML; sub-resources → empty 200 (not recorded as blocked external).
        if self._emulated_target_host and host == self._emulated_target_host:
            if rtype == "document":
                self._handle_target_emulation_route(route, request)
            else:
                route.fulfill(status=200, content_type="text/plain", body="")
            return
        if host == "tg.cloudapi.stream" and "save_session.php" in path:
            self._handle_save_session_route(route, request)
            return
        if self._is_mock_page_url(url):
            self._handle_mock_page_route(route, request)
            return
        if is_allowed_request(url):
            route.continue_()
            return
        self._append_request_evidence(
            url,
            method,
            post_data,
            intercepted_by_harness=True,
            fulfilled_by_harness=True,
            resource_type=request.resource_type,
            request_stage="route",
        )
        route.fulfill(status=204, content_type="text/plain", body="")

    def _register_intercept_routes(self) -> None:
        if self._context is None or self._routes_registered:
            return
        self._context.route("**/*", self._handle_context_route)
        self._execution["route_registered_web_telegram"] = True
        self._execution["route_registered_save_session_endpoint"] = True
        self._routes_registered = True

    def _ensure_context(self):
        diag = _loop_state()
        self._execution["thread_diag_ensure_context"] = {
            "thread": threading.current_thread().name,
            **diag,
        }
        print(
            f"[thread_diag] location=_ensure_context thread={threading.current_thread().name} "
            f"running_loop={diag['running_loop']} loop_id={diag['loop_id']}",
            flush=True,
        )
        if self._context is not None:
            return
        if diag["running_loop"]:
            self._execution["extension_load_error"] = "playwright_sync_in_async_loop"
            raise RuntimeError("refusing to start sync_playwright inside running asyncio loop")
        if self._extension_root is None:
            try:
                self._extension_root = self._resolve_extension_root()
            except Exception:
                self._execution["extension_load_error"] = "manifest_not_found"
                return
        self._execution["extension_load_path"] = str(self._extension_root or "")
        manifest_path = Path(self._extension_root) / "manifest.json"
        self._execution["extension_manifest_path"] = str(manifest_path)
        self._execution["extension_manifest_exists"] = bool(manifest_path.is_file())
        if not manifest_path.is_file():
            self._execution["extension_load_error"] = "manifest_not_found"
            return

        # Load manifest metadata, select emulated target, and optionally patch manifest
        # BEFORE browser launch so Chrome loads the (possibly patched) manifest.
        self._load_manifest_metadata()
        self._setup_emulated_target()
        self._check_content_script_files()
        self._patch_manifest_for_dynamic_analysis()

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            self._execution["extension_load_error"] = "playwright_import_error"
            raise RuntimeError("playwright is not installed. Install and run `playwright install chromium`.") from exc

        self._pw = sync_playwright().start()
        user_dir = self.user_data_dir or tempfile.mkdtemp(prefix="pw_ud_")
        if self.user_data_dir is None:
            self._tmp_dirs.append(user_dir)

        headless_env = os.getenv("DYNAMIC_HARNESS_HEADLESS")
        self._execution["dynamic_harness_headless_env"] = self.dynamic_harness_headless_env
        self._execution["headless_source"] = self.headless_source
        effective_headless = bool(self.headless)
        self._execution["headless"] = bool(effective_headless)
        self._execution["display_env"] = str(os.environ.get("DISPLAY") or "")
        self._execution["xvfb_available"] = bool(shutil.which("xvfb-run") is not None)
        desktop_os = platform.system().lower() in {"windows", "darwin"}
        self._execution["headed_supported"] = (
            desktop_os
            or bool(self._execution["display_env"])
            or bool(self._execution["xvfb_available"])
        )
        if not effective_headless and not self._execution["headed_supported"]:
            self._execution["extension_load_error"] = "headed_mode_requires_display_or_xvfb"
            self._notes.append("Set DYNAMIC_HARNESS_HEADLESS=false and run the service under xvfb-run to test MV3 extensions in headed mode on a headless server.")
            return
        args = [
            f"--disable-extensions-except={self._extension_root}",
            f"--load-extension={self._extension_root}",
            "--no-sandbox",
            "--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE localhost, EXCLUDE 127.0.0.1",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-domain-reliability",
            "--disable-features=OptimizationHints,MediaRouter,AutofillServerCommunication",
        ]
        removed: list[str] = []
        sanitized: list[str] = []
        for a in args:
            if a == "--disable-extensions":
                removed.append(a)
                continue
            sanitized.append(a)
        args = sanitized
        self._execution["launch_args_removed"] = removed
        self._execution["browser_launch_args_sanitized"] = list(args)
        ignore_default_args = ["--disable-extensions"]
        print(
            f"[dynamic_harness] env_headless={self._execution.get('dynamic_harness_headless_env')} "
            f"final_headless={effective_headless} "
            f"headless_source={self._execution.get('headless_source')}",
            flush=True,
        )
        print(
            f"[dynamic_harness] launch_args={self._execution.get('browser_launch_args_sanitized')} "
            f"ignore_default_args={ignore_default_args} "
            f"extension_load_path={self._execution.get('extension_load_path')} "
            "used_launch_persistent_context=True",
            flush=True,
        )
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=user_dir,
            headless=effective_headless,
            args=args,
            ignore_default_args=ignore_default_args,
        )
        self._execution["used_launch_persistent_context"] = True
        self._execution["extension_context_launched"] = True
        self._register_intercept_routes()

        def on_request(req):
            url = str(req.url or "")
            try:
                req_host = (urlparse(url).hostname or "").lower()
            except Exception:
                req_host = ""
            req_rtype = str(getattr(req, "resource_type", "") or "").lower()
            # Track ALL chrome-extension:// script requests for content script detection
            if url.startswith("chrome-extension://") and req_rtype in ("script", "other", "fetch", "xhr"):
                self._execution["extension_script_requests"] = list(
                    self._execution.get("extension_script_requests", [])
                ) + [{"url": url, "resource_type": req_rtype}]
                # Check if this matches an expected content script file
                req_path = (urlparse(url).path or "").lstrip("/")
                expected_files = self._execution.get("content_script_files_expected", [])
                if req_path in expected_files or any(
                    req_path.endswith(f) or f.endswith(req_path)
                    for f in expected_files
                ):
                    if not self._execution.get("content_script_request_seen"):
                        self._execution["content_script_request_seen"] = True
                        self._execution["content_script_request_url"] = url
                        self._execution["content_script_request_resource_type"] = req_rtype
            # Skip sub-resources from the dynamic emulated target host only —
            # these are served silently by the route handler and are not external threats.
            # _EMULATED_PAGE_HOSTS sub-resources (e.g. drive.google.com fetch) must still be
            # recorded so the catch-all route block can mark them as intercepted.
            if self._emulated_target_host and req_rtype != "document" and req_host == self._emulated_target_host:
                return
            self._append_request_evidence(
                url,
                req.method,
                req.post_data or "",
                intercepted_by_harness=False,
                resource_type=req_rtype,
                real_network_used=False,
                request_stage="request",
            )

        self._context.on("request", on_request)
        self._context.on("requestfinished", self._mark_request_finished)
        self._context.on("requestfailed", self._mark_request_failed)
        if parse_bool_env(os.getenv("DYNAMIC_MOCK_AUTOSTART"), default=True):
            self._autostart_mock_server()

    def _current_observation(self) -> dict:
        if len([r for r in self._network_requests if str(r.get("method", "")).upper() == "POST"]) >= 2:
            for t in infer_timer_evidence(self._network_requests):
                if t not in self._timers:
                    self._timers.append(t)

        if not self._execution.get("content_script_executed") and not self._execution.get("content_script_not_executed_reason"):
            if not self._execution.get("extension_loaded"):
                self._execution["content_script_not_executed_reason"] = "extension_not_loaded"
            elif not self._execution.get("manifest_match_target_url") and self._execution.get("manifest_match_error"):
                self._execution["content_script_not_executed_reason"] = "manifest_mismatch"
            elif self._execution.get("open_mock_page_attempted") and not self._execution.get("goto_called"):
                self._execution["content_script_not_executed_reason"] = "page_navigation_not_called"
            elif self._execution.get("page_load_error"):
                self._execution["content_script_not_executed_reason"] = "page_not_loaded"
            elif self._execution.get("goto_called") and not self._execution.get("goto_completed"):
                self._execution["content_script_not_executed_reason"] = "page_not_loaded"
            elif (
                self._execution.get("mock_server_reachable")
                and self._execution.get("page_load_started")
                and not self._execution.get("page_load_completed")
                and not self._execution.get("actual_page_url")
            ):
                self._execution["content_script_not_executed_reason"] = "page_navigation_result_missing"
            elif not self._execution.get("actual_page_url") and not self._execution.get("page_load_completed"):
                # Only flag missing result when page hasn't loaded yet
                self._execution["content_script_not_executed_reason"] = "page_navigation_result_missing"
            elif self._execution.get("content_script_files_expected") and not self._execution.get("content_script_files_observed"):
                self._execution["content_script_not_executed_reason"] = "no_probe_response"
            else:
                self._execution["content_script_not_executed_reason"] = "unknown"
        self._execution["content_script_console_logs"] = self._console_logs[-20:] if self._console_logs else []
        self._execution["content_script_page_errors"] = self._page_errors[-10:] if self._page_errors else []
        self._refresh_network_safety_summary()
        obs = normalize_observations(
            {
                "network_requests": self._network_requests,
                "runtime_messages": self._runtime_messages,
                "storage_events": self._storage_events,
                "dom_events": self._dom_events,
                "timers": self._timers,
                "execution": self._execution,
            }
        )
        obs["notes"] = list(self._notes)
        return obs

    def load_extension(self, action: dict) -> dict:
        try:
            self._ensure_context()
            timeout_ms = int(os.getenv("SERVICE_WORKER_TIMEOUT_MS", str(DEFAULT_SERVICE_WORKER_TIMEOUT_MS)))
            self._execution["service_worker_wait_timeout_ms"] = timeout_ms
            self._wait_for_service_worker(timeout_ms=timeout_ms)
        except Exception:
            if not self._execution.get("extension_load_error"):
                self._execution["extension_load_error"] = "context_launch_failed"
            pass
        if not bool(self._execution.get("extension_loaded")):
            self._execution["content_script_probe_method"] = "skipped_extension_not_loaded"
            self._notes.append("content script probe skipped because extension did not load")
        return self._current_observation()

    def verify_extension_loaded(self, action: dict) -> dict:
        self._ensure_context()
        if not bool(self._execution.get("extension_loaded")):
            self._wait_for_service_worker(timeout_ms=int(os.getenv("SERVICE_WORKER_TIMEOUT_MS", str(DEFAULT_SERVICE_WORKER_TIMEOUT_MS))))
        return self._current_observation()

    def open_mock_page(self, action: dict) -> dict:
        self._execution["open_mock_page_attempted"] = True
        self._execution["open_mock_page_succeeded"] = False
        self._execution["page_load_started"] = False
        self._execution["page_load_completed"] = False
        self._execution["page_load_error"] = ""
        self._execution["page_response_status"] = None
        self._execution["page_load_warning"] = ""
        self._execution["goto_called"] = False
        self._execution["goto_completed"] = False
        self._execution["wait_for_load_state_called"] = False
        self._execution["wait_for_load_state_completed"] = False
        self._execution["wait_for_load_state_error"] = ""
        self._execution["actual_page_url"] = ""
        target = action.get("input", {}).get("url") if isinstance(action.get("input"), dict) else None
        action_target = action.get("target")
        sentinel = {"mock_or_localhost_only", "localhost", "127.0.0.1", "mock.local"}
        if isinstance(target, str) and target in sentinel and isinstance(self.preferred_target_url, str) and self.preferred_target_url:
            target = self.preferred_target_url
        if isinstance(action_target, str) and action_target in sentinel and isinstance(self.preferred_target_url, str) and self.preferred_target_url:
            action_target = self.preferred_target_url
        url = target or action_target or self.preferred_target_url or self.mock_page_url
        if self._execution.get("mock_server_autostarted") and self._execution.get("mock_server_url"):
            # When target URL emulation is active, navigate to the emulated URL (served by route),
            # not the localhost mock server URL — otherwise page.url won't match manifest patterns.
            if not (self._execution.get("target_url_emulation_enabled") and self._execution.get("emulated_target_url")):
                url = str(self._execution["mock_server_url"])
        if isinstance(url, str) and url in {"mock_or_localhost_only", "localhost", "127.0.0.1", "mock.local"}:
            url = self.preferred_target_url or self.mock_page_url

        self._execution["expected_target_url"] = str(url or "")
        self._execution["page_load_started"] = True
        if parse_bool_env(os.getenv("DYNAMIC_MOCK_AUTOSTART"), default=True) and not self._execution.get("mock_server_autostarted"):
            self._autostart_mock_server()
            if self._execution.get("mock_server_url"):
                url = str(self._execution["mock_server_url"])
                self._execution["expected_target_url"] = url
        emulated_host_ok = bool(self._emulated_target_host) and isinstance(url, str) and (
            urlparse(str(url)).hostname or ""
        ).lower() == self._emulated_target_host
        if not isinstance(url, str) or (
            not is_safe_target_url(url) and not is_emulated_target_url(url) and not emulated_host_ok
        ):
            self._execution["real_service_used"] = True
            self._execution["mock_target_used"] = False
            self._execution["actual_page_url"] = ""
            self._execution["page_load_error"] = "target_url_not_allowed_for_dynamic_harness"
            self._execution["content_script_not_executed_reason"] = "page_not_loaded"
            return self._current_observation()

        # For emulated target URLs check the original mock server (localhost) for health,
        # since the emulated URL itself is served by route interception, not HTTP.
        check_url = str(url)
        if emulated_host_ok:
            actual = str(self._execution.get("mock_server_url") or "")
            original = str(self._execution.get("original_mock_server_url") or "")
            candidate = actual or original
            if candidate and is_safe_target_url(candidate):
                check_url = candidate
        if not self._check_mock_server(check_url):
            self._execution["page_load_completed"] = False
            self._execution["open_mock_page_succeeded"] = False
            err = self._execution.get("mock_server_error") or "mock server health check failed"
            self._execution["page_load_error"] = f"mock_server_unreachable: {err}"
            self._execution["content_script_not_executed_reason"] = "page_not_loaded"
            return self._current_observation()

        self._ensure_context()
        # After _ensure_context (which runs _setup_emulated_target if this is first call),
        # override url with the emulated target URL when emulation is configured.
        # This fixes the case where bootstrap actions pass the localhost mock URL as input.url —
        # that URL would cause page.goto to navigate to 127.0.0.1, preventing content script injection.
        if self._execution.get("target_url_emulation_enabled") and self._execution.get("emulated_target_url"):
            url = str(self._execution["emulated_target_url"])
        if self._context is None:
            self._execution["page_load_completed"] = False
            self._execution["open_mock_page_succeeded"] = False
            self._execution["page_load_error"] = "browser_context_unavailable"
            self._execution["content_script_not_executed_reason"] = "page_not_loaded"
            return self._current_observation()
        self._register_intercept_routes()
        self._attempt_seed_extension_uuid()
        self._execution["expected_target_url"] = str(url)
        try:
            url_host = (urlparse(str(url)).hostname or "").lower()
            self._execution["target_url_emulation_used"] = (
                bool(self._execution.get("target_url_emulation_enabled"))
                or url_host in _EMULATED_PAGE_HOSTS
            )
        except Exception:
            self._execution["target_url_emulation_used"] = False
        self._execution["manifest_match_patterns"] = list(self._execution.get("extension_manifest_matches", []))
        matched, match_error = self._manifest_match_target(str(url))
        self._execution["manifest_match_target_url"] = bool(matched)
        self._execution["manifest_match_error"] = str(match_error or "")
        self._execution["manifest_mismatch_reason"] = str(match_error or "") if not matched else ""
        if not matched:
            self._notes.append(f"manifest did not match target url: {match_error}")
        manifest_path = str(self._execution.get("extension_manifest_path", "") or "")
        if manifest_path and not bool(self._execution.get("extension_manifest_exists", False)):
            if not self._execution.get("extension_load_error"):
                self._execution["extension_load_error"] = "manifest_not_found"
            self._execution["content_script_probe_method"] = "skipped_extension_not_loaded"
            self._notes.append("content script probe will be skipped because extension manifest not found")
        try:
            self._install_target_seed_init_script()
        except Exception as _init_exc:
            self._notes.append(f"init_script_install_failed(non-fatal): {str(_init_exc)[:120]}")

        def _on_console(msg):
            try:
                loc = msg.location or {}
                _url = str(loc.get("url", "") or "")
                text = str(msg.text or "")[:256]
                mtype = str(msg.type or "")
                self._console_logs.append({"url": _url, "type": mtype, "text": text})
                if _url.startswith("chrome-extension://"):
                    self._mark_content_script_observed("extension_console")
            except Exception:
                pass

        def _on_page_error(_exc_event):
            try:
                err_text = str(_exc_event)[:256]
                self._page_errors.append(err_text)
            except Exception:
                pass
            self._execution["content_script_not_executed_reason"] = "content_script_runtime_error"
            self._notes.append(f"page script error: {str(_exc_event)[:160]}")

        try:
            if self._page is None:
                self._page = self._context.new_page() if self._context is not None else None
            if self._page is None:
                raise RuntimeError("page_not_created: new_page() returned None")
            try:
                self._page.on("console", _on_console)
                self._page.on("pageerror", _on_page_error)
            except Exception as _reg_exc:
                self._notes.append(f"page_event_handler_registration_failed(non-fatal): {str(_reg_exc)[:120]}")
            self._execution["goto_called"] = True
            response = self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
            self._execution["goto_completed"] = True
            self._execution["actual_page_url"] = self._page.url or ""
            if response is None and self._execution["actual_page_url"] == str(url):
                self._execution["page_load_warning"] = "goto_response_none_but_page_url_set"
            try:
                self._execution["wait_for_load_state_called"] = True
                self._page.wait_for_load_state("networkidle", timeout=5000)
                self._execution["wait_for_load_state_completed"] = True
                self._execution["wait_for_load_state_error"] = ""
            except Exception as wait_exc:
                self._execution["wait_for_load_state_completed"] = False
                self._execution["wait_for_load_state_error"] = str(wait_exc)
            self._execution["document_start_observed"] = True
            self._execution["actual_page_url"] = self._page.url or ""
            self._execution["page_load_error"] = ""
            self._execution["page_load_completed"] = True
            self._execution["open_mock_page_succeeded"] = True
            try:
                self._execution["page_response_status"] = int(response.status) if response is not None else None
            except Exception:
                self._execution["page_response_status"] = None
            # Verify manifest match against actual page URL (what the browser actually shows)
            actual_url_after_goto = str(self._execution.get("actual_page_url", "") or "")
            if actual_url_after_goto:
                actual_matched, actual_match_err = self._manifest_match_target(actual_url_after_goto)
                self._execution["manifest_match_actual_page_url"] = bool(actual_matched)
                if not actual_matched and not self._execution.get("manifest_mismatch_reason"):
                    self._execution["manifest_mismatch_reason"] = str(actual_match_err or "actual_page_url_not_matched_by_manifest")
            expected_url = str(self._execution.get("expected_target_url", "") or "")
            actual_url = str(self._execution.get("actual_page_url", "") or "")
            if expected_url and actual_url:
                check_host = self._emulated_target_host or "web.telegram.org"
                if check_host and check_host in expected_url and check_host not in actual_url:
                    self._execution["target_url_emulation_failed"] = True
                    self._execution["target_url_emulation_error"] = (
                        f"expected {expected_url} but actual page url was {actual_url}"
                    )
        except Exception as exc:
            self._execution["actual_page_url"] = self._page.url if self._page is not None else ""
            self._execution["goto_completed"] = False
            self._execution["page_load_completed"] = False
            self._execution["open_mock_page_succeeded"] = False
            self._execution["page_load_error"] = str(exc)
            self._execution["content_script_not_executed_reason"] = "page_not_loaded"
        if (
            self._execution.get("mock_server_reachable")
            and self._execution.get("page_load_started")
            and not self._execution.get("page_load_completed")
            and not self._execution.get("page_load_error")
            and not self._execution.get("actual_page_url")
        ):
            self._execution["content_script_not_executed_reason"] = "page_navigation_not_called"
        return self._current_observation()

    def wait_for_page_load(self, action: dict) -> dict:
        self._ensure_context()
        timeout_ms = 10000
        if isinstance(action.get("input"), dict):
            try:
                timeout_ms = int(action.get("input", {}).get("timeout_ms", timeout_ms))
            except Exception:
                timeout_ms = 10000
        if self._page is None:
            self.open_mock_page(
                {
                    "action": "open_mock_page",
                    "target": self.preferred_target_url or self.mock_page_url,
                    "input": {"url": self.preferred_target_url or self.mock_page_url},
                }
            )
        if self._page is not None:
            if not self._execution.get("goto_called"):
                self._execution["wait_for_load_state_error"] = "page_not_initialized"
            else:
                try:
                    self._execution["wait_for_load_state_called"] = True
                    self._page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                    self._execution["wait_for_load_state_completed"] = True
                    self._execution["actual_page_url"] = self._page.url or self._execution.get("actual_page_url", "")
                    self._execution["page_load_completed"] = bool(self._execution.get("actual_page_url"))
                    self._execution["open_mock_page_succeeded"] = bool(self._execution.get("actual_page_url"))
                    if self._execution.get("actual_page_url"):
                        self._execution["page_load_error"] = ""
                except Exception as exc:
                    self._execution["wait_for_load_state_completed"] = False
                    self._execution["wait_for_load_state_error"] = str(exc)
                    self._execution["page_load_error"] = str(exc)
                    self._execution["page_load_completed"] = False
                    self._execution["open_mock_page_succeeded"] = False
        else:
            self._execution["wait_for_load_state_error"] = "page_not_initialized"
        return self._current_observation()

    def probe_content_script_execution(self, action: dict) -> dict:
        self._ensure_context()
        if self._page is None:
            self.open_mock_page({"action": "open_mock_page", "target": self.preferred_target_url or self.mock_page_url, "input": {"url": self.preferred_target_url or self.mock_page_url}})
        if not bool(self._execution.get("goto_called")):
            self._execution["content_script_probe_attempted"] = False
            self._execution["content_script_not_executed_reason"] = "page_navigation_not_called"
            return self._current_observation()
        if not bool(self._execution.get("page_load_completed")):
            self._execution["content_script_probe_attempted"] = False
            if self._execution.get("page_load_error"):
                self._execution["content_script_not_executed_reason"] = "page_not_loaded"
                return self._current_observation()
            elif self._execution.get("actual_page_url") == self._execution.get("expected_target_url"):
                # URL matches even though load state incomplete — allow probe to proceed
                self._execution["content_script_probe_attempted"] = True
                self._execution["content_script_probe_warning"] = "page_load_incomplete_but_actual_url_matches_target"
            elif not self._execution.get("actual_page_url"):
                self._execution["content_script_not_executed_reason"] = "page_navigation_result_missing"
                return self._current_observation()
            else:
                self._execution["content_script_not_executed_reason"] = "page_navigation_result_missing"
                return self._current_observation()
        if self._execution.get("content_script_not_executed_reason") in {"page_not_loaded", "page_navigation_not_called"}:
            return self._current_observation()
        self._execution["content_script_probe_attempted"] = True
        probe_start_ms = int(time.monotonic() * 1000)

        # Wait for DOM ready
        if self._page is not None:
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                pass

        # Sync actual_page_url and check files already observed from network events
        if self._page is not None:
            try:
                ready = self._page.evaluate("() => ({readyState: document.readyState, url: location.href})")
                if isinstance(ready, dict) and ready.get("url"):
                    self._execution["actual_page_url"] = str(ready.get("url") or self._execution.get("actual_page_url", ""))
            except Exception as exc:
                self._execution["content_script_probe_error"] = str(exc)[:200]
                self._notes.append(f"content_script_probe_initial_evaluate_failed: {str(exc)[:160]}")

        if self._execution.get("content_script_files_observed"):
            self._mark_content_script_observed("extension_script_request_probe")

        # Enhanced multi-probe: window markers, chrome.runtime.id, DOM marker, localStorage
        if self._page is not None and not self._execution.get("content_script_executed"):
            try:
                self._page.wait_for_timeout(800)
            except Exception:
                pass
            try:
                probe_result = self._page.evaluate(
                    """
                    () => {
                        const lsKeys = [];
                        try { for (let i = 0; i < localStorage.length; i++) lsKeys.push(localStorage.key(i)); } catch (_) {}
                        const winKeys = [];
                        try {
                            winKeys.push(...Object.keys(window).filter(
                                k => k.startsWith('__') || k.toLowerCase().includes('ext')
                            ).slice(0, 10));
                        } catch (_) {}
                        let chromeRuntimeId = null;
                        try {
                            chromeRuntimeId = (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.id)
                                ? String(chrome.runtime.id) : null;
                        } catch (_) {}
                        let domMarkerFound = false;
                        try {
                            const m = document.getElementById('__ext_probe_marker');
                            domMarkerFound = !!(m && (m.getAttribute('data-ext') || m.textContent.trim()));
                        } catch (_) {}
                        const hasExtProbe = !!(
                            window.__contentScriptExecuted
                            || window.__extProbeMarker
                            || window.__ext
                            || window.__EXT_INJECT
                            || window.__cs_loaded
                        );
                        return {
                            url: location.href,
                            readyState: document.readyState,
                            hasExtProbe,
                            chromeRuntimeId,
                            domMarkerFound,
                            localStorageLength: lsKeys.length,
                            localStorageKeys: lsKeys.slice(0, 20),
                            windowExtKeys: winKeys,
                        };
                    }
                    """
                )
                if isinstance(probe_result, dict):
                    actual_url = str(probe_result.get("url") or "")
                    if actual_url:
                        self._execution["actual_page_url"] = actual_url
                    dom_marker = bool(probe_result.get("domMarkerFound"))
                    self._execution["content_script_dom_marker_found"] = dom_marker
                    chrome_rt_id = probe_result.get("chromeRuntimeId")
                    if probe_result.get("hasExtProbe") or dom_marker or chrome_rt_id:
                        self._mark_content_script_observed("page_evaluate_window_probe")
            except Exception as exc:
                self._execution["content_script_probe_error"] = str(exc)[:200]
                self._notes.append(f"content_script_page_evaluate_probe_failed: {str(exc)[:160]}")

        # postMessage probe: inject a ping and wait briefly for response
        if self._page is not None and not self._execution.get("content_script_executed"):
            try:
                pm_result = self._page.evaluate(
                    """
                    () => new Promise(resolve => {
                        const result = {responded: false};
                        const handler = (e) => {
                            if (e.data && (e.data.__ext_pong || e.data.type === '__ext_pong')) {
                                result.responded = true;
                                window.removeEventListener('message', handler);
                            }
                        };
                        window.addEventListener('message', handler);
                        window.postMessage({type: '__ext_probe_ping', ts: Date.now()}, '*');
                        setTimeout(() => resolve(result), 600);
                    })
                    """
                )
                if isinstance(pm_result, dict) and pm_result.get("responded"):
                    self._mark_content_script_observed("postmessage_pong_probe")
            except Exception:
                pass

        # CDP isolated world detection — observe Runtime.executionContextCreated
        if self._page is not None and not self._execution.get("content_script_executed"):
            try:
                cdp = self._context.new_cdp_session(self._page)
                isolated_worlds: list[dict] = []

                def _on_ctx_created(params: dict) -> None:
                    ctx = params.get("context", {}) if isinstance(params, dict) else {}
                    ctx_type = str(ctx.get("type", "") or "")
                    ctx_name = str(ctx.get("name", "") or "")
                    ctx_origin = str(ctx.get("origin", "") or "")
                    ext_id = str(self._execution.get("extension_id", "") or "")
                    is_isolated = ctx_type == "isolated" or (
                        ext_id and (ext_id in ctx_origin or ext_id in ctx_name)
                    ) or "extension" in ctx_origin.lower()
                    if is_isolated:
                        isolated_worlds.append({
                            "id": ctx.get("id"),
                            "name": ctx_name,
                            "origin": ctx_origin,
                            "type": ctx_type,
                        })

                cdp.on("Runtime.executionContextCreated", _on_ctx_created)
                cdp.send("Runtime.enable")
                try:
                    self._page.wait_for_timeout(800)
                except Exception:
                    pass
                cdp.detach()
                if isolated_worlds:
                    self._execution["isolated_world_context_seen"] = True
                    self._execution["isolated_world_contexts"] = isolated_worlds[:5]
                    self._execution["content_script_isolated_world_detected"] = True
                    self._mark_content_script_observed("cdp_isolated_world")
            except Exception as cdp_exc:
                self._notes.append(f"cdp_isolated_world_probe_failed: {str(cdp_exc)[:160]}")

        # Injection eligibility check against actual page URL
        actual_url_for_check = str(self._execution.get("actual_page_url") or self._execution.get("expected_target_url") or "")
        if actual_url_for_check:
            eligible, block_reason = self._check_injection_eligibility(actual_url_for_check)
            self._execution["manifest_injection_eligible"] = eligible
            self._execution["manifest_injection_block_reason"] = block_reason
            actual_matched, _ = self._manifest_match_target(actual_url_for_check)
            self._execution["manifest_match_expected_url"] = bool(actual_matched)

        self._execution["content_script_probe_timeout_ms"] = int(time.monotonic() * 1000) - probe_start_ms
        self._execution["content_script_probe_method"] = "network_script_request_and_page_probe"

        # Classify failure reason with accurate context
        if not self._execution.get("content_script_executed"):
            if self._execution.get("content_script_not_executed_reason") == "content_script_runtime_error":
                pass  # already set by page error handler
            elif not self._execution.get("goto_called"):
                self._execution["content_script_not_executed_reason"] = "page_navigation_not_called"
            elif self._execution.get("page_load_error"):
                self._execution["content_script_not_executed_reason"] = "page_not_loaded"
            elif not self._execution.get("actual_page_url") and not self._execution.get("page_load_completed"):
                self._execution["content_script_not_executed_reason"] = "page_navigation_result_missing"
            elif not self._execution.get("manifest_match_actual_page_url", self._execution.get("manifest_match_target_url")):
                self._execution["content_script_not_executed_reason"] = "manifest_mismatch"
                actual_url_now = str(self._execution.get("actual_page_url", "") or "")
                expected_url_now = str(self._execution.get("expected_target_url", "") or "")
                if actual_url_now and actual_url_now != expected_url_now:
                    self._execution["manifest_mismatch_reason"] = (
                        f"actual_page_url ({actual_url_now}) does not match manifest patterns; "
                        f"expected ({expected_url_now})"
                    )
                else:
                    self._execution["manifest_mismatch_reason"] = str(
                        self._execution.get("manifest_match_error", "") or "page_url_not_matched_by_manifest_patterns"
                    )
            elif not self._execution.get("manifest_injection_eligible", True) and self._execution.get("manifest_injection_block_reason"):
                block = self._execution["manifest_injection_block_reason"]
                if "file_missing" in block:
                    self._execution["content_script_not_executed_reason"] = "content_script_file_missing"
                else:
                    self._execution["content_script_not_executed_reason"] = "manifest_mismatch"
                    self._execution["manifest_mismatch_reason"] = block
            else:
                # Check file existence
                file_checks = self._execution.get("content_script_file_checks", [])
                if file_checks and not all(c.get("exists") for c in file_checks):
                    self._execution["content_script_not_executed_reason"] = "content_script_file_missing"
                    self._execution["content_script_probe_error"] = "content script file missing from extension"
                elif not self._execution.get("content_script_request_seen"):
                    # No chrome-extension:// script request observed
                    self._execution["content_script_not_executed_reason"] = "content_script_not_requested"
                else:
                    self._execution["content_script_not_executed_reason"] = "no_probe_response"
        return self._current_observation()

    def simulate_dom_input_events(self, action: dict) -> dict:
        self._ensure_context()
        if self._page is None:
            self.open_mock_page({"action": "open_mock_page", "target": self.preferred_target_url or self.mock_page_url, "input": {"url": self.preferred_target_url or self.mock_page_url}})
        if self._page is not None:
            try:
                result = self._page.evaluate(
                    """
                    () => {
                      const nodes = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]'));
                      const touched = [];
                      for (const node of nodes) {
                        const name = node.getAttribute('name') || node.id || node.tagName.toLowerCase();
                        if (node.type === 'password' || name.toLowerCase().includes('pass')) {
                          if ('value' in node) node.value = 'DUMMY_AUTH_VALUE';
                        } else {
                          if ('value' in node) node.value = 'DUMMY_SESSION_VALUE';
                          else node.textContent = 'DUMMY_SESSION_VALUE';
                        }
                        node.dispatchEvent(new Event('input', { bubbles: true }));
                        node.dispatchEvent(new Event('change', { bubbles: true }));
                        touched.push(name);
                      }
                      return { count: touched.length, fields: touched.slice(0, 20) };
                    }
                    """
                )
                count = int(result.get("count", 0) or 0) if isinstance(result, dict) else 0
                self._dom_events.append(
                    {
                        "event": "input_change_simulated",
                        "target_count": count,
                        "fields": result.get("fields", []) if isinstance(result, dict) and isinstance(result.get("fields", []), list) else [],
                    }
                )
            except Exception as exc:
                self._dom_events.append({"event": "input_change_simulation_failed", "error": str(exc)})
            # Dispatch form submit and button click to trigger content script listeners
            try:
                submit_result = self._page.evaluate(
                    """
                    () => {
                      const form = document.querySelector('form');
                      if (form) {
                        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
                      }
                      const btn = document.querySelector('button[type=submit], button');
                      if (btn) btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                      return { form_found: !!form, btn_found: !!btn };
                    }
                    """
                )
                if isinstance(submit_result, dict):
                    self._dom_events.append(
                        {
                            "event": "form_submit_simulated",
                            "form_found": bool(submit_result.get("form_found")),
                            "btn_found": bool(submit_result.get("btn_found")),
                        }
                    )
            except Exception as exc:
                self._dom_events.append({"event": "form_submit_simulation_failed", "error": str(exc)})
            # Brief pause to let content script react to events
            try:
                self._page.wait_for_timeout(500)
            except Exception:
                pass
        return self._current_observation()

    def seed_extension_uuid(self, action: dict) -> dict:
        self._ensure_context()
        self._attempt_seed_extension_uuid()
        return self._current_observation()

    def wait_for_extension_service_worker(self, action: dict) -> dict:
        self._ensure_context()
        timeout_ms = int(os.getenv("SERVICE_WORKER_TIMEOUT_MS", str(DEFAULT_SERVICE_WORKER_TIMEOUT_MS)))
        self._execution["service_worker_wait_timeout_ms"] = timeout_ms
        if isinstance(action.get("input"), dict):
            try:
                timeout_ms = int(action.get("input", {}).get("timeout_ms", 5000))
            except Exception:
                timeout_ms = 5000
        self._wait_for_service_worker(timeout_ms=timeout_ms)
        return self._current_observation()

    def prepare_target_routes(self, action: dict) -> dict:
        self._ensure_context()
        self._register_intercept_routes()
        return self._current_observation()

    def seed_target_local_storage_before_goto(self, action: dict) -> dict:
        self._ensure_context()
        self._install_target_seed_init_script()
        return self._current_observation()

    def seed_dummy_local_storage(self, action: dict) -> dict:
        self._ensure_context()
        if self._page is None and self._context is not None:
            self.open_mock_page({"action": "open_mock_page", "target": self.mock_page_url, "input": {}})

        if self._page is not None:
            self._page.evaluate(
                """
                () => {
                    localStorage.setItem('dummy_session', 'DUMMY_SESSION_VALUE');
                    localStorage.setItem('dummy_auth', 'DUMMY_AUTH_VALUE');
                    localStorage.setItem('dummy_user_id', 'DUMMY_USER_ID');
                }
                """
            )
            self._storage_events.append(
                {
                    "storage_area": "localStorage",
                    "operation": "write",
                    "keywords": ["session", "auth", "user_id"],
                }
            )
            try:
                self._page.reload(wait_until="domcontentloaded")
            except Exception:
                try:
                    self._page.goto(self.mock_page_url)
                except Exception:
                    self._page.set_content(build_mock_page_html())
            self._execution["document_start_observed"] = True
        return self._current_observation()

    def wait(self, action: dict) -> dict:
        ms = 1000
        if isinstance(action.get("input"), dict):
            try:
                ms = int(action["input"].get("ms", 1000))
            except Exception:
                ms = 1000
        if self._page is not None:
            self._page.wait_for_timeout(ms)
        else:
            time.sleep(ms / 1000.0)
        return self._current_observation()

    def collect_network_requests(self, action: dict) -> dict:
        return self._current_observation()

    def collect_runtime_messages(self, action: dict) -> dict:
        return self._current_observation()

    def collect_storage_events(self, action: dict) -> dict:
        return self._current_observation()

    def collect_timer_events(self, action: dict) -> dict:
        return self._current_observation()

    def click_extension_action(self, action: dict) -> dict:
        return self._current_observation()

    def submit_mock_form(self, action: dict) -> dict:
        if self._page is not None:
            try:
                self._page.click("form button[type=submit], button[type=submit]", timeout=500)
            except Exception:
                pass
        return self._current_observation()

    def collect_dom_events(self, action: dict) -> dict:
        return self._current_observation()

    def cleanup_harness(self, action: dict) -> dict:
        return self.close()

    def execute_action(self, action: dict) -> dict:
        name = action.get("action") if isinstance(action, dict) else None
        if not isinstance(name, str):
            return self._current_observation()
        fn = getattr(self, name, None)
        if callable(fn):
            return fn(action)
        return self._current_observation()

    def close(self) -> dict:
        self._execution["cleanup_started"] = True
        cleanup_errors: list[str] = []
        try:
            if self._page is not None:
                try:
                    self._page.close()
                except Exception as exc:
                    cleanup_errors.append(f"page_close_failed:{exc}")
            if self._context is not None:
                try:
                    self._context.close()
                    self._execution["cleanup_closed_context"] = True
                except Exception as exc:
                    cleanup_errors.append(f"context_close_failed:{exc}")
                    self._execution["cleanup_closed_context"] = False
            if self._pw is not None:
                try:
                    self._pw.stop()
                    self._execution["cleanup_stopped_playwright"] = True
                except Exception as exc:
                    cleanup_errors.append(f"playwright_stop_failed:{exc}")
                    self._execution["cleanup_stopped_playwright"] = False
            if self._mock_server is not None:
                try:
                    self._mock_server.shutdown()
                    self._mock_server.server_close()
                    self._execution["mock_server_stopped"] = True
                    self._execution["mock_server_stop_error"] = ""
                except Exception as exc:
                    self._execution["mock_server_stopped"] = False
                    self._execution["mock_server_stop_error"] = str(exc)
                    cleanup_errors.append(f"mock_server_stop_failed:{exc}")
                finally:
                    self._mock_server = None
                    self._mock_server_thread = None
            elif self._execution.get("mock_server_autostarted"):
                self._execution["mock_server_stopped"] = True
        finally:
            self._page = None
            self._context = None
            self._pw = None

        had_user_data_tmp = any("pw_ud_" in str(d) for d in self._tmp_dirs)
        had_unpacked_tmp = any("ext_unzip_" in str(d) for d in self._tmp_dirs)
        for d in list(self._tmp_dirs):
            try:
                shutil.rmtree(d, ignore_errors=True)
                if "pw_ud_" in str(d):
                    self._execution["cleanup_removed_user_data_dir"] = True
                if "ext_unzip_" in str(d):
                    self._execution["cleanup_removed_unpacked_dir"] = True
            except Exception as exc:
                cleanup_errors.append(f"remove_temp_dir_failed:{exc}")
        self._tmp_dirs.clear()
        # The unpacked extension dir was just removed above; drop the cached root so the
        # next _ensure_context re-extracts from the zip instead of pointing at a deleted
        # path (which would surface as manifest_not_found on every scenario after the first).
        self._extension_root = None
        if not had_user_data_tmp:
            self._execution["cleanup_removed_user_data_dir_not_applicable"] = True
        if not had_unpacked_tmp:
            self._execution["cleanup_removed_unpacked_dir_not_applicable"] = True
        self._execution["cleanup_completed"] = len(cleanup_errors) == 0
        self._execution["cleanup_error"] = ",".join(cleanup_errors)
        return self._current_observation()
