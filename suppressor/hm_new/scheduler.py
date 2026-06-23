# 스케줄러 — pending 폴더 감시 + trigger="date"로 정확한 만료 시각에 릴리즈
# 릴리즈: 넥서스에서 zip 다운로드 → /file_scan으로 POST 전송 → 넥서스·pending 파일 삭제

import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from apscheduler.schedulers.background import BackgroundScheduler

from .config import FILE_SCAN_URL, PENDING_DIR
from . import nexus

log = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


# 홀딩 만료 시 실행 — 넥서스에서 zip 꺼내서 /file_scan으로 POST, 이후 삭제
def _release_job(extension_id: str, browser: str, version: str, ext_name: str):
    log.info("홀딩 만료 → 릴리즈: ext=%s", extension_id)
    try:
        # 1. 넥서스에서 zip 바이너리 다운로드
        file_data = nexus.download(extension_id, browser, version, ext_name)

        # 2. /file_scan 으로 multipart POST 전송 (fire-and-forget, 응답 무시)
        try:
            resp = requests.post(
                FILE_SCAN_URL,
                files={"file": (f"{extension_id}.zip", io.BytesIO(file_data), "application/zip")},
                data={
                    "extID": extension_id,
                    "browser": browser,
                    "version": version,
                    "extName": ext_name,
                },
                timeout=300,
            )
            log.info("/file_scan 전송 완료: ext=%s status=%s", extension_id, resp.status_code)
        except Exception as post_err:
            log.warning("/file_scan 전송 실패 (계속 진행): ext=%s err=%s", extension_id, post_err)

        # 3. 넥서스에서 삭제
        nexus.delete(extension_id, browser, version, ext_name)

        # 4. pending 파일 삭제
        pending_path = os.path.join(PENDING_DIR, f"{extension_id}.json")
        if os.path.exists(pending_path):
            os.remove(pending_path)

        log.info("릴리즈 완료: ext=%s", extension_id)

    except Exception:
        log.exception("릴리즈 실패: ext=%s", extension_id)


# pending 파일 읽어서 릴리즈 잡 등록
def _register_from_pending(filepath: str):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            meta = json.load(f)

        ext_id   = meta["extension_id"]
        browser  = meta["browser"]
        version  = meta["version"]
        ext_name = meta["ext_name"]
        release_at = datetime.fromisoformat(meta["release_at"]).timestamp()
        remaining  = release_at - time.time()

        if remaining <= 0:
            log.info("pending 감지: ext=%s 이미 만료 → 즉시 릴리즈", ext_id)
            _release_job(ext_id, browser, version, ext_name)
        else:
            run_date = datetime.fromtimestamp(release_at, tz=timezone.utc)
            _scheduler.add_job(
                _release_job,
                trigger="date",
                run_date=run_date,
                args=[ext_id, browser, version, ext_name],
                id=f"release_{ext_id}",
                replace_existing=True,
                misfire_grace_time=None,  # 실행이 늦어도 무조건 릴리즈 (기본 1초 grace로 인한 드롭 방지)
            )
            log.info("pending 감지: ext=%s → %.0f초 후 릴리즈 예약", ext_id, remaining)

    except Exception as e:
        log.warning("pending 처리 실패: %s err=%s", filepath, e)


# 재시작 시 pending 폴더에 남아있는 파일로 잡 재등록
def _reschedule_from_pending():
    for filename in os.listdir(PENDING_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(PENDING_DIR, filename)
        log.info("재시작 복구: %s", filename)
        _register_from_pending(filepath)


def start():
    global _scheduler

    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class _PendingHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory or not event.src_path.endswith(".json"):
                return
            log.info("새 pending 파일 감지: %s", event.src_path)
            time.sleep(0.1)  # 파일 쓰기 완료 대기
            _register_from_pending(event.src_path)

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.start()

    _reschedule_from_pending()

    observer = Observer()
    observer.schedule(_PendingHandler(), path=PENDING_DIR, recursive=False)
    observer.start()

    log.info("스케줄러 시작 (pending 폴더 감시 중: %s)", PENDING_DIR)


def stop():
    if _scheduler:
        _scheduler.shutdown()
        log.info("스케줄러 종료")
