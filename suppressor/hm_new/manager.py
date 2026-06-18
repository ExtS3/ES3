# hold 명령 진입점
# 넥서스에 zip 저장 + pending 폴더에 파일 생성 → 스케줄러가 감지해서 잡 등록

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict

from . import nexus
from .config import HOLDING_SECONDS, PENDING_DIR

log = logging.getLogger(__name__)


def request_holding(
    extension_id: str,
    browser: str,
    version: str,
    ext_name: str,
    file_data: bytes,
) -> Dict[str, Any]:
    # 이미 홀딩 중인지 확인 (pending 파일 존재 여부)
    pending_path = os.path.join(PENDING_DIR, f"{extension_id}.json")
    if os.path.exists(pending_path):
        log.warning("이미 홀딩 중: ext=%s", extension_id)
        return {
            "registered": False,
            "extension_id": extension_id,
            "reason": "이미 홀딩 중입니다.",
        }

    release_at = time.time() + HOLDING_SECONDS

    # 넥서스에 zip 바이너리 저장
    nexus.upload(extension_id, browser, version, ext_name, file_data)

    # pending 폴더에 파일 생성 → 스케줄러가 감지해서 릴리즈 잡 등록
    # 릴리즈 시점에 메타정보가 필요하므로 모두 저장
    payload = {
        "extension_id": extension_id,
        "browser": browser,
        "version": version,
        "ext_name": ext_name,
        "release_at": datetime.fromtimestamp(release_at, tz=timezone.utc).isoformat(),
    }
    with open(pending_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    log.info("홀딩 등록: ext=%s (%s초 후 릴리즈)", extension_id, HOLDING_SECONDS)
    return {
        "registered": True,
        "extension_id": extension_id,
        "holding_seconds": HOLDING_SECONDS,
    }
