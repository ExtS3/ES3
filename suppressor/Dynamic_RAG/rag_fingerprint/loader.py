import tempfile
import zipfile
from pathlib import Path

from .utils import FingerprintError


class ExtensionSource:
    def __init__(self, root: Path, temp_dir: tempfile.TemporaryDirectory[str] | None = None):
        self.root = root
        self._temp_dir = temp_dir

    def cleanup(self) -> None:
        if self._temp_dir:
            self._temp_dir.cleanup()


def load_extension_source(path: str) -> ExtensionSource:
    p = Path(path)
    if not p.exists():
        raise FingerprintError(f"Extension path not found: {path}")
    if p.is_dir():
        root = p.resolve()
        if not (root / "manifest.json").exists():
            manifests = list(root.rglob("manifest.json"))
            if not manifests:
                raise FingerprintError(f"manifest.json not found in extension: {path}")
            root = manifests[0].parent.resolve()
        return ExtensionSource(root, None)
    if p.suffix.lower() == ".zip":
        temp_dir = tempfile.TemporaryDirectory(prefix="rag_fingerprint_")
        root = Path(temp_dir.name)
        with zipfile.ZipFile(p, "r") as zf:
            for member in zf.infolist():
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    continue
                zf.extract(member, root)
        manifest_direct = root / "manifest.json"
        if manifest_direct.exists():
            return ExtensionSource(root.resolve(), temp_dir)
        manifests = list(root.rglob("manifest.json"))
        if not manifests:
            raise FingerprintError(f"manifest.json not found in extension zip: {path}")
        return ExtensionSource(manifests[0].parent.resolve(), temp_dir)
    raise FingerprintError("Input must be extension directory or .zip file")


def prepare_output_dir(path: str) -> Path:
    out = Path(path)
    if out.exists() and not out.is_dir():
        raise FingerprintError(f"Output path must be directory: {path}")
    out.mkdir(parents=True, exist_ok=True)
    return out
