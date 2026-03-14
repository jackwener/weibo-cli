"""Custom exceptions for Weibo CLI API client."""

from __future__ import annotations


class WeiboApiError(Exception):
    """Base exception for Weibo API errors."""

    def __init__(self, message: str, code: int | str | None = None, response: dict | None = None):
        super().__init__(message)
        self.code = code
        self.response = response


class SessionExpiredError(WeiboApiError):
    """Raised when session cookies have expired."""

    def __init__(self):
        super().__init__(
            "会话已过期，请重新登录: weibo logout && weibo login",
            code="session_expired",
        )


class AuthRequiredError(WeiboApiError):
    """Raised when user is not logged in."""

    def __init__(self):
        super().__init__("未登录，请先使用 weibo login 扫码登录")


class ParamError(WeiboApiError):
    """Raised when API reports missing or invalid parameters."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(f"参数错误: {message}", code=code)


class RateLimitError(WeiboApiError):
    """Raised when too many requests are made."""

    def __init__(self):
        super().__init__("请求过于频繁，请稍后再试")


class QRExpiredError(WeiboApiError):
    """Raised when the QR code has expired."""

    def __init__(self):
        super().__init__("二维码已过期，请重新运行 weibo login")


def error_code_for_exception(exc: Exception) -> str:
    """Map domain exceptions to stable error code strings."""
    if isinstance(exc, (AuthRequiredError, SessionExpiredError)):
        return "not_authenticated"
    if isinstance(exc, RateLimitError):
        return "rate_limited"
    if isinstance(exc, ParamError):
        return "invalid_params"
    if isinstance(exc, QRExpiredError):
        return "qr_expired"
    if isinstance(exc, WeiboApiError):
        return "api_error"
    return "unknown_error"
