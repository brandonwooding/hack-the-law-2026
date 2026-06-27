"""Shared polite HTTP layer for all adapters.

- sends a User-Agent (legislation.gov.uk requires one);
- rate-limits per host to stay under each source's published limit;
- retries 429/503/504 with backoff and 202 ("being generated") after a wait;
- caches every response to raw/<host>/<hash> so re-runs are free and offline.

Stdlib only (urllib) — no extra dependency.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

#: Minimum seconds between requests per host (conservative vs published limits).
#: legislation.gov.uk 3000/5min=10/s; caselaw 1000/5min~3.3/s; gov.uk 10/s.
HOST_MIN_INTERVAL: dict[str, float] = {
    "www.legislation.gov.uk": 0.2,
    "caselaw.nationalarchives.gov.uk": 0.5,
    "www.gov.uk": 0.15,
    "bills-api.parliament.uk": 0.25,
    "statutoryinstruments-api.parliament.uk": 0.25,
    "hansard-api.parliament.uk": 0.25,
    "api.parliament.uk": 0.3,
}


class NotFound(Exception):
    """Raised on HTTP 404 so adapters can skip-and-log missing documents."""


class Fetcher:
    def __init__(self, cache_dir: Path, user_agent: str, default_interval: float = 0.3):
        self.cache_dir = Path(cache_dir)
        self.user_agent = user_agent
        self.default_interval = default_interval
        self._last: dict[str, float] = {}

    def _throttle(self, host: str) -> None:
        interval = HOST_MIN_INTERVAL.get(host, self.default_interval)
        wait = interval - (time.monotonic() - self._last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def _cache_path(self, url: str, ext: str) -> Path:
        host = urllib.parse.urlparse(url).netloc
        key = hashlib.sha256(url.encode()).hexdigest()[:20]
        return self.cache_dir / host / f"{key}.{ext}"

    def get(self, url: str, accept: str | None = None, ext: str = "xml",
            force: bool = False, max_retries: int = 5) -> tuple[str, Path]:
        """Return (body_text, cache_path). Cached unless force=True."""
        path = self._cache_path(url, ext)
        if path.exists() and not force:
            return path.read_text(encoding="utf-8"), path

        host = urllib.parse.urlparse(url).netloc
        headers = {"User-Agent": self.user_agent}
        if accept:
            headers["Accept"] = accept

        last_err: Exception | None = None
        for attempt in range(max_retries):
            self._throttle(host)
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    status = getattr(r, "status", 200)
                    body = r.read().decode("utf-8", "replace")
                if status == 202:  # dynamically generated; retry after a pause
                    time.sleep(5 * (attempt + 1))
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
                return body, path
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise NotFound(url)
                if e.code in (429, 500, 503, 504):
                    last_err = e
                    time.sleep(min(60, 3 * 2 ** attempt))
                    continue
                raise
            except urllib.error.URLError as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"failed after {max_retries} retries: {url} ({last_err})")

    def get_json(self, url: str, force: bool = False) -> dict:
        body, _ = self.get(url, accept="application/json", ext="json", force=force)
        return json.loads(body)

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
