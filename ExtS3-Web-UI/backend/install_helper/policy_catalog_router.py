"""Chrome 정책 카탈로그 REST API.

GET  /api/install-helper/policy-catalog/types     — 5종 정책 타입 목록 + 예시 JSON
POST /api/install-helper/policy-catalog/render    — 입력 JSON 받아 batch 스크립트 미리보기
POST /api/install-helper/policy-catalog/download  — 입력 JSON 받아 .bat 파일 다운로드
"""

from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from backend.auth.security import require_admin

from .policy_catalog import (
    ChromePolicyName,
    ExtensionAllowedTypesPolicy,
    ExtensionInstallAllowlistPolicy,
    ExtensionInstallBlocklistPolicy,
    ExtensionInstallForcelistEntry,
    ExtensionInstallForcelistPolicy,
    ExtensionSettingsPolicy,
    ExtensionSettingsRule,
    ExtensionType,
    InstallationMode,
    render_allowed_types_batch,
    render_allowlist_batch,
    render_blocklist_batch,
    render_extension_settings_batch,
    render_forcelist_batch,
)


router = APIRouter(
    prefix="/api/install-helper/policy-catalog",
    dependencies=[Depends(require_admin)],
)


VALID_DEMO_ID = "a" * 32


_TYPES = [
    {
        "type": "forcelist",
        "policy_name": ChromePolicyName.EXTENSION_INSTALL_FORCELIST.value,
        "title": "강제 설치 (Forcelist)",
        "description": "지정 확장을 자동 설치하고 사용자가 제거할 수 없게 한다.",
        "example": {
            "entries": [
                {"extension_id": VALID_DEMO_ID},
            ]
        },
    },
    {
        "type": "blocklist",
        "policy_name": ChromePolicyName.EXTENSION_INSTALL_BLOCKLIST.value,
        "title": "설치 차단 (Blocklist)",
        "description": "* 입력 시 전체 차단. Allowlist와 짝지어 화이트리스트 정책으로 사용.",
        "example": {"entries": ["*"]},
    },
    {
        "type": "allowlist",
        "policy_name": ChromePolicyName.EXTENSION_INSTALL_ALLOWLIST.value,
        "title": "설치 허용 (Allowlist)",
        "description": "Blocklist=['*']일 때 의미. 명시한 확장만 설치 허용.",
        "example": {"entries": [VALID_DEMO_ID]},
    },
    {
        "type": "extension_settings",
        "policy_name": ChromePolicyName.EXTENSION_SETTINGS.value,
        "title": "확장별 세부 정책 (ExtensionSettings)",
        "description": "extension별 installation_mode, 권한, 호스트, 최소 버전 등을 한 JSON에 묶음.",
        "example": {
            "rules": {
                VALID_DEMO_ID: {
                    "installation_mode": InstallationMode.FORCE_INSTALLED.value,
                    "blocked_permissions": ["downloads", "cookies"],
                    "runtime_blocked_hosts": ["*://*.example.com"],
                },
                "*": {"installation_mode": InstallationMode.BLOCKED.value},
            }
        },
    },
    {
        "type": "allowed_types",
        "policy_name": ChromePolicyName.EXTENSION_ALLOWED_TYPES.value,
        "title": "설치 가능 타입 (AllowedTypes)",
        "description": "extension, theme, user_script 등 설치 가능한 타입을 제한.",
        "example": {"types": [ExtensionType.EXTENSION.value, ExtensionType.THEME.value]},
    },
]


_RENDERERS = {
    "forcelist": (ExtensionInstallForcelistPolicy, render_forcelist_batch, "forcelist"),
    "blocklist": (ExtensionInstallBlocklistPolicy, render_blocklist_batch, "blocklist"),
    "allowlist": (ExtensionInstallAllowlistPolicy, render_allowlist_batch, "allowlist"),
    "extension_settings": (ExtensionSettingsPolicy, render_extension_settings_batch, "extension_settings"),
    "allowed_types": (ExtensionAllowedTypesPolicy, render_allowed_types_batch, "allowed_types"),
}


def _build_batch(policy_type: str, payload: dict) -> tuple[str, str]:
    if policy_type not in _RENDERERS:
        raise HTTPException(status_code=400, detail=f"Unknown policy type: {policy_type!r}")
    model_cls, renderer, slug = _RENDERERS[policy_type]
    try:
        policy = model_cls.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    script = renderer(policy)
    filename = f"chrome_policy_{slug}.bat"
    return script, filename


@router.get("/types")
async def list_policy_types() -> JSONResponse:
    return JSONResponse(content={"types": _TYPES})


@router.post("/render")
async def render_policy(
    policy_type: str = Body(..., embed=True),
    payload: dict = Body(..., embed=True),
) -> JSONResponse:
    script, filename = _build_batch(policy_type, payload)
    return JSONResponse(content={"script": script, "filename": filename})


@router.post("/download")
async def download_policy(
    policy_type: str = Body(..., embed=True),
    payload: dict = Body(..., embed=True),
) -> Response:
    script, filename = _build_batch(policy_type, payload)
    body = script.encode("ascii", errors="ignore")
    encoded_filename = quote(filename)
    return Response(
        content=body,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )
