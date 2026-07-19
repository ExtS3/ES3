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


def parse_expected_api(scenario_doc: str) -> list[str]:
    """Extract the ``expected_api`` list from a scenario doc's YAML frontmatter.

    Minimal, dependency-free parser: reads only the leading ``---`` ... ``---`` block
    and the ``expected_api:`` list within it. Returns [] when absent or malformed, so
    docs without frontmatter keep scoring on the generic path (backward compatible).
    """
    text = str(scenario_doc or "")
    if not text.lstrip().startswith("---"):
        return []
    body = text.lstrip()
    end = body.find("\n---", 3)
    if end == -1:
        return []
    front = body[3:end]
    apis: list[str] = []
    in_block = False
    for line in front.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped.startswith("expected_api:"):
            inline = stripped[len("expected_api:"):].strip()
            if inline.startswith("[") and inline.endswith("]"):
                items = inline[1:-1].split(",")
                apis.extend(i.strip().strip("'\"") for i in items if i.strip())
                return [a for a in apis if a]
            in_block = True
            continue
        if in_block:
            if stripped.startswith("- "):
                apis.append(stripped[2:].strip().strip("'\""))
            else:
                break
    return [a for a in apis if a]


def collect_expected_apis_from_docs(base_dir: str = SCENARIO_DOC_BASE_DIR) -> list[str]:
    """Union of ``expected_api`` across every scenario doc.

    This is the single source of truth for the set of privileged APIs the system
    observes: the harness wraps exactly these (see PlaywrightDynamicHarness), so adding
    an API to any scenario doc's frontmatter is all it takes to start observing it — no
    code change. Scan-invariant, so callers can gather it once.
    """
    docs_dir = Path(base_dir).resolve() / "scenario_docs"
    apis: set[str] = set()
    if docs_dir.is_dir():
        for md in sorted(docs_dir.glob("*.md")):
            try:
                apis.update(parse_expected_api(md.read_text(encoding="utf-8")))
            except Exception:
                continue
    return sorted(apis)

