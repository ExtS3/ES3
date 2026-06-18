"""Extension Profile JSON generator.

An Extension Profile records the *objective* state of a browser extension per
version and the diff against the previous version. It is deliberately NOT an
analysis-result store: scanner findings, embeddings, fingerprints, obfuscation
scores, capability inference and risk rationale are excluded. The only thing
borrowed from analysis is a thin ``verdict`` breadcrumb (risk_grade + result_id)
so a reader knows where to find the full result.

Public API (the JSON-generation core):
    build_snapshot   - extension archive/dir -> objective snapshot (+ file bytes)
    content_hash     - stable hash over the file (path, sha256) set
    is_minified      - heuristic: is this file undiffable / minified?
    make_unified_diff- unified diff text (+ truncation flag) for two texts
    compute_diff     - snapshot vs snapshot -> permission/manifest/file diff
    build_profile    - assemble/extend a profile document from a snapshot
    validate_profile - jsonschema validation against extension-profile.schema.json

Blob storage (Nexus) and DB persistence are out of scope here. Fetching previous
file bytes for inline diffs is delegated to a pluggable ``blob_loader`` callable;
without it, modified files fall back to pointer-only (blob_ref, diff=null).
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

SCHEMA_VERSION = "1.0"

# Inline-diff guard rails: a single modified file should not blow up the profile.
MAX_DIFF_LINES = 2000
MAX_DIFF_BYTES = 200_000

# Minified / undiffable heuristics.
_MINIFIED_LONGEST_LINE = 5000
_MINIFIED_AVG_LINE = 500
_MINIFIED_DENSE_AVG = 1000
_MINIFIED_DENSE_MAX_LINES = 5

BlobLoader = Callable[[str], Optional[bytes]]
Snapshot = Dict[str, Any]
Profile = Dict[str, Any]

_SCHEMA_CACHE: Optional[Dict[str, Any]] = None


# --------------------------------------------------------------------------- #
# hashing / small helpers
# --------------------------------------------------------------------------- #
def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sorted_unique(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    return sorted({str(v) for v in values})


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


# --------------------------------------------------------------------------- #
# content hash
# --------------------------------------------------------------------------- #
def content_hash(files: List[Dict[str, Any]]) -> str:
    """Stable hash of the file set, keyed by ``'<path>:<sha256>'`` entries.

    Order-independent: entries are sorted before hashing, so two extractions of
    the same files always produce the same content_hash.
    """
    entries = sorted(f"{f['path']}:{f['sha256']}" for f in files)
    joined = "\n".join(entries)
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# minified detection
# --------------------------------------------------------------------------- #
def is_minified(data: Optional[bytes]) -> bool:
    """Heuristic for "we cannot show a useful line diff of this file".

    True when the bytes do not decode as UTF-8, or when any of the line-shape
    thresholds in the design spec are met.
    """
    if data is None:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return True

    lines = text.splitlines() or [text]
    line_count = len(lines)
    longest = max((len(line) for line in lines), default=0)
    total_len = len(text)
    avg = total_len / line_count if line_count else float(total_len)

    if longest > _MINIFIED_LONGEST_LINE:
        return True
    if avg > _MINIFIED_AVG_LINE:
        return True
    if line_count < _MINIFIED_DENSE_MAX_LINES and avg > _MINIFIED_DENSE_AVG:
        return True
    return False


# --------------------------------------------------------------------------- #
# unified diff
# --------------------------------------------------------------------------- #
def make_unified_diff(
    old_text: str,
    new_text: str,
    path: str,
    *,
    max_lines: int = MAX_DIFF_LINES,
    max_bytes: int = MAX_DIFF_BYTES,
) -> Tuple[str, bool]:
    """Return ``(unified_diff_text, truncated)`` for two text blobs.

    Truncation keeps the profile bounded for large but technically-diffable files.
    """
    import difflib

    diff_iter = difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )

    out: List[str] = []
    truncated = False
    total = 0
    for i, line in enumerate(diff_iter):
        if i >= max_lines or total >= max_bytes:
            truncated = True
            break
        out.append(line)
        total += len(line) + 1
    return "\n".join(out), truncated


# --------------------------------------------------------------------------- #
# manifest normalization
# --------------------------------------------------------------------------- #
def _is_host_pattern(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value == "<all_urls>" or "://" in value


def normalize_manifest_state(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the objective, comparable fields out of a manifest.

    For MV2 the host match patterns live inside ``permissions`` (and
    ``optional_permissions``); we split them out into ``host_permissions`` so
    permission diffs compare API permissions and host grants separately, exactly
    like MV3.
    """
    manifest = manifest if isinstance(manifest, dict) else {}
    mv = manifest.get("manifest_version")

    permissions = list(manifest.get("permissions") or [])
    optional = list(manifest.get("optional_permissions") or [])
    host_perms = list(manifest.get("host_permissions") or [])

    if mv == 2:
        host_perms += [p for p in permissions if _is_host_pattern(p)]
        host_perms += [p for p in optional if _is_host_pattern(p)]
        permissions = [p for p in permissions if not _is_host_pattern(p)]
        optional = [p for p in optional if not _is_host_pattern(p)]

    return {
        "manifest_version": mv if isinstance(mv, int) else None,
        "permissions": _sorted_unique(permissions),
        "optional_permissions": _sorted_unique(optional),
        "host_permissions": _sorted_unique(host_perms),
        "content_scripts": manifest.get("content_scripts"),
        "background": manifest.get("background"),
        "content_security_policy": manifest.get("content_security_policy"),
        "web_accessible_resources": manifest.get("web_accessible_resources"),
    }


# --------------------------------------------------------------------------- #
# reading an extension (zip or directory)
# --------------------------------------------------------------------------- #
def _read_files(source: Union[str, Path]) -> List[Tuple[str, bytes]]:
    path = Path(source)
    files: List[Tuple[str, bytes]] = []

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                files.append((_norm_path(info.filename), zf.read(info)))
    elif path.is_dir():
        for fp in sorted(path.rglob("*")):
            if fp.is_file():
                files.append((_norm_path(fp.relative_to(path).as_posix()), fp.read_bytes()))
    else:
        raise ValueError(f"not a zip archive or directory: {source}")

    return files


def _extract_manifest_and_reroot(
    files: List[Tuple[str, bytes]],
) -> Tuple[Dict[str, Any], List[Tuple[str, bytes]]]:
    """Locate manifest.json and re-root every path relative to its directory.

    Handles archives that wrap the extension in a top-level folder.
    """
    candidates = [f for f in files if f[0].rsplit("/", 1)[-1] == "manifest.json"]
    if not candidates:
        raise ValueError("manifest.json not found in extension")

    manifest_path, manifest_bytes = min(candidates, key=lambda f: f[0].count("/"))
    manifest = json.loads(manifest_bytes.decode("utf-8"))

    root = manifest_path.rsplit("/", 1)[0] + "/" if "/" in manifest_path else ""
    rerooted: List[Tuple[str, bytes]] = []
    for path, data in files:
        if root and not path.startswith(root):
            continue
        rerooted.append((path[len(root):], data))
    return manifest, rerooted


# --------------------------------------------------------------------------- #
# snapshot
# --------------------------------------------------------------------------- #
def _normalize_verdict(verdict: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "risk_grade": verdict.get("risk_grade"),
        "result_id": verdict.get("result_id"),
        "analyzed_at": verdict.get("analyzed_at"),
    }


def build_snapshot(
    source: Union[str, Path],
    *,
    verdict: Optional[Dict[str, Any]] = None,
    captured_at: Optional[str] = None,
) -> Tuple[Snapshot, Dict[str, bytes]]:
    """Build an objective snapshot from an extension archive or extracted dir.

    Returns ``(snapshot, file_bytes)``. ``file_bytes`` maps path -> raw bytes for
    the *current* version; pass it to :func:`compute_diff` (and/or upload it to
    the blob store) so the next version can produce inline diffs.
    """
    raw_files = _read_files(source)
    manifest, files = _extract_manifest_and_reroot(raw_files)

    file_entries: List[Dict[str, Any]] = []
    file_bytes: Dict[str, bytes] = {}
    for path, data in files:
        file_entries.append({"path": path, "sha256": _sha256_bytes(data), "size": len(data)})
        file_bytes[path] = data
    file_entries.sort(key=lambda e: e["path"])

    snapshot: Snapshot = {
        "version": str(manifest.get("version", "")),
        "captured_at": captured_at or _now_iso(),
        "content_hash": content_hash(file_entries),
        **normalize_manifest_state(manifest),
        "files": file_entries,
    }
    if verdict is not None:
        snapshot["verdict"] = _normalize_verdict(verdict)

    return snapshot, file_bytes


# --------------------------------------------------------------------------- #
# diff
# --------------------------------------------------------------------------- #
def _string_set_delta(prev: Any, curr: Any) -> Dict[str, List[str]]:
    prev_set = set(prev or [])
    curr_set = set(curr or [])
    return {
        "added": sorted(curr_set - prev_set),
        "removed": sorted(prev_set - curr_set),
    }


_MANIFEST_DIFF_FIELDS = (
    "manifest_version",
    "content_scripts",
    "content_security_policy",
    "web_accessible_resources",
)


def _manifest_changes(prev: Snapshot, curr: Snapshot) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    for field in _MANIFEST_DIFF_FIELDS:
        before, after = prev.get(field), curr.get(field)
        if before != after:
            changes.append({"field": field, "from": before, "to": after})

    # background gets sub-field granularity (e.g. background.service_worker).
    prev_bg = prev.get("background") or {}
    curr_bg = curr.get("background") or {}
    if isinstance(prev_bg, dict) and isinstance(curr_bg, dict):
        for key in sorted(set(prev_bg) | set(curr_bg)):
            if prev_bg.get(key) != curr_bg.get(key):
                changes.append({
                    "field": f"background.{key}",
                    "from": prev_bg.get(key),
                    "to": curr_bg.get(key),
                })
    elif prev_bg != curr_bg:
        changes.append({"field": "background", "from": prev.get("background"), "to": curr.get("background")})

    return changes


def _build_modified_entry(
    path: str,
    from_sha: str,
    to_sha: str,
    curr_file_bytes: Optional[Dict[str, bytes]],
    blob_loader: Optional[BlobLoader],
    max_diff_lines: int,
    max_diff_bytes: int,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "path": path,
        "from_sha256": from_sha,
        "to_sha256": to_sha,
        "blob_ref": {"from": f"nexus://blobs/{from_sha}", "to": f"nexus://blobs/{to_sha}"},
        "diff_format": "unified",
        "diff": None,
        "diff_truncated": False,
        "is_minified": False,
    }

    old_bytes = blob_loader(from_sha) if blob_loader else None
    new_bytes = curr_file_bytes.get(path) if curr_file_bytes else None

    # Pointer-only when we can't see both sides (no blob upload / no current bytes).
    if old_bytes is None or new_bytes is None:
        return entry

    if is_minified(old_bytes) or is_minified(new_bytes):
        entry["is_minified"] = True
        return entry  # diff stays null; blob_ref carries the pointers

    diff_text, truncated = make_unified_diff(
        old_bytes.decode("utf-8"),
        new_bytes.decode("utf-8"),
        path,
        max_lines=max_diff_lines,
        max_bytes=max_diff_bytes,
    )
    entry["diff"] = diff_text
    entry["diff_truncated"] = truncated
    return entry


def _file_diff(
    prev: Snapshot,
    curr: Snapshot,
    curr_file_bytes: Optional[Dict[str, bytes]],
    blob_loader: Optional[BlobLoader],
    max_diff_lines: int,
    max_diff_bytes: int,
) -> Dict[str, Any]:
    prev_by_path = {f["path"]: f for f in prev.get("files", [])}
    curr_by_path = {f["path"]: f for f in curr.get("files", [])}
    prev_paths = set(prev_by_path)
    curr_paths = set(curr_by_path)

    modified: List[Dict[str, Any]] = []
    for path in sorted(prev_paths & curr_paths):
        from_sha = prev_by_path[path]["sha256"]
        to_sha = curr_by_path[path]["sha256"]
        if from_sha == to_sha:
            continue
        modified.append(_build_modified_entry(
            path, from_sha, to_sha, curr_file_bytes, blob_loader,
            max_diff_lines, max_diff_bytes,
        ))

    return {
        "added": sorted(curr_paths - prev_paths),
        "removed": sorted(prev_paths - curr_paths),
        "modified": modified,
    }


def compute_diff(
    prev_snapshot: Snapshot,
    curr_snapshot: Snapshot,
    *,
    curr_file_bytes: Optional[Dict[str, bytes]] = None,
    blob_loader: Optional[BlobLoader] = None,
    max_diff_lines: int = MAX_DIFF_LINES,
    max_diff_bytes: int = MAX_DIFF_BYTES,
) -> Dict[str, Any]:
    """Diff two snapshots: permission deltas, manifest changes, file changes.

    Inline file diffs need both sides' bytes: the current version comes from
    ``curr_file_bytes`` and the previous version from ``blob_loader(sha256)``.
    When either is unavailable for a file, that file degrades to pointer-only
    (``blob_ref`` set, ``diff=null``). Minified files are pointer-only by design.
    """
    return {
        "previous_version": prev_snapshot.get("version"),
        "permissions": _string_set_delta(prev_snapshot.get("permissions"), curr_snapshot.get("permissions")),
        "optional_permissions": _string_set_delta(
            prev_snapshot.get("optional_permissions"), curr_snapshot.get("optional_permissions")
        ),
        "host_permissions": _string_set_delta(
            prev_snapshot.get("host_permissions"), curr_snapshot.get("host_permissions")
        ),
        "manifest_changes": _manifest_changes(prev_snapshot, curr_snapshot),
        "files": _file_diff(
            prev_snapshot, curr_snapshot, curr_file_bytes, blob_loader,
            max_diff_lines, max_diff_bytes,
        ),
    }


# --------------------------------------------------------------------------- #
# profile assembly
# --------------------------------------------------------------------------- #
def build_profile(
    curr_snapshot: Snapshot,
    prev_profile: Optional[Profile] = None,
    *,
    ext_id: Optional[str] = None,
    browser: str = "chrome",
    ext_name: Optional[str] = None,
    publisher: Optional[str] = None,
    curr_file_bytes: Optional[Dict[str, bytes]] = None,
    blob_loader: Optional[BlobLoader] = None,
) -> Profile:
    """Create a new profile or append ``curr_snapshot`` to an existing one.

    On the first version (``prev_profile is None``) the snapshot's
    ``diff_from_previous`` is ``null`` and ``ext_id`` must be supplied. On later
    versions the diff against the latest stored snapshot is attached and
    ``ext_id``/identity carry over from ``prev_profile``.
    """
    if prev_profile is None:
        if not ext_id:
            raise ValueError("ext_id is required when creating a new profile")
        first_snapshot = {**curr_snapshot, "diff_from_previous": None}
        return {
            "schema_version": SCHEMA_VERSION,
            "ext_id": ext_id,
            "browser": browser,
            "ext_name": ext_name,
            "publisher": publisher,
            "first_seen": first_snapshot["captured_at"],
            "last_updated": first_snapshot["captured_at"],
            "latest_version": first_snapshot["version"],
            "snapshots": [first_snapshot],
        }

    prev_snapshots = prev_profile.get("snapshots") or []
    if not prev_snapshots:
        raise ValueError("prev_profile has no snapshots to diff against")
    prev_snapshot = prev_snapshots[-1]

    diff = compute_diff(
        prev_snapshot, curr_snapshot,
        curr_file_bytes=curr_file_bytes, blob_loader=blob_loader,
    )
    new_snapshot = {**curr_snapshot, "diff_from_previous": diff}

    profile = dict(prev_profile)
    profile["snapshots"] = list(prev_snapshots) + [new_snapshot]
    profile["last_updated"] = new_snapshot["captured_at"]
    profile["latest_version"] = new_snapshot["version"]
    if ext_name is not None:
        profile["ext_name"] = ext_name
    if publisher is not None:
        profile["publisher"] = publisher
    return profile


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _load_schema() -> Dict[str, Any]:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        schema_path = Path(__file__).with_name("extension-profile.schema.json")
        _SCHEMA_CACHE = json.loads(schema_path.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE


def validate_profile(profile: Dict[str, Any]) -> List[str]:
    """Validate a profile against the schema. Returns a list of error strings;
    an empty list means the profile is valid."""
    import jsonschema

    schema = _load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(profile), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
