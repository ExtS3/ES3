"""Extension Profile JSON 생성기 단위 테스트."""

import io
import json
import zipfile

import pytest

from profile.builder import (
    build_profile,
    build_snapshot,
    compute_diff,
    content_hash,
    is_minified,
    make_unified_diff,
    normalize_manifest_state,
    validate_profile,
)


# --------------------------------------------------------------------------- #
# fixtures: build chrome extension zips on the fly
# --------------------------------------------------------------------------- #
def _make_zip(tmp_path, name, manifest, files, top_dir=None):
    """Write a .zip extension. ``files`` maps path -> str|bytes content."""
    path = tmp_path / name
    buf = io.BytesIO()
    prefix = f"{top_dir}/" if top_dir else ""
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(prefix + "manifest.json", json.dumps(manifest))
        for fp, content in files.items():
            if isinstance(content, str):
                content = content.encode("utf-8")
            zf.writestr(prefix + fp, content)
    path.write_bytes(buf.getvalue())
    return path


MV3_V1 = {
    "manifest_version": 3,
    "name": "Demo",
    "version": "1.0",
    "permissions": ["storage"],
    "host_permissions": ["https://example.com/*"],
    "background": {"service_worker": "old.js"},
}

MV3_V2 = {
    "manifest_version": 3,
    "name": "Demo",
    "version": "1.1",
    "permissions": ["storage", "tabs"],
    "host_permissions": ["https://example.com/*"],
    "background": {"service_worker": "new.js"},
}


# --------------------------------------------------------------------------- #
# content_hash
# --------------------------------------------------------------------------- #
def test_content_hash_is_order_independent():
    a = [{"path": "a.js", "sha256": "x"}, {"path": "b.js", "sha256": "y"}]
    b = [{"path": "b.js", "sha256": "y"}, {"path": "a.js", "sha256": "x"}]
    assert content_hash(a) == content_hash(b)
    assert content_hash(a).startswith("sha256:")


def test_content_hash_changes_with_content():
    a = [{"path": "a.js", "sha256": "x"}]
    b = [{"path": "a.js", "sha256": "z"}]
    assert content_hash(a) != content_hash(b)


# --------------------------------------------------------------------------- #
# is_minified
# --------------------------------------------------------------------------- #
def test_minified_long_single_line():
    assert is_minified(("var x=" + "a" * 6000 + ";").encode()) is True


def test_minified_normal_code_false():
    src = "\n".join(f"const v{i} = {i};" for i in range(50))
    assert is_minified(src.encode()) is False


def test_minified_undecodable_bytes_true():
    assert is_minified(b"\xff\xfe\x00\x01\x02binary") is True


def test_minified_none_false():
    assert is_minified(None) is False


# --------------------------------------------------------------------------- #
# unified diff
# --------------------------------------------------------------------------- #
def test_unified_diff_basic():
    diff, truncated = make_unified_diff("a\nb\nc", "a\nB\nc", "f.js")
    assert "-b" in diff and "+B" in diff
    assert truncated is False


def test_unified_diff_truncates():
    old = "\n".join(f"old-line-{i}" for i in range(5000))
    new = "\n".join(f"new-line-{i}" for i in range(5000))
    diff, truncated = make_unified_diff(old, new, "f.js", max_lines=50)
    assert truncated is True
    assert diff.count("\n") <= 50


# --------------------------------------------------------------------------- #
# manifest normalization (MV2 host extraction)
# --------------------------------------------------------------------------- #
def test_mv2_hosts_split_out_of_permissions():
    state = normalize_manifest_state({
        "manifest_version": 2,
        "permissions": ["tabs", "https://*.example.com/*", "<all_urls>"],
    })
    assert state["permissions"] == ["tabs"]
    assert "https://*.example.com/*" in state["host_permissions"]
    assert "<all_urls>" in state["host_permissions"]


def test_mv3_permissions_unchanged():
    state = normalize_manifest_state(MV3_V1)
    assert state["permissions"] == ["storage"]
    assert state["host_permissions"] == ["https://example.com/*"]


# --------------------------------------------------------------------------- #
# build_snapshot
# --------------------------------------------------------------------------- #
def test_build_snapshot_basic(tmp_path):
    z = _make_zip(tmp_path, "v1.zip", MV3_V1, {"old.js": "console.log(1)\n"})
    snap, file_bytes = build_snapshot(z, verdict={"risk_grade": "LOW", "result_id": "r1"})

    assert snap["version"] == "1.0"
    assert snap["manifest_version"] == 3
    assert snap["permissions"] == ["storage"]
    assert snap["verdict"] == {"risk_grade": "LOW", "result_id": "r1", "analyzed_at": None}
    paths = {f["path"] for f in snap["files"]}
    assert paths == {"manifest.json", "old.js"}
    assert snap["content_hash"].startswith("sha256:")
    assert "old.js" in file_bytes


def test_build_snapshot_reroots_top_dir(tmp_path):
    z = _make_zip(tmp_path, "v1.zip", MV3_V1, {"old.js": "x\n"}, top_dir="demo-1.0")
    snap, _ = build_snapshot(z)
    paths = {f["path"] for f in snap["files"]}
    assert paths == {"manifest.json", "old.js"}  # top dir stripped


def test_build_snapshot_no_manifest_raises(tmp_path):
    path = tmp_path / "bad.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "hi")
    path.write_bytes(buf.getvalue())
    with pytest.raises(ValueError):
        build_snapshot(path)


# --------------------------------------------------------------------------- #
# compute_diff
# --------------------------------------------------------------------------- #
def test_compute_diff_permissions_and_manifest(tmp_path):
    z1 = _make_zip(tmp_path, "v1.zip", MV3_V1, {"old.js": "a\n"})
    z2 = _make_zip(tmp_path, "v2.zip", MV3_V2, {"new.js": "b\n"})
    s1, _ = build_snapshot(z1)
    s2, _ = build_snapshot(z2)

    diff = compute_diff(s1, s2)
    assert diff["permissions"] == {"added": ["tabs"], "removed": []}
    fields = {c["field"] for c in diff["manifest_changes"]}
    assert "background.service_worker" in fields
    sw = next(c for c in diff["manifest_changes"] if c["field"] == "background.service_worker")
    assert sw["from"] == "old.js" and sw["to"] == "new.js"


def test_compute_diff_file_add_remove(tmp_path):
    z1 = _make_zip(tmp_path, "v1.zip", MV3_V1, {"old.js": "a\n"})
    z2 = _make_zip(tmp_path, "v2.zip", MV3_V2, {"new.js": "b\n"})
    s1, _ = build_snapshot(z1)
    s2, _ = build_snapshot(z2)

    files = compute_diff(s1, s2)["files"]
    assert "new.js" in files["added"]
    assert "old.js" in files["removed"]


def test_compute_diff_inline_modified_with_blob_loader(tmp_path):
    m1 = dict(MV3_V1)
    m2 = dict(MV3_V1)
    m2["version"] = "1.1"
    old_src = "line1\nline2\nline3\n"
    new_src = "line1\nCHANGED\nline3\n"
    z1 = _make_zip(tmp_path, "v1.zip", m1, {"app.js": old_src})
    z2 = _make_zip(tmp_path, "v2.zip", m2, {"app.js": new_src})

    s1, bytes1 = build_snapshot(z1)
    s2, bytes2 = build_snapshot(z2)

    # blob_loader resolves previous-version bytes by sha256 (stand-in for Nexus).
    store = {f["sha256"]: bytes1[f["path"]] for f in s1["files"]}
    diff = compute_diff(s2_prev := s1, s2, curr_file_bytes=bytes2,
                        blob_loader=lambda sha: store.get(sha))

    mod = next(m for m in diff["files"]["modified"] if m["path"] == "app.js")
    assert mod["is_minified"] is False
    assert mod["diff"] is not None
    assert "-line2" in mod["diff"] and "+CHANGED" in mod["diff"]
    assert mod["blob_ref"]["from"].startswith("nexus://blobs/")


def test_compute_diff_modified_pointer_only_without_blob(tmp_path):
    m1 = dict(MV3_V1)
    m2 = dict(MV3_V1)
    m2["version"] = "1.1"
    z1 = _make_zip(tmp_path, "v1.zip", m1, {"app.js": "a\n"})
    z2 = _make_zip(tmp_path, "v2.zip", m2, {"app.js": "b\n"})
    s1, _ = build_snapshot(z1)
    s2, b2 = build_snapshot(z2)

    diff = compute_diff(s1, s2, curr_file_bytes=b2)  # no blob_loader -> no prev bytes
    mod = next(m for m in diff["files"]["modified"] if m["path"] == "app.js")
    assert mod["diff"] is None
    assert mod["blob_ref"]["from"].startswith("nexus://blobs/")


def test_compute_diff_minified_modified_no_inline(tmp_path):
    m1 = dict(MV3_V1)
    m2 = dict(MV3_V1)
    m2["version"] = "1.1"
    old_min = "var a=" + "1" * 6000 + ";"
    new_min = "var a=" + "2" * 6000 + ";"
    z1 = _make_zip(tmp_path, "v1.zip", m1, {"min.js": old_min})
    z2 = _make_zip(tmp_path, "v2.zip", m2, {"min.js": new_min})
    s1, b1 = build_snapshot(z1)
    s2, b2 = build_snapshot(z2)

    store = {f["sha256"]: b1[f["path"]] for f in s1["files"]}
    diff = compute_diff(s1, s2, curr_file_bytes=b2, blob_loader=lambda sha: store.get(sha))
    mod = next(m for m in diff["files"]["modified"] if m["path"] == "min.js")
    assert mod["is_minified"] is True
    assert mod["diff"] is None


# --------------------------------------------------------------------------- #
# build_profile + validate_profile
# --------------------------------------------------------------------------- #
def test_build_profile_first_version_validates(tmp_path):
    z = _make_zip(tmp_path, "v1.zip", MV3_V1, {"old.js": "a\n"})
    snap, _ = build_snapshot(z, verdict={"risk_grade": "LOW", "result_id": "r1"})
    profile = build_profile(snap, ext_id="abc123", ext_name="Demo")

    assert profile["latest_version"] == "1.0"
    assert profile["snapshots"][0]["diff_from_previous"] is None
    assert validate_profile(profile) == []


def test_build_profile_second_version_attaches_diff(tmp_path):
    z1 = _make_zip(tmp_path, "v1.zip", MV3_V1, {"old.js": "a\n"})
    z2 = _make_zip(tmp_path, "v2.zip", MV3_V2, {"new.js": "b\n"})
    s1, _ = build_snapshot(z1)
    s2, b2 = build_snapshot(z2)

    p1 = build_profile(s1, ext_id="abc123")
    p2 = build_profile(s2, p1, curr_file_bytes=b2)

    assert len(p2["snapshots"]) == 2
    assert p2["latest_version"] == "1.1"
    last = p2["snapshots"][-1]["diff_from_previous"]
    assert last["previous_version"] == "1.0"
    assert last["permissions"]["added"] == ["tabs"]
    assert validate_profile(p2) == []


def test_build_profile_requires_ext_id_for_new():
    with pytest.raises(ValueError):
        build_profile({"version": "1.0", "captured_at": "t", "content_hash": "h", "files": []})


def test_validate_profile_reports_errors():
    errors = validate_profile({"schema_version": "1.0"})  # missing required fields
    assert errors  # non-empty -> invalid
