from copy import deepcopy
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict
import json

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.auth.security import require_permission


router = APIRouter()

POLICY_PATH = Path(__file__).resolve().parent / "policy_settings.json"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_FILENAME = "default_policy"

DEFAULT_POLICY: Dict[str, Any] = {
    "critical_auto_reject_enabled": True,
    "low_auto_approve_enabled": False,
    "fallback_decision": "review",
}

def merge_defaults(value: Dict[str, Any]) -> Dict[str, Any]:
    policy = deepcopy(DEFAULT_POLICY)
    if "critical_auto_reject_enabled" in value:
        policy["critical_auto_reject_enabled"] = value["critical_auto_reject_enabled"]
    elif "auto_reject_enabled" in value:
        policy["critical_auto_reject_enabled"] = value["auto_reject_enabled"]

    if "low_auto_approve_enabled" in value:
        policy["low_auto_approve_enabled"] = value["low_auto_approve_enabled"]
    elif "auto_approve_enabled" in value:
        policy["low_auto_approve_enabled"] = value["auto_approve_enabled"]

    policy["fallback_decision"] = "review"
    return policy


def read_policy() -> Dict[str, Any]:
    if not POLICY_PATH.exists():
        write_policy(DEFAULT_POLICY)
        return deepcopy(DEFAULT_POLICY)

    try:
        with POLICY_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Policy JSON is invalid: {exc}") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="Policy JSON must be an object.")

    return merge_defaults(data)


def write_policy(policy: Dict[str, Any]) -> None:
    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with POLICY_PATH.open("w", encoding="utf-8") as file:
        json.dump(policy, file, ensure_ascii=False, indent=2)


def validate_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    merged = merge_defaults(policy)
    merged["critical_auto_reject_enabled"] = bool(merged["critical_auto_reject_enabled"])
    merged["low_auto_approve_enabled"] = bool(merged["low_auto_approve_enabled"])
    merged["fallback_decision"] = "review"

    return merged


_KOREAN_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/malgun.ttf"),
    PROJECT_ROOT / "frontend" / "static" / "fonts" / "NotoSansKR-Regular.ttf",
]
_KOREAN_FONT_NAME = "Helvetica"
for _font_path in _KOREAN_FONT_CANDIDATES:
    if _font_path.exists():
        pdfmetrics.registerFont(TTFont("Korean", str(_font_path)))
        _KOREAN_FONT_NAME = "Korean"
        break

_POLICY_FIELDS = [
    ("critical_auto_reject_enabled", "Critical 자동 거부", "critical 심각도가 포함된 분석 결과를 자동으로 거부합니다."),
    ("low_auto_approve_enabled", "Low 자동 승인", "low 심각도만 확인된 분석 결과를 자동으로 승인합니다."),
    ("fallback_decision", "기본 판정", "위 조건에 해당하지 않는 결과는 관리자 검토 상태로 유지됩니다. (변경 불가)"),
]


def build_policy_document_pdf(policy: Dict[str, Any]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title="ExtS3 Default Policy",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("KTitle", parent=styles["Title"], fontName=_KOREAN_FONT_NAME)
    meta_style = ParagraphStyle(
        "KMeta", parent=styles["Normal"], fontName=_KOREAN_FONT_NAME,
        fontSize=9, textColor=colors.HexColor("#4a5568"),
    )
    cell_style = ParagraphStyle(
        "KCell", parent=styles["Normal"], fontName=_KOREAN_FONT_NAME, fontSize=9, leading=13,
    )
    header_style = ParagraphStyle("KHeader", parent=cell_style, textColor=colors.white)

    def display_value(value: Any) -> str:
        if isinstance(value, bool):
            return "사용" if value else "사용 안 함"
        return str(value)

    elements = [
        Paragraph("ExtS3 기본 정책", title_style),
        Spacer(1, 4 * mm),
        Paragraph(f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", meta_style),
        Spacer(1, 6 * mm),
    ]

    header = ["항목", "값", "설명"]
    data = [[Paragraph(text, header_style) for text in header]]
    for key, label, description in _POLICY_FIELDS:
        data.append([
            Paragraph(label, cell_style),
            Paragraph(display_value(policy.get(key)), cell_style),
            Paragraph(description, cell_style),
        ])

    table = Table(data, colWidths=[35 * mm, 25 * mm, 100 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)

    doc.build(elements)
    return buffer.getvalue()


@router.get("/api/admin/policy")
async def get_policy(_user: dict = Depends(require_permission("manage_extension_policy"))):
    return {"success": True, "data": read_policy()}


@router.post("/api/admin/policy")
async def update_policy(
    payload: Dict[str, Any] = Body(...),
    _user: dict = Depends(require_permission("manage_extension_policy")),
):
    policy = validate_policy(payload)
    write_policy(policy)
    return {"success": True, "data": policy}


@router.get("/api/admin/policy/default.json")
async def download_default_policy_json(
    _user: dict = Depends(require_permission("manage_extension_policy")),
):
    return Response(
        content=json.dumps(read_policy(), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{DEFAULT_POLICY_FILENAME}.json"'},
    )


@router.get("/api/admin/policy/default.pdf")
async def download_default_policy_pdf(
    _user: dict = Depends(require_permission("manage_extension_policy")),
):
    pdf_bytes = build_policy_document_pdf(read_policy())
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{DEFAULT_POLICY_FILENAME}.pdf"'},
    )
