"""CLI entry point for Weibo CLI.

Usage:
    weibo login / status / logout / me
    weibo hot / feed / trending / search <keyword>
    weibo detail <mblogid> / comments <mblogid> / reposts <mblogid>
    weibo profile <uid> / weibos <uid> / following <uid> / followers <uid>
    weibo home
"""

from __future__ import annotations

import logging

import click

from . import __version__
from .commands import auth, personal, search


@click.group()
@click.version_option(version=__version__, prog_name="weibo")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging (show request URLs, timing)")
@click.pass_context
def cli(ctx, verbose: bool) -> None:
    """Weibo CLI — 在终端使用微博 🐦"""
    ctx.ensure_object(dict)
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)


# ─── Auth commands ───────────────────────────────────────────────────

cli.add_command(auth.login)
cli.add_command(auth.logout)
cli.add_command(auth.status)
cli.add_command(auth.me)

# ─── Search / Feed commands ──────────────────────────────────────────

cli.add_command(search.hot)
cli.add_command(search.feed)
cli.add_command(search.detail)
cli.add_command(search.comments)
cli.add_command(search.trending)
cli.add_command(search.search)

# ─── Personal / Profile commands ─────────────────────────────────────

cli.add_command(personal.profile)
cli.add_command(personal.weibos)
cli.add_command(personal.following)
cli.add_command(personal.followers)
cli.add_command(personal.reposts)
cli.add_command(personal.home)


if __name__ == "__main__":
    cli()

