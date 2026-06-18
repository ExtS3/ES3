"""Chrome 관리 정책 카탈로그.

batch.py의 ExtensionSettings 단일 정책 패턴을 일반화해서 Chrome 표준 5종 정책을 다룬다.
각 정책은 Pydantic 스키마 + 레지스트리 렌더러 + batch script 렌더러를 가진다.

레지스트리 경로: HKLM\\Software\\Policies\\Google\\Chrome
공식 문서: https://chromeenterprise.google/policies/
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


CHROME_POLICY_KEY = r"HKLM\Software\Policies\Google\Chrome"
CHROME_WEBSTORE_UPDATE_URL = "https://clients2.google.com/service/update2/crx"
EXTENSION_ID_PATTERN = re.compile(r"^[a-p]{32}$")


class InstallationMode(str, Enum):
    BLOCKED = "blocked"
    ALLOWED = "allowed"
    FORCE_INSTALLED = "force_installed"
    NORMAL_INSTALLED = "normal_installed"
    REMOVED = "removed"


class ExtensionType(str, Enum):
    EXTENSION = "extension"
    THEME = "theme"
    USER_SCRIPT = "user_script"
    HOSTED_APP = "hosted_app"
    LEGACY_PACKAGED_APP = "legacy_packaged_app"
    PLATFORM_APP = "platform_app"


class ChromePolicyName(str, Enum):
    EXTENSION_INSTALL_FORCELIST = "ExtensionInstallForcelist"
    EXTENSION_INSTALL_BLOCKLIST = "ExtensionInstallBlocklist"
    EXTENSION_INSTALL_ALLOWLIST = "ExtensionInstallAllowlist"
    EXTENSION_SETTINGS = "ExtensionSettings"
    EXTENSION_ALLOWED_TYPES = "ExtensionAllowedTypes"


def is_valid_extension_id(value: str) -> bool:
    return bool(EXTENSION_ID_PATTERN.fullmatch(value.lower()))


def is_extension_id_or_wildcard(value: str) -> bool:
    return value == "*" or is_valid_extension_id(value)


def _normalize_id(value: str) -> str:
    return value if value == "*" else value.lower()


class ExtensionSettingsRule(BaseModel):
    """ExtensionSettings 정책의 개별 확장 규칙 또는 '*' 전역 기본값."""

    installation_mode: InstallationMode
    update_url: Optional[str] = None
    override_update_url: bool = False
    allowed_permissions: Optional[List[str]] = None
    blocked_permissions: Optional[List[str]] = None
    runtime_blocked_hosts: Optional[List[str]] = None
    runtime_allowed_hosts: Optional[List[str]] = None
    minimum_version_required: Optional[str] = None

    def to_dict(self) -> dict:
        result: dict = {"installation_mode": self.installation_mode.value}
        installable = self.installation_mode in (
            InstallationMode.FORCE_INSTALLED,
            InstallationMode.NORMAL_INSTALLED,
        )
        if installable:
            result["update_url"] = self.update_url or CHROME_WEBSTORE_UPDATE_URL
            if self.override_update_url:
                result["override_update_url"] = True
        for attr, key in (
            ("allowed_permissions", "allowed_permissions"),
            ("blocked_permissions", "blocked_permissions"),
            ("runtime_blocked_hosts", "runtime_blocked_hosts"),
            ("runtime_allowed_hosts", "runtime_allowed_hosts"),
            ("minimum_version_required", "minimum_version_required"),
        ):
            value = getattr(self, attr)
            if value is not None:
                result[key] = value
        return result


class ExtensionSettingsPolicy(BaseModel):
    """ExtensionSettings: per-extension + '*' wildcard rules. JSON 단일 값으로 등록."""

    rules: Dict[str, ExtensionSettingsRule]

    @field_validator("rules")
    @classmethod
    def _validate_keys(cls, value: Dict[str, ExtensionSettingsRule]):
        normalized: Dict[str, ExtensionSettingsRule] = {}
        for key, rule in value.items():
            if not is_extension_id_or_wildcard(key):
                raise ValueError(f"Invalid extension id or wildcard: {key!r}")
            normalized[_normalize_id(key)] = rule
        if not normalized:
            raise ValueError("ExtensionSettings policy must have at least one rule")
        return normalized

    def to_json(self) -> str:
        return json.dumps(
            {key: rule.to_dict() for key, rule in self.rules.items()},
            separators=(",", ":"),
            sort_keys=True,
        )


class ExtensionInstallForcelistEntry(BaseModel):
    """ExtensionInstallForcelist 항목 — '<id>;<update_url>' 형태로 직렬화."""

    extension_id: str
    update_url: str = CHROME_WEBSTORE_UPDATE_URL

    @field_validator("extension_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not is_valid_extension_id(value):
            raise ValueError(f"Invalid extension id: {value!r}")
        return value.lower()

    def to_value(self) -> str:
        return f"{self.extension_id};{self.update_url}"


class ExtensionInstallForcelistPolicy(BaseModel):
    entries: List[ExtensionInstallForcelistEntry] = Field(min_length=1)

    def to_list(self) -> List[str]:
        return [entry.to_value() for entry in self.entries]


class ExtensionInstallBlocklistPolicy(BaseModel):
    """차단 목록. '*'로 전체 차단(allowlist와 짝)."""

    entries: List[str] = Field(min_length=1)

    @field_validator("entries")
    @classmethod
    def _validate_entries(cls, value: List[str]) -> List[str]:
        for entry in value:
            if not is_extension_id_or_wildcard(entry):
                raise ValueError(f"Invalid blocklist entry: {entry!r}")
        return [_normalize_id(entry) for entry in value]


class ExtensionInstallAllowlistPolicy(BaseModel):
    """허용 목록. blocklist=['*']일 때 의미를 가진다."""

    entries: List[str] = Field(min_length=1)

    @field_validator("entries")
    @classmethod
    def _validate_entries(cls, value: List[str]) -> List[str]:
        for entry in value:
            if not is_valid_extension_id(entry):
                raise ValueError(f"Invalid allowlist entry: {entry!r}")
        return [entry.lower() for entry in value]


class ExtensionAllowedTypesPolicy(BaseModel):
    """설치 허용 확장 타입 제한."""

    types: List[ExtensionType] = Field(min_length=1)

    def to_list(self) -> List[str]:
        return [t.value for t in self.types]


def _escape_powershell_single_quoted(value: str) -> str:
    return value.replace("'", "''")


def _render_string_set_property(name: str, value: str) -> str:
    escaped = _escape_powershell_single_quoted(value)
    return (
        f"powershell -NoProfile -ExecutionPolicy Bypass -Command "
        f"\"New-Item -Path 'Registry::{CHROME_POLICY_KEY}' -Force | Out-Null; "
        f"Set-ItemProperty -Path 'Registry::{CHROME_POLICY_KEY}' "
        f"-Name {name} -Type String -Value '{escaped}'\""
    )


def _render_list_subkey(name: str, entries: List[str]) -> str:
    subkey_path = f"{CHROME_POLICY_KEY}\\{name}"
    commands = [f"New-Item -Path 'Registry::{subkey_path}' -Force | Out-Null"]
    for index, entry in enumerate(entries, start=1):
        escaped = _escape_powershell_single_quoted(entry)
        commands.append(
            f"Set-ItemProperty -Path 'Registry::{subkey_path}' "
            f"-Name '{index}' -Type String -Value '{escaped}'"
        )
    inline = "; ".join(commands)
    return f"powershell -NoProfile -ExecutionPolicy Bypass -Command \"{inline}\""


def _admin_elevation_lines() -> List[str]:
    return [
        "@echo off",
        "setlocal",
        "",
        "net session >nul 2>&1",
        "if not \"%ERRORLEVEL%\"==\"0\" (",
        "  echo [ExtS3] Administrator permission is required.",
        "  echo [ExtS3] Reopening this script with UAC prompt...",
        "  powershell -NoProfile -ExecutionPolicy Bypass -Command \"Start-Process -FilePath '%~f0' -Verb RunAs\"",
        "  exit /b",
        ")",
        "",
    ]


def _failure_handler_lines(action: str) -> List[str]:
    return [
        "if errorlevel 1 (",
        f"  echo [ExtS3] Failed to {action}.",
        "  echo Try running this file again or contact your administrator.",
        "  pause",
        "  exit /b 1",
        ")",
        "",
    ]


def render_policy_batch(
    powershell_lines: List[str],
    *,
    header: str,
    action: str,
) -> str:
    lines = _admin_elevation_lines()
    lines.extend(
        [
            "echo.",
            f"echo [ExtS3] {header}",
            "echo.",
            "",
        ]
    )
    lines.extend(powershell_lines)
    lines.extend(_failure_handler_lines(action))
    lines.extend(
        [
            f"echo [ExtS3] {header} complete.",
            "echo [ExtS3] Chrome must restart to apply the policy.",
            "pause",
            "",
        ]
    )
    return "\r\n".join(lines)


def render_extension_settings_batch(policy: ExtensionSettingsPolicy) -> str:
    powershell = [
        _render_string_set_property(
            ChromePolicyName.EXTENSION_SETTINGS.value,
            policy.to_json(),
        )
    ]
    return render_policy_batch(
        powershell,
        header="Apply ExtensionSettings policy",
        action="apply ExtensionSettings policy",
    )


def render_forcelist_batch(policy: ExtensionInstallForcelistPolicy) -> str:
    powershell = [
        _render_list_subkey(
            ChromePolicyName.EXTENSION_INSTALL_FORCELIST.value,
            policy.to_list(),
        )
    ]
    return render_policy_batch(
        powershell,
        header="Apply ExtensionInstallForcelist policy",
        action="apply ExtensionInstallForcelist policy",
    )


def render_blocklist_batch(policy: ExtensionInstallBlocklistPolicy) -> str:
    powershell = [
        _render_list_subkey(
            ChromePolicyName.EXTENSION_INSTALL_BLOCKLIST.value,
            policy.entries,
        )
    ]
    return render_policy_batch(
        powershell,
        header="Apply ExtensionInstallBlocklist policy",
        action="apply ExtensionInstallBlocklist policy",
    )


def render_allowlist_batch(policy: ExtensionInstallAllowlistPolicy) -> str:
    powershell = [
        _render_list_subkey(
            ChromePolicyName.EXTENSION_INSTALL_ALLOWLIST.value,
            policy.entries,
        )
    ]
    return render_policy_batch(
        powershell,
        header="Apply ExtensionInstallAllowlist policy",
        action="apply ExtensionInstallAllowlist policy",
    )


def render_allowed_types_batch(policy: ExtensionAllowedTypesPolicy) -> str:
    powershell = [
        _render_list_subkey(
            ChromePolicyName.EXTENSION_ALLOWED_TYPES.value,
            policy.to_list(),
        )
    ]
    return render_policy_batch(
        powershell,
        header="Apply ExtensionAllowedTypes policy",
        action="apply ExtensionAllowedTypes policy",
    )
