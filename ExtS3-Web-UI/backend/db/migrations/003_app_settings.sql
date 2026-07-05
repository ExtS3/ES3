-- 관리자 설정 키-값 저장소. 현재는 Slack Incoming Webhook URL(slack_webhook_url) 저장 용도.
CREATE TABLE IF NOT EXISTS admin.app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
