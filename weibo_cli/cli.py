"""CLI entry point for Weibo CLI.

Usage:
    weibo login / status / logout / me
"""

from __future__ import annotations

import logging

import click

from . import __version__
from .commands import auth


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


if __name__ == "__main__":
    cli()
