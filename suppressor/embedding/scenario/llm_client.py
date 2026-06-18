from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _is_truthy_env(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _estimate_tokens_from_chars(total_chars: int) -> int:
    return max(1, int(total_chars / 4))


def normalize_messages(messages: Any) -> list[dict[str, str]]:
    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]

    if not isinstance(messages, list):
        return [{"role": "user", "content": str(messages)}]

    out: list[dict[str, str]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role", "user")).strip().lower()
        if role not in {"system", "user", "assistant"}:
            role = "user"

        content = m.get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for c in content:
                if isinstance(c, dict) and isinstance(c.get("text"), str):
                    parts.append(c["text"])
                elif isinstance(c, str):
                    parts.append(c)
            content_text = "\n".join(parts).strip()
        elif isinstance(content, str):
            content_text = content
        else:
            content_text = str(content)

        out.append({"role": role, "content": content_text})

    return out or [{"role": "user", "content": ""}]


def _log_prompt_diagnostics(
    *,
    model: str,
    messages: list[dict[str, str]],
    num_ctx: int,
    max_tokens: int,
    timeout_sec: int,
) -> None:
    content_lengths = [len(str(m.get("content", ""))) for m in messages]
    total_chars = sum(content_lengths)
    estimated_tokens = _estimate_tokens_from_chars(total_chars)
    may_exceed_context = estimated_tokens > int(num_ctx)

    logger.info(
        "[llm_prompt_diag] backend=ollama model=%s messages=%s total_chars=%s estimated_tokens=%s "
        "num_ctx=%s max_tokens=%s timeout=%s may_exceed_context=%s",
        model,
        len(messages),
        total_chars,
        estimated_tokens,
        num_ctx,
        max_tokens,
        timeout_sec,
        str(may_exceed_context).lower(),
    )

    for idx, msg in enumerate(messages):
        role = str(msg.get("role", "user"))
        logger.info(
            "[llm_prompt_diag] message[%s] role=%s chars=%s",
            idx,
            role,
            len(str(msg.get("content", ""))),
        )


def _dump_prompt_if_enabled(
    *,
    model: str,
    messages: list[dict[str, str]],
    num_ctx: int,
    max_tokens: int,
    timeout_sec: int,
) -> None:
    if not _is_truthy_env("LLM_DEBUG_PROMPT_DUMP", "0"):
        return

    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    estimated_tokens = _estimate_tokens_from_chars(total_chars)
    base_dir = Path(os.getenv("LLM_DEBUG_PROMPT_DUMP_DIR", "/home/ec2-user/suppressor/debug_prompts"))
    safe_model = model.replace("/", "_").replace(":", "_")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_path = base_dir / f"llm_prompt_{ts}_ollama_{safe_model}.json"

    payload = {
        "backend": "ollama",
        "model": model,
        "num_ctx": num_ctx,
        "max_tokens": max_tokens,
        "timeout": timeout_sec,
        "message_count": len(messages),
        "total_chars": total_chars,
        "estimated_tokens": estimated_tokens,
        "messages": messages,
    }

    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[llm_prompt_diag] prompt_dump_saved=%s", str(file_path))
    except Exception as exc:
        logger.warning("[llm_prompt_diag] prompt_dump_failed err=%s", exc)


def call_ollama(messages: Any, **kwargs) -> dict[str, Any]:
    normalized = normalize_messages(messages)

    local_url = kwargs.get("local_url") or os.getenv("LOCAL_LLM_URL", "http://localhost:11434/api/chat")
    local_model = kwargs.get("model") or os.getenv("LOCAL_LLM_MODEL", "qwen2.5:1.5b-instruct-q4_K_M")
    num_ctx = _env_int("LLM_CONTEXT", 4096)
    temperature = _env_float("LLM_TEMPERATURE", 0.1)
    num_predict = _env_int("LLM_MAX_TOKENS", 256)
    timeout_sec = _env_int("LLM_TIMEOUT", 300)
    keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "5m")

    _log_prompt_diagnostics(
        model=local_model,
        messages=normalized,
        num_ctx=num_ctx,
        max_tokens=num_predict,
        timeout_sec=timeout_sec,
    )
    _dump_prompt_if_enabled(
        model=local_model,
        messages=normalized,
        num_ctx=num_ctx,
        max_tokens=num_predict,
        timeout_sec=timeout_sec,
    )

    payload = {
        "model": local_model,
        "messages": normalized,
        "stream": False,
        "keep_alive": keep_alive,
        "format": "json",
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }

    logger.info(
        "LLM call backend=ollama model=%s num_ctx=%s timeout=%s",
        local_model,
        num_ctx,
        timeout_sec,
    )

    try:
        response = requests.post(local_url, json=payload, timeout=timeout_sec)
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError("Ollama server is not reachable. Check: systemctl status ollama") from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"Ollama request timed out after {timeout_sec}s") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Failed to call Ollama API: {exc}") from exc

    if response.status_code >= 400:
        body = ""
        try:
            body = json.dumps(response.json(), ensure_ascii=False)
        except Exception:
            body = response.text

        low = body.lower()
        if "not found" in low and "model" in low:
            raise RuntimeError(f"Ollama model not found. Run: ollama pull {local_model}")

        raise RuntimeError(f"Ollama API error ({response.status_code}): {body}")

    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError("Ollama API returned non-JSON response") from exc

    content = data.get("message", {}).get("content")
    if not isinstance(content, str):
        raise RuntimeError("Ollama API response missing message.content")

    is_json_like = content.strip().startswith("{") and content.strip().endswith("}")
    logger.info(
        "LLM response backend=ollama model=%s response_len=%s json_like=%s",
        local_model,
        len(content),
        str(is_json_like).lower(),
    )

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
        return {"raw_text": content, "parse_error": "response JSON is not an object"}
    except Exception as exc:
        return {"raw_text": content, "parse_error": f"failed to parse JSON: {exc}"}


def call_llm(messages: Any = None, **kwargs) -> dict[str, Any]:
    if messages is None:
        prompt = kwargs.pop("prompt", "")
        system_prompt = kwargs.pop("system_prompt", "")
        messages = []
        if isinstance(system_prompt, str) and system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": str(prompt or "")})

    return call_ollama(messages, **kwargs)


# m7i-flex.large (2 vCPU / 8GB RAM / no GPU)에서는 7B 모델 사용을 피하세요.
# g4dn.xlarge 전환 후 LOCAL_LLM_MODEL=qwen2.5:7b-instruct-q4_K_M 권장.
