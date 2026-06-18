"""Local filesystem store for Extension Profiles.

A stand-in for the eventual Supabase + Nexus backend so the profile step can run
end-to-end without external services. Layout under ``PROFILE_STORE_DIR``::

    profiles/<ext_id>.json    one accumulating profile document per extension
    blobs/<sha256>            raw file bytes, content-addressed (dedup)

The blob directory lets the *next* version produce inline diffs: each scan stores
the current version's file bytes here, and ``make_blob_loader`` reads previous
versions back by sha256. Swap this module out for Nexus/Supabase later without
touching ``builder``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable, Dict, Optional


def _store_dir() -> Path:
    return Path(os.getenv("PROFILE_STORE_DIR", "./profiles"))


def _profiles_dir() -> Path:
    return _store_dir() / "profiles"


def _blobs_dir() -> Path:
    return _store_dir() / "blobs"


def _safe_name(ext_id: str) -> str:
    """Filesystem-safe filename for an ext_id (which may contain spaces/unicode)."""
    cleaned = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in ext_id.strip())
    return cleaned or "_unknown"


def load_profile(ext_id: str) -> Optional[dict]:
    path = _profiles_dir() / f"{_safe_name(ext_id)}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_profile(ext_id: str, profile: dict) -> Path:
    directory = _profiles_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_name(ext_id)}.json"
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def store_blobs(file_bytes: Dict[str, bytes]) -> int:
    """Content-address every file's bytes into the blob dir. Returns count newly written."""
    directory = _blobs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    written = 0
    for data in file_bytes.values():
        sha = hashlib.sha256(data).hexdigest()
        blob_path = directory / sha
        if not blob_path.exists():
            blob_path.write_bytes(data)
            written += 1
    return written


def make_blob_loader() -> Callable[[str], Optional[bytes]]:
    directory = _blobs_dir()

    def _loader(sha256: str) -> Optional[bytes]:
        blob_path = directory / sha256
        return blob_path.read_bytes() if blob_path.exists() else None

    return _loader
