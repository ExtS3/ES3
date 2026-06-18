import os
import shutil
import traceback
import threading
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
import json
from collections import Counter
from fastapi.concurrency import run_in_threadpool

# 모듈 로드
from backend.extanalysis_integration import run_extanalysis_and_static_scan

from backend.scanners.minify_obfuscation import PracticalScanner
obf_runner = PracticalScanner()

# Backend API Routes
from urllib.parse import quote, unquote
from fastapi import HTTPException, Form
import requests
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

import sys

# 스캔이 한 번에 한 번만 되도록 줄 세우기.
from asyncio import Semaphore

# 한 번에 1개의 스캔만 허용하는 세마포어 생성
scan_semaphore = Semaphore(1)

load_dotenv()

BASE_DIR = Path(__file__).parent

# hm_new 스케줄러
from hm_new import start as hm_start, stop as hm_stop

# retro 모니터
if str(BASE_DIR / "retro") not in sys.path:
    sys.path.append(str(BASE_DIR / "retro"))

try:
    from retro.retro_monitor import Settings, RetroMonitor, configure_logging
    _retro_available = True
except ImportError as e:
    print(f"⚠️ RetroMonitor Import Failed: {e}")
    _retro_available = False

try:
    from slack.main import run_with_scan_input as run_slack_with_scan_input
    _slack_available = True
except Exception as slack_import_e:
    print(f"⚠️ Slack import failed: {slack_import_e}")
    run_slack_with_scan_input = None
    _slack_available = False


def run_retro_monitor():
    if not _retro_available:
        return
    try:
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        monitor = RetroMonitor(settings)
        print("🚀 [Retro] Background Monitor Starting...")
        monitor.run_forever()
    except Exception as e:
        print(f"❌ [Retro] Runtime Error: {e}")


# ✅ lifespan은 단 하나 — hm_new 스케줄러 + retro 스레드 모두 여기서 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. hm_new 홀딩 스케줄러 시작
    try:
        from embedding.base_db import ensure_knowledge_base_seeded

        await run_in_threadpool(ensure_knowledge_base_seeded)
    except Exception as seed_e:
        print(f"[pgvector] startup seed check failed: {seed_e}")

    hm_start()
    print("📢 [System] hm_new scheduler started.")

    # 2. retro 백그라운드 스레드 시작
    retro_thread = threading.Thread(target=run_retro_monitor, daemon=True)
    retro_thread.start()
    print("📢 [System] Retro background thread spawned.")

    yield

    # 종료 시 스케줄러 정리
    hm_stop()
    print("📢 [System] hm_new scheduler stopped.")


app = FastAPI(lifespan=lifespan)

from send_web import send_web
from backend.web_payload import build_web_payload
from backend.risk_scoring import calculate_weighted_final_risk

# 라우터 등록
from holding import router as holding_router
app.include_router(holding_router)

# 시나리오 지식베이스 관리 (Web-UI 시나리오 관리 페이지가 프록시로 호출)
from embedding.scenario_router import router as scenario_router
app.include_router(scenario_router)

UPLOAD_DIR = "./storage"
os.makedirs(UPLOAD_DIR, exist_ok=True)

SEVERITY_KEYS = ("critical", "high", "medium", "low")


def _normalize_severity(value: object) -> str | None:
    if value is None:
        return None

    lowered = str(value).strip().lower()
    mapping = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "치명": "critical",
        "높음": "high",
        "보통": "medium",
        "낮음": "low",
    }
    return mapping.get(lowered)


def _extract_single_risk(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get("result_risk"),
        payload.get("final_severity"),
        payload.get("overall_risk"),
        payload.get("recommended_risk"),
    ]
    for candidate in candidates:
        normalized = _normalize_severity(candidate)
        if normalized:
            return normalized
    return None


def _browser_to_program_type(browser: str) -> str:
    lowered = (browser or "").strip().lower()
    mapping = {
        "chrome": "Chrome Extension",
        "edge": "Edge Extension",
        "firefox": "Firefox Extension",
        "opera": "Opera Extension",
    }
    return mapping.get(lowered, f"{browser} Extension" if browser else "Extension")


def _decision_to_nexus_bucket(decision: str) -> str:
    lowered = str(decision or "").strip().lower()
    if lowered == "safe":
        return "safe"
    if lowered in {"reject", "high", "critical"}:
        return "review"
    return "review"


def _build_version_diff_payload(snapshot_diff: dict | None, current_version: str) -> dict:
    """Extension Profile 의 diff_from_previous 를 웹 UI 용 페이로드로 변환한다.

    - summary: 변경 사항 박스에 표시할 개수 요약
    - diff: GitHub 스타일 상세 페이지에서 사용할 전체 변경 내역
    snapshot_diff 가 None 이면(최초 버전) has_previous=False 로 반환한다.
    """
    if not isinstance(snapshot_diff, dict):
        return {
            "has_previous": False,
            "previous_version": None,
            "current_version": current_version,
            "summary": {
                "permissions_added": 0,
                "permissions_removed": 0,
                "host_permissions_added": 0,
                "host_permissions_removed": 0,
                "optional_permissions_added": 0,
                "optional_permissions_removed": 0,
                "permission_changes": 0,
                "manifest_changes": 0,
                "files_added": 0,
                "files_removed": 0,
                "files_modified": 0,
                "code_changes": 0,
            },
            "diff": None,
        }

    def _delta(key: str) -> dict:
        d = snapshot_diff.get(key) or {}
        return {"added": d.get("added") or [], "removed": d.get("removed") or []}

    perms = _delta("permissions")
    host = _delta("host_permissions")
    optional = _delta("optional_permissions")
    manifest_changes = snapshot_diff.get("manifest_changes") or []
    files = snapshot_diff.get("files") or {}
    files_added = files.get("added") or []
    files_removed = files.get("removed") or []
    files_modified = files.get("modified") or []

    permission_changes = (
        len(perms["added"]) + len(perms["removed"])
        + len(host["added"]) + len(host["removed"])
        + len(optional["added"]) + len(optional["removed"])
    )
    code_changes = len(files_added) + len(files_removed) + len(files_modified)

    return {
        "has_previous": True,
        "previous_version": snapshot_diff.get("previous_version"),
        "current_version": current_version,
        "summary": {
            "permissions_added": len(perms["added"]),
            "permissions_removed": len(perms["removed"]),
            "host_permissions_added": len(host["added"]),
            "host_permissions_removed": len(host["removed"]),
            "optional_permissions_added": len(optional["added"]),
            "optional_permissions_removed": len(optional["removed"]),
            "permission_changes": permission_changes,
            "manifest_changes": len(manifest_changes),
            "files_added": len(files_added),
            "files_removed": len(files_removed),
            "files_modified": len(files_modified),
            "code_changes": code_changes,
        },
        "diff": snapshot_diff,
    }


def _is_valid_embedding_vector(value: object) -> bool:
    if not isinstance(value, list) or len(value) == 0:
        return False
    return all(isinstance(v, (int, float)) for v in value)


def _build_embedding_failed_result(message: str) -> dict:
    return {
        "status": "error",
        "error_type": "EmbeddingError",
        "message": "RAG embedding failed; vector DB search and dynamic scenario execution were skipped.",
        "error": message,
        "final_risk": {
            "risk_level": "UNKNOWN",
            "risk_score": 0.0,
            "reason": "RAG embedding failed before scenario matching",
            "matched_scenarios": [],
            "risk_factors": ["embedding_failed"],
            "safety_violation": False,
        },
        "selected_matches_summary": [],
        "scenario_results_summary": [],
        "notes": ["embedding_failed", "vector_db_search_skipped", "dynamic_rag_skipped"],
    }


def _merge_cleanup_observation(dynamic_payload: dict, cleanup_observation: dict | None) -> None:
    if not isinstance(dynamic_payload, dict) or not isinstance(cleanup_observation, dict):
        return
    ex = cleanup_observation.get("execution", {}) if isinstance(cleanup_observation.get("execution", {}), dict) else {}
    if not ex:
        return
    keys = (
        "cleanup_started",
        "cleanup_completed",
        "cleanup_error",
        "cleanup_closed_context",
        "cleanup_stopped_playwright",
        "cleanup_removed_user_data_dir",
        "cleanup_removed_unpacked_dir",
        "cleanup_removed_user_data_dir_not_applicable",
        "cleanup_removed_unpacked_dir_not_applicable",
        "real_network_used",
        "intercepted_by_harness",
        "external_request_attempted",
        "external_request_blocked",
        "external_request_count",
        "blocked_external_request_count",
        "blocked_external_requests",
        "external_request_failed",
        "external_request_block_source",
        "external_request_outcome",
        "unsafe_request_url",
        "unsafe_request_host",
        "extension_load_warning",
        "content_script_probe_warning",
        "page_load_error",
        "page_load_started",
        "page_load_completed",
        "open_mock_page_attempted",
        "open_mock_page_succeeded",
        "content_script_probe_attempted",
        "page_response_status",
        "page_load_warning",
        "goto_called",
        "goto_completed",
        "wait_for_load_state_called",
        "wait_for_load_state_completed",
        "wait_for_load_state_error",
        "mock_server_check_attempted",
        "mock_server_autostart_enabled",
        "mock_server_autostarted",
        "mock_server_host",
        "mock_server_port",
        "mock_server_url",
        "mock_server_reachable",
        "mock_server_status_code",
        "mock_server_error",
        "mock_server_stopped",
        "mock_server_stop_error",
        "actual_page_url",
        "expected_target_url",
        "content_script_not_executed_reason",
        "headless",
        "headless_source",
        "dynamic_harness_headless_env",
    )
    summary_rows = dynamic_payload.get("scenario_results_summary", [])
    if isinstance(summary_rows, list):
        for row in summary_rows:
            if isinstance(row, dict):
                for key in keys:
                    row[key] = ex.get(key, row.get(key))
                ar = row.get("agent_result", {}) if isinstance(row.get("agent_result", {}), dict) else {}
                totals = ar.get("observation_totals", {}) if isinstance(ar.get("observation_totals", {}), dict) else {}
                for key in keys:
                    totals[key] = ex.get(key, totals.get(key))
                if ar:
                    ar["observation_totals"] = totals
                    row["agent_result"] = ar
    final_risk = dynamic_payload.get("final_risk", {}) if isinstance(dynamic_payload.get("final_risk", {}), dict) else {}
    for key in ("real_network_used", "intercepted_by_harness", "external_request_attempted", "external_request_blocked"):
        final_risk[key] = ex.get(key, final_risk.get(key, False))
    if final_risk:
        dynamic_payload["final_risk"] = final_risk


def build_final_risk_summary(
    extension_id: str,
    ext_name: str,
    browser: str,
    version: str,
    static_result_bundle: dict,
    dynamic_result: dict,
    obfuscation_result: dict,
) -> dict:
    counts: Counter = Counter({key: 0 for key in SEVERITY_KEYS})

    static_scan = (
        static_result_bundle.get("static_analysis", {}).get("scan_result", {})
        if isinstance(static_result_bundle, dict)
        else {}
    )
    if isinstance(static_scan, dict):
        for key in SEVERITY_KEYS:
            counts[key] += int(static_scan.get(key, 0) or 0)

    for payload in (dynamic_result, obfuscation_result):
        severity = _extract_single_risk(payload)
        if severity:
            counts[severity] += 1

    return {
        "extension_id": extension_id or "",
        "program_name": ext_name or "unknown",
        "program_type": _browser_to_program_type(browser),
        "browser": browser or "unknown",
        "version": version or "unknown",
        "scan_result": {key: int(counts[key]) for key in SEVERITY_KEYS},
    }

# VSCode(VSIX) 전용 스캔 흐름. Chrome 경로와 완전히 분리된 additive 처리.
# 동적분석을 skip하고 정적 룰만 사용하며, vscode_analysis.decision으로 판정한다.
async def _run_vscode_scan(
    *,
    file: UploadFile,
    file_path: str,
    extID: str,
    browser: str,
    version: str,
    extName: str,
) -> dict:
    from backend.vscode_analysis.runner import run_vscode_static_analysis

    vscode_result = await run_in_threadpool(run_vscode_static_analysis, file_path)

    # 동적/난독화는 VSCode에서 실행하지 않음 (skipped)
    dynamic_result = {"status": "skipped"}
    obfuscation_analysis = {"status": "skipped"}

    # build_web_payload가 기대하는 static_result 번들 형태로 감싼다.
    full_result = {
        "status": "success" if vscode_result.get("status") == "ok" else "error",
        "analysis_id": None,
        "static_analysis": vscode_result,
    }

    vscode_decision = vscode_result.get("decision", {}) or {}
    # decision.py: suggest_reject=True면 reject 의도(build_web_payload가 review로 강등),
    # 그 외엔 review. VSCode Tier1은 자동 approve 없음.
    decision = "reject" if vscode_decision.get("suggest_reject") else "review"

    final_risk_summary = build_final_risk_summary(
        extension_id=extID,
        ext_name=extName,
        browser=browser,
        version=version,
        static_result_bundle=full_result,
        dynamic_result=dynamic_result,
        obfuscation_result=obfuscation_analysis,
    )
    scan_counts = final_risk_summary["scan_result"]
    if scan_counts.get("critical", 0) > 0:
        final_risk_summary["risk_level"] = "CRITICAL"
    elif scan_counts.get("high", 0) > 0:
        final_risk_summary["risk_level"] = "HIGH"
    elif scan_counts.get("medium", 0) > 0:
        final_risk_summary["risk_level"] = "MEDIUM"
    else:
        final_risk_summary["risk_level"] = "LOW"
    final_risk_summary["recommended_decision"] = "review"
    final_risk_summary["decision_reason"] = vscode_decision.get("reason", "")

    _fired = sorted({(f.get("rule_id") or f.get("rule") or "?") for f in vscode_result.get("findings", [])})
    print(
        f"[VSCODE-SCAN] ext={extName}({extID}) v{version} "
        f"counts={vscode_result.get('scan_result')} fired={_fired} "
        f"decision={decision} suggest_reject={vscode_decision.get('suggest_reject')} "
        f"reason={vscode_decision.get('reason')}",
        flush=True,
    )

    web_payload = build_web_payload(
        ext_id=extID,
        ext_name=extName,
        browser=browser,
        version=version,
        file_name=file.filename,
        static_result=full_result,
        obfuscation_result=obfuscation_analysis,
        dynamic_result=dynamic_result,
        rag_fingerprint_result={},
        rag_rerank_result={},
        final_risk_summary=final_risk_summary,
        decision=decision,
    )

    # 대시보드 표시 교정: VSCode는 dynamic 부재라 build_web_payload가 overall.risk_level을
    # LOW로 깔 수 있다. 정적 severity 기반 값으로 교정 (공유 web_payload.py 미수정, 본 분기에서만).
    if isinstance(web_payload.get("overall"), dict):
        web_payload["overall"]["risk_level"] = final_risk_summary["risk_level"]

    # Nexus review/ 업로드 — 대시보드('승인 대기중인 앱')가 Nexus review 폴더를 읽으므로 필요.
    # Chrome 경로(main.py nexus upload 블록)와 동일 함수·정책 재사용.
    if os.getenv("ENABLE_NEXUS_UPLOAD", "true").strip().lower() == "true":
        try:
            await file.seek(0)
            nexus_bucket = _decision_to_nexus_bucket(decision)
            await upload_plugin(
                browser=browser, extID=extID, version=version,
                file=file, extName=extName, judge=decision, decision=nexus_bucket,
            )
            print(f"✅ [VSCODE Nexus] {extID} → {nexus_bucket} 업로드 완료", flush=True)
        except Exception as nexus_e:
            print(f"⚠️ [VSCODE Nexus] 업로드 실패: {str(nexus_e).strip() or repr(nexus_e)}", flush=True)

    # Web UI(/api/receive)로 결과 전달 — Chrome 경로와 동일 ENABLE_WEB_FORWARD 정책.
    if os.getenv("ENABLE_WEB_FORWARD", "false").strip().lower() == "true":
        try:
            await send_web(web_payload)
            print(f"✅ [VSCODE Web-Forward] {extID} 전송 완료", flush=True)
        except Exception as web_e:
            print(f"⚠️ [VSCODE Web-Forward] 전송 실패: {str(web_e).strip() or repr(web_e)}", flush=True)

    return {
        "status": "success",
        "analysis_id": None,
        "extension_id": final_risk_summary["extension_id"],
        "program_name": final_risk_summary["program_name"],
        "program_type": final_risk_summary["program_type"],
        "scan_result": final_risk_summary["scan_result"],
        "final_risk_summary": final_risk_summary,
        "static_result": vscode_result,
        "dynamic_result": dynamic_result,
        "obfuscation_result": obfuscation_analysis,
        "vscode_decision": vscode_decision,
        "web_payload": web_payload,
    }


@app.post("/file_scan")
async def scan(
    file: UploadFile = File(...),
    extID: str = Form(...),
    browser: str = Form(...),
    version: str = Form(...),
    extName: str = Form(...)
):
    async with scan_semaphore:
        file_path = os.path.abspath(os.path.join(UPLOAD_DIR, file.filename))
        path_obj = Path(file_path)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # VSCode(VSIX)는 동적분석 불가 → 전용 정적 흐름으로 early-branch.
        # Chrome/기타 브라우저는 아래 기존 경로를 그대로 탄다 (불변).
        if (browser or "").strip().lower() == "vscode":
            try:
                return await _run_vscode_scan(
                    file=file,
                    file_path=file_path,
                    extID=extID,
                    browser=browser,
                    version=version,
                    extName=extName,
                )
            except Exception as vscode_e:
                print("\n" + "=" * 50)
                print("❌ VSCode 정적 분석 파이프라인 에러:")
                traceback.print_exc()
                print("=" * 50 + "\n")
                return {"status": "error", "message": str(vscode_e)}

        dynamic_result = {"status": "skipped"}
        full_result = {
            "status": "skipped",
            "analysis_id": None,
            "static_analysis": {},
        }
        obfuscation_analysis = {"status": "skipped"}
        decision = "unknown"

        rag_fingerprint_result = {}
        rag_rerank_result = {}
        dynamic_rag_result = {}
        final_risk = "LOW"
        dynamic_harness = None

        try:
            # --- 1. RAG 핑거프린트 정적 분석 + Vector 검색 + Rerank + Dynamic RAG ---
            print(">>>> RAG 분석 실행")

            try:
                # 1. 확장 프로그램 코드 기반 vector_fingerprint 생성
                from Dynamic_RAG.rag_fingerprint.analyzer import analyze_extension_static

                rag_raw = await run_in_threadpool(
                    analyze_extension_static,
                    file_path,   # 업로드된 확장 zip 또는 디렉터리 절대 경로
                    None,        # output_dir=None이면 파일 저장 없이 dict만 반환
                    False,       # include_declared_third_party
                )

                rag_fingerprint_result = rag_raw.get("vector_fingerprint", {})

                if not rag_fingerprint_result:
                    raise RuntimeError("RAG vector_fingerprint 생성 결과가 비어 있습니다.")

                print(f"✅ RAG 핑거프린트 추출 완료: {rag_fingerprint_result}")

                # 2. vector_fingerprint 임베딩
                from embedding.embed import embed_fingerprint

                embedding_vector = embed_fingerprint(rag_fingerprint_result)
                if not _is_valid_embedding_vector(embedding_vector):
                    raise RuntimeError("embedding_failed: empty embedding vector")
                print(f"✅ RAG 임베딩 생성 완료: dim={len(embedding_vector)}")

                # 3. Vector DB 1차 검색
                from embedding.compare import compareDB

                if not _is_valid_embedding_vector(embedding_vector):
                    print("❌ Vector DB 검색 스킵: empty embedding vector", flush=True)
                    raise RuntimeError("embedding_vector_empty")
                compare_result = compareDB(embedding_vector)

                if compare_result is None:
                    raise RuntimeError("Vector DB compareDB 결과가 None입니다.")

                print(f"✅ Vector DB 1차 검색 완료: count={len(compare_result) if isinstance(compare_result, list) else 'unknown'}")

                # 4. Vector DB 후보 rerank
                from embedding.rerank import rerank_compare_result

                rag_rerank_result = rerank_compare_result(
                    query_fingerprint=rag_fingerprint_result,
                    compare_result=compare_result,
                    min_final_score=0.0,
                    extension_target=file_path,
                )

                top_match = None
                try:
                    top_match = rag_rerank_result.get("reranked_matches", [])[0]
                except Exception:
                    top_match = None
                try:
                    top_candidates = []
                    for m in rag_rerank_result.get("reranked_matches", [])[:3]:
                        if not isinstance(m, dict):
                            continue
                        top_candidates.append(
                            {
                                "pattern_name": m.get("pattern_name"),
                                "score": m.get("final_score"),
                                "candidate_only": True,
                                "threshold_passed": float(m.get("final_score", 0.0) or 0.0) >= 0.35,
                                "concrete_api_evidence": m.get("concrete_api_evidence", []),
                            }
                        )
                    print(
                        "vector_top_pattern=",
                        rag_rerank_result.get("vector_top_pattern"),
                        "score=",
                        rag_rerank_result.get("vector_top_score"),
                    )
                    print(
                        "evidence_rerank_top_pattern=",
                        rag_rerank_result.get("evidence_rerank_top_pattern"),
                        "score=",
                        rag_rerank_result.get("evidence_rerank_top_score"),
                        "concrete_api_evidence=",
                        (rag_rerank_result.get("reranked_matches", [{}])[0] or {}).get("concrete_api_evidence", []),
                    )
                    print("top_candidate_patterns=", top_candidates)
                    if top_candidates:
                        print(
                            f"Candidate preserved: true candidate_only=true threshold=0.35",
                            flush=True,
                        )
                except Exception:
                    pass
                if top_match:
                    print(
                        "✅ RAG rerank 완료:",
                        "top_pattern=", top_match.get("pattern_name"),
                        "score=", top_match.get("final_score"),
                    )
                else:
                    print("✅ RAG rerank 완료")

                # 5. Playwright Dynamic Harness 준비
                from embedding.scenario import (
                    DynamicActionAdapter,
                    run_multi_scenario_dynamic_rag_analysis,
                    resolve_dynamic_target_url,
                    compact_result_one_line_summary,
                    compact_result_json_line,
                )
                from embedding.scenario.playwright_dynamic_harness import PlaywrightDynamicHarness


                preferred_target_url = resolve_dynamic_target_url(rag_fingerprint_result)
                if not preferred_target_url:
                    preferred_target_url = "http://127.0.0.1:8080/mock/index.html"
                print("resolved dynamic target url:", preferred_target_url)
                print("[file_scan] Dynamic RAG will run in threadpool", flush=True)
                print(f"[file_scan] DYNAMIC_HARNESS_HEADLESS={os.getenv('DYNAMIC_HARNESS_HEADLESS')}", flush=True)
                try:
                    loop = asyncio.get_running_loop()
                    print(
                        f"[thread_diag] location=main_before_threadpool thread={threading.current_thread().name} "
                        f"running_loop=True loop_id={id(loop)}",
                        flush=True,
                    )
                except RuntimeError:
                    print(
                        f"[thread_diag] location=main_before_threadpool thread={threading.current_thread().name} "
                        "running_loop=False loop_id=None",
                        flush=True,
                    )

                dynamic_harness = PlaywrightDynamicHarness(
                    extension_target=file_path,
                    mock_page_url="http://127.0.0.1:8080/mock/index.html",
                    receiver_origin="http://127.0.0.1:9999",
                    intercept_mock_receiver=True,
                    preferred_target_url=preferred_target_url,
                )

                adapter = DynamicActionAdapter(dynamic_harness)

                dynamic_rag_result = await run_in_threadpool(
                    run_multi_scenario_dynamic_rag_analysis,
                    vector_fingerprint=rag_fingerprint_result,
                    rerank_result=rag_rerank_result,
                    execute_action=adapter.execute_action,
                    target_url=preferred_target_url,
                    response_mode="compact",
                )

                print(compact_result_one_line_summary(dynamic_rag_result))
                try:
                    fr = dynamic_rag_result.get("final_risk", {}) if isinstance(dynamic_rag_result, dict) else {}
                    scenarios = dynamic_rag_result.get("scenario_results_summary", []) if isinstance(dynamic_rag_result, dict) else []
                    first = scenarios[0] if isinstance(scenarios, list) and scenarios else {}
                    totals = (
                        first.get("agent_result", {}).get("observation_totals", {})
                        if isinstance(first, dict)
                        else {}
                    )
                    print(
                        "Dynamic RAG runtime flags:",
                        f"headless={totals.get('headless')}",
                        f"extension_loaded={totals.get('extension_loaded')}",
                        f"service_worker_ready={totals.get('service_worker_ready')}",
                        f"cleanup_completed={totals.get('cleanup_completed')}",
                    )
                except Exception:
                    pass

                # 6. LLM dynamic agent + Playwright harness 실행 + evidence scoring + 최종 위험도 산출
                #
                # 주의:
                # - 여기서 load_extension/open_mock_page/seed_dummy_local_storage를 직접 호출하지 않는다.
                # - LLM이 scenario 문서를 보고 action을 생성한다.
                # - DynamicActionAdapter가 action을 PlaywrightDynamicHarness로 라우팅한다.

                final_risk = (
                    dynamic_rag_result
                    .get("final_risk", {})
                    .get("risk_level", "LOW")
                )

                dynamic_result = dynamic_rag_result

                print("✅ Dynamic RAG 완료")
                print(compact_result_json_line(dynamic_rag_result))
                print(f"✅ 최종 RAG 위험도: {final_risk}")

            except Exception as rag_e:
                rag_detail = str(rag_e).strip() or repr(rag_e)
                if "embedding_failed" in rag_detail or "embedding_vector_empty" in rag_detail:
                    print(f"❌ RAG 임베딩 실패: {rag_detail}")
                    print("⚠️ Vector DB 검색 스킵: embedding_failed")
                    print("⚠️ Dynamic RAG 스킵: embedding_failed")
                    rag_fingerprint_result = {
                        "status": "error",
                        "error_type": "EmbeddingError",
                        "message": rag_detail,
                    }
                    rag_rerank_result = {
                        "status": "skipped",
                        "reason": "embedding_failed",
                    }
                    dynamic_rag_result = _build_embedding_failed_result(rag_detail)
                    dynamic_result = dynamic_rag_result
                    final_risk = "LOW"
                else:
                    print(f"⚠️ RAG 분석 중 에러 발생 (Skipping): {rag_detail}")
                    traceback.print_exc()
                    rag_fingerprint_result = {
                        "status": "error",
                        "message": rag_detail,
                    }

                    rag_rerank_result = {
                        "status": "error",
                        "message": rag_detail,
                    }

                    dynamic_rag_result = {
                        "status": "error",
                        "message": rag_detail,
                        "final_risk": {
                            "risk_level": "LOW",
                            "risk_score": 0.0,
                            "reason": "RAG pipeline failed and was skipped",
                        },
                    }

                    dynamic_result = dynamic_rag_result
                    final_risk = "LOW"

            finally:
                if dynamic_harness is not None:
                    try:
                        if 'adapter' in locals() and adapter is not None and hasattr(adapter, "close"):
                            close_result = adapter.close()
                        else:
                            close_result = dynamic_harness.close()
                        import inspect
                        if inspect.isawaitable(close_result):
                            close_result = await close_result
                        _merge_cleanup_observation(dynamic_rag_result, close_result)
                        _merge_cleanup_observation(dynamic_result, close_result)

                    except Exception as close_e:
                        print(f"⚠️ Playwright harness close 중 에러 발생: {close_e}")


            # --- 2. 정적 분석 ---
            print(">>>>> 정적분석 실행")
            try:
                full_result = await run_in_threadpool(
                    run_extanalysis_and_static_scan,
                    file_path,
                )
                if isinstance(full_result, dict):
                    full_result.setdefault("status", "success")
                else:
                    full_result = {
                        "status": "error",
                        "message": "static analysis returned non-dict result",
                        "analysis_id": None,
                        "static_analysis": {},
                        "raw_result_type": type(full_result).__name__,
                    }
            except Exception as static_e:
                static_detail = str(static_e).strip() or repr(static_e)
                print(f"⚠️ 정적 분석 중 에러 발생 (Skipping): {static_detail}")
                traceback.print_exc()
                full_result = {
                    "status": "error",
                    "message": static_detail,
                    "analysis_id": None,
                    "static_analysis": {},
                }

            # --- 3. 난독화 분석 ---
            print(">>>>>>> 난독화 분석 실행")
            try:
                obfuscation_analysis = await run_in_threadpool(
                    obf_runner.run,
                    path_obj,
                )
                if isinstance(obfuscation_analysis, dict):
                    obfuscation_analysis.setdefault("status", "success")
                else:
                    obfuscation_analysis = {
                        "status": "error",
                        "message": "obfuscation analysis returned non-dict result",
                        "raw_result_type": type(obfuscation_analysis).__name__,
                    }
            except Exception as obf_e:
                obf_detail = str(obf_e).strip() or repr(obf_e)
                print(f"⚠️ 난독화 분석 중 에러 발생 (Skipping): {obf_detail}")
                obfuscation_analysis = {
                    "status": "error",
                    "message": obf_detail,
                }

            print("다이나믹/RAG 요약:", compact_result_one_line_summary(dynamic_result) if isinstance(dynamic_result, dict) else "unavailable")
            print(f"스태틱 요약: status={full_result.get('status') if isinstance(full_result, dict) else 'unknown'}")
            print(f"난독화 요약: status={obfuscation_analysis.get('status') if isinstance(obfuscation_analysis, dict) else 'unknown'}")

            # --- 4. 결과 저장 ---
            RESULT_DIR = Path("./results_json")
            base_filename = f"{extID}_{version}"
            target_dir = RESULT_DIR / base_filename
            target_dir.mkdir(parents=True, exist_ok=True)

            try:
                with open(target_dir / f"{base_filename}_dynamic.json", "w", encoding="utf-8") as f:
                    json.dump(dynamic_result, f, ensure_ascii=False, indent=2)

                with open(target_dir / f"{base_filename}_dynamic_rag.json", "w", encoding="utf-8") as f:
                    json.dump(dynamic_rag_result, f, ensure_ascii=False, indent=2)

                with open(target_dir / f"{base_filename}_rag_fingerprint.json", "w", encoding="utf-8") as f:
                    json.dump(rag_fingerprint_result, f, ensure_ascii=False, indent=2)

                with open(target_dir / f"{base_filename}_rag_rerank.json", "w", encoding="utf-8") as f:
                    json.dump(rag_rerank_result, f, ensure_ascii=False, indent=2)

                with open(target_dir / f"{base_filename}_static.json", "w", encoding="utf-8") as f:
                    json.dump(full_result, f, ensure_ascii=False, indent=2)

                with open(target_dir / f"{base_filename}_obfuscation.json", "w", encoding="utf-8") as f:
                    json.dump(obfuscation_analysis, f, ensure_ascii=False, indent=2)

                print(f"✅ 분석 결과 저장 완료: {RESULT_DIR.absolute()}")

            except Exception as save_e:
                print(f"⚠️ 결과 파일 저장 중 에러 발생: {save_e}")

            final_risk_summary = build_final_risk_summary(
                extension_id=extID,
                ext_name=extName,
                browser=browser,
                version=version,
                static_result_bundle=full_result,
                dynamic_result=dynamic_result,
                obfuscation_result=obfuscation_analysis,
            )
            weighted_risk_result = calculate_weighted_final_risk(
                static_result=full_result,
                obfuscation_result=obfuscation_analysis,
                dynamic_result=dynamic_result,
                rag_rerank_result=rag_rerank_result if isinstance(rag_rerank_result, dict) else None,
            )
            print(
                "✅ 최종 Weighted Risk:",
                f"level={weighted_risk_result.get('risk_level')}",
                f"score={weighted_risk_result.get('risk_score')}",
                f"decision={weighted_risk_result.get('recommended_decision')}",
            )
            final_risk_summary["weighted_risk"] = weighted_risk_result
            final_risk_summary["risk_level"] = weighted_risk_result.get("risk_level", "UNKNOWN")
            final_risk_summary["risk_score"] = weighted_risk_result.get("risk_score", 0.0)
            final_risk_summary["recommended_decision"] = weighted_risk_result.get("recommended_decision", "review")
            final_risk_summary["decision_reason"] = weighted_risk_result.get("decision_reason", "")
            decision = weighted_risk_result.get("recommended_decision", "review")

            # extension profile (버전별 객관적 변경 이력 — 로컬 파일 저장)
            # build_web_payload 이전에 실행하여 version_diff 를 web_payload 에 실어 보낸다.
            extension_profile_result = {
                "status": "skipped",
                "enabled": os.getenv("ENABLE_EXTENSION_PROFILE", "true").strip().lower() == "true",
            }
            version_diff_payload = None
            if extension_profile_result["enabled"]:
                try:
                    from backend.profile.builder import build_profile, build_snapshot, validate_profile
                    from backend.profile.local_store import (
                        load_profile,
                        make_blob_loader,
                        save_profile,
                        store_blobs,
                    )

                    snapshot, profile_file_bytes = build_snapshot(file_path)
                    # 업로드 시 지정한 버전을 정본으로 사용 (manifest.json의 version과 무관)
                    if version:
                        snapshot["version"] = str(version)
                    snapshot["verdict"] = {
                        "risk_grade": weighted_risk_result.get("risk_level"),
                        "result_id": base_filename,
                        "analyzed_at": snapshot["captured_at"],
                    }
                    store_blobs(profile_file_bytes)  # 다음 버전 인라인 diff용 로컬 blob 저장

                    prev_profile = load_profile(extID)
                    prev_snapshots = (prev_profile or {}).get("snapshots") or []
                    last_snapshot = prev_snapshots[-1] if prev_snapshots else None

                    if (
                        last_snapshot
                        and last_snapshot.get("version") == snapshot["version"]
                        and last_snapshot.get("content_hash") == snapshot["content_hash"]
                    ):
                        # 동일 버전·동일 내용 재스캔 → 프로필 갱신 생략 (idempotent)
                        extension_profile_result = {
                            "status": "unchanged",
                            "enabled": True,
                            "versions": len(prev_snapshots),
                            "latest_version": prev_profile.get("latest_version"),
                        }
                        version_diff_payload = _build_version_diff_payload(
                            last_snapshot.get("diff_from_previous"), snapshot["version"]
                        )
                        print(f"ℹ️ [Profile] 변경 없음 (v{snapshot['version']}) — 갱신 생략")
                    else:
                        profile_doc = build_profile(
                            snapshot,
                            prev_profile,
                            ext_id=extID,
                            browser=browser,
                            ext_name=extName,
                            curr_file_bytes=profile_file_bytes,
                            blob_loader=make_blob_loader(),
                        )
                        profile_errors = validate_profile(profile_doc)
                        if profile_errors:
                            raise RuntimeError(f"profile schema invalid: {profile_errors[:3]}")

                        profile_path = save_profile(extID, profile_doc)
                        latest_snapshot = profile_doc["snapshots"][-1]
                        version_diff_payload = _build_version_diff_payload(
                            latest_snapshot.get("diff_from_previous"), snapshot["version"]
                        )
                        extension_profile_result = {
                            "status": "success",
                            "enabled": True,
                            "path": str(profile_path),
                            "versions": len(profile_doc.get("snapshots", [])),
                            "latest_version": profile_doc.get("latest_version"),
                        }
                        print(
                            f"✅ [Profile] 저장 완료: {profile_path} "
                            f"(versions={extension_profile_result['versions']})"
                        )
                except Exception as profile_e:
                    profile_detail = str(profile_e).strip() or repr(profile_e)
                    extension_profile_result = {
                        "status": "error",
                        "enabled": True,
                        "message": profile_detail,
                    }
                    print(f"⚠️ [Profile] 생성 실패: {profile_detail}")

            web_payload = build_web_payload(
                ext_id=extID,
                ext_name=extName,
                browser=browser,
                version=version,
                file_name=file.filename,
                static_result=full_result,
                obfuscation_result=obfuscation_analysis,
                dynamic_result=dynamic_result,
                rag_fingerprint_result=rag_fingerprint_result,
                rag_rerank_result=rag_rerank_result,
                final_risk_summary=final_risk_summary,
                decision=decision,
            )

            # 버전 변경 사항 요약 + 전체 diff 를 web_payload 에 실어
            # 웹 UI 의 summary.json 에 자동 영속화되도록 한다.
            if version_diff_payload is not None:
                web_payload["version_diff"] = version_diff_payload

            # web forward
            web_forward_result = {
                "status": "skipped",
                "enabled": os.getenv("ENABLE_WEB_FORWARD", "false").strip().lower() == "true",
            }
            if web_forward_result["enabled"]:
                try:
                    web_response = await send_web(web_payload)
                    web_forward_result = {
                        "status": "success",
                        "enabled": True,
                        "response": web_response,
                    }
                    print(f"✅ [Web-Forward] {extID} 전송 완료")
                except Exception as web_e:
                    web_detail = str(web_e).strip() or repr(web_e)
                    web_forward_result = {
                        "status": "error",
                        "enabled": True,
                        "message": web_detail,
                    }
                    print(f"⚠️ [Web-Forward] 전송 실패: {web_detail}")

            # slack forward
            slack_result = {
                "status": "skipped",
                "enabled": os.getenv("ENABLE_SLACK_FORWARD", "false").strip().lower() == "true",
            }
            if slack_result["enabled"]:
                if not _slack_available or run_slack_with_scan_input is None:
                    slack_result = {
                        "status": "error",
                        "enabled": True,
                        "message": "Slack module is not available",
                    }
                else:
                    try:
                        wr = final_risk_summary.get("weighted_risk", {}) if isinstance(final_risk_summary, dict) else {}
                        cs = wr.get("component_scores", {}) if isinstance(wr, dict) else {}
                        dyn = cs.get("dynamic", {}) if isinstance(cs, dict) else {}
                        sta = cs.get("static", {}) if isinstance(cs, dict) else {}
                        obf = cs.get("obfuscation", {}) if isinstance(cs, dict) else {}
                        component_note = (
                            f"Dynamic: {dyn.get('risk_level')} / {dyn.get('score')} / w {dyn.get('weight')} | "
                            f"Static: {sta.get('risk_level')} / {sta.get('score')} / w {sta.get('weight')} | "
                            f"Obfuscation: {obf.get('risk_level')} / {obf.get('score')} / w {obf.get('weight')}"
                        )
                        slack_input = {
                            "extension_id": extID,
                            "program_name": extName,
                            "program_type": final_risk_summary.get("program_type"),
                            "browser": browser,
                            "version": version,
                            "decision": decision,
                            "risk_level": final_risk_summary.get("risk_level"),
                            "risk_score": final_risk_summary.get("risk_score"),
                            "decision_reason": final_risk_summary.get("decision_reason"),
                            "scan_result": final_risk_summary.get("scan_result"),
                            "weighted_risk": wr,
                            "web_payload": web_payload,
                            "component_score_summary": component_note,
                        }
                        slack_flow = run_slack_with_scan_input(slack_input)
                        slack_result = {
                            "status": "success",
                            "enabled": True,
                            "decision": slack_flow.get("decision") if isinstance(slack_flow, dict) else decision,
                            "sent_slack": bool(slack_flow.get("sent_slack", True)) if isinstance(slack_flow, dict) else True,
                            "response": slack_flow,
                        }
                        print(f"✅ [Slack] 전송 완료: sent={slack_result.get('sent_slack')}")
                    except Exception as slack_e:
                        slack_detail = str(slack_e).strip() or repr(slack_e)
                        slack_result = {
                            "status": "error",
                            "enabled": True,
                            "message": slack_detail,
                        }
                        print(f"⚠️ [Slack] 전송 실패: {slack_detail}")

            # nexus upload
            nexus_upload_result = {
                "status": "skipped",
                "enabled": os.getenv("ENABLE_NEXUS_UPLOAD", "true").strip().lower() == "true",
            }
            if nexus_upload_result["enabled"]:
                try:
                    await file.seek(0)
                    nexus_bucket = _decision_to_nexus_bucket(decision)
                    upload_result = await upload_plugin(
                        browser=browser,
                        extID=extID,
                        version=version,
                        file=file,
                        extName=extName,
                        judge=decision,
                        decision=nexus_bucket,
                    )
                    nexus_upload_result = {
                        "status": "success",
                        "enabled": True,
                        "result": upload_result,
                    }
                    print(f"✅ nexus 업로드 완료: {upload_result}")
                except Exception as nexus_e:
                    nexus_detail = str(nexus_e).strip() or repr(nexus_e)
                    nexus_upload_result = {
                        "status": "error",
                        "enabled": True,
                        "message": nexus_detail,
                    }
                    print(f"⚠️ nexus 업로드 실패: {nexus_detail}")

            # # --- 5. 판별 ---
            # try:
            #     from judge import judge
            #     judge_result = judge()
            # except Exception as judge_e:
            #     print(f"⚠️ judge 처리 중 오류: {judge_e}")
            #     judge_result = "error"
#
            # # --- 5-1. Slack 처리 ---
            # try:
            #     slack_flow = run_slack_with_scan_input(final_risk_summary)
            #     slack_result = {
            #         "status": "processed",
            #         "decision": slack_flow.get("decision"),
            #         "sent_slack": bool(slack_flow.get("sent_slack", False)),
            #     }
            #     print("Slack 처리 결과:", slack_result)
#
            # except Exception as slack_e:
            #     slack_detail = str(slack_e).strip() or repr(slack_e)
            #     print(f"⚠️ Slack 알림 처리 중 에러 발생 (Skipping): {slack_detail}")
            #     slack_result = {
            #         "status": "error",
            #         "message": slack_detail,
            #     }
#
            # decision = slack_result.get("decision") or "unknown"
#
            # # --- 6. Nexus 업로드 ---
            # await file.seek(0)
            # await upload_plugin(
            #     browser=browser,
            #     extID=extID,
            #     version=version,
            #     file=file,
            #     extName=extName,
            #     judge=judge_result,
            #     decision=decision,
            # )
            # print("nexus 업로드 완료")
#
            return {
                "status": "success",
                "analysis_id": full_result.get("analysis_id"),
                "extension_id": final_risk_summary["extension_id"],
                "program_name": final_risk_summary["program_name"],
                "program_type": final_risk_summary["program_type"],
                "scan_result": final_risk_summary["scan_result"],
                "final_risk_summary": final_risk_summary,
                "static_result": full_result.get("static_analysis"),
                "dynamic_result": dynamic_result,
                "obfuscation_result": obfuscation_analysis,
                "rag_fingerprint_result": rag_fingerprint_result,
                "rag_rerank_result": rag_rerank_result,
                "dynamic_rag_result": dynamic_rag_result,
                "rag_final_risk": final_risk,
                "slack_result": slack_result,
                "web_forward_result": web_forward_result,
                "nexus_upload_result": nexus_upload_result,
                "extension_profile_result": extension_profile_result,
                "web_payload": web_payload,
            }

        except Exception as e:
            print("\n" + "=" * 50)
            print("❌ 전체 분석 파이프라인 에러:")
            traceback.print_exc()
            print("=" * 50 + "\n")
            return {
                "status": "error",
                "message": str(e),
            }



# Nexus 설정
NEXUS_BASE_URL  = os.getenv("NEXUS_BASE_URL")
NEXUS_REPOSITORY = os.getenv("NEXUS_REPOSITORY")
NEXUS_USERNAME  = os.getenv("NEXUS_USERNAME")
NEXUS_PASSWORD  = os.getenv("NEXUS_PASSWORD")


async def upload_plugin(browser: str, extID: str, version: str, file: UploadFile, extName: str, judge: str, decision: str):
    print(
        "📦 [Nexus Upload] start:",
        f"decision={decision}",
        f"browser={browser}",
        f"extName={extName}",
        f"version={version}",
        f"extID={extID}",
    )
    try:
        missing = [
            name for name, value in {
                "NEXUS_BASE_URL": NEXUS_BASE_URL,
                "NEXUS_REPOSITORY": NEXUS_REPOSITORY,
                "NEXUS_USERNAME": NEXUS_USERNAME,
                "NEXUS_PASSWORD": NEXUS_PASSWORD,
            }.items()
            if not value
        ]
        if missing:
            raise HTTPException(status_code=500, detail=f"Nexus config missing: {', '.join(missing)}")

        await file.seek(0)
        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다.")

        filename = f"{extID}.zip"
        nexus_path = f"{decision}/{browser}/{extName}/{version}/{filename}"
        encoded_path = quote(nexus_path, safe='/')
        upload_url = f"{NEXUS_BASE_URL}/repository/{NEXUS_REPOSITORY}/{encoded_path}"

        response = requests.put(
            upload_url,
            data=file_bytes,
            auth=(NEXUS_USERNAME, NEXUS_PASSWORD),
            headers={"Content-Type": "application/octet-stream"},
            timeout=60,
        )

        if response.status_code not in [200, 201, 204]:
            raise HTTPException(status_code=500, detail=f"Nexus 업로드 실패: {response.status_code}")

        return {"success": True, "nexus_path": nexus_path, "message": "Nexus 업로드 성공"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/plugins/download")
def download_plugin(plugin_name: str, version: str, filename: str):
    try:
        safe_filename = unquote(filename)
        nexus_path = f"{plugin_name}/{version}/{safe_filename}"
        encoded_path = quote(nexus_path, safe='/')
        download_url = f"{NEXUS_BASE_URL}/repository/{NEXUS_REPOSITORY}/{encoded_path}"

        response = requests.get(
            download_url,
            auth=(NEXUS_USERNAME, NEXUS_PASSWORD),
            stream=True,
            timeout=30,
        )

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="파일을 찾을 수 없습니다.")

        def iterfile():
            for chunk in response.iter_content(chunk_size=8192):
                yield chunk

        encoded_header_filename = quote(safe_filename)
        headers = {"Content-Disposition": f"attachment; filename*=utf-8''{encoded_header_filename}"}

        return StreamingResponse(iterfile(), media_type="application/octet-stream", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
