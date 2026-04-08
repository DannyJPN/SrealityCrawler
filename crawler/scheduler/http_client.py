from __future__ import annotations

import ssl
import time
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass
class HttpResponse:
    url: str
    status_code: int
    content: bytes
    content_type: str

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="ignore")


class HttpClient:
    def __init__(self, user_agent: str, timeout_seconds: int, verify_tls: bool, delay_seconds: float) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.delay_seconds = delay_seconds
        self._ssl_context: Optional[ssl.SSLContext]
        if verify_tls:
            self._ssl_context = None
        else:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self._ssl_context = context

    def get(self, url: str) -> HttpResponse:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.6",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds, context=self._ssl_context) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "")
                result = HttpResponse(
                    url=response.geturl(),
                    status_code=response.getcode(),
                    content=body,
                    content_type=content_type,
                )
        except HTTPError as exc:
            result = HttpResponse(
                url=url,
                status_code=exc.code,
                content=exc.read(),
                content_type=exc.headers.get("Content-Type", ""),
            )

        time.sleep(self.delay_seconds)
        return result
