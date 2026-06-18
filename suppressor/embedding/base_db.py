import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from embedding.embed import embed_fingerprint
from embedding.pgvector_store import count_vectors, insert_vector_record

load_dotenv()


def embed_full_text(text: str) -> list[float]:
    embed_url = os.environ.get("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")
    legacy_embed_url = os.environ.get("OLLAMA_EMBED_LEGACY_URL", "http://localhost:11434/api/embeddings")
    model = os.environ.get("EMBEDDING_MODEL", "bge-m3")

    try:
        response = requests.post(
            embed_url,
            json={"model": model, "input": text},
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"ollama embed error({response.status_code}): {response.text}")

        payload = response.json()
        result = payload.get("embeddings")
        if isinstance(result, list) and result and isinstance(result[0], list):
            return result[0]
        if isinstance(result, list):
            return result

        legacy_response = requests.post(
            legacy_embed_url,
            json={"model": model, "prompt": text},
            timeout=60,
        )
        if legacy_response.status_code >= 400:
            raise RuntimeError(f"ollama legacy embed error({legacy_response.status_code}): {legacy_response.text}")
        legacy_payload = legacy_response.json()
        legacy_vector = legacy_payload.get("embedding")
        if isinstance(legacy_vector, list):
            return legacy_vector

        raise RuntimeError("unsupported Ollama embedding response")
    except Exception as exc:
        print(f"[pgvector] embedding failed: {exc}")
        return []


def load_base_json(file_path: Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("base JSON root must be an object")
    return data


def normalize_base_record(file_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    file_stem = file_path.stem

    if isinstance(data.get("vector_fingerprint"), dict):
        pattern_name = data.get("pattern_name") or file_stem
        doc_ref = data.get("doc_ref") or f"scenario_docs/{pattern_name}.md"
        vector_fingerprint = data["vector_fingerprint"]
    else:
        pattern_name = data.get("pattern_name") or file_stem
        doc_ref = data.get("doc_ref") or f"scenario_docs/{pattern_name}.md"
        vector_fingerprint = data

    if not isinstance(pattern_name, str) or not pattern_name.strip():
        raise ValueError("pattern_name is empty")
    if not isinstance(doc_ref, str) or not doc_ref.strip():
        raise ValueError("doc_ref is empty")
    if not isinstance(vector_fingerprint, dict) or not vector_fingerprint:
        raise ValueError("vector_fingerprint is empty or invalid")

    required_keys = [
        "manifest_profile",
        "capability_profile",
        "static_code_signals",
        "predicted_flows",
        "behavior_tags",
    ]
    missing = [key for key in required_keys if key not in vector_fingerprint]
    if missing:
        raise ValueError(f"vector_fingerprint missing required keys: {missing}")

    return {
        "pattern_name": pattern_name,
        "doc_ref": doc_ref,
        "vector_fingerprint": vector_fingerprint,
    }


def build_embedding_text(vector_fingerprint: dict[str, Any]) -> str:
    return json.dumps(
        vector_fingerprint,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_document_payload(record: dict[str, Any]) -> str:
    payload = {
        "pattern_name": record["pattern_name"],
        "doc_ref": record["doc_ref"],
        "vector_fingerprint": record["vector_fingerprint"],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def validate_doc_ref_exists(project_root: Path, doc_ref: str) -> bool:
    return (project_root / doc_ref).exists()


def store_all_knowledge_base() -> None:
    project_root = Path(__file__).resolve().parent
    base_dir = project_root / "base"
    if not base_dir.exists():
        alt_base_dir = project_root.parent / "base"
        if alt_base_dir.exists():
            base_dir = alt_base_dir

    if not base_dir.exists():
        print(f"[pgvector] base directory not found: {base_dir}")
        return

    json_files = sorted(base_dir.glob("*.json"))
    if not json_files:
        print("[pgvector] no base JSON files found")
        return

    print(f"[pgvector] seeding {len(json_files)} base scenario embeddings from {base_dir}")
    success_count = 0
    fail_count = 0

    for index, file_path in enumerate(json_files, start=1):
        try:
            raw_data = load_base_json(file_path)
            record = normalize_base_record(file_path, raw_data)
            doc_ref = record["doc_ref"]
            vector_fingerprint = record["vector_fingerprint"]

            if not validate_doc_ref_exists(project_root.parent, doc_ref) and not validate_doc_ref_exists(project_root, doc_ref):
                print(f"[pgvector] warning: scenario doc not found for {record['pattern_name']}: {doc_ref}")

            vector = embed_fingerprint(vector_fingerprint)
            if not vector:
                raise RuntimeError("embedding vector generation failed")

            document_payload = build_document_payload(record)
            insert_vector_record(document_payload, vector)
            success_count += 1
            print(f"[pgvector] seeded {index}/{len(json_files)}: {record['pattern_name']} dim={len(vector)}")
        except Exception as exc:
            fail_count += 1
            print(f"[pgvector] failed to seed {file_path.name}: {exc}")

    print(f"[pgvector] seed complete: success={success_count} fail={fail_count}")


def ensure_knowledge_base_seeded() -> None:
    try:
        existing_count = count_vectors()
    except Exception as exc:
        print(f"[pgvector] knowledge base check failed: {exc}")
        return

    if existing_count > 0:
        print(f"[pgvector] knowledge base already loaded: {existing_count} vectors")
        return

    print("[pgvector] knowledge base is empty; creating embeddings from embedding/base")
    store_all_knowledge_base()


if __name__ == "__main__":
    store_all_knowledge_base()
