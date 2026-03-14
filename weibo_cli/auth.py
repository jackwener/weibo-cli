"""Authentication for Weibo.

Strategy:
1. Try loading saved credential from ~/.config/weibo-cli/credential.json
2. Try extracting cookies from local browsers via browser-cookie3
3. Fallback: QR code login in terminal

QR Login Flow (reverse-engineered from passport.weibo.com):
1. GET  /sso/signin → obtain X-CSRF-TOKEN cookie
2. GET  /sso/v2/qrcode/image → get qrid + QR image URL
3. Render QR code in terminal (data = scan URL with qrid)
4. Poll GET /sso/v2/qrcode/check every 2s until success
5. On success, follow crossdomain URL to obtain session cookies
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import qrcode

from .constants import (
    CONFIG_DIR,
    CREDENTIAL_FILE,
    PASSPORT_HEADERS,
    PASSPORT_URL,
    QR_CHECK_URL,
    QR_ENTRY,
    QR_IMAGE_URL,
    QR_REDIRECT_URL,
    QR_SOURCE,
    QR_VERSION,
    REQUIRED_COOKIES,
    RETCODE_QR_NOT_SCANNED,
    RETCODE_SUCCESS,
    SSO_SIGNIN_URL,
)
from .exceptions import QRExpiredError

logger = logging.getLogger(__name__)

# Credential TTL: warn and attempt refresh after 7 days
CREDENTIAL_TTL_DAYS = 7
_CREDENTIAL_TTL_SECONDS = CREDENTIAL_TTL_DAYS * 86400

# QR poll config
POLL_INTERVAL_S = 2
POLL_TIMEOUT_S = 240  # 4 minutes


# ── Credential data class ───────────────────────────────────────────


class Credential:
    """Holds Weibo session cookies."""

    def __init__(self, cookies: dict[str, str]):
        self.cookies = cookies

    @property
    def is_valid(self) -> bool:
        return bool(self.cookies)

    def to_dict(self) -> dict[str, Any]:
        return {"cookies": self.cookies, "saved_at": time.time()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Credential:
        return cls(cookies=data.get("cookies", {}))

    def as_cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())


# ── Credential persistence ──────────────────────────────────────────


def save_credential(credential: Credential) -> None:
    """Save credential to config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CREDENTIAL_FILE.write_text(json.dumps(credential.to_dict(), indent=2, ensure_ascii=False))
    CREDENTIAL_FILE.chmod(0o600)
    logger.info("Credential saved to %s", CREDENTIAL_FILE)


def load_credential() -> Credential | None:
    """Load credential from saved file with TTL-based auto-refresh."""
    if not CREDENTIAL_FILE.exists():
        return None
    try:
        data = json.loads(CREDENTIAL_FILE.read_text())
        cred = Credential.from_dict(data)
        if not cred.is_valid:
            return None

        # Check TTL — auto-refresh if stale
        saved_at = data.get("saved_at", 0)
        if saved_at and (time.time() - saved_at) > _CREDENTIAL_TTL_SECONDS:
            logger.info("Credential older than %d days, attempting browser refresh", CREDENTIAL_TTL_DAYS)
            fresh = extract_browser_credential()
            if fresh:
                logger.info("Auto-refreshed credential from browser")
                return fresh
            logger.warning("Cookie refresh failed; using existing cookies (age: %d+ days)", CREDENTIAL_TTL_DAYS)
        return cred
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to load saved credential: %s", e)
    return None


def clear_credential() -> None:
    """Remove saved credential file."""
    if CREDENTIAL_FILE.exists():
        CREDENTIAL_FILE.unlink()
        logger.info("Credential removed: %s", CREDENTIAL_FILE)


# ── Browser cookie extraction ───────────────────────────────────────


def extract_browser_credential(cookie_source: str | None = None) -> Credential | None:
    """Extract Weibo cookies from local browsers via browser-cookie3."""
    extract_script = '''
import json, sys
try:
    import browser_cookie3 as bc3
except ImportError:
    print(json.dumps({"error": "not_installed"}))
    sys.exit(0)

target = sys.argv[1] if len(sys.argv) > 1 else None

browsers = [
    ("Chrome", bc3.chrome),
    ("Firefox", bc3.firefox),
    ("Edge", bc3.edge),
    ("Brave", bc3.brave),
    ("Chromium", bc3.chromium),
    ("Opera", bc3.opera),
    ("Vivaldi", bc3.vivaldi),
]

for name, attr in [("Arc", "arc"), ("Safari", "safari"), ("LibreWolf", "librewolf")]:
    fn = getattr(bc3, attr, None)
    if fn:
        browsers.append((name, fn))

if target:
    target_lower = target.lower()
    browsers = [(n, fn) for n, fn in browsers if n.lower() == target_lower]
    if not browsers:
        print(json.dumps({"error": f"unsupported_browser: {target}"}))
        sys.exit(0)

for name, loader in browsers:
    try:
        cj = loader(domain_name=".weibo.com")
        cookies = {c.name: c.value for c in cj if "weibo.com" in (c.domain or "") or "sina.com" in (c.domain or "")}
        if cookies:
            print(json.dumps({"browser": name, "cookies": cookies}))
            sys.exit(0)
    except Exception:
        pass

print(json.dumps({"error": "no_cookies"}))
'''

    try:
        cmd = [sys.executable, "-c", extract_script]
        if cookie_source:
            cmd.append(cookie_source)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        if result.returncode != 0:
            logger.debug("Cookie extraction subprocess failed: %s", result.stderr)
            return None

        output = result.stdout.strip()
        if not output:
            return None

        data = json.loads(output)
        if "error" in data:
            if data["error"] == "not_installed":
                logger.debug("browser-cookie3 not installed, skipping")
            else:
                logger.debug("No valid Weibo cookies found: %s", data["error"])
            return None

        cookies = data["cookies"]
        browser_name = data["browser"]
        logger.info("Found cookies in %s (%d cookies)", browser_name, len(cookies))
        cred = Credential(cookies=cookies)
        save_credential(cred)
        return cred

    except subprocess.TimeoutExpired:
        logger.warning("Cookie extraction timed out (browser may be running)")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Cookie extraction parse error: %s", e)
        return None


# ── QR Code terminal rendering ──────────────────────────────────────


def _render_qr_half_blocks(matrix: list[list[bool]]) -> str:
    """Render QR matrix using Unicode half-block characters (▀▄█ and space)."""
    if not matrix:
        return ""

    # Add 1-module quiet zone
    size = len(matrix)
    padded = [[False] * (size + 2)]
    for row in matrix:
        padded.append([False] + list(row) + [False])
    padded.append([False] * (size + 2))
    matrix = padded
    rows = len(matrix)

    # Check terminal width
    term_cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    qr_width = len(matrix[0])
    if qr_width > term_cols:
        logger.warning("Terminal too narrow (%d) for QR (%d)", term_cols, qr_width)
        return ""

    lines: list[str] = []
    for y in range(0, rows, 2):
        line = ""
        top_row = matrix[y]
        bottom_row = matrix[y + 1] if y + 1 < rows else [False] * len(top_row)
        for x in range(len(top_row)):
            top = top_row[x]
            bottom = bottom_row[x]
            if top and bottom:
                line += "█"
            elif top and not bottom:
                line += "▀"
            elif not top and bottom:
                line += "▄"
            else:
                line += " "
        lines.append(line)
    return "\n".join(lines)


def _display_qr_in_terminal(data: str) -> bool:
    """Display *data* as a QR code in the terminal using Unicode half-blocks.

    Returns True on success.
    """
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(data)
    qr.make(fit=True)
    modules = qr.get_matrix()

    rendered = _render_qr_half_blocks(modules)
    if rendered:
        print(rendered)
        return True

    # Fallback to basic ASCII
    qr2 = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr2.add_data(data)
    qr2.make(fit=True)
    qr2.print_ascii(invert=True)
    return True


# ── QR Login flow ───────────────────────────────────────────────────


def qr_login() -> Credential:
    """Full QR code login flow for Weibo.

    1. Visit passport.weibo.com/sso/signin to get X-CSRF-TOKEN cookie
    2. GET /sso/v2/qrcode/image → qrid + image URL
    3. Extract scan URL from image URL, render QR in terminal
    4. Poll /sso/v2/qrcode/check every 2s
    5. On success, follow crossdomain URL for session cookies
    """
    with httpx.Client(
        base_url=PASSPORT_URL,
        headers=dict(PASSPORT_HEADERS),
        follow_redirects=True,
        timeout=httpx.Timeout(30),
    ) as client:
        # Step 1: Get CSRF token by visiting login page
        logger.info("Getting CSRF token from login page...")
        resp = client.get(
            SSO_SIGNIN_URL,
            params={
                "entry": QR_ENTRY,
                "source": QR_SOURCE,
                "url": QR_REDIRECT_URL,
            },
        )
        resp.raise_for_status()

        csrf_token = client.cookies.get("X-CSRF-TOKEN")
        if not csrf_token:
            raise RuntimeError("Failed to obtain X-CSRF-TOKEN from passport.weibo.com")

        logger.info("Got CSRF token: %s...", csrf_token[:20])

        # Update headers with CSRF token
        client.headers["x-csrf-token"] = csrf_token

        # Step 2: Get QR code
        logger.info("Requesting QR code...")
        resp = client.get(QR_IMAGE_URL, params={"entry": QR_ENTRY, "size": "180"})
        resp.raise_for_status()
        qr_data = resp.json()

        if qr_data.get("retcode") != RETCODE_SUCCESS:
            raise RuntimeError(f"Failed to get QR code: {qr_data.get('msg', 'Unknown error')}")

        qrid = qr_data["data"]["qrid"]
        image_url = qr_data["data"]["image"]
        logger.info("Got qrid: %s", qrid)

        # Step 3: Extract scan URL from image URL and render QR
        # The QR encodes: https://passport.weibo.cn/signin/qrcode/scan?qr={qrid}&...
        parsed = urlparse(image_url)
        qs = parse_qs(parsed.query)
        scan_url = qs.get("data", [f"https://passport.weibo.cn/signin/qrcode/scan?qr={qrid}"])[0]

        print("\n📱 请使用 微博APP 扫描以下二维码登录:\n")
        print("   打开微博手机APP → 我的页面 → 扫一扫\n")
        _display_qr_in_terminal(scan_url)
        print(f"\n⏳ 等待扫码中... (超时: {POLL_TIMEOUT_S // 60} 分钟)")
        print(f"   (QR ID: {qrid[:20]}...)\n")

        # Step 4: Poll for scan status
        start_time = time.time()
        last_status = None

        while (time.time() - start_time) < POLL_TIMEOUT_S:
            try:
                resp = client.get(
                    QR_CHECK_URL,
                    params={
                        "entry": QR_ENTRY,
                        "source": QR_SOURCE,
                        "url": QR_REDIRECT_URL,
                        "qrid": qrid,
                        "rid": "",
                        "ver": QR_VERSION,
                    },
                )
                resp.raise_for_status()
                check_data = resp.json()
                retcode = check_data.get("retcode")
                msg = check_data.get("msg", "")

                if retcode != last_status:
                    logger.info("QR check: retcode=%s msg=%s", retcode, msg)
                    last_status = retcode

                if retcode == RETCODE_SUCCESS:
                    print("  ✅ 扫码成功！正在完成登录...")

                    # Step 5: Follow crossdomain URL to get session cookies
                    cross_url = check_data.get("data", {}).get("url", "")
                    alt = check_data.get("data", {}).get("alt", "")

                    cookies = {}

                    # Collect cookies from passport domain
                    for name, value in client.cookies.items():
                        cookies[name] = value

                    if cross_url:
                        logger.info("Following crossdomain URL...")
                        try:
                            # Use a separate client for cross-domain requests
                            with httpx.Client(
                                follow_redirects=True,
                                timeout=httpx.Timeout(30),
                                headers={"User-Agent": PASSPORT_HEADERS["User-Agent"]},
                            ) as cross_client:
                                cross_resp = cross_client.get(cross_url)
                                for name, value in cross_resp.cookies.items():
                                    cookies[name] = value
                                for name, value in cross_client.cookies.items():
                                    cookies[name] = value
                        except Exception as e:
                            logger.warning("Cross-domain follow failed: %s", e)

                    if alt:
                        # alt parameter may need to be exchanged for final cookies
                        try:
                            alt_url = f"https://login.sina.com.cn/sso/login.php?entry=miniblog&alt={alt}&returntype=TEXT"
                            with httpx.Client(
                                follow_redirects=True,
                                timeout=httpx.Timeout(30),
                                headers={"User-Agent": PASSPORT_HEADERS["User-Agent"]},
                            ) as alt_client:
                                alt_resp = alt_client.get(alt_url)
                                for name, value in alt_resp.cookies.items():
                                    cookies[name] = value
                                for name, value in alt_client.cookies.items():
                                    cookies[name] = value
                        except Exception as e:
                            logger.warning("Alt token exchange failed: %s", e)

                    if not cookies:
                        raise RuntimeError("Login succeeded but no cookies were obtained")

                    credential = Credential(cookies=cookies)
                    save_credential(credential)
                    print("  ✅ 登录成功！凭证已保存到", CREDENTIAL_FILE)
                    return credential

                elif retcode == RETCODE_QR_NOT_SCANNED:
                    # Still waiting for scan
                    pass

                else:
                    # Could be scanned/confirmed/expired
                    if "已扫" in msg or "扫描" in msg:
                        print("  📲 已扫码，请在手机上确认登录...")
                    elif "过期" in msg or "expired" in msg.lower():
                        raise QRExpiredError()

            except httpx.TimeoutException:
                logger.debug("QR check timeout, retrying...")
            except QRExpiredError:
                raise

            time.sleep(POLL_INTERVAL_S)

        raise QRExpiredError()


# ── Unified get_credential ──────────────────────────────────────────


def get_credential() -> Credential | None:
    """Try all auth methods and return credential.

    1. Saved credential file
    2. Browser cookie extraction
    """
    cred = load_credential()
    if cred:
        logger.info("Loaded credential from %s", CREDENTIAL_FILE)
        return cred

    cred = extract_browser_credential()
    if cred:
        logger.info("Extracted credential from browser")
        return cred

    return None
