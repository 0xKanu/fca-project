"""HTTP layer for the FCA scraper.

Provides a rate-limited, retrying session. Respectful scraping is a core
design principle: a single worker thread, a 1s delay between requests, and an
identifiable User-Agent so the FCA can tell what we are and contact us.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scraper import config

logger = logging.getLogger(__name__)

USER_AGENT = (
    "FCA-research-scraper/0.1 "
    "(academic research; respectful scraping; 1s rate limit; "
    "contact: fca-research@example.invalid)"
)


class RateLimitExceeded(Exception):
    """Raised when the server tells us we are being throttled."""


class FetchSession:
    """A requests.Session wrapper with retry, backoff and rate limiting."""

    def __init__(self, delay: float | None = None):
        self.delay = delay if delay is not None else config.REQUEST_DELAY
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request_ts: datetime | None = None

    def _throttle(self) -> None:
        """Enforce the minimum delay between successive requests."""
        if self._last_request_ts is None:
            self._last_request_ts = datetime.now()
            return
        elapsed = (datetime.now() - self._last_request_ts).total_seconds()
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_ts = datetime.now()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(
            (requests.ConnectionError, requests.Timeout, RateLimitExceeded)
        ),
        reraise=True,
    )
    def _get(self, url: str, **kwargs) -> requests.Response:
        self._throttle()
        resp = self.session.get(url, timeout=30, **kwargs)
        if resp.status_code == 429:
            raise RateLimitExceeded(f"Rate limited by {url}")
        resp.raise_for_status()
        return resp

    def get(self, url: str, **kwargs) -> requests.Response:
        """Fetch a URL, retrying transient failures, honouring rate limits."""
        try:
            return self._get(url, **kwargs)
        except requests.HTTPError as exc:
            logger.warning("HTTP error fetching %s: %s", url, exc)
            raise
