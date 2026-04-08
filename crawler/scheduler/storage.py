from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CsvPaths:
    runs: Path
    listings: Path
    listing_params: Path
    listing_images: Path
    listing_sources: Path


class CsvStorage:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.paths = CsvPaths(
            runs=data_dir / "runs.csv",
            listings=data_dir / "listings.csv",
            listing_params=data_dir / "listing_params.csv",
            listing_images=data_dir / "listing_images.csv",
            listing_sources=data_dir / "listing_sources.csv",
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def append_run(self, row: dict[str, str]) -> None:
        self._append_row(self.paths.runs, row)

    def upsert_listing(self, listing_id: int, row: dict[str, str]) -> None:
        key = str(listing_id)
        rows = self._read_rows(self.paths.listings)
        rows = [existing for existing in rows if existing.get("listing_id") != key]
        rows.append({**row, "listing_id": key})
        self._rewrite_rows(self.paths.listings, rows)

    def replace_params(self, listing_id: int, rows_to_add: list[dict[str, str]]) -> None:
        key = str(listing_id)
        rows = self._read_rows(self.paths.listing_params)
        rows = [existing for existing in rows if existing.get("listing_id") != key]
        rows.extend(rows_to_add)
        self._rewrite_rows(self.paths.listing_params, rows)

    def replace_images(self, listing_id: int, rows_to_add: list[dict[str, str]]) -> None:
        key = str(listing_id)
        rows = self._read_rows(self.paths.listing_images)
        rows = [existing for existing in rows if existing.get("listing_id") != key]
        rows.extend(rows_to_add)
        self._rewrite_rows(self.paths.listing_images, rows)

    def upsert_source(self, listing_id: int, source_name: str, row: dict[str, str]) -> None:
        key = str(listing_id)
        rows = self._read_rows(self.paths.listing_sources)
        rows = [
            existing
            for existing in rows
            if not (existing.get("listing_id") == key and existing.get("source_name") == source_name)
        ]
        rows.append({**row, "listing_id": key, "source_name": source_name})
        self._rewrite_rows(self.paths.listing_sources, rows)

    def _append_row(self, path: Path, row: dict[str, str]) -> None:
        rows = self._read_rows(path)
        rows.append(row)
        self._rewrite_rows(path, rows)

    def _read_rows(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return list(reader)

    def _rewrite_rows(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames: list[str] = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    fieldnames.append(key)

        if not fieldnames:
            return

        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})
