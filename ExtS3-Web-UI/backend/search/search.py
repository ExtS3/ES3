import asyncio
import copy
import math
import os
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.search.browser.chrome_id import get_extension_info_async
from backend.search.browser.chrome_name import search_by_name_async
from backend.search.browser.vscode_id import vscode_search_by_id_async
from backend.search.browser.vscode_name import vscode_search_by_name_async

router = APIRouter()
SEARCH_CACHE_TTL_SECONDS = int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "300"))
SEARCH_DEFAULT_LIMIT = int(os.getenv("SEARCH_DEFAULT_LIMIT", "20"))
SEARCH_DETAIL_CONCURRENCY = int(os.getenv("SEARCH_DETAIL_CONCURRENCY", "12"))
_search_cache = {}


def _cache_get(key):
    cached = _search_cache.get(key)
    if not cached:
        return None
    expires_at, value = cached
    if expires_at < time.time():
        _search_cache.pop(key, None)
        return None
    return copy.deepcopy(value)


def _cache_set(key, value):
    _search_cache[key] = (time.time() + SEARCH_CACHE_TTL_SECONDS, copy.deepcopy(value))
    return value


def _parse_date(value):
    text = str(value or "").strip()
    if not text or text == "N/A":
        return None

    candidates = [
        "%Y. %m. %d.",
        "%Y.%m.%d.",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _days_since_update(updated):
    parsed = _parse_date(updated)
    if not parsed:
        return None
    return max(0, (datetime.utcnow() - parsed).days)


def _recommendation_score(item):
    rating = float(item.get("rating_value") or item.get("rating") or 0)
    users_count = int(item.get("users_count") or 0)
    updated_days = _days_since_update(item.get("updated"))

    rating_score = min(max(rating, 0), 5) * 20
    popularity_score = min(math.log10(users_count + 1) * 12, 72)

    if updated_days is None:
        recency_score = 0
    elif updated_days <= 180:
        recency_score = 18
    elif updated_days <= 365:
        recency_score = 12
    elif updated_days <= 730:
        recency_score = 6
    else:
        recency_score = 0

    info_penalty = 0
    for key in ("name", "description", "version", "logo_url"):
        if not item.get(key) or item.get(key) == "N/A":
            info_penalty += 5

    query_match_score = float(item.get("query_match_score") or 0)

    return round(rating_score + popularity_score + recency_score + query_match_score - info_penalty, 2)


def _query_match_score(item, search_query):
    query = str(search_query or "").strip().lower()
    if not query:
        return 0

    name = str(item.get("name") or "").lower()
    description = str(item.get("description") or item.get("summary") or "").lower()
    tokens = [token for token in query.split() if token]

    score = 0
    if query and query in name:
        score += 28
    if query and query in description:
        score += 10

    if tokens:
        name_hits = sum(1 for token in tokens if token in name)
        description_hits = sum(1 for token in tokens if token in description)
        score += (name_hits / len(tokens)) * 18
        score += (description_hits / len(tokens)) * 6

    return round(min(score, 45), 2)


def _enrich_result(item, search_rank=None, search_query=None):
    item["search_rank"] = search_rank
    item["updated_days"] = _days_since_update(item.get("updated"))
    item["query_match_score"] = _query_match_score(item, search_query)
    item["recommendation_score"] = _recommendation_score(item)
    return item


def _valid_result(info):
    return (
        info.get("success")
        and info.get("data")
        and info["data"].get("name")
        and info["data"]["name"] != "Chrome 웹스토어에 오신 것을 환영합니다"
    )


async def _gather_extension_info(ids, get_info):
    semaphore = asyncio.Semaphore(max(1, SEARCH_DETAIL_CONCURRENCY))
    limits = httpx.Limits(
        max_connections=max(1, SEARCH_DETAIL_CONCURRENCY),
        max_keepalive_connections=max(1, SEARCH_DETAIL_CONCURRENCY),
    )

    async with httpx.AsyncClient(timeout=10, follow_redirects=True, limits=limits) as client:
        async def fetch(ext_id):
            async with semaphore:
                return await get_info(client, ext_id)

        return await asyncio.gather(*(fetch(ext_id) for ext_id in ids))


@router.post("/api/search_name")
async def search_name_api(request: Request):
    data = await request.json()
    extension_name = data.get("extension_name")
    browser = data.get("browser")
    limit = max(1, min(int(data.get("limit") or SEARCH_DEFAULT_LIMIT), 80))
    cache_key = ("name", browser, str(extension_name or "").strip().lower(), limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    if browser == "Chrome" or browser == "VSCode":
        if browser == "Chrome":
            ids = await search_by_name_async(extension_name, limit=limit)
            get_info = get_extension_info_async
        else:
            ids = await vscode_search_by_name_async(extension_name, size=limit)
            get_info = vscode_search_by_id_async

        if not ids:
            return JSONResponse(content={"success": False, "error": "검색 결과가 없습니다."})

        responses = await _gather_extension_info(ids, get_info)

        all_results = []
        for index, info in enumerate(responses):
            if _valid_result(info):
                all_results.append(_enrich_result(info["data"], search_rank=index + 1, search_query=extension_name))

        all_results.sort(key=lambda item: item.get("recommendation_score", 0), reverse=True)

        payload = {
                "success": True,
                "data": all_results,
                "meta": {
                    "candidate_count": len(ids),
                    "result_count": len(all_results),
                    "default_sort": "recommended",
                    "cached": False,
                },
            }
        return JSONResponse(content=_cache_set(cache_key, payload))

    return JSONResponse(content={"success": False, "error": "지원하지 않는 브라우저입니다."})


@router.post("/api/search_id")
async def search_id_api(request: Request):
    data = await request.json()
    extension_id = data.get("extension_id")
    browser = data.get("browser")
    cache_key = ("id", browser, str(extension_id or "").strip().lower())
    cached = _cache_get(cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    if browser == "Chrome":
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            result = await get_extension_info_async(client, extension_id)
        if _valid_result(result):
            result["data"] = _enrich_result(result["data"], search_rank=1)
            return JSONResponse(content=_cache_set(cache_key, result))

    elif browser == "VSCode":
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            result = await vscode_search_by_id_async(client, extension_id)
        if _valid_result(result):
            result["data"] = _enrich_result(result["data"], search_rank=1)
            return JSONResponse(content=_cache_set(cache_key, result))

    return JSONResponse(content={"success": False, "error": "확장 프로그램을 찾을 수 없습니다."})
