import requests
import httpx


API_BASE_URL = "https://open-vsx.org/api"
MARKET_BASE_URL = "https://open-vsx.org/extension"


def _normalize_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return ""
    # Open VSX timestamp 예: "2026-03-05T03:59:45.436054Z"
    # search.py 의 _parse_date 가 읽는 "%Y-%m-%d" 형식으로 정규화
    return text[:10]


def vscode_search_by_id(ext_id):
    try:
        publisher, name = str(ext_id).split(".", 1)

        url = f"{API_BASE_URL}/{publisher}/{name}/latest"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        payload = res.json()

        files = payload.get("files") or {}
        download_count = int(payload.get("downloadCount") or 0)
        rating_value = float(payload.get("averageRating") or 0.0)
        updated = _normalize_timestamp(payload.get("timestamp"))
        description = payload.get("description") or "N/A"

        return {
            "success": True,
            "data": {
                "id": ext_id,
                "name": payload.get("displayName") or payload.get("name") or "N/A",
                "logo_url": files.get("icon") or "N/A",
                "version": payload.get("version") or "N/A",
                "users": str(download_count),
                "users_count": download_count,
                "rating": f"{rating_value:.1f}" if rating_value else "0.0",
                "rating_value": rating_value,
                "updated": updated,
                "last_updated": updated,
                "summary": description,
                "description": description,
                "url": f"{MARKET_BASE_URL}/{publisher}/{name}",
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def vscode_search_by_id_async(client, ext_id):
    try:
        publisher, name = str(ext_id).split(".", 1)

        url = f"{API_BASE_URL}/{publisher}/{name}/latest"
        res = await client.get(url)
        res.raise_for_status()
        payload = res.json()

        files = payload.get("files") or {}
        download_count = int(payload.get("downloadCount") or 0)
        rating_value = float(payload.get("averageRating") or 0.0)
        updated = _normalize_timestamp(payload.get("timestamp"))
        description = payload.get("description") or "N/A"

        return {
            "success": True,
            "data": {
                "id": ext_id,
                "name": payload.get("displayName") or payload.get("name") or "N/A",
                "logo_url": files.get("icon") or "N/A",
                "version": payload.get("version") or "N/A",
                "users": str(download_count),
                "users_count": download_count,
                "rating": f"{rating_value:.1f}" if rating_value else "0.0",
                "rating_value": rating_value,
                "updated": updated,
                "last_updated": updated,
                "summary": description,
                "description": description,
                "url": f"{MARKET_BASE_URL}/{publisher}/{name}",
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
