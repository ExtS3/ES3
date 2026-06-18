import re
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from backend.auth.security import require_permission


router = APIRouter()

CHROME_WEBSTORE_UPDATE_URL = "https://clients2.google.com/service/update2/crx"
EXTENSION_ID_PATTERN = re.compile(r"^[a-p]{32}$")
CHROME_POLICY_KEY = r"HKLM\Software\Policies\Google\Chrome"


def is_valid_chrome_extension_id(extension_id: str) -> bool:
    return bool(EXTENSION_ID_PATTERN.fullmatch(extension_id))


def safe_batch_filename(extension_name: str, extension_id: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", extension_name).strip("_")
    if not safe_name:
        safe_name = extension_id
    return f"install_{safe_name}_{extension_id}.bat"


def safe_uninstall_batch_filename(extension_name: str, extension_id: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", extension_name).strip("_")
    if not safe_name:
        safe_name = extension_id
    return f"uninstall_{safe_name}_{extension_id}.bat"


def render_extension_settings_policy(extension_id: str) -> str:
    return json.dumps(
        {
            extension_id: {
                "installation_mode": "normal_installed",
                "update_url": CHROME_WEBSTORE_UPDATE_URL,
                "override_update_url": True,
            }
        },
        separators=(",", ":"),
    )


def render_install_batch(extension_id: str, extension_name: str) -> str:
    display_name = extension_name.encode("ascii", errors="ignore").decode("ascii").replace('"', "'")
    if not display_name:
        display_name = extension_id
    lines = [
        "@echo off",
        "setlocal",
        "",
        "net session >nul 2>&1",
        "if not \"%ERRORLEVEL%\"==\"0\" (",
        "  echo [ExtS3] Administrator permission is required.",
        "  echo [ExtS3] Reopening this installer with UAC prompt...",
        "  powershell -NoProfile -ExecutionPolicy Bypass -Command \"Start-Process -FilePath '%~f0' -Verb RunAs\"",
        "  exit /b",
        ")",
        "",
        f"set \"EXTENSION_ID={extension_id}\"",
        f"set \"EXTENSION_NAME={display_name}\"",
        f"set \"POLICY_KEY={CHROME_POLICY_KEY}\"",
        "",
        "echo.",
        "echo [ExtS3] Chrome extension install helper",
        "echo Target: %EXTENSION_NAME%",
        "echo ID: %EXTENSION_ID%",
        "echo.",
        "",
        "powershell -NoProfile -ExecutionPolicy Bypass -Command \"$policy=@{}; $policy[$env:EXTENSION_ID]=@{installation_mode='normal_installed'; update_url='" + CHROME_WEBSTORE_UPDATE_URL + "'; override_update_url=$true}; $json=$policy | ConvertTo-Json -Compress -Depth 5; New-Item -Path 'Registry::%POLICY_KEY%' -Force | Out-Null; Set-ItemProperty -Path 'Registry::%POLICY_KEY%' -Name ExtensionSettings -Type String -Value $json\"",
        "if errorlevel 1 (",
        "  echo.",
        "  echo [ExtS3] Failed to register the Chrome extension policy.",
        "  echo Try running this file again or contact your administrator.",
        "  pause",
        "  exit /b 1",
        ")",
        "",
        "echo.",
        "echo [ExtS3] Policy registration complete.",
        "echo [ExtS3] Chrome must restart to apply the extension policy.",
        "echo [ExtS3] Clearing previous external uninstall marker if it exists.",
        "powershell -NoProfile -ExecutionPolicy Bypass -Command \"$root=Join-Path $env:LOCALAPPDATA 'Google\\Chrome\\User Data'; if (Test-Path $root) { Get-ChildItem -Path $root -Filter Preferences -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $p=$_.FullName; try { $json=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json; if ($json.extensions -and $json.extensions.external_uninstalls -and ($json.extensions.external_uninstalls -contains $env:EXTENSION_ID)) { Copy-Item -LiteralPath $p -Destination ($p + '.exts3.bak') -Force; $json.extensions.external_uninstalls = @($json.extensions.external_uninstalls | Where-Object { $_ -ne $env:EXTENSION_ID }); $json | ConvertTo-Json -Depth 100 -Compress | Set-Content -LiteralPath $p -Encoding UTF8 } } catch {} } }\"",
        "echo [ExtS3] Press any key to close Chrome and reopen the extensions page.",
        "pause",
        "taskkill /IM chrome.exe /F >nul 2>&1",
        "set \"CHROME_EXE=\"",
        "if exist \"%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe\" set \"CHROME_EXE=%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe\"",
        "if not defined CHROME_EXE if exist \"%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe\" set \"CHROME_EXE=%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe\"",
        "if not defined CHROME_EXE if exist \"%LocalAppData%\\Google\\Chrome\\Application\\chrome.exe\" set \"CHROME_EXE=%LocalAppData%\\Google\\Chrome\\Application\\chrome.exe\"",
        "if not defined CHROME_EXE for /f \"tokens=2,*\" %%A in ('reg query \"HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe\" /ve 2^>nul') do set \"CHROME_EXE=%%B\"",
        "if not defined CHROME_EXE for /f \"tokens=2,*\" %%A in ('reg query \"HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe\" /ve 2^>nul') do set \"CHROME_EXE=%%B\"",
        "",
        "if defined CHROME_EXE (",
        "  start \"\" \"%CHROME_EXE%\" \"chrome://extensions\"",
        ") else (",
        "  echo.",
        "  echo [ExtS3] Chrome executable was not found automatically.",
        "  echo Open Chrome manually and go to chrome://extensions",
        ")",
        "pause",
        "",
    ]
    return "\r\n".join(lines)


def render_uninstall_batch(extension_id: str, extension_name: str) -> str:
    display_name = extension_name.encode("ascii", errors="ignore").decode("ascii").replace('"', "'")
    if not display_name:
        display_name = extension_id

    lines = [
        "@echo off",
        "setlocal",
        "",
        "net session >nul 2>&1",
        "if not \"%ERRORLEVEL%\"==\"0\" (",
        "  echo [ExtS3] Administrator permission is required.",
        "  echo [ExtS3] Reopening this uninstaller with UAC prompt...",
        "  powershell -NoProfile -ExecutionPolicy Bypass -Command \"Start-Process -FilePath '%~f0' -Verb RunAs\"",
        "  exit /b",
        ")",
        "",
        f"set \"EXTENSION_ID={extension_id}\"",
        f"set \"EXTENSION_NAME={display_name}\"",
        f"set \"POLICY_KEY={CHROME_POLICY_KEY}\"",
        "",
        "echo.",
        "echo [ExtS3] Chrome extension uninstall helper",
        "echo Target: %EXTENSION_NAME%",
        "echo ID: %EXTENSION_ID%",
        "echo.",
        "",
        "powershell -NoProfile -ExecutionPolicy Bypass -Command \"$path='Registry::%POLICY_KEY%'; if (Test-Path $path) { $current=(Get-ItemProperty -Path $path -Name ExtensionSettings -ErrorAction SilentlyContinue).ExtensionSettings; if ($current) { $settings=$current | ConvertFrom-Json; if ($settings.PSObject.Properties.Name -contains $env:EXTENSION_ID) { $settings.PSObject.Properties.Remove($env:EXTENSION_ID); if ($settings.PSObject.Properties.Count -gt 0) { $json=$settings | ConvertTo-Json -Compress -Depth 10; Set-ItemProperty -Path $path -Name ExtensionSettings -Type String -Value $json } else { Remove-ItemProperty -Path $path -Name ExtensionSettings -ErrorAction SilentlyContinue } } } }\"",
        "if errorlevel 1 (",
        "  echo.",
        "  echo [ExtS3] Failed to remove the Chrome extension policy.",
        "  echo Try running this file again or contact your administrator.",
        "  pause",
        "  exit /b 1",
        ")",
        "",
        "echo.",
        "echo [ExtS3] Policy removal complete.",
        "echo [ExtS3] Chrome must restart to apply the policy removal.",
        "echo [ExtS3] Press any key to close Chrome and reopen the extensions page.",
        "pause",
        "taskkill /IM chrome.exe /F >nul 2>&1",
        "set \"CHROME_EXE=\"",
        "if exist \"%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe\" set \"CHROME_EXE=%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe\"",
        "if not defined CHROME_EXE if exist \"%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe\" set \"CHROME_EXE=%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe\"",
        "if not defined CHROME_EXE if exist \"%LocalAppData%\\Google\\Chrome\\Application\\chrome.exe\" set \"CHROME_EXE=%LocalAppData%\\Google\\Chrome\\Application\\chrome.exe\"",
        "if not defined CHROME_EXE for /f \"tokens=2,*\" %%A in ('reg query \"HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe\" /ve 2^>nul') do set \"CHROME_EXE=%%B\"",
        "if not defined CHROME_EXE for /f \"tokens=2,*\" %%A in ('reg query \"HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe\" /ve 2^>nul') do set \"CHROME_EXE=%%B\"",
        "",
        "if defined CHROME_EXE (",
        "  start \"\" \"%CHROME_EXE%\" \"chrome://extensions\"",
        ") else (",
        "  echo.",
        "  echo [ExtS3] Chrome executable was not found automatically.",
        "  echo Open Chrome manually and go to chrome://extensions",
        ")",
        "pause",
        "",
    ]
    return "\r\n".join(lines)


@router.post("/api/install-helper/batch")
async def download_install_helper_batch(
    request: Request,
    _user: dict = Depends(require_permission("install_extension")),
):
    data = await request.json()
    extension_id = (data.get("extension_id") or "").strip().lower()
    extension_name = (data.get("extName") or data.get("extension_name") or extension_id).strip()

    if not is_valid_chrome_extension_id(extension_id):
        raise HTTPException(status_code=400, detail="유효한 Chrome Web Store 확장 ID가 아닙니다.")

    if not extension_name:
        extension_name = extension_id

    body = render_install_batch(extension_id, extension_name).encode("ascii")
    filename = safe_batch_filename(extension_name, extension_id)
    encoded_filename = quote(filename)

    return Response(
        content=body,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/api/install-helper/uninstall-batch")
async def download_uninstall_helper_batch(
    request: Request,
    _user: dict = Depends(require_permission("install_extension")),
):
    data = await request.json()
    extension_id = (data.get("extension_id") or "").strip().lower()
    extension_name = (data.get("extName") or data.get("extension_name") or extension_id).strip()

    if not is_valid_chrome_extension_id(extension_id):
        raise HTTPException(status_code=400, detail="유효한 Chrome Web Store 확장 ID가 아닙니다.")

    if not extension_name:
        extension_name = extension_id

    body = render_uninstall_batch(extension_id, extension_name).encode("ascii")
    filename = safe_uninstall_batch_filename(extension_name, extension_id)
    encoded_filename = quote(filename)

    return Response(
        content=body,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )
