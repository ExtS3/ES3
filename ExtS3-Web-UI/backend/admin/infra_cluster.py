"""확장 인프라 클러스터 오염 판정.

BadBlocker(island.io, 2026-06) 사례 대응: 같은 백엔드 인프라(코드 내 외부 도메인)를
공유하는 자매 확장 중 하나가 거부되면, 나머지는 risk_score와 무관하게 자동 승인을
차단하고 수동 review로 보낸다. BadBlocker의 자매 확장들(Adblock for Chrome 등)이
동일 인프라(adblock-for-youtube.com)를 쓰다 malware로 제거된 패턴이 근거.

저장은 레포 관례(policy_settings.json, reject 기록)를 따라 JSON 파일 하나.
오염 여부는 저장하지 않고 판정 시점에 reject 기록과 조인해 도출한다 —
전파용 상태 기계가 없으므로 reject 취소·기록 변경에도 자동으로 일관된다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

INFRA_PATH = Path(__file__).resolve().parent / "extension_infra.json"

# 공용 CDN·플랫폼 도메인 — 공유해도 "같은 운영 주체" 근거가 되지 않음.
# ponytail: 수동 allowlist. 오탐 도메인이 발견되면 여기 추가.
BENIGN_DOMAINS = frozenset({
    "google.com", "www.google.com", "googleapis.com", "www.googleapis.com",
    "fonts.googleapis.com", "gstatic.com", "fonts.gstatic.com",
    "chrome.google.com", "chromewebstore.google.com",
    "github.com", "raw.githubusercontent.com", "api.github.com",
    "cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com",
    "youtube.com", "www.youtube.com",
    "mozilla.org", "addons.mozilla.org",
    "sentry.io", "www.w3.org", "example.com",
    "localhost", "127.0.0.1",
})


def normalize_domain(value: Any) -> Optional[str]:
    """URL 또는 도메인 문자열 → 소문자 netloc. 판정 가치가 없으면 None."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    if "://" in text:
        text = urlparse(text).netloc
    text = text.split("/")[0].split(":")[0].strip()
    if "." not in text or text in BENIGN_DOMAINS:
        return None
    return text


def _read_infra(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def record_signals(
    ext_id: str,
    browser: str,
    ext_name: str,
    domains: List[Any],
    *,
    infra_path: Path = INFRA_PATH,
) -> List[str]:
    """분석 결과 수신 시 확장의 인프라 신호(외부 도메인)를 적재한다.

    같은 확장이 다시 분석되면 도메인 집합을 합집합으로 누적한다
    (버전이 바뀌며 도메인이 사라져도 과거 연관은 유지).
    """
    normalized = sorted({d for d in (normalize_domain(v) for v in domains or []) if d})
    ext_key = str(ext_id or "").strip()
    if not ext_key or ext_key == "unknown_id":
        return normalized

    infra = _read_infra(infra_path)
    entry = infra.get(ext_key) or {}
    merged = sorted(set(entry.get("domains") or []) | set(normalized))
    infra[ext_key] = {
        "browser": str(browser or ""),
        "ext_name": str(ext_name or ""),
        "domains": merged,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    infra_path.parent.mkdir(parents=True, exist_ok=True)
    infra_path.write_text(json.dumps(infra, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def find_cluster_taint(
    ext_id: str,
    domains: List[Any],
    reject_records: List[Dict[str, Any]],
    *,
    infra_path: Path = INFRA_PATH,
) -> Optional[Dict[str, Any]]:
    """현재 확장이 거부 이력 확장과 도메인을 공유하면 근거를 반환, 아니면 None."""
    my_domains = {d for d in (normalize_domain(v) for v in domains or []) if d}
    if not my_domains:
        return None

    ext_key = str(ext_id or "").strip()
    rejected_ids = {
        str(r.get("id") or "").strip()
        for r in reject_records or []
        if isinstance(r, dict)
    } - {ext_key, ""}
    if not rejected_ids:
        return None

    infra = _read_infra(infra_path)
    matches = []
    for other_id in sorted(rejected_ids):
        other = infra.get(other_id) or {}
        shared = my_domains & set(other.get("domains") or [])
        if shared:
            matches.append({
                "ext_id": other_id,
                "ext_name": other.get("ext_name") or "",
                "shared_domains": sorted(shared),
            })

    if not matches:
        return None
    return {"tainted": True, "matches": matches}
