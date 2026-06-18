import json
import re

import requests
import httpx
from bs4 import BeautifulSoup


DETAIL_BASE_URL = "https://chromewebstore.google.com/detail"


def _first_meta(soup, *names):
    for key, value in names:
        tag = soup.find("meta", attrs={key: value})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _parse_number(value):
    text = str(value or "").strip().lower().replace(",", "")
    if not text:
        return 0

    multiplier = 1
    if text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]

    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def _extract_json_ld(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    return item
    return {}


def _extract_text_value(patterns, text, default="N/A"):
    for pattern in patterns:
        try:
            match = re.search(pattern, text, re.IGNORECASE)
        except re.error:
            continue
        if match:
            return match.group(1).strip()
    return default


def _clean_text(value):
    return " ".join(str(value or "").split())


def _extract_overview_description(soup):
    selectors = [
        ".mN52G.oB8Rd",
        ".mN52G",
        ".oB8Rd",
        '[jsname="bN97Pc"]',
        '[jsname="C4s9Ed"]',
    ]

    for selector in selectors:
        element = soup.select_one(selector)
        if not element:
            continue

        text = _clean_text(element.get_text(" "))
        if len(text) >= 30:
            return text

    return ""


def _extract_detail_field(soup, labels):
    normalized_labels = {label.lower() for label in labels}

    for label_element in soup.select(".QDHp8e"):
        label = _clean_text(label_element.get_text(" ")).lower()
        if label not in normalized_labels:
            continue

        parent = label_element.parent
        if not parent:
            continue

        values = []
        for child in parent.find_all(recursive=False):
            if child is label_element:
                continue
            text = _clean_text(child.get_text(" "))
            if text:
                values.append(text)

        if values:
            return " ".join(values)

    text = _clean_text(soup.get_text(" "))
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s+(.+?)(?:\s+Version|\s+Updated|\s+Features|\s+Flag concern|\s+Size|\s+Languages|\s+Developer|$)",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

    return ""


def get_extension_info(extension_id):
    url = f"{DETAIL_BASE_URL}/{extension_id}?hl=en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")
        json_ld = _extract_json_ld(soup)
        aggregate_rating = json_ld.get("aggregateRating") if isinstance(json_ld, dict) else {}
        if not isinstance(aggregate_rating, dict):
            aggregate_rating = {}

        name = (
            (soup.find("h1").text.strip() if soup.find("h1") else "")
            or json_ld.get("name")
            or _first_meta(soup, ("property", "og:title"), ("name", "title"))
            or "N/A"
        )

        logo_url = (
            _first_meta(soup, ("property", "og:image"), ("name", "twitter:image"))
            or json_ld.get("image")
            or "N/A"
        )
        if isinstance(logo_url, list):
            logo_url = logo_url[0] if logo_url else "N/A"

        meta_description = (
            _first_meta(soup, ("property", "og:description"), ("name", "description"))
            or json_ld.get("description")
            or ""
        )
        overview_description = _extract_overview_description(soup)
        description = overview_description or meta_description or "N/A"

        all_text = " ".join(soup.get_text(" ").split())
        version = _extract_detail_field(soup, ["Version", "버전"]) or _extract_text_value(
            [
                r"버전\s*([0-9][0-9A-Za-z.\-_]*)",
                r"Version\s*([0-9][0-9A-Za-z.\-_]*)",
            ],
            all_text,
        )
        updated = _extract_detail_field(soup, ["Updated", "업데이트 날짜"]) or _extract_text_value(
            [
                r"업데이트 날짜[:\s]*([0-9. /\-]+)",
                r"Updated\s+([A-Za-z]+ \d{1,2}, \d{4})",
                r"Updated[:\s]*([A-Za-z0-9, /\-]+?)(?:\s+Features|\s+Flag concern|\s+Size|$)",
            ],
            all_text,
        )

        users = _extract_text_value(
            [
                r"사용자\s*([\d,.]+[KkMm]?)\s*\+?\s*명",
                r"([\d,.]+[KkMm]?)\s*\+?\s*users",
            ],
            all_text,
            "0",
        )
        rating = (
            str(aggregate_rating.get("ratingValue") or "")
            or _extract_text_value(
                [
                    r"별표\s*([\d.]+)\s*개",
                    r"([\d.]+)\s+out of 5",
                    r"Rated\s*([\d.]+)",
                    r"Rating\s*([\d.]+)",
                ],
                all_text,
                "0.0",
            )
        )

        users_count = _parse_number(users)
        try:
            rating_value = float(str(rating).replace(",", "."))
        except ValueError:
            rating_value = 0.0

        return {
            "success": True,
            "data": {
                "id": extension_id,
                "name": name,
                "logo_url": logo_url,
                "version": version,
                "users": users,
                "users_count": users_count,
                "rating": f"{rating_value:.1f}" if rating_value else "0.0",
                "rating_value": rating_value,
                "updated": updated,
                "last_updated": updated,
                "summary": description,
                "description": description,
                "url": url,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_extension_info_async(client, extension_id):
    url = f"{DETAIL_BASE_URL}/{extension_id}?hl=en"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
    }

    try:
        res = await client.get(url, headers=headers)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")
        json_ld = _extract_json_ld(soup)
        aggregate_rating = json_ld.get("aggregateRating") if isinstance(json_ld, dict) else {}
        if not isinstance(aggregate_rating, dict):
            aggregate_rating = {}

        name = (
            (soup.find("h1").text.strip() if soup.find("h1") else "")
            or json_ld.get("name")
            or _first_meta(soup, ("property", "og:title"), ("name", "title"))
            or "N/A"
        )

        logo_url = (
            _first_meta(soup, ("property", "og:image"), ("name", "twitter:image"))
            or json_ld.get("image")
            or "N/A"
        )
        if isinstance(logo_url, list):
            logo_url = logo_url[0] if logo_url else "N/A"

        meta_description = (
            _first_meta(soup, ("property", "og:description"), ("name", "description"))
            or json_ld.get("description")
            or ""
        )
        overview_description = _extract_overview_description(soup)
        description = overview_description or meta_description or "N/A"

        all_text = " ".join(soup.get_text(" ").split())
        version = _extract_detail_field(soup, ["Version", "踰꾩쟾"]) or _extract_text_value(
            [
                r"踰꾩쟾\s*([0-9][0-9A-Za-z.\-_]*)",
                r"Version\s*([0-9][0-9A-Za-z.\-_]*)",
            ],
            all_text,
        )
        updated = _extract_detail_field(soup, ["Updated", "?낅뜲?댄듃 ?좎쭨"]) or _extract_text_value(
            [
                r"?낅뜲?댄듃 ?좎쭨[:\s]*([0-9. /\-]+)",
                r"Updated\s+([A-Za-z]+ \d{1,2}, \d{4})",
                r"Updated[:\s]*([A-Za-z0-9, /\-]+?)(?:\s+Features|\s+Flag concern|\s+Size|$)",
            ],
            all_text,
        )

        users = _extract_text_value(
            [
                r"?ъ슜??s*([\d,.]+[KkMm]?)\s*\+?\s*紐?",
                r"([\d,.]+[KkMm]?)\s*\+?\s*users",
            ],
            all_text,
            "0",
        )
        rating = (
            str(aggregate_rating.get("ratingValue") or "")
            or _extract_text_value(
                [
                    r"蹂꾪몴\s*([\d.]+)\s*媛?",
                    r"([\d.]+)\s+out of 5",
                    r"Rated\s*([\d.]+)",
                    r"Rating\s*([\d.]+)",
                ],
                all_text,
                "0.0",
            )
        )

        users_count = _parse_number(users)
        try:
            rating_value = float(str(rating).replace(",", "."))
        except ValueError:
            rating_value = 0.0

        return {
            "success": True,
            "data": {
                "id": extension_id,
                "name": name,
                "logo_url": logo_url,
                "version": version,
                "users": users,
                "users_count": users_count,
                "rating": f"{rating_value:.1f}" if rating_value else "0.0",
                "rating_value": rating_value,
                "updated": updated,
                "last_updated": updated,
                "summary": description,
                "description": description,
                "url": url,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
