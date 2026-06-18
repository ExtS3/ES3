import asyncio
import os
import time
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from requests.auth import HTTPBasicAuth

from backend.auth.security import require_permission

router = APIRouter()

NEXUS_BASE_URL = os.getenv("NEXUS_BASE_URL")
NEXUS_REPOSITORY = os.getenv("NEXUS_REPOSITORY")
NEXUS_USERNAME = os.getenv("NEXUS_USERNAME")
NEXUS_PASSWORD = os.getenv("NEXUS_PASSWORD")
NEXUS_STORAGE_LIMIT_BYTES = os.getenv("NEXUS_STORAGE_LIMIT_BYTES")
NEXUS_DASHBOARD_CACHE_TTL_SECONDS = int(os.getenv("NEXUS_DASHBOARD_CACHE_TTL_SECONDS", "30"))

nexus_auth = HTTPBasicAuth(NEXUS_USERNAME, NEXUS_PASSWORD)
httpx_nexus_auth = httpx.BasicAuth(NEXUS_USERNAME or "", NEXUS_PASSWORD or "")
_dashboard_cache = {"expires_at": 0.0, "payload": None}


def get_storage_limit_bytes():
    try:
        return int(NEXUS_STORAGE_LIMIT_BYTES) if NEXUS_STORAGE_LIMIT_BYTES else None
    except ValueError:
        return None


def fetch_nexus_assets():
    nexus_url = f"{NEXUS_BASE_URL}/service/rest/v1/assets"
    all_assets = []
    continuation_token = None

    while True:
        params = {"repository": NEXUS_REPOSITORY}
        if continuation_token:
            params["continuationToken"] = continuation_token

        response = requests.get(
            nexus_url,
            auth=nexus_auth,
            params=params,
            timeout=10,
        )

        if response.status_code != 200:
            print(f"Nexus API Error: {response.status_code} - {response.text}")
            break

        data = response.json()
        for item in data.get("items", []):
            if item.get("path"):
                item["path"] = item["path"].lstrip("/")
            all_assets.append(item)
        continuation_token = data.get("continuationToken")

        if not continuation_token:
            break

    return all_assets


async def fetch_nexus_assets_async(client):
    nexus_url = f"{NEXUS_BASE_URL}/service/rest/v1/assets"
    all_assets = []
    continuation_token = None

    while True:
        params = {"repository": NEXUS_REPOSITORY}
        if continuation_token:
            params["continuationToken"] = continuation_token

        response = await client.get(nexus_url, params=params)

        if response.status_code != 200:
            print(f"Nexus API Error: {response.status_code} - {response.text}")
            break

        data = response.json()
        for item in data.get("items", []):
            if item.get("path"):
                item["path"] = item["path"].lstrip("/")
            all_assets.append(item)
        continuation_token = data.get("continuationToken")

        if not continuation_token:
            break

    return all_assets


def fetch_nexus_assets_by_name(names):
    nexus_url = f"{NEXUS_BASE_URL}/service/rest/v1/search/assets"
    matches = []
    for name in names:
        if not name:
            continue
        continuation_token = None
        while True:
            params = {"repository": NEXUS_REPOSITORY, "name": name}
            if continuation_token:
                params["continuationToken"] = continuation_token

            response = requests.get(
                nexus_url,
                auth=nexus_auth,
                params=params,
                timeout=10,
            )
            if response.status_code != 200:
                print(f"Nexus Search API Error: {response.status_code} - {response.text}")
                break

            data = response.json()
            for item in data.get("items", []):
                if item.get("path"):
                    item["path"] = item["path"].lstrip("/")
                matches.append(item)
            continuation_token = data.get("continuationToken")
            if not continuation_token:
                break
    return matches


async def fetch_nexus_assets_by_name_async(client, names):
    nexus_url = f"{NEXUS_BASE_URL}/service/rest/v1/search/assets"

    async def fetch_one(name):
        if not name:
            return []

        matches = []
        continuation_token = None
        while True:
            params = {"repository": NEXUS_REPOSITORY, "name": name}
            if continuation_token:
                params["continuationToken"] = continuation_token

            response = await client.get(nexus_url, params=params)
            if response.status_code != 200:
                print(f"Nexus Search API Error: {response.status_code} - {response.text}")
                break

            data = response.json()
            for item in data.get("items", []):
                if item.get("path"):
                    item["path"] = item["path"].lstrip("/")
                matches.append(item)
            continuation_token = data.get("continuationToken")
            if not continuation_token:
                break
        return matches

    results = await asyncio.gather(*(fetch_one(name) for name in names))
    return [item for group in results for item in group]


def fetch_nexus_blobstores():
    nexus_url = f"{NEXUS_BASE_URL}/service/rest/v1/blobstores"
    response = requests.get(
        nexus_url,
        auth=nexus_auth,
        timeout=10,
    )

    if response.status_code != 200:
        print(f"Nexus Blob Store API Error: {response.status_code} - {response.text}")
        return []

    return response.json()


async def fetch_nexus_blobstores_async(client):
    nexus_url = f"{NEXUS_BASE_URL}/service/rest/v1/blobstores"
    response = await client.get(nexus_url)

    if response.status_code != 200:
        print(f"Nexus Blob Store API Error: {response.status_code} - {response.text}")
        return []

    return response.json()


def get_safe_item_name(item):
    path = item.get("path") or ""
    parts = path.split("/")
    return parts[1] if len(parts) > 1 and parts[0] == "safe" else None


def build_dashboard_summary(assets, blobstores=None):
    blobstores = blobstores or []
    safe_assets = [
        item for item in assets
        if (item.get("path") or "").startswith("safe/")
    ]
    active_repo_names = {
        name for name in (get_safe_item_name(item) for item in safe_assets)
        if name
    }
    asset_total_storage_bytes = sum(
        item.get("fileSize") or 0
        for item in assets
        if isinstance(item.get("fileSize") or 0, (int, float))
    )
    blobstore_total_storage_bytes = sum(
        item.get("totalSizeInBytes") or 0
        for item in blobstores
        if isinstance(item.get("totalSizeInBytes") or 0, (int, float))
    )
    available_storage_bytes = sum(
        item.get("availableSpaceInBytes") or 0
        for item in blobstores
        if isinstance(item.get("availableSpaceInBytes") or 0, (int, float))
    )
    has_blobstore_metrics = any(
        "totalSizeInBytes" in item or "availableSpaceInBytes" in item
        for item in blobstores
    )
    total_storage_bytes = blobstore_total_storage_bytes or asset_total_storage_bytes
    storage_limit_bytes = (
        total_storage_bytes + available_storage_bytes
        if has_blobstore_metrics
        else get_storage_limit_bytes()
    )

    return {
        "totalStorageBytes": total_storage_bytes,
        "availableStorageBytes": available_storage_bytes if has_blobstore_metrics else None,
        "storageLimitBytes": storage_limit_bytes,
        "blobstores": blobstores,
        "activeRepositoryCount": len(active_repo_names),
        "totalAssetCount": len(assets),
        "safeAssetCount": len(safe_assets),
        "extensionActivityPercent": round((len(safe_assets) / len(assets)) * 100) if assets else 0,
    }


def fetch_dashboard_payload():
    now = time.monotonic()
    cached_payload = _dashboard_cache["payload"]
    if cached_payload is not None and _dashboard_cache["expires_at"] > now:
        return cached_payload

    assets = fetch_nexus_assets()
    blobstores = fetch_nexus_blobstores()
    payload = {
        "items": assets,
        "summary": build_dashboard_summary(assets, blobstores),
    }
    _dashboard_cache["payload"] = payload
    _dashboard_cache["expires_at"] = now + NEXUS_DASHBOARD_CACHE_TTL_SECONDS
    return payload


async def fetch_dashboard_payload_async(client):
    now = time.monotonic()
    cached_payload = _dashboard_cache["payload"]
    if cached_payload is not None and _dashboard_cache["expires_at"] > now:
        return cached_payload

    assets, blobstores = await asyncio.gather(
        fetch_nexus_assets_async(client),
        fetch_nexus_blobstores_async(client),
    )
    payload = {
        "items": assets,
        "summary": build_dashboard_summary(assets, blobstores),
    }
    _dashboard_cache["payload"] = payload
    _dashboard_cache["expires_at"] = now + NEXUS_DASHBOARD_CACHE_TTL_SECONDS
    return payload


@router.post("/api/nexus/list")
async def nexus_list(_user: dict = Depends(require_permission("install_extension"))):
    try:
        async with httpx.AsyncClient(auth=httpx_nexus_auth, timeout=10) as client:
            all_assets = await fetch_nexus_assets_async(client)
        print(f"총 {len(all_assets)}개의 자산을 Nexus에서 성공적으로 불러왔습니다.")
        return all_assets
    except Exception as e:
        print(f"Nexus 리스트 취득 중 오류: {e}")
        return []


@router.post("/api/nexus/exists")
async def nexus_exists(
    request: Request,
    _user: dict = Depends(require_permission("install_extension")),
):
    data = await request.json()
    ext_id = data.get("extID") or data.get("extension_id")
    version = data.get("extVersion") or data.get("version")

    if not ext_id:
        raise HTTPException(status_code=400, detail="extension id is required")

    candidate_names = [f"{ext_id}.zip", f"{ext_id}.vsix"]
    if version:
        candidate_names.append(f"{ext_id}-{version}.vsix")

    try:
        async with httpx.AsyncClient(auth=httpx_nexus_auth, timeout=10) as client:
            matches = await fetch_nexus_assets_by_name_async(client, candidate_names)
    except Exception as e:
        print(f"Nexus exists lookup error: {e}")
        matches = []

    target = None
    for item in matches:
        path = item.get("path") or ""
        filename = PurePosixPath(path).name
        stem = filename.rsplit(".", 1)[0]
        if stem == ext_id or (version and stem == f"{ext_id}-{version}"):
            target = item
            break

    if not target:
        return {"exists": False, "item": None, "status": None}

    path = target.get("path") or ""
    top_level = path.split("/")[0] if path else None
    return {
        "exists": True,
        "item": target,
        "status": target.get("status") or top_level,
        "top_level": top_level,
    }


@router.get("/api/nexus/download")
async def nexus_download(path: str, _user: dict = Depends(require_permission("install_extension"))):
    normalized_path = path.lstrip("/")
    if not normalized_path.startswith("safe/") or not normalized_path.endswith(".zip"):
        raise HTTPException(status_code=400, detail="safe zip path is required")

    encoded_path = quote(normalized_path, safe="/")
    download_url = f"{NEXUS_BASE_URL}/repository/{NEXUS_REPOSITORY}/{encoded_path}"
    response = requests.get(
        download_url,
        auth=nexus_auth,
        stream=True,
        timeout=30,
    )

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Nexus file was not found")

    filename = PurePosixPath(normalized_path).name
    encoded_filename = quote(filename)

    def iterfile():
        for chunk in response.iter_content(chunk_size=8192):
            yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/nexus/dashboard")
async def nexus_dashboard():
    try:
        async with httpx.AsyncClient(auth=httpx_nexus_auth, timeout=10) as client:
            return await fetch_dashboard_payload_async(client)
    except Exception as e:
        print(f"Nexus dashboard summary error: {e}")
        return {
            "items": [],
            "summary": build_dashboard_summary([]),
        }
