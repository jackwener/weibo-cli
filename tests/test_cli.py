"""Tests for Weibo CLI — importability, command registration, and output format."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from weibo_cli.cli import cli


# ── Import & registration tests ─────────────────────────────────────


def test_import_cli():
    """CLI module is importable."""
    from weibo_cli import cli as cli_mod
    assert cli_mod is not None


def test_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Weibo CLI" in result.output


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.2.1" in result.output


EXPECTED_COMMANDS = [
    "login", "logout", "status", "me",
    "hot", "feed", "detail", "comments", "trending", "search",
    "profile", "weibos", "following", "followers", "reposts", "home",
]


@pytest.mark.parametrize("cmd", EXPECTED_COMMANDS)
def test_command_registered(cmd):
    """All expected commands are registered."""
    runner = CliRunner()
    result = runner.invoke(cli, [cmd, "--help"])
    assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


def test_command_count():
    """Ensure we have exactly the expected number of commands."""
    assert len(cli.commands) == len(EXPECTED_COMMANDS)


# ── Constants tests ─────────────────────────────────────────────────


def test_constants_urls():
    from weibo_cli.constants import BASE_URL, PASSPORT_URL, HOT_SEARCH_URL
    assert BASE_URL == "https://weibo.com"
    assert PASSPORT_URL == "https://passport.weibo.com"
    assert HOT_SEARCH_URL.startswith("/ajax/")


def test_constants_headers():
    from weibo_cli.constants import HEADERS
    assert "User-Agent" in HEADERS
    assert "Chrome" in HEADERS["User-Agent"]


# ── Exception tests ─────────────────────────────────────────────────


def test_exception_hierarchy():
    from weibo_cli.exceptions import WeiboApiError, SessionExpiredError, QRExpiredError, error_code_for_exception
    assert issubclass(SessionExpiredError, WeiboApiError)
    assert issubclass(QRExpiredError, WeiboApiError)
    assert error_code_for_exception(SessionExpiredError()) == "not_authenticated"
    assert error_code_for_exception(QRExpiredError()) == "qr_expired"


def test_all_error_codes():
    from weibo_cli.exceptions import (
        AuthRequiredError, ParamError, RateLimitError, error_code_for_exception
    )
    assert error_code_for_exception(AuthRequiredError()) == "not_authenticated"
    assert error_code_for_exception(RateLimitError()) == "rate_limited"
    assert error_code_for_exception(ParamError("test")) == "invalid_params"
    assert error_code_for_exception(ValueError("test")) == "unknown_error"


# ── Command help text ───────────────────────────────────────────────


@pytest.mark.parametrize("cmd,expected_text", [
    ("hot", "热搜"),
    ("feed", "Feed"),
    ("detail", "详情"),
    ("comments", "评论"),
    ("trending", "趋势"),
    ("search", "搜索"),
    ("profile", "用户资料"),
    ("weibos", "微博列表"),
    ("following", "关注列表"),
    ("followers", "粉丝列表"),
    ("reposts", "转发"),
    ("home", "关注者"),
])
def test_command_help_text(cmd, expected_text):
    """Each command has appropriate help description."""
    runner = CliRunner()
    result = runner.invoke(cli, [cmd, "--help"])
    assert expected_text in result.output


@pytest.mark.parametrize("cmd", ["hot", "feed", "detail", "comments", "trending", "search", "profile", "weibos", "following", "followers", "reposts", "home"])
def test_json_option_available(cmd):
    """All data commands support --json flag."""
    runner = CliRunner()
    result = runner.invoke(cli, [cmd, "--help"])
    assert "--json" in result.output
