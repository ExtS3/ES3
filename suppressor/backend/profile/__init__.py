"""Extension Profile: objective, version-by-version change history of an extension.

Records what an extension *is* and how it changes between versions (manifest
facts, file hashes/sizes, diffs) — not analysis output. See ``builder`` for the
JSON generator.
"""

from .builder import (
    build_profile,
    build_snapshot,
    compute_diff,
    content_hash,
    is_minified,
    make_unified_diff,
    validate_profile,
)

__all__ = [
    "build_profile",
    "build_snapshot",
    "compute_diff",
    "content_hash",
    "is_minified",
    "make_unified_diff",
    "validate_profile",
]
