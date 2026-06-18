from copy import deepcopy
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any, Dict
import json

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response

from backend.auth.security import require_permission


router = APIRouter()

POLICY_PATH = Path(__file__).resolve().parent / "policy_settings.json"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_DOCUMENT_PATH = PROJECT_ROOT / "policy.md"
DEFAULT_POLICY_PDF_FILENAME = "default_policy.pdf"

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


def _load_reportlab():
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF 생성을 위해 reportlab 패키지가 필요합니다. requirements.txt 설치 후 다시 시도하세요.",
        ) from exc

    return {
        "colors": colors,
        "A4": A4,
        "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet,
        "mm": mm,
        "pdfmetrics": pdfmetrics,
        "TTFont": TTFont,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
    }


def _register_pdf_font(pdf: Dict[str, Any]) -> str:
    candidates = [
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/NotoSansKR-VF.ttf"),
        PROJECT_ROOT / "frontend" / "static" / "fonts" / "NotoSansKR-Regular.ttf",
    ]
    for font_path in candidates:
        if font_path.exists():
            pdf["pdfmetrics"].registerFont(pdf["TTFont"]("Korean", str(font_path)))
            return "Korean"
    return "Helvetica"


def _paragraph(pdf: Dict[str, Any], text: str, style: Any) -> Any:
    return pdf["Paragraph"](escape(text).replace("\n", "<br/>"), style)


def _is_markdown_table(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].lstrip().startswith("|")
        and lines[index + 1].lstrip().startswith("|")
        and set(lines[index + 1].replace("|", "").replace(":", "").replace(" ", "").strip()) <= {"-"}
    )


def _consume_markdown_table(pdf: Dict[str, Any], lines: list[str], index: int, style: Any, font_name: str) -> tuple[Any, int]:
    rows = []
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        if cells and all(set(cell.replace(":", "").replace(" ", "")) <= {"-"} for cell in cells):
            index += 1
            continue
        rows.append([_paragraph(pdf, cell, style) for cell in cells])
        index += 1

    column_count = max((len(row) for row in rows), default=1)
    for row in rows:
        row.extend([_paragraph(pdf, "", style)] * (column_count - len(row)))

    table = pdf["Table"](rows, repeatRows=1)
    table.setStyle(
        pdf["TableStyle"](
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (-1, 0), pdf["colors"].HexColor("#e8eff4")),
                ("GRID", (0, 0), (-1, -1), 0.4, pdf["colors"].HexColor("#a8b3bb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table, index


def _markdown_to_pdf_elements(pdf: Dict[str, Any], markdown: str, styles: Dict[str, Any], font_name: str) -> list[Any]:
    elements = []
    lines = markdown.splitlines()
    index = 0
    in_code_block = False
    code_lines: list[str] = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                elements.append(_paragraph(pdf, "\n".join(code_lines), styles["code"]))
                elements.append(pdf["Spacer"](1, 6))
                code_lines = []
            in_code_block = not in_code_block
            index += 1
            continue

        if in_code_block:
            code_lines.append(line)
            index += 1
            continue

        if not stripped:
            elements.append(pdf["Spacer"](1, 4))
            index += 1
            continue

        if _is_markdown_table(lines, index):
            table, index = _consume_markdown_table(pdf, lines, index, styles["table_cell"], font_name)
            elements.append(table)
            elements.append(pdf["Spacer"](1, 8))
            continue

        if stripped.startswith("# "):
            elements.append(_paragraph(pdf, stripped[2:].strip(), styles["title"]))
        elif stripped.startswith("## "):
            elements.append(_paragraph(pdf, stripped[3:].strip(), styles["h2"]))
        elif stripped.startswith("### "):
            elements.append(_paragraph(pdf, stripped[4:].strip(), styles["h3"]))
        elif stripped.startswith("- "):
            elements.append(_paragraph(pdf, f"• {stripped[2:].strip()}", styles["body"]))
        elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == ".":
            elements.append(_paragraph(pdf, stripped, styles["body"]))
        else:
            elements.append(_paragraph(pdf, stripped, styles["body"]))

        index += 1

    if code_lines:
        elements.append(_paragraph(pdf, "\n".join(code_lines), styles["code"]))

    return elements


def build_policy_document_pdf() -> bytes:
    if not POLICY_DOCUMENT_PATH.exists():
        raise HTTPException(status_code=404, detail="policy.md 파일을 찾을 수 없습니다.")

    markdown = POLICY_DOCUMENT_PATH.read_text(encoding="utf-8")
    pdf = _load_reportlab()
    font_name = _register_pdf_font(pdf)
    buffer = BytesIO()

    doc = pdf["SimpleDocTemplate"](
        buffer,
        pagesize=pdf["A4"],
        rightMargin=18 * pdf["mm"],
        leftMargin=18 * pdf["mm"],
        topMargin=18 * pdf["mm"],
        bottomMargin=18 * pdf["mm"],
        title="ExtS3 Default Policy",
    )
    styles = pdf["getSampleStyleSheet"]()
    pdf_styles = {
        "title": pdf["ParagraphStyle"](
            "KoreanTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=18,
            leading=24,
            spaceAfter=10,
        ),
        "h2": pdf["ParagraphStyle"](
            "KoreanHeading2",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=19,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "h3": pdf["ParagraphStyle"](
            "KoreanHeading3",
            parent=styles["Heading3"],
            fontName=font_name,
            fontSize=12,
            leading=17,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": pdf["ParagraphStyle"](
            "KoreanBody",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=14,
            wordWrap="CJK",
        ),
        "table_cell": pdf["ParagraphStyle"](
            "KoreanTableCell",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=7,
            leading=10,
            wordWrap="CJK",
        ),
        "code": pdf["ParagraphStyle"](
            "KoreanCode",
            parent=styles["Code"],
            fontName=font_name,
            fontSize=7,
            leading=10,
            backColor=pdf["colors"].HexColor("#f0f4f8"),
            borderPadding=5,
            wordWrap="CJK",
        ),
    }

    elements = _markdown_to_pdf_elements(pdf, markdown, pdf_styles, font_name)
    elements.append(pdf["Spacer"](1, 8))
    elements.append(_paragraph(pdf, f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", pdf_styles["body"]))
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


@router.get("/api/admin/policy/default.pdf")
async def download_default_policy_pdf(
    _user: dict = Depends(require_permission("manage_extension_policy")),
):
    pdf_bytes = build_policy_document_pdf()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{DEFAULT_POLICY_PDF_FILENAME}"'},
    )
