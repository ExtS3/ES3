import re
from pathlib import Path
from typing import Any

from .utils import read_text_safe

SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"']", re.I)
INLINE_SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.I | re.S)


def scan_html(path: Path) -> dict[str, Any]:
    text = read_text_safe(path)
    if text is None:
        return {"file": str(path), "scripts": [], "inline_scripts": []}
    scripts = SCRIPT_SRC_RE.findall(text)
    inline = [s.strip() for s in INLINE_SCRIPT_RE.findall(text) if s.strip()]
    return {"file": str(path), "scripts": scripts, "inline_scripts": inline}
