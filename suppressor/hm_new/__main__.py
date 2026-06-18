"""
사용법:
  python -m hm_new              # 스케줄러 실행 (Ctrl+C로 종료)
  python -m hm_new hold <id>    # 홀딩 등록 후 즉시 종료
"""

import subprocess
import sys


def _ensure_packages():
    from pathlib import Path
    req = Path(__file__).parent / "requirements.txt"
    if not req.exists():
        return
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"패키지 설치 실패: {e}")
        sys.exit(1)


_ensure_packages()

import logging
import time
from . import request_holding, start, stop
from .config import HOLDING_SECONDS, NEXUS_BASE_URL, NEXUS_REPO, OUTPUT_DIR, PENDING_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def main():
    args = sys.argv[1:]

    if args and args[0] == "hold":
        if len(args) < 2:
            print("사용법: python -m hm_new hold <extension_id>")
            sys.exit(1)
        extension_id = args[1]
        result = request_holding(extension_id)
        if not result["registered"]:
            print(f"홀딩 등록 실패: {result['reason']}")
            sys.exit(1)
        print(f"홀딩 등록 완료")
        print(f"  extension_id : {result['extension_id']}")
        print(f"  홀딩 시간    : {HOLDING_SECONDS}초")
        print(f"  넥서스       : {NEXUS_BASE_URL}/repository/{NEXUS_REPO}/holding/")
        print(f"  릴리즈 폴더  : {OUTPUT_DIR}")
        return

    start()
    print(f"스케줄러 실행 중 (Ctrl+C로 종료)")
    print(f"  홀딩 시간    : {HOLDING_SECONDS}초")
    print(f"  넥서스       : {NEXUS_BASE_URL}/repository/{NEXUS_REPO}/holding/")
    print(f"  pending 폴더 : {PENDING_DIR}")
    print(f"  릴리즈 폴더  : {OUTPUT_DIR}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop()
        print("종료")


if __name__ == "__main__":
    main()
