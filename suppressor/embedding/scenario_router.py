"""Scenario knowledge-base management API.

Exposes the endpoints the ExtS3-Web-UI admin "시나리오 관리" page proxies to:

    GET    /api/scenario/db-status          -> vector DB health + count
    GET    /api/scenario/list               -> all base scenarios
    GET    /api/scenario/detail/{id}         -> one scenario (json + doc)
    POST   /api/scenario/upload             -> add a scenario (json + md)
    DELETE /api/scenario/delete/{id}         -> remove a user scenario (json + md)
    POST   /api/scenario/reload             -> wipe + re-embed all scenarios

Each scenario is addressed by a Chrome-extension-style id: 32 chars drawn from
``a``–``p`` (one hex nibble each).

* The 26 builtin scenarios carry a **fixed** ``scenario_id`` derived
  deterministically from their ``pattern_name`` (SHA-256 → a-p). These ids never
  change across reseed / reinstall and the scenarios cannot be deleted.
* User-uploaded scenarios get a **random** ``scenario_id`` that is checked for
  collisions against every existing id before being assigned.

Scenario definitions live in ``embedding/base/<id>.json`` and their human docs in
``embedding/scenario_docs/<stem>.md``.
"""

import hashlib
import json
import secrets
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from embedding.base_db import normalize_base_record, store_all_knowledge_base
from embedding.pgvector_store import clear_vectors, count_vectors

router = APIRouter(prefix="/api/scenario", tags=["scenario"])

_EMBEDDING_DIR = Path(__file__).resolve().parent
_BASE_DIR = _EMBEDDING_DIR / "base"
_DOCS_DIR = _EMBEDDING_DIR / "scenario_docs"

# 16-symbol alphabet (one hex nibble each), mirrors the Chrome extension id scheme.
_ID_ALPHABET = "abcdefghijklmnop"
_ID_LENGTH = 32


def _derive_fixed_id(seed: str) -> str:
    """Deterministic id from a seed (used for the fixed builtin scenarios)."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return "".join(_ID_ALPHABET[int(char, 16)] for char in digest[:_ID_LENGTH])


def _is_valid_id(scenario_id: str) -> bool:
    return (
        isinstance(scenario_id, str)
        and len(scenario_id) == _ID_LENGTH
        and all(char in _ID_ALPHABET for char in scenario_id)
    )


def _scenario_id_of(path: Path, data: dict) -> str:
    """Resolve a scenario's id: stored ``scenario_id`` or derived from pattern_name."""
    stored = data.get("scenario_id")
    if isinstance(stored, str) and _is_valid_id(stored):
        return stored
    pattern_name = data.get("pattern_name") or path.stem
    return _derive_fixed_id(pattern_name)


def _load_scenario(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_scenarios():
    """Yield (path, data, scenario_id) for every readable base scenario."""
    if not _BASE_DIR.exists():
        return
    for path in sorted(_BASE_DIR.glob("*.json")):
        try:
            data = _load_scenario(path)
        except Exception:
            continue
        yield path, data, _scenario_id_of(path, data)


def _find_by_id(scenario_id: str):
    """Return (path, data) for the scenario with this id, or None."""
    for path, data, sid in _iter_scenarios():
        if sid == scenario_id:
            return path, data
    return None


def _existing_ids() -> set:
    return {sid for _, _, sid in _iter_scenarios()}


def _new_unique_id() -> str:
    existing = _existing_ids()
    for _ in range(1000):
        candidate = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LENGTH))
        if candidate not in existing:
            return candidate
    raise HTTPException(status_code=500, detail="고유 시나리오 ID 생성에 실패했습니다.")


def _behavior_tags(data: dict) -> list:
    vf = data.get("vector_fingerprint") if isinstance(data.get("vector_fingerprint"), dict) else data
    tags = vf.get("behavior_tags") if isinstance(vf, dict) else None
    return tags if isinstance(tags, list) else []


def _is_builtin(data: dict) -> bool:
    return data.get("builtin") is True


def _doc_path_for(path: Path) -> Path:
    """Markdown doc lives next to the JSON, keyed by the same file stem."""
    return _DOCS_DIR / f"{path.stem}.md"


def _read_doc(path: Path) -> str | None:
    doc_path = _doc_path_for(path)
    if not doc_path.exists():
        return None
    try:
        return doc_path.read_text(encoding="utf-8")
    except Exception:
        return None


@router.get("/db-status")
async def db_status():
    try:
        return {"status": "ok", "vector_count": count_vectors()}
    except Exception as exc:  # connection / pgvector / schema failure
        return {"status": "error", "detail": str(exc)}


@router.get("/list")
async def list_scenarios():
    scenarios = []
    for path, data, sid in _iter_scenarios():
        scenarios.append(
            {
                "id": sid,
                "pattern_name": data.get("pattern_name") or path.stem,
                "behavior_tags": _behavior_tags(data),
                "has_doc": _doc_path_for(path).exists(),
                "builtin": _is_builtin(data),
            }
        )
    return {"scenarios": scenarios}


@router.get("/detail/{scenario_id}")
async def get_scenario(scenario_id: str):
    found = _find_by_id(scenario_id)
    if not found:
        raise HTTPException(status_code=404, detail="시나리오를 찾을 수 없습니다.")
    path, data = found
    return {
        "id": scenario_id,
        "pattern_name": data.get("pattern_name") or path.stem,
        "builtin": _is_builtin(data),
        "behavior_tags": _behavior_tags(data),
        "doc": _read_doc(path),
        "scenario": data,
    }


@router.post("/upload")
async def upload_scenario(
    json_file: UploadFile = File(...),
    md_file: UploadFile = File(None),
):
    raw = await json_file.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JSON 파싱 실패: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON 최상위는 객체여야 합니다.")

    # 구조 검증 (필수 키 누락 등은 ValueError)
    try:
        normalize_base_record(Path(json_file.filename or "scenario.json"), data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"시나리오 형식 오류: {exc}")

    # 사용자 업로드는 항상 새 고유 ID를 부여한다 (기존 빌트인/사용자 ID와 충돌 없음).
    scenario_id = _new_unique_id()
    data["scenario_id"] = scenario_id
    data["builtin"] = False
    data["doc_ref"] = f"scenario_docs/{scenario_id}.md"

    _BASE_DIR.mkdir(parents=True, exist_ok=True)
    target = _BASE_DIR / f"{scenario_id}.json"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if md_file and md_file.filename:
        _DOCS_DIR.mkdir(parents=True, exist_ok=True)
        md_bytes = await md_file.read()
        (_DOCS_DIR / f"{scenario_id}.md").write_bytes(md_bytes)

    return {
        "id": scenario_id,
        "message": f"시나리오 저장 완료 (ID: {scenario_id})",
        "reload_required": True,
    }


@router.delete("/delete/{scenario_id}")
async def delete_scenario(scenario_id: str):
    found = _find_by_id(scenario_id)
    if not found:
        raise HTTPException(status_code=404, detail="시나리오를 찾을 수 없습니다.")
    path, data = found

    if _is_builtin(data):
        raise HTTPException(
            status_code=400,
            detail="기본 제공(빌트인) 시나리오는 삭제할 수 없습니다.",
        )

    doc_path = _doc_path_for(path)
    path.unlink(missing_ok=True)
    doc_path.unlink(missing_ok=True)

    return {
        "id": scenario_id,
        "message": f"시나리오 '{scenario_id}' 삭제 완료",
        "reload_required": True,
    }


@router.post("/reload")
async def reload_scenarios():
    try:
        clear_vectors()
        store_all_knowledge_base()
        return {
            "message": "vectorDB 재적재 완료",
            "vector_count": count_vectors(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"재적재 실패: {exc}")
