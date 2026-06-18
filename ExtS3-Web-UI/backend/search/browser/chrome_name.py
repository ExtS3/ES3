import asyncio
import re
import os
import time
from urllib.parse import quote

import requests
import httpx
from bs4 import BeautifulSoup


DETAIL_ID_RE = re.compile(r"/detail/(?:[^/?#]+/)?([a-p]{32})(?:[/?#]|$)")


def _append_unique(ext_ids, ext_id, limit):
    if ext_id and ext_id not in ext_ids:
        ext_ids.append(ext_id)
    return len(ext_ids) >= limit


def _extract_ids_from_html(html, limit):
    ext_ids = []

    soup = BeautifulSoup(html, "html.parser")
    for item in soup.select('a[href*="/detail/"]'):
        href = item.get("href", "")
        match = DETAIL_ID_RE.search(href)
        if match and _append_unique(ext_ids, match.group(1), limit):
            return ext_ids

    for match in DETAIL_ID_RE.finditer(html):
        if _append_unique(ext_ids, match.group(1), limit):
            break

    return ext_ids


def _search_by_name_with_requests(extension_name, limit):
    search_url = f"https://chromewebstore.google.com/search/{quote(extension_name)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(search_url, headers=headers, timeout=10)
    if response.status_code != 200:
        return []

    return _extract_ids_from_html(response.text, limit)


async def _search_by_name_with_httpx(client, extension_name, limit):
    search_url = f"https://chromewebstore.google.com/search/{quote(extension_name)}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
    }

    response = await client.get(search_url, headers=headers)
    if response.status_code != 200:
        return []

    return _extract_ids_from_html(response.text, limit)


def _search_by_name_with_selenium(extension_name, limit):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    search_url = f"https://chromewebstore.google.com/search/{quote(extension_name)}"
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,2200")
    options.add_argument("--lang=ko-KR")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(search_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/detail/"]'))
        )

        ext_ids = []
        stable_rounds = 0
        last_count = 0

        for _ in range(12):
            page_ids = _extract_ids_from_html(driver.page_source, limit)
            for ext_id in page_ids:
                if _append_unique(ext_ids, ext_id, limit):
                    return ext_ids

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.0)

            if len(ext_ids) == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
                last_count = len(ext_ids)

            if stable_rounds >= 3:
                break

        return ext_ids
    finally:
        driver.quit()


def _query_variants(extension_name):
    base = " ".join(str(extension_name or "").split())
    if not base:
        return []

    variants = [
        base,
        f"{base} extension",
        f"{base} chrome",
        f"{base} for chrome",
        f"free {base}",
        f"{base} tool",
    ]

    seen = []
    for variant in variants:
        normalized = variant.lower()
        if normalized not in seen:
            seen.append(normalized)
            yield variant


def _expand_ids_with_related_queries(extension_name, ext_ids, limit):
    for variant in _query_variants(extension_name):
        if len(ext_ids) >= limit:
            break
        try:
            for ext_id in _search_by_name_with_requests(variant, 10):
                if _append_unique(ext_ids, ext_id, limit):
                    return ext_ids
        except Exception as e:
            print(f"Related search skipped ({variant}): {e}")
    return ext_ids


async def _expand_ids_with_related_queries_async(extension_name, ext_ids, limit):
    variants = list(_query_variants(extension_name))
    if not variants or len(ext_ids) >= limit:
        return ext_ids

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        tasks = [
            _search_by_name_with_httpx(client, variant, 10)
            for variant in variants
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for variant, result in zip(variants, results):
        if len(ext_ids) >= limit:
            break
        if isinstance(result, Exception):
            print(f"Related search skipped ({variant}): {result}")
            continue
        for ext_id in result:
            if _append_unique(ext_ids, ext_id, limit):
                return ext_ids

    return ext_ids


def search_by_name(extension_name, limit=40):
    if not extension_name:
        return []

    limit = max(1, min(int(limit or 40), 80))

    try:
        ids = _search_by_name_with_requests(extension_name, limit)
        if ids:
            return _expand_ids_with_related_queries(extension_name, ids, limit)
    except Exception as e:
        print(f"Search error: {e}")

    if os.getenv("CHROME_SEARCH_USE_SELENIUM", "false").lower() == "true":
        try:
            ids = _search_by_name_with_selenium(extension_name, limit)
            if ids:
                return _expand_ids_with_related_queries(extension_name, ids, limit)
        except Exception as e:
            print(f"Selenium search fallback: {e}")

    return []


async def search_by_name_async(extension_name, limit=40):
    if not extension_name:
        return []

    limit = max(1, min(int(limit or 40), 80))

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            ids = await _search_by_name_with_httpx(client, extension_name, limit)
        if ids:
            return await _expand_ids_with_related_queries_async(extension_name, ids, limit)
    except Exception as e:
        print(f"Search error: {e}")

    if os.getenv("CHROME_SEARCH_USE_SELENIUM", "false").lower() == "true":
        try:
            ids = _search_by_name_with_selenium(extension_name, limit)
            if ids:
                return await _expand_ids_with_related_queries_async(extension_name, ids, limit)
        except Exception as e:
            print(f"Selenium search fallback: {e}")

    return []
