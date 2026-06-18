"""
AI 판단 결과를 포함한 Slack Block Kit 메시지를 생성하고 전송합니다.
기존 suppressor Slack(기본 알림)과 별개로 AI 요약 메시지를 추가 전송합니다.
"""
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


def _webhook_url() -> Optional[str]:
    return os.getenv("SLACK_WEBHOOK_URL")


def _dashboard_url(ext_id: str, ext_name: str, browser: str, version: str) -> str:
    base = os.getenv("DASHBOARD_BASE_URL", "http://localhost:8000").rstrip("/")
    q = urllib.parse.urlencode({"id": ext_id, "name": ext_name,
                                "browser": browser, "version": version})
    return f"{base}/admin/log?{q}"


_LEVEL_EMOJI = {
    "critical": "🔴", "high": "🟠", "medium": "🟡",
    "low": "🟢", "none": "⚪", "unknown": "❓",
}
_REC_EMOJI = {"reject": "🚫", "escalate": "⚠️", "approve": "✅"}

def _le(level: str) -> str:
    return _LEVEL_EMOJI.get((level or "").lower(), "❓")

def _re(rec: str) -> str:
    return _REC_EMOJI.get((rec or "").lower(), "❓")


def build_slack_payload(judgment: dict, web_payload: dict) -> Dict[str, Any]:
    ext      = (web_payload.get("extension") or {}) if isinstance(web_payload, dict) else {}
    name     = judgment.get("extension_name") or ext.get("name", "unknown")
    ext_id   = judgment.get("extension_id")   or ext.get("extension_id", "")
    browser  = ext.get("browser", "unknown")
    version  = ext.get("version", "unknown")

    verdict  = judgment.get("verdict", {}) or {}
    groups   = judgment.get("risk_groups", {}) or {}
    ambiguous = judgment.get("ambiguous", []) or []
    checklist = judgment.get("checklist", []) or []
    breakdown = judgment.get("score_breakdown", {}) or {}

    rec        = verdict.get("recommendation", "escalate")
    confidence = verdict.get("confidence", "?")
    risk_level = judgment.get("input_risk_level", "UNKNOWN")
    risk_score = judgment.get("input_risk_score", 0.0)
    dashboard  = _dashboard_url(ext_id, name, browser, version)

    d = breakdown.get("dynamic", {})
    s = breakdown.get("static", {})
    o = breakdown.get("obfuscation", {})

    blocks: List[Dict] = [
        # ── 헤더 ──────────────────────────────────────────────────────
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔍 [AI 검토 요약] {name} — {risk_level} ({risk_score:.2f})",
                "emoji": True,
            },
        },
        {"type": "divider"},

        # ── AI 판단 요약 ───────────────────────────────────────────────
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{_re(rec)} AI 판단: `{rec.upper()}`*  _(신뢰도: {confidence})_\n"
                    f"> {verdict.get('summary', '-')}\n"
                    f"*주요 근거:* {verdict.get('key_reason', '-')}"
                ),
            },
        },
        {"type": "divider"},

        # ── 점수 분해 ─────────────────────────────────────────────────
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": (
                    f"*점수 분해* | "
                    f"동적 `{d.get('score',0):.2f}`×0.65 ({d.get('level','?')})  "
                    f"정적 `{s.get('score',0):.2f}`×0.20 ({s.get('level','?')})  "
                    f"난독화 `{o.get('score',0):.2f}`×0.15 ({o.get('level','?')})"
                ),
            }],
        },
        {"type": "divider"},

        # ── 위험 그룹 ─────────────────────────────────────────────────
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📊 위험 그룹 분석*"},
        },
    ]

    # 4개 그룹을 2열씩 section fields로 표시
    group_defs = [
        ("permission", "권한/접근"),
        ("code",       "코드/난독화"),
        ("behavior",   "동적 행동"),
        ("pattern",    "유사 패턴"),
    ]
    fields: List[Dict] = []
    for key, label in group_defs:
        grp   = groups.get(key, {}) or {}
        level = grp.get("level", "unknown")
        items = grp.get("key_items", []) or []
        note  = grp.get("note", "") or ""
        # Slack section.fields 항목당 2000자 제한 → 안전하게 60자로 자름
        items_str = ", ".join(f"`{str(i)[:60]}`" for i in items[:3]) if items else "-"
        note_str  = str(note)[:20]
        field_text = f"{_le(level)} *{label}* ({level})\n{items_str}\n_{note_str}_"
        fields.append({"type": "mrkdwn", "text": field_text[:2000]})

    blocks.append({"type": "section", "fields": fields[:2]})
    if len(fields) > 2:
        blocks.append({"type": "section", "fields": fields[2:]})

    # ── 불명확한 항목 ──────────────────────────────────────────────────
    if ambiguous:
        amb_lines = "\n".join(
            f"• *{a.get('issue','')}* → {a.get('check','')}"
            for a in ambiguous[:3]
        )
        blocks += [
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*❓ 불명확한 항목*\n{amb_lines}"},
            },
        ]

    # ── 체크리스트 ────────────────────────────────────────────────────
    if checklist:
        check_lines = "\n".join(f"{i+1}. {c}" for i, c in enumerate(checklist[:3]))
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*✅ 담당자 확인 체크리스트*\n{check_lines}"},
        })

    # ── 대시보드 버튼 ─────────────────────────────────────────────────
    blocks += [
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": "📋 세부 분석 보기", "emoji": True},
                "url": dashboard,
                "style": "primary",
                "action_id": "view_dashboard",
            }],
        },
    ]

    return {
        "text": f"[AI 검토 요약] {name} — {rec.upper()} ({risk_level})",
        "blocks": blocks,
    }


def send_to_slack(judgment: dict, web_payload: dict) -> bool:
    url = _webhook_url()
    if not url:
        print("[AI Slack] ❌ SLACK_WEBHOOK_URL 환경변수 미설정 — 전송 건너뜀")
        print("[AI Slack]    .env 파일 또는 환경변수에 SLACK_WEBHOOK_URL=https://hooks.slack.com/... 를 설정하세요.")
        return False

    payload = build_slack_payload(judgment, web_payload)

    # 페이로드 크기 사전 검사 (Slack 제한: 블록 50개, 텍스트 3000자)
    if len(payload.get("blocks", [])) > 50:
        print(f"[AI Slack] ⚠️ 블록 수 초과({len(payload['blocks'])}개) — 잘라냄")
        payload["blocks"] = payload["blocks"][:50]

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass

        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            body = r.read().decode("utf-8", errors="replace")
            print(f"[AI Slack] ✅ 전송 완료 (HTTP {r.status}) body={body[:80]}")
            return True

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[AI Slack] ❌ HTTP {e.code} — Slack 응답: {body[:400]}")
        print("[AI Slack]    흔한 원인: invalid_payload(Block Kit 오류), no_service(웹훅 만료)")
        # 디버그용: 페이로드 일부 출력
        print(f"[AI Slack]    전송 시도한 payload text: {payload.get('text','')[:100]}")
    except Exception as e:
        print(f"[AI Slack] ❌ 전송 실패: {type(e).__name__}: {e}")

    return False
