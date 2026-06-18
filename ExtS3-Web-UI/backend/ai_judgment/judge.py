"""
LLM 호출 및 JSON 파싱.
실패 시 fallback 판단을 반환해 항상 결과 구조를 보장합니다.
"""
import datetime
import json
import os
import re
import time
from typing import Any, Dict, Optional

import requests

from backend.ai_judgment.extractor import extract_for_llm
from backend.ai_judgment.prompts import SYSTEM_PROMPT, build_user_prompt

LLM_URL         = os.getenv("LOCAL_LLM_URL",   "http://localhost:11434/api/chat")
LLM_MODEL       = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:1.5b-instruct-q4_K_M")
LLM_MAX_TOKENS  = int(os.getenv("AI_JUDGMENT_MAX_TOKENS", "1024"))
LLM_TIMEOUT     = int(os.getenv("LLM_TIMEOUT",  "300"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "5m")


def _parse_json(text: str) -> Optional[dict]:
    text = text.strip()
    # 직접 파싱
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # ```json ... ``` 블록
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 첫 번째 { ... } 블록
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _fallback(ext_data: dict, reason: str) -> dict:
    return {
        "verdict": {
            "recommendation": "escalate",
            "confidence": "low",
            "summary": "AI 분석 실패 — 수동 검토 필요",
            "key_reason": f"LLM 오류: {reason[:60]}",
        },
        "risk_groups": {
            "permission": {"level": "unknown", "key_items": ext_data.get("permissions", [])[:3],      "note": "수동 확인 필요"},
            "code":       {"level": "unknown", "key_items": ext_data.get("static_findings", [])[:2],  "note": "수동 확인 필요"},
            "behavior":   {"level": "unknown", "key_items": ext_data.get("matched_scenarios", [])[:2],"note": "수동 확인 필요"},
            "pattern":    {"level": "unknown", "key_items": ext_data.get("top_patterns", [])[:2],     "note": "수동 확인 필요"},
        },
        "ambiguous": [{"issue": "AI 분석 불가", "check": "분석 결과 전체 직접 검토"}],
        "checklist": ["정적 분석 결과 직접 확인", "동적 런타임 증거 검토", "외부 도메인 정상 여부 확인"],
        "_error": reason,
    }


def run_judgment(web_payload: dict) -> dict:
    """
    web_payload를 받아 LLM 판단을 수행하고 구조화된 결과를 반환합니다.

    Returns: judgment dict (항상 반환, LLM 실패 시 fallback 포함)
    """
    ext_data    = extract_for_llm(web_payload)
    user_prompt = build_user_prompt(ext_data)

    base = {
        "judgment_id":     f"JDG-{ext_data['id'][:16]}-{int(time.time())}",
        "extension_id":    ext_data["id"],
        "extension_name":  ext_data["name"],
        "analyzed_at":     datetime.datetime.now().isoformat(),
        "ai_model":        LLM_MODEL,
        "input_risk_level": ext_data["risk_level"],
        "input_risk_score": ext_data["risk_score"],
        "score_breakdown": {
            "dynamic":     {"score": ext_data["d_score"], "level": ext_data["d_level"], "weight": 0.65},
            "static":      {"score": ext_data["s_score"], "level": ext_data["s_level"], "weight": 0.20},
            "obfuscation": {"score": ext_data["o_score"], "level": ext_data["o_level"], "weight": 0.15},
        },
    }

    try:
        resp = requests.post(
            LLM_URL,
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": LLM_TEMPERATURE,
                    "num_predict": LLM_MAX_TOKENS,
                },
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()

        raw = resp.json().get("message", {}).get("content", "")
        parsed = _parse_json(raw)

        if parsed:
            base.update({
                "verdict":     parsed.get("verdict", {}),
                "risk_groups": parsed.get("risk_groups", {}),
                "ambiguous":   parsed.get("ambiguous", []),
                "checklist":   parsed.get("checklist", []),
            })
            print(f"[AI Judgment] ✅ 판단 완료: {ext_data['name']} → {parsed.get('verdict', {}).get('recommendation', '?')}")
        else:
            print(f"[AI Judgment] ⚠️ JSON 파싱 실패. raw={raw[:200]}")
            base.update(_fallback(ext_data, "JSON 파싱 실패"))

    except requests.exceptions.Timeout:
        print("[AI Judgment] ⏱️ LLM 타임아웃")
        base.update(_fallback(ext_data, "LLM 타임아웃"))
    except Exception as e:
        print(f"[AI Judgment] ❌ LLM 오류: {e}")
        base.update(_fallback(ext_data, str(e)))

    return base
