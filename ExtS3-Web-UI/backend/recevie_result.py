import os

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException
from typing import Dict, Any
from pathlib import Path
import json
import re

router = APIRouter()


def _run_ai_judgment(web_payload: dict, target_dir: Path) -> None:
    """AI 판단 실행 → judgment.json 저장 → Slack 전송 (백그라운드 태스크)"""
    if os.getenv("ENABLE_AI_JUDGMENT", "true").lower() != "true":
        return
    try:
        from backend.ai_judgment.judge import run_judgment
        from backend.ai_judgment.slack import send_to_slack

        judgment = run_judgment(web_payload)

        with open(target_dir / "judgment.json", "w", encoding="utf-8") as f:
            json.dump(judgment, f, ensure_ascii=False, indent=2)
        print(f"[AI Judgment] judgment.json 저장: {target_dir}")

        send_to_slack(judgment, web_payload)

    except Exception as e:
        print(f"[AI Judgment] 백그라운드 오류: {e}")

# 데이터를 저장할 기본 루트 디렉토리
BASE_SAVE_DIR = Path("analysis_result")
POLICY_PATH = Path(__file__).resolve().parent / "admin" / "policy_settings.json"


def safe_path_part(value: Any, default: str) -> str:
    """
    파일/디렉토리 경로에 들어가면 위험한 문자를 정리한다.
    """
    if value is None:
        return default

    text = str(value).strip()
    if not text:
        return default

    # 슬래시, 역슬래시, 제어문자 제거
    text = re.sub(r"[\\/:\*\?\"<>\|\x00-\x1f]", "_", text)

    # 너무 긴 이름 방지
    return text[:120] if text else default


def get_nested(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    payload["web_payload"]["extension"]["browser"] 같은 중첩 값을 안전하게 가져온다.
    """
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _normalize_decision(value: Any) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in {"approve", "safe"}:
        return "safe"
    if lowered in {"reject", "rejected", "critical"}:
        return "reject"
    if lowered in {"review", "manual_review", "hold"}:
        return "review"
    return lowered or "undecided"


def _read_policy() -> Dict[str, Any]:
    default = {
        "critical_auto_reject_enabled": True,
        "low_auto_approve_enabled": False,
        "fallback_decision": "review",
    }
    try:
        if not POLICY_PATH.exists():
            return default
        with POLICY_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            return default
        return {**default, **data, "fallback_decision": "review"}
    except Exception as policy_e:
        print(f"[receive_result] policy read failed: {policy_e}")
        return default


def _apply_auto_policy(raw_decision: Any, recommended_decision: Any, risk_level: Any) -> tuple[str, Dict[str, Any]]:
    policy = _read_policy()
    raw = _normalize_decision(raw_decision)
    recommended = _normalize_decision(recommended_decision)
    risk = str(risk_level or "").strip().upper()

    if recommended == "reject" or risk == "CRITICAL":
        decision = "reject" if policy.get("critical_auto_reject_enabled") else "review"
        reason = "critical_auto_reject" if decision == "reject" else "manual_review"
    elif risk == "LOW" or recommended == "safe" or raw == "safe":
        decision = "safe" if policy.get("low_auto_approve_enabled") else "review"
        reason = "low_auto_approve" if decision == "safe" else "manual_review"
    elif raw == "reject":
        decision = raw
        reason = "explicit_decision"
    else:
        decision = "review"
        reason = "recommended_review"

    return decision, {
        "risk_level": risk or "UNKNOWN",
        "recommended_decision": recommended,
        "incoming_decision": raw,
        "decision": decision,
        "reason": reason,
        "policy": {
            "critical_auto_reject_enabled": bool(policy.get("critical_auto_reject_enabled")),
            "low_auto_approve_enabled": bool(policy.get("low_auto_approve_enabled")),
            "fallback_decision": "review",
        },
    }


def _nexus_status_for_decision(decision: Any) -> str:
    normalized = _normalize_decision(decision)
    if normalized == "safe":
        return "safe"
    if normalized == "reject":
        return "reject"
    return "review"


def _reconcile_nexus_location(
    *,
    decision: str,
    auto_policy: Dict[str, Any],
    browser: str,
    ext_names: list[str],
    version: str,
    ext_id: str,
) -> Dict[str, Any]:
    target_status = _nexus_status_for_decision(decision)
    candidate_statuses = [
        _nexus_status_for_decision(auto_policy.get("incoming_decision")),
        _nexus_status_for_decision(auto_policy.get("recommended_decision")),
    ]
    candidate_statuses = list(dict.fromkeys(candidate_statuses))

    try:
        from backend.admin.decision.nexus_file import (
            build_nexus_path,
            delete_nexus_file,
            fetch_nexus_asset_paths,
            move_nexus_file,
        )

        normalized_names = []
        for name in ext_names:
            text = str(name or "").strip()
            if text and text not in normalized_names:
                normalized_names.append(text)
        if not normalized_names:
            normalized_names.append("unknown_extension")

        target_path = build_nexus_path(target_status, browser, normalized_names[0], version, ext_id)
        asset_paths = fetch_nexus_asset_paths()
        asset_lookup = {path.lower(): path for path in asset_paths}

        if target_status == "reject":
            for status in candidate_statuses:
                for ext_name in normalized_names:
                    source_path = build_nexus_path(status, browser, ext_name, version, ext_id)
                    if source_path.lower() not in asset_lookup:
                        continue
                    resolved_source = asset_lookup[source_path.lower()]
                    delete_nexus_file(resolved_source)
                    return {
                        "status": "deleted",
                        "source_path": resolved_source,
                        "target_path": None,
                        "candidate_statuses": candidate_statuses,
                    }

            return {
                "status": "source_not_found",
                "target_path": None,
                "candidate_statuses": candidate_statuses,
            }

        if target_path.lower() in asset_lookup:
            return {
                "status": "already_target",
                "target_path": asset_lookup[target_path.lower()],
                "candidate_statuses": candidate_statuses,
            }

        for status in candidate_statuses:
            for ext_name in normalized_names:
                source_path = build_nexus_path(status, browser, ext_name, version, ext_id)
                if source_path.lower() not in asset_lookup:
                    continue
                resolved_source = asset_lookup[source_path.lower()]
                move_nexus_file(resolved_source, target_path)
                return {
                    "status": "moved",
                    "source_path": resolved_source,
                    "target_path": target_path,
                    "candidate_statuses": candidate_statuses,
                }

        return {
            "status": "source_not_found",
            "target_path": target_path,
            "candidate_statuses": candidate_statuses,
        }
    except Exception as nexus_e:
        print(f"[receive_result] nexus reconcile failed: {nexus_e}")
        return {
            "status": "error",
            "message": str(nexus_e),
            "candidate_statuses": candidate_statuses,
        }


@router.post("/api/receive")
async def receive_and_save_analysis(
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(...),
):
    try:
        # 새 구조 대응:
        # 1) payload 자체가 web_payload일 수도 있고
        # 2) payload["web_payload"] 안에 새 schema가 들어있을 수도 있다.
        web_payload = payload.get("web_payload")
        if not isinstance(web_payload, dict):
            web_payload = payload

        extension = web_payload.get("extension", {}) if isinstance(web_payload, dict) else {}
        overall = web_payload.get("overall", {}) if isinstance(web_payload, dict) else {}

        # 1. 경로 구성을 위한 정보 추출
        # 기존 legacy top-level 필드 우선, 없으면 새 web_payload 구조에서 추출
        raw_decision = (
            payload.get("decision")
            or payload.get("judge")
            or overall.get("recommended_decision")
            or "undecided"
        )
        decision, auto_policy = _apply_auto_policy(
            raw_decision=raw_decision,
            recommended_decision=overall.get("recommended_decision"),
            risk_level=overall.get("risk_level"),
        )

        browser = (
            payload.get("browser")
            or extension.get("browser")
            or "unknown_browser"
        )

        ext_name = (
            payload.get("extName")
            or payload.get("ext_name")
            or extension.get("name")
            or "unknown_extension"
        )

        version = (
            payload.get("version")
            or extension.get("version")
            or "unknown_version"
        )

        ext_id = (
            payload.get("extID")
            or payload.get("ext_id")
            or extension.get("extension_id")
            or "unknown_id"
        )

        raw_ext_name = str(ext_name or "").strip()
        decision = safe_path_part(decision, "undecided")
        browser = safe_path_part(browser, "unknown_browser")
        ext_name = safe_path_part(ext_name, "unknown_extension")
        version = safe_path_part(version, "unknown_version")
        ext_id = safe_path_part(ext_id, "unknown_id")
        nexus_reconcile = _reconcile_nexus_location(
            decision=decision,
            auto_policy=auto_policy,
            browser=browser,
            ext_names=[ext_name, raw_ext_name],
            version=version,
            ext_id=ext_id,
        )

        # 2. 저장 경로 생성
        # analysis_result/{decision}/{browser}/{extName}/{version}/{extID}
        target_dir = BASE_SAVE_DIR / decision / browser / ext_name / version / ext_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # 3. 상세 분석 결과 추출
        full_details = payload.get("full_details")

        # full_details가 없거나 비어 있으면 새 web_payload 요약을 최소 저장
        if not isinstance(full_details, dict) or not full_details:
            full_details = {
                "summary_detail": web_payload
            }

        # 4. 각 상세 항목을 개별 JSON 파일로 저장
        saved_files = []
        for key, content in full_details.items():
            safe_key = safe_path_part(key, "detail")
            file_name = f"{safe_key.replace('_detail', '')}.json"
            file_path = target_dir / file_name

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)

            saved_files.append(file_name)

        # 5. final_risk_summary 보정
        final_risk_summary = payload.get("final_risk_summary")

        if not isinstance(final_risk_summary, dict):
            final_risk_summary = {
                "risk_level": overall.get("risk_level", "UNKNOWN"),
                "risk_score": overall.get("risk_score", 0.0),
                "recommended_decision": overall.get("recommended_decision", decision),
                "decision_reason": overall.get("decision_reason", ""),
                "severity_counts": overall.get("severity_counts", {}),
                "weights": overall.get("weights", {}),
                "component_scores": overall.get("component_scores", {}),
            }

        # 6. 요약 정보 및 메타데이터 저장
        summary_data = {
            "judge": decision,
            "decision": decision,
            "final_risk_summary": final_risk_summary,
            "summary": payload.get("summary") or {
                "risk_level": overall.get("risk_level", "UNKNOWN"),
                "risk_score": overall.get("risk_score", 0.0),
                "recommended_decision": overall.get("recommended_decision", decision),
                "decision_reason": overall.get("decision_reason", ""),
            },
            "auto_policy": auto_policy,
            "nexus_reconcile": nexus_reconcile,
            "metadata": {
                "extID": ext_id,
                "extName": ext_name,
                "browser": browser,
                "version": version,
                "schema_version": web_payload.get("schema_version") if isinstance(web_payload, dict) else None,
                "payload_type": web_payload.get("payload_type") if isinstance(web_payload, dict) else None,
            },
            "web_payload": web_payload,
        }

        with open(target_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        decision_rag_result = payload.get("decision_rag_result")
        if not isinstance(decision_rag_result, dict) and isinstance(web_payload, dict):
            decision_rag_result = web_payload.get("decision_rag_result")

        if isinstance(decision_rag_result, dict) and decision_rag_result:
            with open(target_dir / "decision_rag_result.json", "w", encoding="utf-8") as f:
                json.dump(decision_rag_result, f, ensure_ascii=False, indent=2)
            saved_files.append("decision_rag_result.json")

        print(f"[receive_result] data saved: {target_dir.absolute()}")

        # review 판정인 경우 AI 판단 백그라운드 실행
        if decision == "review":
            background_tasks.add_task(_run_ai_judgment, web_payload, target_dir)

        return {
            "status": "success",
            "message": f"Results saved to {target_dir}",
            "path": str(target_dir),
            "saved_files": saved_files + ["summary.json"],
            "metadata": summary_data["metadata"],
            "decision": decision,
        }

    except Exception as e:
        print(f"[receive_result] data save error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
