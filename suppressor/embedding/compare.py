import json
import os

from dotenv import load_dotenv

from embedding.pgvector_store import search_vectors

load_dotenv()

FALLBACK_PATTERN_NAME = "session_storage_exfiltration_document_start"
FALLBACK_DOC_REF = "scenario_docs/session_storage_exfiltration_document_start.md"


def _is_probably_fingerprint(obj):
    return isinstance(obj, dict) and all(
        k in obj
        for k in [
            "manifest_profile",
            "capability_profile",
            "static_code_signals",
            "predicted_flows",
            "behavior_tags",
        ]
    )


def _parse_document_to_dict(document):
    if isinstance(document, dict):
        return document, None
    if isinstance(document, str):
        try:
            parsed = json.loads(document)
            if isinstance(parsed, dict):
                return parsed, None
            return None, "document JSON is not an object"
        except Exception as exc:
            return None, f"document parse failed: {exc}"
    return None, "document is neither dict nor JSON string"


def _unwrap_document_payload(document_obj, row):
    pattern_name = row.get("pattern_name")
    doc_ref = row.get("doc_ref")
    vf = None

    if isinstance(document_obj, dict) and "vector_fingerprint" in document_obj:
        pattern_name = document_obj.get("pattern_name") or pattern_name
        doc_ref = document_obj.get("doc_ref") or doc_ref
        vf = document_obj.get("vector_fingerprint")
    elif _is_probably_fingerprint(document_obj):
        vf = document_obj

    if isinstance(vf, dict) and "vector_fingerprint" in vf:
        pattern_name = vf.get("pattern_name") or pattern_name
        doc_ref = vf.get("doc_ref") or doc_ref
        vf = vf.get("vector_fingerprint")

    if isinstance(vf, dict) and "vector_fingerprint" in vf:
        vf = vf.get("vector_fingerprint")

    if not _is_probably_fingerprint(vf):
        vf = None

    if not isinstance(pattern_name, str) or not pattern_name.strip():
        rid = row.get("id")
        pattern_name = rid.strip() if isinstance(rid, str) and rid.strip() else FALLBACK_PATTERN_NAME

    if not isinstance(doc_ref, str) or not doc_ref.strip():
        doc_ref = f"scenario_docs/{pattern_name}.md" if pattern_name != FALLBACK_PATTERN_NAME else FALLBACK_DOC_REF

    return pattern_name, doc_ref, vf


def normalize_compare_result_rows(results: list[dict]) -> list[dict]:
    normalized: list[dict] = []

    for row in results if isinstance(results, list) else []:
        if not isinstance(row, dict):
            continue

        similarity = row.get("similarity", row.get("score", row.get("vector_similarity", 0.0)))
        try:
            score = float(similarity or 0.0)
        except (TypeError, ValueError):
            score = 0.0

        payload = {}
        document_obj, parse_error = _parse_document_to_dict(row.get("document"))
        if isinstance(document_obj, dict):
            pattern_name, doc_ref, fingerprint = _unwrap_document_payload(document_obj, row)
            payload["doc_ref"] = doc_ref
            payload["pattern_name"] = pattern_name
            if isinstance(fingerprint, dict):
                payload["vector_fingerprint"] = fingerprint
            else:
                payload["parse_error"] = "document does not contain valid vector_fingerprint"
        elif parse_error:
            pattern_name = row.get("pattern_name") or FALLBACK_PATTERN_NAME
            doc_ref = row.get("doc_ref") or (
                f"scenario_docs/{pattern_name}.md" if pattern_name != FALLBACK_PATTERN_NAME else FALLBACK_DOC_REF
            )
            payload["doc_ref"] = doc_ref
            payload["pattern_name"] = pattern_name
            payload["parse_error"] = parse_error

        normalized.append(
            {
                "id": row.get("id"),
                "score": score,
                "similarity": score,
                "payload": payload,
            }
        )

    return normalized


def compareDB(embedding_vector: list[float]):
    try:
        results = search_vectors(
            embedding_vector,
            match_threshold=float(os.environ.get("PGVECTOR_MATCH_THRESHOLD", "0")),
            match_count=int(os.environ.get("PGVECTOR_MATCH_COUNT", "10")),
        )
        normalized_results = normalize_compare_result_rows(results)

        print("\n" + "=" * 65)
        print(f"[pgvector] Vector similarity search result: {len(normalized_results)} rows")
        print("-" * 65)
        print(f"{'rank':<4} | {'score':<10} | {'id'}")
        print("-" * 65)
        for i, res in enumerate(normalized_results, start=1):
            score_pct = float(res.get("score", 0.0)) * 100
            print(f"{i:2d}   | {score_pct:8.2f}% | {res.get('id')}")
        print("=" * 65 + "\n")

        return normalized_results
    except Exception as exc:
        print(f"[pgvector] vector search failed: {exc}")
        return []
