from __future__ import annotations

import gzip
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def parse_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA_PATTERN.search(html)
    if not match:
        raise ValueError("Next.js payload not found in HTML")
    return json.loads(match.group(1))


def extract_search_results(next_data: dict[str, Any]) -> dict[str, Any]:
    queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
    payload = next(
        (
            query["state"]["data"]
            for query in queries
            if query.get("queryKey", [None])[0] == "estatesSearch"
        ),
        None,
    )
    if payload is None:
        raise ValueError("Search payload not found in Next.js data")
    return payload


def extract_detail_payload(next_data: dict[str, Any]) -> dict[str, Any]:
    queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
    payload = next(
        (
            query["state"]["data"]
            for query in queries
            if query.get("queryKey", [None])[0] == "estate"
        ),
        None,
    )
    if payload is None:
        raise ValueError("Detail payload not found in Next.js data")
    return payload


def parse_sitemap_index(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    return [node.text for node in root.findall("sm:sitemap/sm:loc", SITEMAP_NS) if node.text]


def parse_sitemap_urls(gzip_bytes: bytes) -> list[str]:
    xml_text = gzip.decompress(gzip_bytes).decode("utf-8", errors="ignore")
    root = ET.fromstring(xml_text)
    return [node.text for node in root.findall("sm:url/sm:loc", SITEMAP_NS) if node.text]


def filter_czech_detail_urls(urls: Iterable[str]) -> list[str]:
    return [
        url
        for url in urls
        if url.startswith("https://www.sreality.cz/detail/")
    ]


def extract_listing_id(url: str) -> int | None:
    match = re.search(r"/(\d+)(?:/)?$", url)
    return int(match.group(1)) if match else None


def normalize_image_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    return url


def save_html_if_changed(path: Path, html: str) -> bool:
    content = html.encode("utf-8", errors="ignore")
    if path.exists() and path.read_bytes() == content:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return True
