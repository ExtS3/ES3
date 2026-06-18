import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional


def _resolve_clamav_binary() -> Optional[str]:
    # PATH 또는 환경변수로 ClamAV 실행 파일 위치를 찾는다.
    env_path = os.getenv("CLAMSCAN_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    for candidate in ("clamscan", "clamdscan"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _resolve_clamav_database() -> Optional[str]:
    # 사용자 지정 DB 경로를 우선 사용한다.
    database_path = os.getenv("CLAMAV_DATABASE")
    if database_path and os.path.exists(database_path):
        return database_path
    default_path = os.path.join("C:\\Program Files\\ClamAV", "database")
    if os.path.exists(default_path):
        return default_path
    return None


def _parse_infected_lines(output: str) -> List[str]:
    infected = []
    for line in output.splitlines():
        if line.rstrip().endswith("FOUND"):
            infected.append(line.strip())
    return infected


def scan_with_clamav(target: str) -> Dict[str, Any]:
    # ClamAV로 단일 파일/디렉터리를 스캔한다.
    binary = _resolve_clamav_binary()
    database_path = _resolve_clamav_database()
    if not binary:
        return {
            "available": False,
            "status": "unavailable",
            "target": target,
            "engine": None,
            "infected": False,
            "infected_files": [],
            "exit_code": None,
            "raw_output": "",
            "error": "ClamAV binary not found",
        }

    command = [binary, "--infected", "--no-summary"]
    if database_path:
        command.append(f"--database={database_path}")
    if os.path.isdir(target):
        command.append("--recursive")
    command.append(target)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except Exception as exc:
        return {
            "available": True,
            "status": "error",
            "target": target,
            "engine": os.path.basename(binary),
            "infected": False,
            "infected_files": [],
            "exit_code": None,
            "raw_output": "",
            "error": str(exc),
        }

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    infected_files = _parse_infected_lines(output)
    if completed.returncode == 0:
        status = "clean"
    elif completed.returncode == 1:
        status = "infected"
    else:
        status = "error"

    return {
        "available": True,
        "status": status,
        "target": target,
        "engine": os.path.basename(binary),
        "database": database_path,
        "infected": status == "infected",
        "infected_files": infected_files,
        "exit_code": completed.returncode,
        "raw_output": output,
        "error": None if status != "error" else output or "ClamAV scan failed",
    }


def run_clamav_bundle_scan(package_path: str, extracted_target: Optional[str] = None) -> Dict[str, Any]:
    # 원본 패키지와 압축 해제 루트를 함께 스캔하고 결과를 합친다.
    package_result = scan_with_clamav(package_path)
    extracted_result = None
    if extracted_target and os.path.abspath(extracted_target) != os.path.abspath(package_path):
        extracted_result = scan_with_clamav(extracted_target)

    infected_files: List[str] = []
    for result in (package_result, extracted_result):
        if isinstance(result, dict):
            infected_files.extend(result.get("infected_files", []))

    available = package_result.get("available", False) or (extracted_result or {}).get("available", False)
    infected = package_result.get("infected", False) or (extracted_result or {}).get("infected", False)
    status = "unavailable"
    if available:
        if infected:
            status = "infected"
        elif package_result.get("status") == "error" or (extracted_result or {}).get("status") == "error":
            status = "error"
        else:
            status = "clean"

    return {
        "available": available,
        "status": status,
        "infected": infected,
        "infected_files": infected_files,
        "package_scan": package_result,
        "extracted_scan": extracted_result,
    }
