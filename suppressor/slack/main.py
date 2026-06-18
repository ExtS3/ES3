import argparse
import json
import os
import urllib.parse
from typing import Any, Dict, List, Optional

ScanResultCount = Dict[str, int]
ProgramScan = Dict[str, Any]
ScanResults = List[ProgramScan]

#환경 변수 불러오기 (Slack URL, Admin Dashboard)
def load_dotenv(dotenv_path: Optional[str] = None) -> None:
    if dotenv_path is None:
        dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(dotenv_path):
        return

    try:
        with open(dotenv_path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass

#Dashboard URL 생성
def make_dashboard_url(
    extension_id: str,
    program_name: str,
    browser: str,
    version: str,
) -> str:
    encoded_id = urllib.parse.quote_plus(extension_id or "")
    encoded_name = urllib.parse.quote_plus(program_name)
    encoded_browser = urllib.parse.quote_plus(browser or "")
    encoded_version = urllib.parse.quote_plus(version or "")

    base_url = os.getenv("DASHBOARD_BASE_URL", "").rstrip("/")
    path = (
        f"/admin/log?id={encoded_id}"
        f"&name={encoded_name}"
        f"&browser={encoded_browser}"
        f"&version={encoded_version}"
    )

    if base_url:
        return f"{base_url}{path}"
    return path

#탐지 결과 검증 후 딕셔너리 반환
def normalize_scan_input(scan_input: Any) -> ScanResults:
    if isinstance(scan_input, dict):
        programs = [scan_input]
    elif isinstance(scan_input, list):
        programs = scan_input
    else:
        raise ValueError("scan_input must be a dict or a list of dicts")

    normalized_results: ScanResults = []
    for program in programs:
        if not isinstance(program, dict):
            raise ValueError("Each program input must be a JSON object")

        extension_id = str(program.get("extension_id") or program.get("id") or "")
        program_name = program.get("program_name", "unknown")
        program_type = program.get("program_type", "unknown")
        browser = str(program.get("browser") or "").strip()
        if not browser:
            browser = str(program_type or "unknown").strip()
            if browser.lower().endswith(" extension"):
                browser = browser[: -len(" extension")].strip()
        version = str(program.get("version") or "unknown")
        scan_result = program.get("scan_result")
        if not isinstance(scan_result, dict):
            raise ValueError("scan_result must be an object with severity counts")

        normalized_results.append(
            {
                "extension_id": extension_id,
                "program_type": program_type,
                "browser": browser,
                "version": version,
                "program_name": program_name,
                "dashboard_url": make_dashboard_url(extension_id, program_name, browser, version),
                "scan_result": {
                    "critical": int(scan_result.get("critical", 0) or 0),
                    "high": int(scan_result.get("high", 0) or 0),
                    "medium": int(scan_result.get("medium", 0) or 0),
                    "low": int(scan_result.get("low", 0) or 0),
                },
            }
        )

    return normalized_results

#스캔 결과 기반으로 위험, 검토필요, 안전 판단
def score_scan_results(results: ScanResults) -> str:
    totals = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in results:
        scan_result = item.get("scan_result", {})
        totals["critical"] += scan_result.get("critical", 0)
        totals["high"] += scan_result.get("high", 0)
        totals["medium"] += scan_result.get("medium", 0)
        totals["low"] += scan_result.get("low", 0)

    if totals["critical"] == 0 and totals["high"] == 0 and totals["medium"] == 0 and totals["low"] >= 1:
        return "safe"
    return "review"


#Slack 전송 메시지 생성 함수
def build_slack_payload(result_label: str, results: ScanResults) -> Dict[str, Any]:
    status_emoji = {
        "review": "🟡",
        "high": "🔴",
    }.get(result_label, "⚪")
    for idx, item in enumerate(results, start=1):

        program_name = item.get("program_name", "unknown")
        scan_result = item.get("scan_result", {})
        program_type = item.get("program_type", "unknown")
        dashboard_url = item.get("dashboard_url", "")
        
        blocks: List[Dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} {program_name} Scan result - {result_label.upper()} {status_emoji}",
                }
            },
            {"type": "divider"},
        ]

        section_block: Dict[str, Any] = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Program Name* : {program_name}\n"
                    f"*Program Type* : {program_type}\n"
                    f"*Scan Result* : critical `{scan_result.get('critical', 0)}` / "
                    f"high `{scan_result.get('high', 0)}` / "
                    f"medium `{scan_result.get('medium', 0)}` / "
                    f"low `{scan_result.get('low', 0)}`"
                ),
            }
        }

        section_block["accessory"] = {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "세부정보",
                "emoji": True,
            },
            "url": dashboard_url,
            "action_id": f"open_dashboard_{idx}",
        }

        blocks.append(section_block)
        blocks.append({"type": "divider"})

    return {
        "text": f"{status_emoji} Scan result: {result_label.upper()}",
        "blocks": blocks,
    }

#Slack에 알림 전송
def send_slack_notification(payload: Dict[str, Any]) -> bool:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("[SLACK] Webhook not configured. Payload below:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return False

    try:
        import ssl
        import urllib.request
        import urllib.error
    except Exception:
        print("[SLACK] Unable to import required networking modules.")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return False

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        context = ssl.create_default_context()
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass

        with urllib.request.urlopen(request, timeout=10, context=context) as response:
            response_text = response.read().decode("utf-8", errors="replace")
            print(f"[SLACK] Notification sent. Response: {response.status} {response_text}")
            return True

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"[SLACK] HTTP Error: {exc.code} {exc.reason}")
        print(f"[SLACK] Response body: {error_body}")
        print("[SLACK] Payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return False

    except Exception as exc:
        print(f"[SLACK] Failed to send notification: {exc}")
        print("[SLACK] Payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return False

#Slack 전송 결과 출력
def summarize_flow(result_label: str, sent_slack: bool) -> None:
    if result_label == "safe":
        print("Result: SAFE — no Slack notification needed.")
        print("Action: OK")
        return
    if sent_slack:
        print(f"Result: {result_label.upper()} — Slack notification sent.")
    else:
        print(f"Result: {result_label.upper()} — Slack notification not sent.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score scan results from JSON input and optionally notify Slack.")
    parser.add_argument(
        "--scan-json",
        help="Scan input JSON string. Example: '{\"program_name\": \"확장 프로그램 이름\", \"program_type\": \"크롬\", \"scan_result\": {...}}'",
    )
    parser.add_argument(
        "--scan-file",
        help="Path to a JSON file containing scan input.",
    )
    return parser.parse_args()

def run_with_scan_input(scan_input: Any) -> Dict[str, Any]:
    load_dotenv()
    results = normalize_scan_input(scan_input)
    decision = score_scan_results(results)

    # Optional override from upstream weighted decision/risk_level.
    # - reject/high/critical/review/medium => "review" (always notify)
    # - approve/low => "safe"
    if isinstance(scan_input, dict):
        upstream_decision = str(scan_input.get("decision", "")).strip().lower()
        upstream_risk = str(scan_input.get("risk_level", "")).strip().lower()

        if upstream_decision in {"reject", "high", "critical", "review", "medium", "meduim"}:
            decision = "review"
        elif upstream_decision in {"approve", "safe", "low"}:
            decision = "safe"
        else:
            if upstream_risk in {"critical", "high", "medium", "meduim"}:
                decision = "review"
            elif upstream_risk == "low":
                decision = "safe"

    sent_slack = False
    payload: Dict[str, Any] | None = None
    if decision != "safe":
        payload = build_slack_payload(decision, results)
        sent_slack = send_slack_notification(payload)

    summarize_flow(decision, sent_slack)
    return {
        "decision": decision,
        "sent_slack": sent_slack,
        "results": results,
        "payload": payload,
    }

def main() -> None:
    args = parse_args()

    if args.scan_file:
        with open(args.scan_file, encoding="utf-8") as file:
            scan_input = json.load(file)
    elif args.scan_json:
        scan_input = json.loads(args.scan_json)
    else:
        raise SystemExit("Error: --scan-json or --scan-file is required.")

    results = normalize_scan_input(scan_input)
    decision = score_scan_results(results)

    print("=== Scan results ===")
    flow = run_with_scan_input(scan_input)
    print(json.dumps(flow["results"], indent=2, ensure_ascii=False))
    print(f"Decision: {flow['decision']}")

if __name__ == "__main__":
    main()
