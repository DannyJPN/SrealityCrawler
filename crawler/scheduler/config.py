from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SearchCombination:
    type_slug: str
    type_id: int
    main_slug: str
    main_id: int

    @property
    def key(self) -> str:
        return f"{self.type_slug}/{self.main_slug}"

    @property
    def search_url(self) -> str:
        return f"https://www.sreality.cz/hledani/{self.type_slug}/{self.main_slug}"


SEARCH_COMBINATIONS = (
    SearchCombination("prodej", 1, "byty", 1),
    SearchCombination("prodej", 1, "domy", 2),
    SearchCombination("prodej", 1, "pozemky", 3),
    SearchCombination("prodej", 1, "komercni", 4),
    SearchCombination("prodej", 1, "ostatni", 5),
    SearchCombination("pronajem", 2, "byty", 1),
    SearchCombination("pronajem", 2, "domy", 2),
    SearchCombination("pronajem", 2, "pozemky", 3),
    SearchCombination("pronajem", 2, "komercni", 4),
    SearchCombination("pronajem", 2, "ostatni", 5),
    SearchCombination("drazba", 3, "byty", 1),
    SearchCombination("drazba", 3, "domy", 2),
    SearchCombination("drazba", 3, "pozemky", 3),
    SearchCombination("drazba", 3, "komercni", 4),
    SearchCombination("drazba", 3, "ostatni", 5),
)


@dataclass(frozen=True)
class CrawlerConfig:
    data_dir: Path
    html_dir: Path
    logs_dir: Path
    request_timeout_seconds: int
    download_delay_seconds: float
    max_pages_per_combination: int
    max_details: int
    max_sitemaps: int
    max_sitemap_urls: int
    user_agent: str
    verify_tls: bool

    @classmethod
    def from_env(cls, project_root: Path) -> "CrawlerConfig":
        data_dir = Path(os.getenv("SREALITY_DATA_DIR", project_root / "Data"))
        verify_tls = os.getenv("SREALITY_INSECURE_TLS", "0") not in {"1", "true", "yes"}

        return cls(
            data_dir=data_dir,
            html_dir=data_dir / "html",
            logs_dir=data_dir / "logs",
            request_timeout_seconds=int(os.getenv("DOWNLOAD_TIMEOUT", "30")),
            download_delay_seconds=float(os.getenv("DOWNLOAD_DELAY", "0.1")),
            max_pages_per_combination=int(os.getenv("SREALITY_MAX_PAGES_PER_COMBINATION", "1")),
            max_details=int(os.getenv("SREALITY_MAX_DETAILS", "25")),
            max_sitemaps=int(os.getenv("SREALITY_MAX_SITEMAPS", "1")),
            max_sitemap_urls=int(os.getenv("SREALITY_MAX_SITEMAP_URLS", "1000")),
            user_agent=os.getenv(
                "SREALITY_USER_AGENT",
                (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/135.0.0.0 Safari/537.36"
                ),
            ),
            verify_tls=verify_tls,
        )
