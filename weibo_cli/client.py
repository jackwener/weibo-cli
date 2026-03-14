"""API client for Weibo with rate limiting, retry, and anti-detection."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from .auth import Credential
from .constants import (
    BASE_URL,
    BUILD_COMMENTS_URL,
    FEED_GROUPS_URL,
    FOLLOWERS_URL,
    FRIENDS_TIMELINE_URL,
    FRIENDS_URL,
    GET_CONFIG_URL,
    HEADERS,
    HOT_BAND_URL,
    HOT_SEARCH_URL,
    HOT_TIMELINE_URL,
    MOBILE_BASE_URL,
    MOBILE_SEARCH_URL,
    MY_MBLOG_URL,
    PROFILE_INFO_URL,
    REPOST_TIMELINE_URL,
    SEARCH_BAND_URL,
    STATUSES_SHOW_URL,
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
    """

    def __init__(
        self,
        credential: Credential | None = None,
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

    # ── Response handling ───────────────────────────────────────────

    def _merge_response_cookies(self, resp: httpx.Response) -> None:
        for name, value in resp.cookies.items():
            if value:
                self.client.cookies.set(name, value)

    def _handle_response(self, data: dict[str, Any], action: str, *, raw: bool = False) -> dict[str, Any]:
        """Validate API response.

        Weibo uses {ok: 1, data: {...}} format for most endpoints.
        When raw=True, return the full response dict (for APIs that don't wrap data).
        When raw=False (default), unwrap and return data["data"].
        """
        ok = data.get("ok")

        if ok == -100:
            raise SessionExpiredError()

        message = data.get("msg", data.get("message", "Unknown error"))

        if ok == 0:
            if "请先登录" in str(message) or "请登录后使用" in str(message) or "登录" in str(message):
                raise SessionExpiredError()
            raise WeiboApiError(f"{action}: {message} (ok={ok})", code=ok, response=data)

        if ok == 1:
            return data if raw else data.get("data", data)

        # ok is some other truthy value (e.g. raw APIs return full dict)
        if ok:
            return data if raw else data.get("data", data)

        raise WeiboApiError(f"{action}: {message} (ok={ok})", code=ok, response=data)

    # ── Request with retry ──────────────────────────────────────────

    def _request(self, method: str, url: str, *, client: httpx.Client | None = None, **kwargs) -> dict[str, Any]:
        self._rate_limit_delay()
        last_exc: Exception | None = None
        http = client or self.client

        for attempt in range(self._max_retries):
            t0 = time.time()
            try:
                resp = http.request(method, url, **kwargs)
                elapsed = time.time() - t0
                if not client:  # only merge cookies for the main client
                    self._merge_response_cookies(resp)
                self._mark_request()

                logger.info("[#%d] %s %s → %d (%.2fs)", self._request_count, method, url[:60], resp.status_code, elapsed)

                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning("HTTP %d, retrying in %.1fs (%d/%d)", resp.status_code, wait, attempt + 1, self._max_retries)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                text = resp.text
                if text.startswith("<"):
                    raise WeiboApiError(f"Received HTML instead of JSON from {url}")
                return resp.json()

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                wait = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)

        if last_exc:
            raise WeiboApiError(f"Request failed after {self._max_retries} retries: {last_exc}") from last_exc
        raise WeiboApiError(f"Request failed after {self._max_retries} retries")

    def _get(self, url: str, params: dict[str, Any] | None = None, action: str = "", *, raw: bool = False) -> dict[str, Any]:
        data = self._request("GET", url, params=params)
        try:
            result = self._handle_response(data, action, raw=raw)
            self._rate_limit_count = 0
            return result
        except RateLimitError:
            logger.info("Retrying after rate-limit cooldown...")
            data = self._request("GET", url, params=params)
            result = self._handle_response(data, action, raw=raw)
            self._rate_limit_count = 0
            return result

    # ── Hot Search / Trending ───────────────────────────────────────

    def get_hot_search(self) -> dict[str, Any]:
        """Get hot search list (微博热搜 sidebar, ~52 items)."""
        return self._get(HOT_SEARCH_URL, action="热搜")

    def get_hot_band(self) -> dict[str, Any]:
        """Get full hot band list (微博热搜榜)."""
        return self._get(HOT_BAND_URL, action="热搜榜")

    def get_search_band(self) -> dict[str, Any]:
        """Get search band (trending sidebar, ~16 items)."""
        return self._get(SEARCH_BAND_URL, action="搜索推荐")

    # ── Feed / Timeline ─────────────────────────────────────────────

    def get_hot_timeline(self, group_id: str = "102803", count: int = 10, max_id: str = "0") -> dict[str, Any]:
        """Get hot timeline (热门微博 feed)."""
        return self._get(HOT_TIMELINE_URL, params={
            "since_id": "0", "refresh": "0",
            "group_id": group_id, "containerid": group_id,
            "extparam": "discover|new_feed",
            "max_id": max_id, "count": str(count),
        }, action="热门Feed", raw=True)

    def get_friends_timeline(self, count: int = 20, max_id: str = "0") -> dict[str, Any]:
        """Get friends timeline (关注者 feed, requires auth)."""
        return self._get(FRIENDS_TIMELINE_URL, params={
            "count": str(count), "max_id": max_id,
        }, action="关注Feed", raw=True)

    def get_feed_groups(self) -> dict[str, Any]:
        """Get feed group configuration."""
        return self._get(FEED_GROUPS_URL, params={"is_new_segment": "1", "fetch_hot": "1"}, action="Feed分组", raw=True)

    # ── User / Profile ──────────────────────────────────────────────

    def get_profile(self, uid: str) -> dict[str, Any]:
        """Get user profile info."""
        return self._get(PROFILE_INFO_URL, params={"uid": uid}, action="用户资料")

    def get_user_weibos(self, uid: str, page: int = 1, count: int = 20, feature: int = 0) -> dict[str, Any]:
        """Get user's weibo list."""
        return self._get(MY_MBLOG_URL, params={
            "uid": uid, "page": str(page), "feature": str(feature),
        }, action="用户微博")

    # ── Weibo Detail ────────────────────────────────────────────────

    def get_weibo_detail(self, mblogid: str) -> dict[str, Any]:
        """Get single weibo detail by mblogid (e.g. 'Qw06Kd98p')."""
        return self._get(STATUSES_SHOW_URL, params={"id": mblogid}, action="微博详情", raw=True)

    # ── Comments / Reposts ──────────────────────────────────────────

    def get_comments(self, weibo_id: str, count: int = 20, max_id: int = 0) -> dict[str, Any]:
        """Get comments for a weibo."""
        params: dict[str, Any] = {"id": weibo_id, "is_show_bulletin": "2", "count": str(count), "flow": "0"}
        if max_id:
            params["max_id"] = str(max_id)
        return self._get(BUILD_COMMENTS_URL, params=params, action="评论")

    def get_reposts(self, weibo_id: str, page: int = 1, count: int = 10) -> dict[str, Any]:
        """Get repost/forward list for a weibo."""
        return self._get(REPOST_TIMELINE_URL, params={
            "id": weibo_id, "page": str(page), "count": str(count),
        }, action="转发", raw=True)

    # ── Social ──────────────────────────────────────────────────────

    def get_following(self, uid: str, page: int = 1) -> dict[str, Any]:
        """Get user's following list."""
        return self._get(FRIENDS_URL, params={"uid": uid, "page": str(page)}, action="关注列表", raw=True)

    def get_followers(self, uid: str, page: int = 1) -> dict[str, Any]:
        """Get user's follower list."""
        return self._get(FOLLOWERS_URL, params={
            "uid": uid, "page": str(page), "relate": "fans",
        }, action="粉丝列表", raw=True)

    # ── Search ──────────────────────────────────────────────────────

    def search_weibo(self, keyword: str, page: int = 1) -> dict[str, Any]:
        """Search weibos by keyword using mobile API."""
        # containerid format: 100103type=1&q=keyword
        containerid = f"100103type=1&q={keyword}"
        params = {
            "containerid": containerid,
            "page_type": "searchall",
            "page": str(page),
        }
        # Use a separate httpx client for m.weibo.cn
        cookies = {}
        if self.credential:
            cookies = self.credential.cookies
        with httpx.Client(
            base_url=MOBILE_BASE_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                "Accept": "application/json, text/plain, */*",
                "Referer": f"{MOBILE_BASE_URL}/",
                "X-Requested-With": "XMLHttpRequest",
            },
            cookies=cookies,
            follow_redirects=True,
            timeout=httpx.Timeout(self._timeout),
        ) as mobile:
            data = self._request("GET", MOBILE_SEARCH_URL, params=params, client=mobile)
        return data

    # ── Config ──────────────────────────────────────────────────────

    def get_config(self) -> dict[str, Any]:
        """Get app configuration (contains current user info)."""
        return self._get(GET_CONFIG_URL, action="配置")
