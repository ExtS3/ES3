import os
import json
import shutil
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

load_dotenv()

pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))

NEXUS_BASE_URL = os.getenv("NEXUS_BASE_URL")
NEXUS_REPOSITORY = os.getenv("NEXUS_REPOSITORY")
NEXUS_USERNAME = os.getenv("NEXUS_USERNAME")
NEXUS_PASSWORD = os.getenv("NEXUS_PASSWORD")

REJECT_LIST_PATH = Path(__file__).resolve().parents[1] / "reject_list.json"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_RESULT_PATH = PROJECT_ROOT / "analysis_result"


def get_extension_payload(data):
    ext_id = data.get("id")
    app_name = data.get("app_name") or data.get("name")
    browser = data.get("browser") or data.get("app_browser")
    version = data.get("version")

    missing = [
        key for key, value in {
            "id": ext_id,
            "app_name": app_name,
            "browser": browser,
            "version": version,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing)}")

    values = {
        "id": str(ext_id).strip(),
        "app_name": str(app_name).strip(),
        "browser": str(browser).strip(),
        "version": str(version).strip(),
        "source_path": str(data.get("source_path") or "").strip(),
    }

    for key, value in values.items():
        if key == "source_path":
            continue
        if "/" in value or "\\" in value:
            raise HTTPException(status_code=400, detail=f"Invalid path segment: {key}")

    if values["source_path"]:
        values["source_path"] = validate_review_path(values["source_path"])

    return values


def validate_review_path(path):
    path = str(path or "").strip().lstrip("/")
    if "\\" in path or ".." in path.split("/"):
        raise HTTPException(status_code=400, detail="Invalid source path")
    if not path.startswith("review/") or not path.endswith(".zip"):
        raise HTTPException(status_code=400, detail="source_path must be a review zip path")
    return path


def normalize_nexus_path(path):
    return str(path or "").strip().lstrip("/")


def build_nexus_path(status, browser, app_name, version, ext_id):
    filename = ext_id if ext_id.endswith(".zip") else f"{ext_id}.zip"
    return f"{status}/{browser}/{app_name}/{version}/{filename}"


def build_review_source_path(payload):
    if payload.get("source_path"):
        return payload["source_path"]

    return build_nexus_path(
        "review",
        payload["browser"],
        payload["app_name"],
        payload["version"],
        payload["id"],
    )


def build_safe_path_from_review_path(source_path):
    source_path = validate_review_path(source_path)
    return source_path.replace("review/", "safe/", 1)


def _find_child_case_insensitive(parent, child_name):
    if not parent.exists() or not parent.is_dir():
        return None

    child_lower = child_name.strip().lower()
    for child in parent.iterdir():
        if child.name.strip().lower() == child_lower:
            return child
    return None


def delete_analysis_result_for_review_path(source_path):
    source_path = validate_review_path(source_path)

    relative_parts = Path(source_path[:-4]).parts
    target_path = ANALYSIS_RESULT_PATH
    for part in relative_parts:
        target_path = _find_child_case_insensitive(target_path, part)
        if target_path is None:
            return None

    analysis_root = ANALYSIS_RESULT_PATH.resolve()
    resolved_target = target_path.resolve()
    try:
        resolved_target.relative_to(analysis_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid analysis_result delete path")

    if not resolved_target.is_dir():
        return None

    shutil.rmtree(resolved_target)

    review_root = (ANALYSIS_RESULT_PATH / "review").resolve()
    current = resolved_target.parent
    while current != review_root and current != analysis_root:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent

    return str(resolved_target)


def nexus_file_url(path):
    missing_env = [
        name for name, value in {
            "NEXUS_BASE_URL": NEXUS_BASE_URL,
            "NEXUS_REPOSITORY": NEXUS_REPOSITORY,
            "NEXUS_USERNAME": NEXUS_USERNAME,
            "NEXUS_PASSWORD": NEXUS_PASSWORD,
        }.items()
        if not value
    ]
    if missing_env:
        raise HTTPException(status_code=500, detail=f"Missing Nexus env vars: {', '.join(missing_env)}")

    encoded_path = quote(path, safe="/")
    return f"{NEXUS_BASE_URL}/repository/{NEXUS_REPOSITORY}/{encoded_path}"


def fetch_nexus_asset_paths():
    missing_env = [
        name for name, value in {
            "NEXUS_BASE_URL": NEXUS_BASE_URL,
            "NEXUS_REPOSITORY": NEXUS_REPOSITORY,
            "NEXUS_USERNAME": NEXUS_USERNAME,
            "NEXUS_PASSWORD": NEXUS_PASSWORD,
        }.items()
        if not value
    ]
    if missing_env:
        raise HTTPException(status_code=500, detail=f"Missing Nexus env vars: {', '.join(missing_env)}")

    assets_url = f"{NEXUS_BASE_URL}/service/rest/v1/assets"
    paths = []
    continuation_token = None

    while True:
        params = {"repository": NEXUS_REPOSITORY}
        if continuation_token:
            params["continuationToken"] = continuation_token

        response = requests.get(
            assets_url,
            auth=(NEXUS_USERNAME, NEXUS_PASSWORD),
            params=params,
            timeout=10,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Nexus asset lookup failed: {response.status_code}")

        data = response.json()
        paths.extend(normalize_nexus_path(item.get("path")) for item in data.get("items", []) if item.get("path"))
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            return paths


def resolve_review_source_path(requested_path):
    requested_path = validate_review_path(requested_path)
    asset_paths = fetch_nexus_asset_paths()

    if requested_path in asset_paths:
        return requested_path

    requested_lower = requested_path.lower()
    for path in asset_paths:
        if path.lower() == requested_lower:
            return path

    raise HTTPException(status_code=404, detail=f"Nexus file not found: {requested_path}")


def get_nexus_file(path):
    response = requests.get(
        nexus_file_url(path),
        auth=(NEXUS_USERNAME, NEXUS_PASSWORD),
        timeout=60,
    )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Nexus file not found: {path}")
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Nexus download failed: {response.status_code}",
        )
    return response.content


def put_nexus_file(path, content):
    response = requests.put(
        nexus_file_url(path),
        data=content,
        auth=(NEXUS_USERNAME, NEXUS_PASSWORD),
        headers={"Content-Type": "application/zip"},
        timeout=60,
    )
    if response.status_code not in (200, 201, 204):
        raise HTTPException(
            status_code=502,
            detail=f"Nexus upload failed: {response.status_code}",
        )


def delete_nexus_file(path):
    response = requests.delete(
        nexus_file_url(path),
        auth=(NEXUS_USERNAME, NEXUS_PASSWORD),
        timeout=60,
    )
    if response.status_code not in (200, 202, 204, 404):
        raise HTTPException(
            status_code=502,
            detail=f"Nexus delete failed: {response.status_code}",
        )


def move_nexus_file(source_path, target_path):
    content = get_nexus_file(source_path)
    put_nexus_file(target_path, content)
    delete_nexus_file(source_path)


def append_reject_record(record):
    REJECT_LIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    if REJECT_LIST_PATH.exists():
        try:
            records = json.loads(REJECT_LIST_PATH.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                records = []
        except Exception:
            records = []
    else:
        records = []

    records.append({
        **record,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    })

    REJECT_LIST_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_reject_records():
    if not REJECT_LIST_PATH.exists():
        return []

    try:
        records = json.loads(REJECT_LIST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(records, list):
        return []

    return sorted(
        records,
        key=lambda item: item.get("rejected_at") or "",
        reverse=True,
    )


_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle(
    "KTitle", parent=_STYLES["Title"], fontName="HYGothic-Medium",
)
_META_STYLE = ParagraphStyle(
    "KMeta", parent=_STYLES["Normal"], fontName="HYGothic-Medium",
    fontSize=9, textColor=colors.HexColor("#4a5568"),
)
_CELL_STYLE = ParagraphStyle(
    "KCell", parent=_STYLES["Normal"], fontName="HYGothic-Medium",
    fontSize=8, leading=11, alignment=TA_LEFT,
)
_HEADER_STYLE = ParagraphStyle(
    "KHeader", parent=_CELL_STYLE, textColor=colors.white,
)


def build_reject_report_pdf(records):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=15 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        title="Rejected Extension Report",
    )

    elements = [
        Paragraph("거절된 확장 프로그램 보고서", _TITLE_STYLE),
        Spacer(1, 4 * mm),
        Paragraph(
            f"생성 시각: {datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')} KST",
            _META_STYLE,
        ),
        Paragraph(f"총 거절 건수: {len(records)}건", _META_STYLE),
        Spacer(1, 6 * mm),
    ]

    if not records:
        elements.append(Paragraph("거절된 확장 프로그램이 없습니다.", _META_STYLE))
    else:
        header = ["#", "앱 이름", "ID", "브라우저", "버전", "거절 시각", "경로"]
        data = [[Paragraph(text, _HEADER_STYLE) for text in header]]
        for index, item in enumerate(records, start=1):
            row = [
                str(index),
                item.get("app_name") or item.get("id") or "Unknown",
                item.get("id") or "Unknown",
                item.get("browser") or "Unknown",
                item.get("version") or "Unknown",
                item.get("rejected_at") or "Unknown",
                item.get("source_path") or "",
            ]
            data.append([Paragraph(str(value), _CELL_STYLE) for value in row])

        table = Table(
            data,
            colWidths=[8 * mm, 28 * mm, 24 * mm, 20 * mm, 16 * mm, 42 * mm, 42 * mm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d3748")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(table)

    doc.build(elements)
    return buffer.getvalue()
