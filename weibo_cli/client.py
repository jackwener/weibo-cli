"""API client for Weibo with rate limiting, retry, and anti-detection."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from .constants import (
    BASE_URL,
    HEADERS,
    RETCODE_SUCCESS,
)
from .exceptions import WeiboApiError, RateLimitError, SessionExpiredError

logger = logging.getLogger(__name__)


class WeiboClient:
    """Weibo API client with Gaussian jitter, exponential backoff, and session-stable identity.

    Anti-detection strategy:
    - Gaussian jitter delay between requests (~1s mean, σ=0.3)
    - 5% chance of a random long pause (2-5s) to mimic reading behavior
    - Exponential backoff on HTTP 429/5xx (up to 3 retries)
    - Response cookies merged back into session jar
    - Request counter for monitoring
    """

    def __init__(
        self,
        credential: object | None = None,
        timeout: float = 30.0,
        request_delay: float = 1.0,
        max_retries: int = 3,
    ):
        self.credential = credential
        self._timeout = timeout
        self._request_delay = request_delay
        self._base_request_delay = request_delay
        self._max_retries = max_retries
        self._last_request_time = 0.0
        self._request_count = 0
        self._rate_limit_count = 0
        self._http: httpx.Client | None = None

    def _build_client(self) -> httpx.Client:
        cookies = {}
        if self.credential:
            cookies = self.credential.cookies
        return httpx.Client(
            base_url=BASE_URL,
            headers=dict(HEADERS),
            cookies=cookies,
            follow_redirects=True,
            timeout=httpx.Timeout(self._timeout),
        )

    @property
    def client(self) -> httpx.Client:
        if not self._http:
            raise RuntimeError("Client not initialized. Use 'with WeiboClient() as client:'")
        return self._http

    def __enter__(self) -> WeiboClient:
        self._http = self._build_client()
        return self

    def __exit__(self, *args: Any) -> None:
        if self._http:
            self._http.close()
            self._http = None

    # ── Rate limiting ───────────────────────────────────────────────

    def _rate_limit_delay(self) -> None:
        """Enforce minimum delay with Gaussian jitter to mimic human browsing."""
        if self._request_delay <= 0:
            return
        elapsed = time.time() - self._last_request_time
        if elapsed < self._request_delay:
            jitter = max(0, random.gauss(0.3, 0.15))
            if random.random() < 0.05:
                jitter += random.uniform(2.0, 5.0)
            sleep_time = self._request_delay - elapsed + jitter
            logger.debug("Rate-limit delay: %.2fs", sleep_time)
            time.sleep(sleep_time)

    def _mark_request(self) -> None:
        self._last_request_time = time.time()
        self._request_count += 1

    @property
    def request_stats(self) -> dict[str, int | float]:
        """Return current request statistics."""
        return {
            "request_count": self._request_count,
            "last_request_time": self._last_request_time,
        }

    # ── Response handling ───────────────────────────────────────────

    def _merge_response_cookies(self, resp: httpx.Response) -> None:
        """Persist response Set-Cookie headers back into the session jar."""
        for name, value in resp.cookies.items():
            if value:
                self.client.cookies.set(name, value)

    def _handle_response(self, data: dict[str, Any], action: str) -> dict[str, Any]:
        """Validate API response and return data payload."""
        # Weibo uses two response formats:
        # 1. {ok: 1, data: {...}} — for ajax endpoints
        # 2. {retcode: 20000000, msg: "succ", data: {...}} — for passport endpoints
        ok = data.get("ok")
        if ok == 1:
            return data.get("data", {})

        retcode = data.get("retcode")
        if retcode == RETCODE_SUCCESS:
            return data.get("data", {})

        message = data.get("msg", data.get("message", "Unknown error"))
        code = retcode or data.get("errno", -1)

        # Check for session expired patterns
        if ok == 0 and "请先登录" in str(message):
            raise SessionExpiredError()
        if ok == -100:
            raise SessionExpiredError()

        raise WeiboApiError(f"{action}: {message} (code={code})", code=code, response=data)

    # ── Request with retry ──────────────────────────────────────────

    def _request(self, method: str, url: str, **kwargs) -> dict[str, Any]:
        """Execute HTTP request with rate-limit delay, retry, and cookie merge."""
        self._rate_limit_delay()
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            t0 = time.time()
            try:
                resp = self.client.request(method, url, **kwargs)
                elapsed = time.time() - t0
                self._merge_response_cookies(resp)
                self._mark_request()

                logger.info(
                    "[#%d] %s %s → %d (%.2fs)",
                    self._request_count, method, url[:60], resp.status_code, elapsed,
                )

                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "HTTP %d from %s, retrying in %.1fs (attempt %d/%d)",
                        resp.status_code, url[:80], wait, attempt + 1, self._max_retries,
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()

                text = resp.text
                if text.startswith("<"):
                    raise WeiboApiError(f"Received HTML instead of JSON from {url} (possible auth redirect)")

                return resp.json()

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                elapsed = time.time() - t0
                last_exc = exc
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "[#%d] %s %s → Network error: %s (%.2fs), retrying in %.1fs (attempt %d/%d)",
                    self._request_count + 1, method, url[:60], exc, elapsed, wait,
                    attempt + 1, self._max_retries,
                )
                time.sleep(wait)

        if last_exc:
            raise WeiboApiError(f"Request failed after {self._max_retries} retries: {last_exc}") from last_exc
        raise WeiboApiError(f"Request failed after {self._max_retries} retries")

    def _get(self, url: str, params: dict[str, Any] | None = None, action: str = "") -> dict[str, Any]:
        """GET request with response validation and rate-limit retry."""
        data = self._request("GET", url, params=params)
        try:
            result = self._handle_response(data, action)
            self._rate_limit_count = 0
            return result
        except RateLimitError:
            logger.info("Retrying after rate-limit cooldown...")
            data = self._request("GET", url, params=params)
            result = self._handle_response(data, action)
            self._rate_limit_count = 0
            return result

    # ── Business methods (placeholder — to be expanded) ─────────────

    def get_hot_search(self) -> dict[str, Any]:
        """Get hot search list (微博热搜)."""
        return self._get("/ajax/side/hotSearch", action="热搜")

    def get_user_info(self, uid: str) -> dict[str, Any]:
        """Get user profile info."""
        return self._get("/ajax/profile/info", params={"uid": uid}, action="用户信息")

    def get_my_timeline(self, uid: str, page: int = 1) -> dict[str, Any]:
        """Get user's timeline (微博列表)."""
        return self._get("/ajax/statuses/mymblog", params={"uid": uid, "page": page}, action="微博列表")
