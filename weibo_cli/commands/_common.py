"""Common helpers for CLI commands."""

from __future__ import annotations

import json
import sys
from typing import Any

import click
from rich.console import Console

from ..auth import Credential, get_credential
from ..client import WeiboClient
from ..exceptions import WeiboApiError, SessionExpiredError, error_code_for_exception

console = Console()


def require_auth() -> Credential:
    """Get credential or exit with error."""
    cred = get_credential()
    if not cred:
        console.print("[yellow]⚠️  未登录[/yellow]，使用 [bold]weibo login[/bold] 扫码登录")
        sys.exit(1)
    return cred


def structured_output_options(command):
    """Decorator: add --json/--yaml options to a Click command."""
    command = click.option("--yaml", "as_yaml", is_flag=True, help="以 YAML 格式输出")(command)
    command = click.option("--json", "as_json", is_flag=True, help="以 JSON 格式输出")(command)
    return command


def handle_command(credential, *, action, render=None, as_json=False, as_yaml=False) -> Any:
    """Run action → route output: JSON / YAML(non-TTY) / Rich render.

    Also supports SessionExpiredError auto browser refresh retry.
    """
    try:
        # First attempt
        try:
            with WeiboClient(credential) as client:
                data = action(client)
        except SessionExpiredError:
            from ..auth import extract_browser_credential
            fresh = extract_browser_credential()
            if fresh:
                with WeiboClient(fresh) as client:
                    data = action(client)
            else:
                raise

        # Output routing
        if as_json:
            click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        elif as_yaml or not sys.stdout.isatty():
            try:
                import yaml
                click.echo(yaml.dump(data, allow_unicode=True, default_flow_style=False))
            except ImportError:
                click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        elif render:
            render(data)
        return data

    except WeiboApiError as exc:
        code = error_code_for_exception(exc)
        console.print(f"[red]❌ [{code}] {exc}[/red]")
        return None
