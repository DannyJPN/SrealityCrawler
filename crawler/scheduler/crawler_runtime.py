from __future__ import annotations

import argparse
import logging
import math
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import CrawlerConfig, SEARCH_COMBINATIONS, SearchCombination
from .http_client import HttpClient
from .parsers import (
    extract_detail_payload,
    extract_listing_id,
    extract_search_results,
    filter_czech_detail_urls,
    normalize_image_url,
    parse_next_data,
    parse_sitemap_index,
    parse_sitemap_urls,
    save_html_if_changed,
)
from .storage import CsvStorage


LOGGER = logging.getLogger(__name__)


@dataclass
class ProgressState:
    is_running: bool = False
    percent: float = 0.0
    stage: str = "idle"
    discovered_listings: int = 0
    fetched_details: int = 0
    run_id: str = ""
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["percent"] = round(self.percent, 2)
        return payload


class ProgressTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = ProgressState()

    def update(self, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(self.state, key, value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.state.as_dict()


class CrawlerRunner:
    def __init__(self, project_root: Path, config: CrawlerConfig, progress: ProgressTracker) -> None:
        self.project_root = project_root
        self.config = config
        self.progress = progress
        self.storage = CsvStorage(config.data_dir)
        self.client = HttpClient(
            user_agent=config.user_agent,
            timeout_seconds=config.request_timeout_seconds,
            verify_tls=config.verify_tls,
            delay_seconds=config.download_delay_seconds,
        )
        self.lock_path = config.data_dir / "run.lock"

    def run_once(
        self,
        max_pages_per_combination: int | None = None,
        max_details: int | None = None,
        max_sitemaps: int | None = None,
        combinations_filter: set[str] | None = None,
    ) -> dict[str, Any]:
        self._acquire_lock()
        run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc)

        try:
            self.progress.update(
                is_running=True,
                percent=0.0,
                stage="starting",
                discovered_listings=0,
                fetched_details=0,
                run_id=run_id,
                message="Crawler run started",
            )
            search_pages_limit = max_pages_per_combination or self.config.max_pages_per_combination
            detail_limit = max_details or self.config.max_details
            sitemap_limit = max_sitemaps or self.config.max_sitemaps

            detail_url_by_id = self._discover_detail_urls_from_sitemaps(sitemap_limit)
            search_items = self._discover_listing_ids_from_search(search_pages_limit, combinations_filter)
            self.progress.update(discovered_listings=len(search_items), percent=45.0, stage="detail-selection")

            selected = []
            for item in search_items:
                detail_url = detail_url_by_id.get(item["listing_id"])
                if detail_url:
                    item["detail_url"] = detail_url
                    selected.append(item)
                if len(selected) >= detail_limit:
                    break

            if not selected:
                fallback_urls = list(detail_url_by_id.items())[:detail_limit]
                selected = [
                    {
                        "listing_id": listing_id,
                        "detail_url": detail_url,
                        "source_name": "sitemap",
                        "search_url": "",
                        "combination_key": "",
                    }
                    for listing_id, detail_url in fallback_urls
                ]

            results = self._fetch_detail_records(selected)
            finished_at = datetime.now(timezone.utc)
            summary = {
                "run_id": run_id,
                "started_at_utc": started_at.isoformat(),
                "finished_at_utc": finished_at.isoformat(),
                "search_discoveries": str(len(search_items)),
                "detail_candidates": str(len(selected)),
                "detail_successes": str(results["detail_successes"]),
                "detail_failures": str(results["detail_failures"]),
                "storage_backend": "csv",
            }
            self.storage.append_run(summary)
            self.progress.update(
                is_running=False,
                percent=100.0,
                stage="completed",
                fetched_details=results["detail_successes"],
                message="Crawler run completed",
            )
            return summary
        finally:
            self._release_lock()

    def _discover_detail_urls_from_sitemaps(self, sitemap_limit: int) -> dict[int, str]:
        self.progress.update(stage="sitemap", percent=5.0, message="Downloading sitemap index")
        response = self.client.get("https://www.sreality.cz/sitemap.xml")
        sitemap_urls = parse_sitemap_index(response.text)[:sitemap_limit]

        detail_url_by_id: dict[int, str] = {}
        for index, sitemap_url in enumerate(sitemap_urls, start=1):
            self.progress.update(
                stage="sitemap",
                percent=5.0 + 15.0 * (index / max(1, len(sitemap_urls))),
                message=f"Downloading sitemap {index}/{len(sitemap_urls)}",
            )
            sitemap_response = self.client.get(sitemap_url)
            urls = parse_sitemap_urls(sitemap_response.content)
            for detail_url in filter_czech_detail_urls(urls):
                listing_id = extract_listing_id(detail_url)
                if listing_id is None:
                    continue
                detail_url_by_id.setdefault(listing_id, detail_url)
                if len(detail_url_by_id) >= self.config.max_sitemap_urls:
                    return detail_url_by_id

        return detail_url_by_id

    def _discover_listing_ids_from_search(
        self,
        max_pages_per_combination: int,
        combinations_filter: set[str] | None,
    ) -> list[dict[str, Any]]:
        discovered: list[dict[str, Any]] = []
        combinations = [
            combination
            for combination in SEARCH_COMBINATIONS
            if not combinations_filter or combination.key in combinations_filter
        ]
        combinations_total = max(1, len(combinations))
        for index, combination in enumerate(combinations, start=1):
            for page in range(1, max_pages_per_combination + 1):
                percent = 20.0 + 25.0 * ((index - 1) / combinations_total)
                self.progress.update(
                    stage="search",
                    percent=percent,
                    message=f"Fetching {combination.key} page {page}",
                )
                url = combination.search_url if page == 1 else f"{combination.search_url}?strana={page}"
                try:
                    response = self.client.get(url)
                    if response.status_code >= 400:
                        raise RuntimeError(f"HTTP {response.status_code}")
                    payload = extract_search_results(parse_next_data(response.text))
                except Exception as exc:
                    LOGGER.warning("Skipping search page %s: %s", url, exc)
                    break
                pagination = payload.get("pagination") or {}
                total = int(pagination.get("total") or 0)
                total_pages = max(1, math.ceil(total / max(1, int(pagination.get("limit") or 22))))

                for item in payload.get("results", []):
                    listing_id = int(item["id"])
                    row = {
                        "listing_id": listing_id,
                        "source_name": "search",
                        "search_url": url,
                        "combination_key": combination.key,
                        "category_main": item.get("categoryMainCb", {}).get("name", ""),
                        "category_type": item.get("categoryTypeCb", {}).get("name", ""),
                        "category_sub": item.get("categorySubCb", {}).get("name", ""),
                        "name": item.get("name", ""),
                        "price_czk": str(item.get("priceCzk") or ""),
                        "price_czk_per_sqm": str(item.get("priceCzkPerSqM") or ""),
                        "locality_city": item.get("locality", {}).get("city", ""),
                        "locality_district": item.get("locality", {}).get("district", ""),
                        "locality_region": item.get("locality", {}).get("region", ""),
                    }
                    self.storage.upsert_source(listing_id, "search", row)
                    discovered.append(
                        {
                            "listing_id": listing_id,
                            "source_name": "search",
                            "search_url": url,
                            "combination_key": combination.key,
                        }
                    )

                if page >= total_pages:
                    break

        unique: dict[int, dict[str, Any]] = {}
        for item in discovered:
            unique[item["listing_id"]] = item
        return list(unique.values())

    def _fetch_detail_records(self, items: list[dict[str, Any]]) -> dict[str, int]:
        successes = 0
        failures = 0
        total = max(1, len(items))
        for index, item in enumerate(items, start=1):
            self.progress.update(
                stage="detail",
                percent=45.0 + 50.0 * (index / total),
                message=f"Fetching detail {index}/{total}",
            )
            try:
                response = self.client.get(item["detail_url"])
                if response.status_code >= 400:
                    raise RuntimeError(f"HTTP {response.status_code}")
                payload = extract_detail_payload(parse_next_data(response.text))
                self._store_detail_payload(item, payload, response.text)
                successes += 1
            except Exception as exc:
                failures += 1
                LOGGER.warning("Failed to fetch listing %s: %s", item["listing_id"], exc)

            self.progress.update(fetched_details=successes)

        return {"detail_successes": successes, "detail_failures": failures}

    def _store_detail_payload(self, item: dict[str, Any], payload: dict[str, Any], html: str) -> None:
        listing_id = int(item["listing_id"])
        html_filename = f"{listing_id}.html"
        html_path = self.config.html_dir / html_filename
        html_changed = save_html_if_changed(html_path, html)

        locality = payload.get("locality") or {}
        listing_row = {
            "source_name": item.get("source_name", ""),
            "detail_url": item.get("detail_url", ""),
            "search_url": item.get("search_url", ""),
            "combination_key": item.get("combination_key", ""),
            "name": payload.get("name", ""),
            "description": payload.get("description", ""),
            "note": payload.get("note", ""),
            "category_main": payload.get("categoryMainCb", {}).get("name", ""),
            "category_type": payload.get("categoryTypeCb", {}).get("name", ""),
            "category_sub": payload.get("categorySubCb", {}).get("name", ""),
            "price_czk": str(payload.get("priceCzk") or ""),
            "price_summary_czk": str(payload.get("priceSummaryCzk") or ""),
            "price_czk_per_sqm": str(payload.get("priceCzkPerSqM") or ""),
            "price_display": payload.get("price", ""),
            "locality_city": locality.get("city", ""),
            "locality_city_part": locality.get("cityPart", ""),
            "locality_district": locality.get("district", ""),
            "locality_region": locality.get("region", ""),
            "locality_street": locality.get("street", ""),
            "locality_zip": str(locality.get("zip") or ""),
            "latitude": str(locality.get("latitude") or ""),
            "longitude": str(locality.get("longitude") or ""),
            "html_filename": html_filename,
            "html_changed": "1" if html_changed else "0",
        }
        self.storage.upsert_listing(listing_id, listing_row)

        params_rows = []
        for key, value in sorted((payload.get("params") or {}).items()):
            params_rows.append(
                {
                    "listing_id": str(listing_id),
                    "param_key": key,
                    "param_value": json_dumps(value),
                }
            )
        self.storage.replace_params(listing_id, params_rows)

        image_rows = []
        for image in payload.get("images") or []:
            image_rows.append(
                {
                    "listing_id": str(listing_id),
                    "image_id": str(image.get("id") or ""),
                    "image_order": str(image.get("order") or ""),
                    "image_kind": str(image.get("kind") or ""),
                    "image_url": normalize_image_url(image.get("url") or ""),
                    "image_width": str(image.get("width") or ""),
                    "image_height": str(image.get("height") or ""),
                }
            )
        self.storage.replace_images(listing_id, image_rows)

        self.storage.upsert_source(
            listing_id,
            item.get("source_name", "detail"),
            {
                "detail_url": item.get("detail_url", ""),
                "search_url": item.get("search_url", ""),
                "combination_key": item.get("combination_key", ""),
            },
        )

    def _acquire_lock(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_path.touch(exist_ok=False)
        except FileExistsError as exc:
            raise RuntimeError("Crawler run already in progress") from exc

    def _release_lock(self) -> None:
        if self.lock_path.exists():
            self.lock_path.unlink()


def json_dumps(value: Any) -> str:
    return "" if value is None else __import__("json").dumps(value, ensure_ascii=False, sort_keys=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a limited Sreality crawler with CSV fallback storage.")
    parser.add_argument("--once", action="store_true", help="Run a single crawl and exit.")
    parser.add_argument("--max-pages-per-combination", type=int, default=None)
    parser.add_argument("--max-details", type=int, default=None)
    parser.add_argument("--max-sitemaps", type=int, default=None)
    parser.add_argument(
        "--combination",
        action="append",
        default=[],
        help="Restrict crawling to one or more exact search combinations, for example prodej/byty.",
    )
    parser.add_argument("--insecure-tls", action="store_true", help="Disable TLS verification.")
    return parser
