"""Constants for Weibo CLI — API endpoints, headers, and config paths."""

from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".config" / "weibo-cli"
CREDENTIAL_FILE = CONFIG_DIR / "credential.json"

# ── Base URLs ───────────────────────────────────────────────────────
BASE_URL = "https://weibo.com"
PASSPORT_URL = "https://passport.weibo.com"

# ── QR Login API (passport.weibo.com) ───────────────────────────────
QR_IMAGE_URL = "/sso/v2/qrcode/image"       # GET  → qrid + image URL
QR_CHECK_URL = "/sso/v2/qrcode/check"       # GET  → poll scan status
WEB_CONFIG_URL = "/sso/v2/web/config"        # POST → login config
SSO_SIGNIN_URL = "/sso/signin"               # GET  → initial page (get CSRF token)

# ── Hot Search / Trending ───────────────────────────────────────────
HOT_SEARCH_URL = "/ajax/side/hotSearch"          # GET → sidebar hot search (public)
HOT_BAND_URL = "/ajax/statuses/hot_band"         # GET → full hot search list (public)
SEARCH_BAND_URL = "/ajax/side/searchBand"        # GET → trending sidebar

# ── Feed / Timeline ────────────────────────────────────────────────
HOT_TIMELINE_URL = "/ajax/feed/hottimeline"      # GET → hot feed (public)
FRIENDS_TIMELINE_URL = "/ajax/feed/friendstimeline"  # GET → friends feed (auth)
FEED_GROUPS_URL = "/ajax/feed/allGroups"         # GET → feed groups (public)

# ── User / Profile ─────────────────────────────────────────────────
PROFILE_INFO_URL = "/ajax/profile/info"          # GET ?uid= → user profile (auth)
MY_MBLOG_URL = "/ajax/statuses/mymblog"          # GET ?uid=&page= → user weibos (auth)

# ── Weibo Detail ────────────────────────────────────────────────────
STATUSES_SHOW_URL = "/ajax/statuses/show"        # GET ?id= → single weibo detail (auth)

# ── Comments / Reposts ──────────────────────────────────────────────
BUILD_COMMENTS_URL = "/ajax/statuses/buildComments"  # GET → comments for a weibo
REPOST_TIMELINE_URL = "/ajax/statuses/repostTimeline"  # GET → reposts for a weibo

# ── Social ──────────────────────────────────────────────────────────
FRIENDS_URL = "/ajax/friendships/friends"        # GET ?uid= → following list
FOLLOWERS_URL = "/ajax/friendships/friends"      # GET ?uid=&relate=fans → follower list

# ── Search ──────────────────────────────────────────────────────────
MOBILE_BASE_URL = "https://m.weibo.cn"
MOBILE_SEARCH_URL = "/api/container/getIndex"    # GET → mobile search (keyword)

# ── Config ──────────────────────────────────────────────────────────
GET_CONFIG_URL = "/ajax/config/get_config"       # GET → app config (auth)
SIDE_CARDS_URL = "/ajax/side/cards"              # GET → sidebar cards

# ── Request Headers (Chrome 145, macOS) ─────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"{BASE_URL}/",
}

# ── Passport-specific headers ───────────────────────────────────────
PASSPORT_HEADERS = {
    **HEADERS,
    "x-requested-with": "XMLHttpRequest",
    "Referer": f"{PASSPORT_URL}/sso/signin?entry=miniblog&source=miniblog&url=https://weibo.com/",
}

# ── Cookie keys required for authenticated sessions ─────────────────
REQUIRED_COOKIES = {"SUB", "SUBP"}

# ── QR Login constants ──────────────────────────────────────────────
QR_ENTRY = "miniblog"
QR_SOURCE = "miniblog"
QR_REDIRECT_URL = "https://weibo.com/"
QR_VERSION = "20250520"

# ── Response codes ──────────────────────────────────────────────────
RETCODE_SUCCESS = 20000000
RETCODE_QR_NOT_SCANNED = 50114001
RETCODE_QR_SCANNED = 50114002
RETCODE_QR_EXPIRED = 50114004
