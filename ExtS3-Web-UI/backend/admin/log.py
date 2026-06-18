import json
import textwrap
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.auth.security import require_admin

router = APIRouter()


@router.post("/api/admin/log")
async def get_analysis_logs(request: Request, _user: dict = Depends(require_admin)):
    data = await request.json()
    return load_analysis_logs(data)


@router.post("/api/admin/log/pdf")
async def download_analysis_log_pdf(request: Request, _user: dict = Depends(require_admin)):
    data = await request.json()
    result = load_analysis_logs(data)
    pdf_bytes = build_analysis_log_pdf(
        result["data"],
        ext_id=result["id"],
        ext_name=result["extName"],
        resolved_path=result["resolved_path"],
    )
    version = str(data.get("version") or "unknown").strip()
    filename = f"{safe_filename(result['id'])}_{safe_filename(version)}_analysis_report.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


def load_analysis_logs(data: dict):
    ext_id = str(data.get("id", "")).strip()
    ext_name = str(data.get("app_name", "")).strip()
    browser = str(data.get("app_browser") or data.get("browser") or "").strip()
    version = str(data.get("version", "")).strip()
    source_path = str(data.get("source_path", "")).strip()

    if not all([ext_id, browser, version]):
        raise HTTPException(status_code=400, detail="id, browser, version are required")

    root_path = Path(__file__).resolve().parent.parent.parent
    base_root = root_path / "analysis_result"

    # 결과는 analysis_result/{decision}/{browser}/{name}/{version}/{id}/ 에 저장된다.
    # 대시보드 목록의 버킷(source_path)과 실제 저장된 decision 버킷(review/reject/approve)이
    # 다를 수 있으므로(예: 자동 정책 reject) 모든 decision 버킷을 가로질러 탐색한다.
    decision_buckets = (
        [d for d in sorted(base_root.iterdir()) if d.is_dir()] if base_root.exists() else []
    )

    def find_case_insensitive(parent: Path | None, target_name: str) -> Path | None:
        if not parent or not parent.exists() or not target_name:
            return None
        target_lower = target_name.strip().lower()
        for child in parent.iterdir():
            if child.name.strip().lower() == target_lower:
                return child
        return None

    def target_from_source_path() -> Path | None:
        if not source_path:
            return None

        parts = Path(source_path.replace("\\", "/")).parts
        if len(parts) < 5:
            return None

        # 선행 버킷명(review/reject/...)은 무시하고 browser/name/version/id tail 만 사용한다.
        file_stem = Path(parts[-1]).stem
        relative_tail = Path(*parts[1:-1], file_stem)
        for bucket in decision_buckets:
            candidate = bucket / relative_tail
            if candidate.exists():
                return candidate
        return None

    def target_from_params() -> Path | None:
        for bucket in decision_buckets:
            browser_path = find_case_insensitive(bucket, browser)
            app_path = find_case_insensitive(browser_path, ext_name)
            version_path = find_case_insensitive(app_path, version)
            target_path = find_case_insensitive(version_path, ext_id)
            if target_path and target_path.exists():
                return target_path
        return None

    def target_by_id_scan() -> Path | None:
        for bucket in decision_buckets:
            browser_path = find_case_insensitive(bucket, browser)
            if not browser_path or not browser_path.exists():
                continue
            for summary_file in browser_path.glob(f"*/{version}/{ext_id}/summary.json"):
                return summary_file.parent
        return None

    target_path = target_from_source_path() or target_from_params() or target_by_id_scan()

    if not target_path or not target_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "analysis_result/{decision}/{browser}/{name}/{version}/{id}/summary.json "
                "path was not found"
            ),
        )

    try:
        target_path.resolve().relative_to(base_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid analysis_result path")

    target_files = [
        "dynamic.json",
        "external.json",
        "obfuscation.json",
        "static.json",
        "summary.json",
        "decision_rag_result.json",
    ]
    analysis_results = {}

    try:
        for file_name in target_files:
            file_path = target_path / file_name
            key = file_name.replace(".json", "")
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    analysis_results[key] = json.load(f)
            else:
                analysis_results[key] = {}

        return {
            "success": True,
            "id": ext_id,
            "extName": ext_name or target_path.parent.parent.name,
            "resolved_path": str(target_path.relative_to(base_root)),
            "data": analysis_results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def safe_filename(value: str) -> str:
    text = "".join("_" if ch in '\\/:*?"<>|' else ch for ch in str(value or "analysis"))
    return text.strip(" .") or "analysis"


def get_nested(data: dict, *keys, default=None):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def add_paragraph(story, styles, text: object, style_name: str = "Body"):
    story.append(styles[style_name](escape(str(text or "-"))))


def add_kv(story, styles, label: str, value: object):
    add_paragraph(story, styles, f"{label}: {value if value not in (None, '') else '-'}")


def wrapped_json(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, indent=2)
    lines = []
    for line in raw.splitlines():
        if len(line) <= 110:
            lines.append(line)
        else:
            lines.extend(textwrap.wrap(line, width=110, break_long_words=True, break_on_hyphens=False))
    return "\n".join(lines)


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def append_section(lines: list[str], title: str):
    lines.extend(["", title])


def append_items(lines: list[str], title: str, items: list, empty: str = "표시할 항목 없음", limit: int = 10):
    lines.append(f"{title}:")
    shown = [item for item in as_list(items) if item not in (None, "")]
    if not shown:
        lines.append(f"- {empty}")
        return
    for item in shown[:limit]:
        if isinstance(item, dict):
            label = item.get("title") or item.get("type") or item.get("scenario") or item.get("pattern_name") or "항목"
            detail = item.get("description") or item.get("evidence") or item.get("severity") or ""
            lines.append(f"- {label}: {detail}" if detail else f"- {label}")
        else:
            lines.append(f"- {item}")


def build_analysis_log_pdf(logs: dict, *, ext_id: str, ext_name: str, resolved_path: str) -> bytes:
    summary = logs.get("summary") if isinstance(logs, dict) else {}
    payload = summary.get("web_payload") if isinstance(summary, dict) else {}
    if not isinstance(payload, dict):
        payload = summary if isinstance(summary, dict) else {}

    overall = payload.get("overall") or summary.get("summary") or summary.get("final_risk_summary") or {}
    final_risk = summary.get("final_risk_summary") or overall or {}
    extension = payload.get("extension") or {}
    decision_rag = logs.get("decision_rag_result") or payload.get("decision_rag_result") or {}
    static_analysis = payload.get("static_analysis") if isinstance(payload, dict) else {}
    dynamic_analysis = payload.get("dynamic_analysis") if isinstance(payload, dict) else {}
    obfuscation_analysis = payload.get("obfuscation_analysis") if isinstance(payload, dict) else {}
    rag_analysis = payload.get("rag_analysis") if isinstance(payload, dict) else {}

    lines = [
        "분석 리포트",
        "",
        f"앱 이름: {ext_name or extension.get('name') or '-'}",
        f"확장 ID: {ext_id or '-'}",
        f"브라우저: {extension.get('browser') or '-'}",
        f"버전: {extension.get('version') or '-'}",
        f"생성 시각: {datetime.now(timezone.utc).isoformat()}",
        f"분석 경로: {resolved_path or '-'}",
        "",
        "결과 내용",
        f"판정: {final_risk.get('recommended_decision') or overall.get('recommended_decision') or '-'}",
        f"위험도: {final_risk.get('risk_level') or overall.get('risk_level') or '-'}",
        f"위험 점수: {final_risk.get('risk_score') or overall.get('risk_score') or '-'}",
        f"판정 사유: {final_risk.get('decision_reason') or overall.get('decision_reason') or overall.get('summary') or '-'}",
    ]

    append_section(lines, "주요 위험 근거")
    risk_factors = overall.get("risk_factors") if isinstance(overall, dict) else []
    review_reasons = get_nested(payload, "review", "review_reasons", default=[])
    append_items(lines, "위험 플래그", risk_factors, "특이 위험 플래그 없음", limit=8)
    append_items(lines, "검토 사유", review_reasons, "별도 검토 사유 없음", limit=8)

    append_section(lines, "컴포넌트 점수")
    component_scores = final_risk.get("component_scores") or overall.get("component_scores") or {}
    if component_scores:
        for name, score in component_scores.items():
            if not isinstance(score, dict):
                continue
            lines.append(
                f"{name}: {score.get('risk_level', '-')} / score={score.get('score', '-')} / "
                f"weight={score.get('weight', '-')}"
            )
    else:
        lines.append("컴포넌트 점수 없음")

    append_section(lines, "정적 분석")
    lines.append(f"상태: {static_analysis.get('status', '-') if isinstance(static_analysis, dict) else '-'}")
    lines.append(f"위험도: {static_analysis.get('risk_level') or 'UNKNOWN' if isinstance(static_analysis, dict) else '-'}")
    lines.append(f"요약: {static_analysis.get('summary', '-') if isinstance(static_analysis, dict) else '-'}")
    append_items(lines, "주요 문제", static_analysis.get("key_findings") if isinstance(static_analysis, dict) else [], "표시할 주요 문제가 없습니다.", limit=8)
    append_items(lines, "권한 근거", static_analysis.get("permissions") if isinstance(static_analysis, dict) else [], "권한 위험 신호 없음", limit=12)
    append_items(lines, "외부 도메인 근거", static_analysis.get("external_domains") if isinstance(static_analysis, dict) else [], "외부 도메인 없음", limit=8)

    append_section(lines, "동적 분석")
    runtime = dynamic_analysis.get("runtime_evidence", {}) if isinstance(dynamic_analysis, dict) else {}
    lines.append(f"상태: {dynamic_analysis.get('status', '-') if isinstance(dynamic_analysis, dict) else '-'}")
    lines.append(f"위험도: {dynamic_analysis.get('risk_level', '-') if isinstance(dynamic_analysis, dict) else '-'}")
    lines.append(f"요약: {dynamic_analysis.get('summary', '-') if isinstance(dynamic_analysis, dict) else '-'}")
    lines.append(f"실제 관측된 네트워크 요청: {runtime.get('network_requests', 0) if isinstance(runtime, dict) else 0}건")
    lines.append(f"실제 관측된 스토리지 접근: {runtime.get('storage_access', 0) if isinstance(runtime, dict) else 0}건")
    lines.append(f"실제 관측된 메시지 이벤트: {runtime.get('message_events', 0) if isinstance(runtime, dict) else 0}건")
    append_items(lines, "위험 플래그", dynamic_analysis.get("risk_factors") if isinstance(dynamic_analysis, dict) else [], "특이 위험 플래그 없음", limit=8)
    append_items(lines, "주요 관측", dynamic_analysis.get("key_observations") if isinstance(dynamic_analysis, dict) else [], "표시할 관측 결과 없음", limit=8)

    append_section(lines, "난독화 분석")
    lines.append(f"상태: {obfuscation_analysis.get('status', '-') if isinstance(obfuscation_analysis, dict) else '-'}")
    lines.append(f"위험도: {obfuscation_analysis.get('risk_level', '-') if isinstance(obfuscation_analysis, dict) else '-'}")
    lines.append(f"요약: {obfuscation_analysis.get('summary', '-') if isinstance(obfuscation_analysis, dict) else '-'}")
    lines.append(f"패킹/압축 의심: {'있음' if get_nested(obfuscation_analysis, 'packed_or_minified', default=False) else '없음'}")
    append_items(lines, "난독화 파일", obfuscation_analysis.get("obfuscated_files") if isinstance(obfuscation_analysis, dict) else [], "없음", limit=12)
    append_items(lines, "주요 지표", obfuscation_analysis.get("key_indicators") if isinstance(obfuscation_analysis, dict) else [], "표시할 난독화 지표가 없습니다.", limit=8)

    append_section(lines, "RAG 분석")
    top_patterns = rag_analysis.get("top_patterns", []) if isinstance(rag_analysis, dict) else []
    top_pattern = top_patterns[0] if top_patterns and isinstance(top_patterns[0], dict) else {}
    lines.append(f"상태: {rag_analysis.get('status', '-') if isinstance(rag_analysis, dict) else '-'}")
    lines.append(f"요약: {rag_analysis.get('summary', '-') if isinstance(rag_analysis, dict) else '-'}")
    lines.append(f"가장 유사한 패턴: {top_pattern.get('pattern_name') or '없음'}")
    lines.append(f"유사도: {top_pattern.get('score', '-')}")
    lines.append(f"후보 기준: {'통과' if top_pattern.get('threshold_passed') else '미통과'}")
    append_items(lines, "근거", top_pattern.get("evidence") if isinstance(top_pattern, dict) else [], "표시할 근거 없음", limit=10)

    append_section(lines, "Decision RAG")
    lines.append(f"상태: {decision_rag.get('status') if isinstance(decision_rag, dict) else '-'}")
    lines.append(f"LLM 상태: {decision_rag.get('llm_call_status') if isinstance(decision_rag, dict) else '-'}")
    recommendation = get_nested(decision_rag, "llm_recommendation", "recommendation", default="-")
    lines.append(f"LLM 권고: {recommendation}")
    lines.append(f"유사 사례 수: {decision_rag.get('similar_cases_count') if isinstance(decision_rag, dict) else '-'}")
    append_items(lines, "핵심 근거", get_nested(decision_rag, "llm_recommendation", "key_evidence", default=[]), "표시할 LLM 근거 없음", limit=8)

    append_section(lines, "권장 검토 사항")
    review = payload.get("review") if isinstance(payload, dict) else {}
    actions = review.get("recommended_actions") if isinstance(review, dict) else []
    reasons = review.get("review_reasons") if isinstance(review, dict) else []
    for item in (reasons or [])[:8]:
        lines.append(f"- {item}")
    for item in (actions or [])[:8]:
        lines.append(f"- {item}")
    if not reasons and not actions:
        lines.append("표시할 권장 검토 사항 없음")

    return build_plain_text_pdf(lines)


def _pdf_utf16_hex(value: str) -> str:
    return str(value or "").encode("utf-16-be").hex().upper()


def build_plain_text_pdf(lines: list[str]) -> bytes:
    wrapped_lines = []
    for line in lines:
        if line == "---PAGEBREAK---":
            wrapped_lines.append(line)
            continue
        if len(line) <= 92:
            wrapped_lines.append(line)
        else:
            wrapped_lines.extend(textwrap.wrap(line, width=92, break_long_words=True, break_on_hyphens=False))

    pages = [[]]
    for line in wrapped_lines:
        if line == "---PAGEBREAK---":
            if pages[-1]:
                pages.append([])
            continue
        pages[-1].append(line)
        if len(pages[-1]) >= 54:
            pages.append([])
    pages = [page for page in pages if page] or [["No data"]]

    objects = []

    def add_object(content: str) -> int:
        objects.append(content)
        return len(objects)

    catalog_id = add_object("<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add_object("")
    cid_font_id = add_object(
        "<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HYGoThic-Medium "
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (Korea1) /Supplement 2 >> "
        "/DW 1000 >>"
    )
    font_id = add_object(
        "<< /Type /Font /Subtype /Type0 /BaseFont /HYGoThic-Medium "
        f"/Encoding /UniKS-UCS2-H /DescendantFonts [{cid_font_id} 0 R] >>"
    )
    page_ids = []

    for page_lines in pages:
        text_parts = ["BT", "/F1 9 Tf", "42 800 Td", "12 TL"]
        for line in page_lines:
            text_parts.append(f"<{_pdf_utf16_hex(line)}> Tj")
            text_parts.append("T*")
        text_parts.append("ET")
        stream = "\n".join(text_parts)
        content_id = add_object(
            f"<< /Length {len(stream.encode('latin-1'))} >>\n"
            f"stream\n{stream}\nendstream"
        )
        page_id = add_object(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        page_ids.append(page_id)

    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] "
        f"/Count {len(page_ids)} >>"
    )

    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, content in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{object_id} 0 obj\n{content}\nendobj\n".encode("latin-1"))

    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.write(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("latin-1")
    )
    return output.getvalue()
