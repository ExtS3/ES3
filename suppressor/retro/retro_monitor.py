#!/usr/bin/env python3
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import argparse
import base64
import hashlib
import io
import json
import logging
import os
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

try:
    import yara
except Exception:
    yara = None


ID_REGEX = re.compile(r"^[a-p]{32}$")
VERSION_REGEX = re.compile(r"^\d+(?:\.\d+)*$")


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def safe_json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_version(version: str) -> Tuple[int, ...]:
    if not version:
        return tuple()
    parts = []
    for part in re.split(r"[._-]", version.strip()):
        if part.isdigit():
            parts.append(int(part))
        else:
            digits = re.findall(r"\d+", part)
            parts.append(int(digits[0]) if digits else 0)
    return tuple(parts)


def compare_versions(a: str, b: str) -> int:
    na, nb = normalize_version(a), normalize_version(b)
    max_len = max(len(na), len(nb))
    na += (0,) * (max_len - len(na))
    nb += (0,) * (max_len - len(nb))
    if na > nb:
        return 1
    if na < nb:
        return -1
    return 0


def chrome_id_from_public_key_b64(public_key_b64: str) -> Optional[str]:
    try:
        raw = base64.b64decode(public_key_b64)
        digest = hashlib.sha256(raw).hexdigest()[:32]
        trans = str.maketrans("0123456789abcdef", "abcdefghijklmnop")
        ext_id = digest.translate(trans)
        if ID_REGEX.match(ext_id):
            return ext_id
    except Exception:
        return None
    return None


def slugify(text: str) -> str:
    value = (text or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "extension"


@dataclass
class Settings:
    nexus_base_url: str
    nexus_repository: str
    nexus_username: str
    nexus_password: str
    state_path: Path = Path("./retro_state.json")
    queue_path: Path = Path("./retro_queue.jsonl")
    verify_ssl: bool = True
    user_agent: str = "retro-monitor/1.0"
    request_timeout: int = 30
    interval_hours: int = 24
    layerx_base_url: str = "https://layerxsecurity.com"
    layerx_save_raw_html: bool = False
    layerx_summary_char_limit: int = 400
    yara_rule_path: Optional[Path] = None
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            nexus_base_url=os.environ["NEXUS_BASE_URL"].rstrip("/"),
            nexus_repository=os.environ["NEXUS_REPOSITORY"],
            nexus_username=os.environ["NEXUS_USERNAME"],
            nexus_password=os.environ["NEXUS_PASSWORD"],
            state_path=Path(os.getenv("RETRO_STATE_PATH", "./retro_state.json")),
            queue_path=Path(os.getenv("RETRO_QUEUE_PATH", "./retro_queue.jsonl")),
            verify_ssl=os.getenv("NEXUS_VERIFY_SSL", "true").lower() in {"1", "true", "yes", "y"},
            user_agent=os.getenv("USER_AGENT", "retro-monitor/1.0"),
            request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
            interval_hours=int(os.getenv("RETRO_INTERVAL_HOURS", "24")),
            layerx_base_url=os.getenv("LAYERX_BASE_URL", "https://layerxsecurity.com").rstrip("/"),
            layerx_save_raw_html=os.getenv("LAYERX_SAVE_RAW_HTML", "false").lower() in {"1", "true", "yes", "y"},
            layerx_summary_char_limit=int(os.getenv("LAYERX_SUMMARY_CHAR_LIMIT", "400")),
            yara_rule_path=Path(os.environ["YARA_RULE_PATH"]) if os.getenv("YARA_RULE_PATH") else None,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


@dataclass
class ExtensionArtifact:
    asset_id: Optional[str]
    name: str
    path: str
    download_url: str
    file_name: str
    file_ext: str
    sha256: Optional[str] = None
    manifest_version: Optional[str] = None
    extension_id: Optional[str] = None
    store_url: Optional[str] = None
    homepage_url: Optional[str] = None
    update_url: Optional[str] = None
    package_name: Optional[str] = None
    manifest_key_present: bool = False


class NexusClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(settings.nexus_username, settings.nexus_password)
        self.session.headers.update({"User-Agent": settings.user_agent})
        self.session.verify = settings.verify_ssl

    def list_assets(self) -> Iterator[dict]:
        url = f"{self.settings.nexus_base_url}/service/rest/v1/assets"
        continuation_token = None
        while True:
            params = {"repository": self.settings.nexus_repository}
            if continuation_token:
                params["continuationToken"] = continuation_token
            resp = self.session.get(url, params=params, timeout=self.settings.request_timeout)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("items", []):
                yield item
            continuation_token = data.get("continuationToken")
            if not continuation_token:
                break

    def download_asset(self, download_url: str) -> bytes:
        resp = self.session.get(download_url, timeout=self.settings.request_timeout)
        if resp.status_code == 404:
            return None  # 🔥 여기
        resp.raise_for_status()
        return resp.content


class StoreVersionClient:
    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    def get_latest_version(self, extension_id: str) -> Optional[str]:
        if not sync_playwright:
            raise RuntimeError("playwright is not installed. Install with: pip install playwright && playwright install chromium")
        url = f"https://chromewebstore.google.com/detail/x/{extension_id}"
        selectors = ['div:has-text("Version")', 'span:has-text("Version")', 'div[role="main"]', 'body']
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_seconds * 1000)
                page.wait_for_timeout(2500)
                candidates = []
                for sel in selectors:
                    try:
                        text = page.locator(sel).first.inner_text(timeout=2000)
                        if text:
                            candidates.append(text)
                    except Exception:
                        pass
                try:
                    candidates.append(page.content())
                except Exception:
                    pass
                for blob in candidates:
                    version = self._extract_version(blob)
                    if version:
                        return version
            finally:
                browser.close()
        return None

    @staticmethod
    def _extract_version(text: str) -> Optional[str]:
        patterns = [
            r"Version\s*([0-9]+(?:\.[0-9]+)+)",
            r'"version"\s*[:=]\s*"([0-9]+(?:\.[0-9]+)+)"',
            r">\s*([0-9]+(?:\.[0-9]+){1,})\s*<",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                value = m.group(1).strip()
                if VERSION_REGEX.match(value):
                    return value
        return None


class LayerXReputationChecker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})
        self.compiled_yara = None
        if settings.yara_rule_path and yara is not None and settings.yara_rule_path.exists():
            self.compiled_yara = yara.compile(filepath=str(settings.yara_rule_path))

    def check_extension(self, artifact: ExtensionArtifact) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "provider": "layerx",
            "enabled": True,
            "status": "not_checked",
            "extension_id": artifact.extension_id,
            "url": None,
            "title": None,
            "risk_summary": {},
            "sections": {},
            "summary": {},
        }
        if not artifact.extension_id:
            result["status"] = "missing_extension_id"
            return result

        url = self._resolve_layerx_url(artifact)
        result["url"] = url
        try:
            resp = self.session.get(url, timeout=self.settings.request_timeout)
            if resp.status_code == 404:
                result["status"] = "not_found"
                return result
            resp.raise_for_status()
        except Exception as exc:
            result["status"] = "error"
            result["error"] = str(exc)
            return result

        soup = BeautifulSoup(resp.text, "html.parser")
        if not soup.find(id="risk-analysis"):
            result["status"] = "not_found"
            return result

        result["status"] = "ok"
        result["title"] = self._safe_text(soup.title)

        risk_section = soup.find("section", id="risk-analysis")
        cves_section = soup.find("section", id="cves")
        permissions_section = soup.find("section", id="permissions")
        host_permissions_section = soup.find("section", id="host-permissions")
        secrets_section = soup.find("section", id="secrets")
        extension_details_section = self._find_card_by_header(soup, "Extension Details")
        owner_details_section = self._find_card_by_header(soup, "Owner Details")

        result["risk_summary"] = self._parse_risk_summary(risk_section)
        result["sections"] = {
            "risk_analysis": self._pack_section(risk_section),
            "extension_details": self._pack_section(extension_details_section),
            "cves": self._pack_section(cves_section),
            "owner_details": self._pack_section(owner_details_section),
            "permissions": self._pack_section(permissions_section),
            "host_permissions": self._pack_section(host_permissions_section),
            "secrets": self._pack_section(secrets_section),
        }
        result["summary"] = self.summarize_layerx_result(result)
        return result

    def run_yara(self, artifact_bytes: bytes) -> Dict[str, Any]:
        result = {"enabled": self.compiled_yara is not None, "matches": []}
        if not self.compiled_yara:
            return result
        try:
            matches = self.compiled_yara.match(data=artifact_bytes)
            result["matches"] = [m.rule for m in matches]
        except Exception as exc:
            result["error"] = str(exc)
        return result

    def _resolve_layerx_url(self, artifact: ExtensionArtifact) -> str:
        extension_id = artifact.extension_id or ""
        candidates = [
            slugify(artifact.package_name or ""),
            slugify(artifact.name or ""),
            slugify(Path(artifact.file_name).stem),
            "extension",
        ]
        tried = set()
        for slug in candidates:
            if slug in tried:
                continue
            tried.add(slug)
            url = f"{self.settings.layerx_base_url}/extensions/chrome/{slug}/{extension_id}/"
            try:
                resp = self.session.get(url, timeout=self.settings.request_timeout)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                if self._looks_like_extension_page(soup, extension_id):
                    return url
            except Exception:
                pass
        return f"{self.settings.layerx_base_url}/extensions/chrome/extension/{extension_id}/"

    @staticmethod
    def _safe_text(node: Any) -> Optional[str]:
        if not node:
            return None
        text = node.get_text(" ", strip=True)
        return text or None

    def _pack_section(self, section: Any) -> Dict[str, Any]:
        if not section:
            return {"found": False, "text": None, "html": None}
        html = str(section) if self.settings.layerx_save_raw_html else None
        return {"found": True, "text": self._safe_text(section), "html": html}

    def _looks_like_extension_page(self, soup: BeautifulSoup, extension_id: str) -> bool:
        if not soup.find(id="risk-analysis"):
            return False
        canonical = soup.find("link", rel="canonical")
        canonical_href = (canonical.get("href") or "") if canonical else ""
        if extension_id and extension_id in canonical_href:
            return True
        for alt in soup.find_all("link", rel="alternate"):
            href = alt.get("href") or ""
            if extension_id and extension_id in href:
                return True
        return False

    def _find_card_by_header(self, soup: BeautifulSoup, header_text: str) -> Any:
        for header in soup.find_all("div", class_="ep-card__header"):
            if self._safe_text(header) == header_text:
                parent = header.find_parent("section")
                if parent:
                    return parent
        return None

    def _parse_risk_summary(self, section: Any) -> Dict[str, Any]:
        result = {
            "score_text": None,
            "risk_label": None,
            "status_badge": None,
            "version_text": None,
            "malicious_like": False,
            "severity_rank": 0,
        }
        if not section:
            return result

        section_text = self._safe_text(section) or ""
        value = section.select_one(".ep-score-ring__value")
        label = section.select_one(".ep-score-ring__label")
        badge = section.select_one(".ep-summary__status span:last-child")
        version_text = section.select_one(".ep-summary__version p")

        risk_label = self._safe_text(label)
        status_badge = self._safe_text(badge)
        version_value = self._safe_text(version_text)

        lower = section_text.lower()
        malicious_like = any(
            token in lower
            for token in [
                "malicious extension",
                "critical risk",
                "malware type",
                "attack vector",
                "affiliate hijacker",
                "browser traffic manipulation malware",
                "trojan",
                "stealer",
                "hijacker",
                "spyware",
            ]
        )

        severity_rank = 0
        joined = f"{risk_label or ''} {status_badge or ''} {section_text}".lower()
        if "critical risk" in joined or "malicious extension" in joined:
            severity_rank = 4
        elif "high risk" in joined:
            severity_rank = 3
        elif "medium risk" in joined or "moderate" in joined:
            severity_rank = 2
        elif "low risk" in joined:
            severity_rank = 1

        result.update(
            {
                "score_text": self._safe_text(value),
                "risk_label": risk_label,
                "status_badge": status_badge,
                "version_text": version_value,
                "malicious_like": malicious_like,
                "severity_rank": severity_rank,
            }
        )
        return result

    @staticmethod
    def _truncate_text(text: Optional[str], limit: int) -> Optional[str]:
        if text is None:
            return None
        value = text.strip()
        if len(value) <= limit:
            return value
        return f"{value[:limit].rstrip()}..."

    def summarize_layerx_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        sections = (result or {}).get("sections") or {}
        limit = max(self.settings.layerx_summary_char_limit, 120)
        section_order = [
            "risk_analysis",
            "permissions",
            "host_permissions",
            "secrets",
            "cves",
            "owner_details",
            "extension_details",
        ]
        summary_sections: Dict[str, Any] = {}
        for name in section_order:
            payload = sections.get(name) or {}
            summary_sections[name] = {
                "found": bool(payload.get("found")),
                "text": self._truncate_text(payload.get("text"), limit),
            }
        return {
            "provider": (result or {}).get("provider"),
            "status": (result or {}).get("status"),
            "url": (result or {}).get("url"),
            "title": (result or {}).get("title"),
            "risk_summary": (result or {}).get("risk_summary") or {},
            "sections": summary_sections,
        }


class RetroMonitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.nexus = NexusClient(settings)
        self.store = StoreVersionClient(timeout_seconds=settings.request_timeout)
        self.reputation = LayerXReputationChecker(settings)
        self.logger = logging.getLogger("retro_monitor")
        self.state = safe_json_load(settings.state_path, {"extensions": {}})
        self._migrate_legacy_state()

    def save_state(self) -> None:
        safe_json_dump(self.settings.state_path, self.state)

    def _migrate_legacy_state(self) -> None:
        """Drop legacy VirusTotal fields from persisted state."""
        extensions = self.state.get("extensions")
        if not isinstance(extensions, dict):
            return
        changed = False
        for baseline in extensions.values():
            if not isinstance(baseline, dict):
                continue
            if "vt_file" in baseline:
                baseline.pop("vt_file", None)
                changed = True
            if "vt_domains" in baseline:
                baseline.pop("vt_domains", None)
                changed = True
        if changed:
            self.logger.info("removed legacy virustotal state fields (vt_file/vt_domains)")

    def enqueue(self, event: Dict[str, Any]) -> None:
        self.settings.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings.queue_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def iter_extension_artifacts(self) -> Iterator[Tuple[ExtensionArtifact, bytes]]:
        for item in self.nexus.list_assets():
            path = item.get("path", "")
            download_url = item.get("downloadUrl")
            if not download_url:
                continue

            file_name = Path(path).name
            suffix = Path(file_name).suffix.lower()
            if suffix not in {".zip", ".crx"}:
                continue

            content = self.nexus.download_asset(download_url)
            checksum = (item.get("checksum") or {}).get("sha256") or sha256_bytes(content)

            artifact = ExtensionArtifact(
                asset_id=item.get("id"),
                name=Path(path).stem,
                path=path,
                download_url=download_url,
                file_name=file_name,
                file_ext=suffix,
                sha256=checksum,
            )
            self._hydrate_manifest_metadata(artifact, content)
            yield artifact, content

    def _hydrate_manifest_metadata(self, artifact: ExtensionArtifact, artifact_bytes: bytes) -> None:
        raw_zip = artifact_bytes
        if artifact.file_ext == ".crx":
            raw_zip = self._extract_zip_from_crx(artifact_bytes)

        try:
            with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
                manifest_name = self._find_manifest_name(zf)
                if not manifest_name:
                    return
                manifest = json.loads(zf.read(manifest_name).decode("utf-8", errors="replace"))

                artifact.manifest_version = str(manifest.get("version") or "")
                artifact.package_name = str(manifest.get("name") or "")
                artifact.homepage_url = manifest.get("homepage_url")
                artifact.update_url = manifest.get("update_url")

                key_value = manifest.get("key")
                if key_value:
                    artifact.manifest_key_present = True
                    artifact.extension_id = chrome_id_from_public_key_b64(key_value)

                if not artifact.extension_id:
                    maybe_id = self._extract_extension_id_from_text(f"{artifact.path} {artifact.file_name}")
                    if maybe_id:
                        artifact.extension_id = maybe_id

                if artifact.extension_id:
                    artifact.store_url = f"https://chromewebstore.google.com/detail/x/{artifact.extension_id}"
        except Exception as exc:
            self.logger.warning("manifest parse failed for %s: %s", artifact.path, exc)

    @staticmethod
    def _extract_zip_from_crx(crx_bytes: bytes) -> bytes:
        if crx_bytes[:4] != b"Cr24":
            return crx_bytes
        version = int.from_bytes(crx_bytes[4:8], "little")
        if version == 2:
            pub_len = int.from_bytes(crx_bytes[8:12], "little")
            sig_len = int.from_bytes(crx_bytes[12:16], "little")
            header_len = 16 + pub_len + sig_len
            return crx_bytes[header_len:]
        if version == 3:
            header_len = int.from_bytes(crx_bytes[8:12], "little")
            return crx_bytes[12 + header_len:]
        return crx_bytes

    @staticmethod
    def _find_manifest_name(zf: zipfile.ZipFile) -> Optional[str]:
        lower_map = {name.lower(): name for name in zf.namelist()}
        if "manifest.json" in lower_map:
            return lower_map["manifest.json"]
        for name in zf.namelist():
            if name.lower().endswith("/manifest.json"):
                return name
        return None

    @staticmethod
    def _extract_extension_id_from_text(text: str) -> Optional[str]:
        for token in re.findall(r"[a-p]{32}", text):
            if ID_REGEX.match(token):
                return token
        return None

    def evaluate_one(self, artifact: ExtensionArtifact, artifact_bytes: bytes) -> list[Dict[str, Any]]:
        events: list[Dict[str, Any]] = []
        key = artifact.extension_id or artifact.path
        baseline = self.state["extensions"].get(key, {})

        if artifact.extension_id:
            try:
                latest_store_version = self.store.get_latest_version(artifact.extension_id)
            except Exception as exc:
                latest_store_version = None
                self.logger.warning("store version lookup failed for %s: %s", artifact.extension_id, exc)

            if latest_store_version and artifact.manifest_version and compare_versions(latest_store_version, artifact.manifest_version) > 0:
                events.append({
                    "event_type": "HOLD_FOR_NEW_VERSION",
                    "reason": "store_version_newer_than_nexus",
                    "detected_at": utc_now(),
                    "extension_id": artifact.extension_id,
                    "nexus_version": artifact.manifest_version,
                    "store_version": latest_store_version,
                    "asset_path": artifact.path,
                    "download_url": artifact.download_url,
                    "recommended_action": "enqueue_holding_or_reanalysis",
                })
            baseline["last_store_version"] = latest_store_version

        layerx_result = self.reputation.check_extension(artifact)
        old_layerx = baseline.get("layerx", {})
        layerx_reason = self.determine_layerx_review_reason(old_layerx, layerx_result)
        if layerx_reason:
            events.append({
                "event_type": "HOLD_FOR_REPUTATION_REVIEW",
                "reason": layerx_reason,
                "detected_at": utc_now(),
                "extension_id": artifact.extension_id,
                "asset_path": artifact.path,
                "layerx": {
                    "status": layerx_result.get("status"),
                    "url": layerx_result.get("url"),
                    "risk_summary": layerx_result.get("risk_summary") or {},
                    "summary": layerx_result.get("summary") or {},
                },
                "recommended_action": "enqueue_holding_or_reanalysis",
            })
        baseline["layerx"] = layerx_result

        if self.reputation.compiled_yara:
            yara_result = self.reputation.run_yara(artifact_bytes)
            old_matches = set((baseline.get("yara") or {}).get("matches", []))
            new_matches = set(yara_result.get("matches", []))
            if new_matches - old_matches:
                events.append({
                    "event_type": "HOLD_FOR_REPUTATION_REVIEW",
                    "reason": "new_yara_match",
                    "detected_at": utc_now(),
                    "extension_id": artifact.extension_id,
                    "asset_path": artifact.path,
                    "yara": yara_result,
                    "recommended_action": "enqueue_reanalysis",
                })
            baseline["yara"] = yara_result

        baseline.update({
            "extension_id": artifact.extension_id,
            "asset_path": artifact.path,
            "sha256": artifact.sha256,
            "manifest_version": artifact.manifest_version,
            "last_checked_at": utc_now(),
            "store_url": artifact.store_url,
        })
        self.state["extensions"][key] = baseline
        return events

    @staticmethod
    def _is_layerx_malicious_like(result: Dict[str, Any]) -> bool:
        risk = (result or {}).get("risk_summary") or {}
        return bool(risk.get("malicious_like"))

    @staticmethod
    def _is_layerx_worse(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
        if not old or old.get("status") != "ok":
            return False
        if not new or new.get("status") != "ok":
            return False
        old_rank = int(((old or {}).get("risk_summary") or {}).get("severity_rank") or 0)
        new_rank = int(((new or {}).get("risk_summary") or {}).get("severity_rank") or 0)
        return new_rank > old_rank and new_rank >= 3

    @classmethod
    def determine_layerx_review_reason(cls, old: Dict[str, Any], new: Dict[str, Any]) -> Optional[str]:
        if not new or new.get("status") != "ok":
            return None
        if not old or old.get("status") != "ok":
            return None
        if cls._is_layerx_malicious_like(new) and not cls._is_layerx_malicious_like(old):
            return "layerx_malicious_like_detected"
        if cls._is_layerx_worse(old, new):
            return "layerx_risk_worsened_to_high_or_critical"
        return None

    def run_once(self) -> int:
        event_count = 0
        for artifact, artifact_bytes in self.iter_extension_artifacts():
            self.logger.info("checking %s | version=%s | id=%s", artifact.path, artifact.manifest_version, artifact.extension_id)
            events = self.evaluate_one(artifact, artifact_bytes)
            for event in events:
                self.enqueue(event)
                event_count += 1
                self.logger.warning("enqueued %s for %s", event["event_type"], artifact.path)
        self.save_state()
        return event_count

    def run_forever(self) -> None:
        # 시간 단위
        # interval_seconds = max(self.settings.interval_hours, 1) * 3600
        # 초 단위
        interval_seconds = self.settings.interval_hours
        while True:
            try:
                count = self.run_once()
                self.logger.info("cycle complete; events=%s", count)
            except Exception:
                self.logger.exception("retro cycle failed")
            time.sleep(interval_seconds)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Nexus Chrome extension retro monitor (LayerX reputation version)")
    parser.add_argument("--once", action="store_true", help="run one retro cycle and exit")
    parser.add_argument("--loop", action="store_true", help="run forever on the configured interval")
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main() -> int:
    args = build_arg_parser().parse_args()
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    monitor = RetroMonitor(settings)
    if args.loop:
        monitor.run_forever()
        return 0
    monitor.run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
