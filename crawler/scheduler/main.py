from __future__ import annotations

import logging
from pathlib import Path

from .config import CrawlerConfig
from .crawler_runtime import CrawlerRunner, ProgressTracker, build_arg_parser
from .server import CrawlerHttpServer


def configure_logging(logs_dir: Path) -> None:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(logs_dir / "crawler.log", encoding="utf-8"),
        ],
    )


def find_project_root(start: Path) -> Path:
    for candidate in [start.parent, *start.parents]:
        if (candidate / "SPECIFIKACE.md").exists() or (candidate / ".env.example").exists():
            return candidate
    return start.parent


def main() -> None:
    args = build_arg_parser().parse_args()
    project_root = find_project_root(Path(__file__).resolve())
    config = CrawlerConfig.from_env(project_root)
    if args.insecure_tls:
        config = CrawlerConfig(
            **{
                **config.__dict__,
                "verify_tls": False,
            }
        )

    configure_logging(config.logs_dir)

    progress = ProgressTracker()
    runner = CrawlerRunner(project_root=project_root, config=config, progress=progress)

    if args.once:
        runner.run_once(
            max_pages_per_combination=args.max_pages_per_combination,
            max_details=args.max_details,
            max_sitemaps=args.max_sitemaps,
            combinations_filter=set(args.combination or []),
        )
        return

    server = CrawlerHttpServer(host="0.0.0.0", port=7070, runner=runner, progress=progress)
    server.serve_forever()


if __name__ == "__main__":
    main()
