import base64
import logging
import urllib.error
import urllib.parse
import urllib.request

from .config import NEXUS_BASE_URL, NEXUS_PASSWORD, NEXUS_REPO, NEXUS_USERNAME

log = logging.getLogger(__name__)


def _headers() -> dict:
    token = base64.b64encode(f"{NEXUS_USERNAME}:{NEXUS_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _file_url(browser: str, ext_name: str, version: str, extension_id: str) -> str:
    """holding/[browser]/[extName]/[version]/[extension_id].zip (한글,공백 URL 인코딩)"""
    path = f"holding/{browser}/{ext_name}/{version}/{extension_id}.zip"
    encoded_path = urllib.parse.quote(path, safe="/")
    return f"{NEXUS_BASE_URL}/repository/{NEXUS_REPO}/{encoded_path}"


# 넥서스에 zip 바이너리 저장
def upload(extension_id: str, browser: str, version: str, ext_name: str, file_data: bytes):
    url = _file_url(browser, ext_name, version, extension_id)
    headers = {**_headers(), "Content-Type": "application/octet-stream"}
    req = urllib.request.Request(url, data=file_data, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=30):
            log.info("넥서스 저장 완료: ext=%s → %s", extension_id, url)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"넥서스 저장 실패: HTTP {e.code} → {url}") from e


# 넥서스에서 zip 바이너리 다운로드
def download(extension_id: str, browser: str, version: str, ext_name: str) -> bytes:
    url = _file_url(browser, ext_name, version, extension_id)
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            log.info("넥서스 다운로드 완료: ext=%s (%d bytes)", extension_id, len(data))
            return data
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"넥서스 다운로드 실패: HTTP {e.code} → {url}") from e


# 넥서스에서 해당 항목 삭제
def delete(extension_id: str, browser: str, version: str, ext_name: str):
    url = _file_url(browser, ext_name, version, extension_id)
    req = urllib.request.Request(url, headers=_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=15):
            log.info("넥서스 삭제 완료: ext=%s", extension_id)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise RuntimeError(f"넥서스 삭제 실패: HTTP {e.code}") from e
