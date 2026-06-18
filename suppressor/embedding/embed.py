import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

def embed_fingerprint(fp_data: dict) -> list[float]:
    embed_url = os.environ.get("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")
    legacy_embed_url = os.environ.get("OLLAMA_EMBED_LEGACY_URL", "http://localhost:11434/api/embeddings")
    model = os.environ.get("EMBEDDING_MODEL", "bge-m3")

    # 텍스트 변환 (분석 결과 데이터 활용)
    capabilities = fp_data.get("capability_profile", [])
    text = ", ".join(capabilities) if capabilities else json.dumps(fp_data, ensure_ascii=False)

    retries = 3
    backoff_seconds = [1, 3, 7]
    last_error = None
    for attempt in range(1, retries + 1):
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
                vector = result[0]
            elif isinstance(result, list):
                vector = result
            else:
                legacy_response = requests.post(
                    legacy_embed_url,
                    json={"model": model, "prompt": text},
                    timeout=60,
                )
                if legacy_response.status_code >= 400:
                    raise RuntimeError(
                        f"ollama legacy embed error({legacy_response.status_code}): {legacy_response.text}"
                    )
                legacy_payload = legacy_response.json()
                vector = legacy_payload.get("embedding")

            if not isinstance(vector, list) or not vector:
                raise RuntimeError("empty embedding vector from ollama")

            os.makedirs("embedding", exist_ok=True)
            with open("embedding/embedding.json", "w", encoding="utf-8") as f:
                json.dump(vector, f, ensure_ascii=False, indent=2)
            return vector
        except Exception as e:
            last_error = e
            print(f"⚠️ embedding attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(backoff_seconds[attempt - 1])

    print(f"❌ embedding_failed after retries: {last_error}")
    return []
