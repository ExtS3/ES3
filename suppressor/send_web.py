import httpx

import os
from dotenv import load_dotenv

load_dotenv()

async def send_web(payload: dict) -> dict:
    """
    웹 대시보드로 요약 payload를 전송합니다.
    """
    url = os.getenv("WEB_RECEIVE_URL")
    url = url
    if not url:
        raise RuntimeError("WEB_RECEIVE_URL is not set")

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)

    result = {
        "status_code": response.status_code,
        "url": url,
        "text": response.text[:1000],
    }
    try:
        result["json"] = response.json()
    except Exception:
        result["json"] = None

    if response.status_code >= 400:
        raise RuntimeError(
            f"web forward failed: status={response.status_code}, body={response.text[:1000]}"
        )

    return result
