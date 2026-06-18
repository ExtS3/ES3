import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXCLUDED_DIRS = {"node_modules", ".git", "dist", "build", "coverage", "out"}
DEFAULT_MAX_FILE_SIZE = 2 * 1024 * 1024


class FingerprintError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(prune_empty(data), f, ensure_ascii=False, indent=2)


def read_text_safe(path: Path, max_bytes: int = DEFAULT_MAX_FILE_SIZE) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    if path.stat().st_size > max_bytes:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def iter_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in suffixes:
                out.append(p)
    return sorted(out)


def stable_json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint_hash(data: Any) -> str:
    return hashlib.sha256(stable_json_dumps(data).encode("utf-8")).hexdigest()


def dedup_sorted(items: list[str]) -> list[str]:
    return sorted(set(i for i in items if i))


def prune_empty(obj: Any) -> Any:
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            pv = prune_empty(v)
            if pv in (None, "", [], {}):
                continue
            if pv is False:
                continue
            new[k] = pv
        return new
    if isinstance(obj, list):
        out = [prune_empty(i) for i in obj]
        out = [i for i in out if i not in (None, "", [], {}, False)]
        return out
    return obj
