"""
관리자 앱 설정 API. 현재는 Slack Incoming Webhook URL 저장/조회만 담당한다.
웹훅 URL은 비밀값이므로 조회 시 마지막 토큰을 마스킹해서 반환한다.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth.security import require_admin
from backend.database import execute_query

router = APIRouter(prefix="/api/admin/settings", dependencies=[Depends(require_admin)])

SLACK_WEBHOOK_KEY = "slack_webhook_url"


class SlackWebhookRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=512)


def _mask(url: str) -> str:
    head, _, tail = url.rpartition("/")
    return f"{head}/{'*' * 8}" if head else "*" * 8


def get_slack_webhook_url() -> str | None:
    """DB에 저장된 웹훅 URL 원본을 반환. Slack 전송 모듈에서 사용."""
    rows = execute_query("SELECT value FROM app_settings WHERE key = %s", (SLACK_WEBHOOK_KEY,))
    if rows and rows[0].get("value"):
        return rows[0]["value"].strip()
    return None


@router.get("/slack-webhook")
async def read_slack_webhook():
    rows = execute_query("SELECT value FROM app_settings WHERE key = %s", (SLACK_WEBHOOK_KEY,))
    if rows is None:
        raise HTTPException(status_code=500, detail="Database query failed.")
    if not rows:
        return {"configured": False, "url": None, "masked_url": None}
    # 관리자 전용 엔드포인트이므로 관리 화면 표시용으로 원본 URL을 함께 반환
    return {"configured": True, "url": rows[0]["value"], "masked_url": _mask(rows[0]["value"])}


@router.post("/slack-webhook")
async def save_slack_webhook(body: SlackWebhookRequest):
    url = body.url.strip()
    if not url.startswith("https://hooks.slack.com/"):
        raise HTTPException(
            status_code=400,
            detail="Slack Incoming Webhook URL은 https://hooks.slack.com/ 으로 시작해야 합니다.",
        )
    ok = execute_query(
        """
        INSERT INTO app_settings (key, value)
        VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (SLACK_WEBHOOK_KEY, url),
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save webhook URL.")
    return {"configured": True, "url": url, "masked_url": _mask(url)}
