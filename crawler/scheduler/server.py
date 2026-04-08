from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .crawler_runtime import CrawlerRunner, ProgressTracker


LOGGER = logging.getLogger(__name__)


class CrawlerHttpServer:
    def __init__(self, host: str, port: int, runner: CrawlerRunner, progress: ProgressTracker) -> None:
        self.runner = runner
        self.progress = progress
        self._server = ThreadingHTTPServer((host, port), self._build_handler())

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        runner = self.runner
        progress = self.progress

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/healthz":
                    self._send_json(200, {"status": "ok"})
                    return
                if self.path == "/progress":
                    self._send_json(200, progress.snapshot())
                    return
                self._send_json(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/run-now":
                    self._send_json(404, {"error": "not_found"})
                    return
                if progress.snapshot().get("is_running"):
                    self._send_json(409, {"error": "already_running"})
                    return

                thread = threading.Thread(target=self._run_crawler, daemon=True)
                thread.start()
                self._send_json(202, {"status": "accepted"})

            def log_message(self, format: str, *args: Any) -> None:
                LOGGER.info("%s - %s", self.address_string(), format % args)

            def _run_crawler(self) -> None:
                try:
                    runner.run_once()
                except Exception as exc:
                    progress.update(is_running=False, stage="failed", message=str(exc))
                    LOGGER.exception("Crawler run failed: %s", exc)

            def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
