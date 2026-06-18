import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def _load_env():
    candidates = [
        PROJECT_ROOT / ".env",
        PROJECT_ROOT.parent / ".env",
    ]
    for path in candidates:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.split("#")[0].strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        break


_load_env()


def _resolve(env_key: str, default: str) -> str:
    val = os.getenv(env_key, default)
    p = Path(val)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return str(p)


# 홀딩 시간 (테스트: 30 / 실서비스: 604800 = 7일)
HOLDING_SECONDS = int(os.getenv("HOLDING_SECONDS", "30"))

# Nexus
NEXUS_BASE_URL = os.getenv("NEXUS_BASE_URL", "http://localhost:8081")
NEXUS_REPO     = os.getenv("NEXUS_REPOSITORY", "es3")
NEXUS_USERNAME = os.getenv("NEXUS_USERNAME", "admin")
NEXUS_PASSWORD = os.getenv("NEXUS_PASSWORD", "admin123")

# 스케줄러 폴더
PENDING_DIR = _resolve("PENDING_DIR", "pending")
OUTPUT_DIR  = _resolve("OUTPUT_DIR", "released")

# 홀딩 만료 후 파일을 전달할 스캔 엔드포인트
FILE_SCAN_URL = os.getenv("FILE_SCAN_URL", "http://localhost:8000/file_scan")
