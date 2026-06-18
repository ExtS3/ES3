from __future__ import annotations

from pathlib import Path

from .config import SCENARIO_DOC_BASE_DIR


def load_scenario_doc(doc_ref: str, base_dir: str = SCENARIO_DOC_BASE_DIR) -> str:
    base_path = Path(base_dir).resolve()
    raw_ref = str(doc_ref or "").strip().replace("\\", "/")
    ref = raw_ref
    if ref.startswith("scenario_docs/"):
        stripped = ref[len("scenario_docs/") :]
        stripped_path = (base_path / stripped).resolve()
        original_path = (base_path / raw_ref).resolve()
        ref = stripped if stripped_path.is_file() else raw_ref
    target_path = (base_path / ref).resolve()

    try:
        target_path.relative_to(base_path)
    except ValueError as exc:
        raise ValueError(f"Path traversal blocked for doc_ref: {doc_ref}") from exc

    if not target_path.is_file():
        raise FileNotFoundError(f"Scenario document not found: {target_path}")

    return target_path.read_text(encoding="utf-8")

