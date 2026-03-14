"""Personal & profile commands: profile, weibos, following, followers, reposts, home."""

from __future__ import annotations

import click
from rich.panel import Panel
from rich.table import Table

from ._common import console, format_count, handle_command, require_auth, strip_html, structured_output_options


@click.command()
@click.argument("uid")
@structured_output_options
def profile(uid, as_json, as_yaml):
    """查看用户资料 (weibo profile <uid>)"""
    cred = require_auth()

    def _render(data):
        user = data.get("user", data)
        lines = []
        name = user.get("screen_name", "未知")
        verified = " ✓" if user.get("verified") else ""
        lines.append(f"[bold cyan]{name}{verified}[/bold cyan]")
        if user.get("verified_reason"):
            lines.append(f"[dim]{user['verified_reason']}[/dim]")
        if user.get("description"):
            lines.append(f"\n{user['description']}")

        lines.append("")
        stats = []
        if user.get("followers_count") is not None:
            stats.append(f"[bold]粉丝[/bold] {format_count(user['followers_count'])}")
        if user.get("friends_count") is not None:
            stats.append(f"[bold]关注[/bold] {format_count(user['friends_count'])}")
        if user.get("statuses_count") is not None:
            stats.append(f"[bold]微博[/bold] {format_count(user['statuses_count'])}")
        if stats:
            lines.append("  |  ".join(stats))

        if user.get("location"):
            lines.append(f"\n📍 {user['location']}")
        if user.get("gender"):
            gender = "♂ 男" if user["gender"] == "m" else "♀ 女" if user["gender"] == "f" else ""
            if gender:
                lines.append(f"  {gender}")

        console.print(Panel("\n".join(lines), title=f"@{name}", border_style="cyan", padding=(0, 1)))

        # Show tab list if available
        tabs = data.get("tabList", [])
        if tabs:
            tab_names = [t.get("tabName", t.get("name", "")) for t in tabs]
            console.print(f"[dim]可用 Tab: {' | '.join(tab_names)}[/dim]")

    def _action(client):
        return client.get_profile(uid)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("uid")
@click.option("--page", "-p", default=1, help="页码")
@click.option("--count", "-n", default=20, help="条数")
@structured_output_options
def weibos(uid, page, count, as_json, as_yaml):
    """查看用户微博列表 (weibo weibos <uid>)"""
    cred = require_auth()

    def _render(data):
        statuses = data if isinstance(data, list) else data.get("list", data.get("statuses", []))
        if not statuses:
            console.print("[yellow]暂无微博[/yellow]")
            return

        for i, s in enumerate(statuses[:count], 1):
            text = strip_html(s.get("text_raw", s.get("text", "")))
            source = s.get("source", "")
            created = s.get("created_at", "")
            reposts = s.get("reposts_count", 0)
            comments_count = s.get("comments_count", 0)
            likes = s.get("attitudes_count", 0)
            mblogid = s.get("mblogid", "")

            content = f"[dim]{created}  via {source}[/dim]\n"
            content += f"{text[:300]}\n"
            if s.get("pic_ids"):
                content += f"[dim]📷 {len(s['pic_ids'])} 张图片[/dim]\n"
            content += f"[dim]💬 {comments_count}  🔁 {reposts}  ❤️ {likes}[/dim]"
            if mblogid:
                content += f"  [dim]ID: {mblogid}[/dim]"

            console.print(Panel(content, title=f"#{i}", border_style="blue", padding=(0, 1)))

    def _action(client):
        return client.get_user_weibos(uid, page=page)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("uid")
@click.option("--page", "-p", default=1, help="页码")
@structured_output_options
def following(uid, page, as_json, as_yaml):
    """查看用户关注列表 (weibo following <uid>)"""
    cred = require_auth()

    def _render(data):
        users = data.get("users", []) if isinstance(data, dict) else data
        if not users:
            console.print("[yellow]暂无关注[/yellow]")
            return

        table = Table(title="关注列表", show_lines=False, padding=(0, 1))
        table.add_column("UID", style="dim", width=12)
        table.add_column("昵称", style="bold")
        table.add_column("粉丝", justify="right")
        table.add_column("简介", max_width=40)

        for u in users:
            uid_str = str(u.get("id", u.get("idstr", "")))
            name = u.get("screen_name", "")
            verified = " ✓" if u.get("verified") else ""
            followers = format_count(u.get("followers_count", 0))
            desc = (u.get("description", "") or "")[:40]
            table.add_row(uid_str, f"{name}{verified}", followers, desc)

        console.print(table)

    def _action(client):
        return client.get_following(uid, page=page)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("uid")
@click.option("--page", "-p", default=1, help="页码")
@structured_output_options
def followers(uid, page, as_json, as_yaml):
    """查看用户粉丝列表 (weibo followers <uid>)"""
    cred = require_auth()

    def _render(data):
        users = data.get("users", []) if isinstance(data, dict) else data
        if not users:
            console.print("[yellow]暂无粉丝[/yellow]")
            return

        table = Table(title="粉丝列表", show_lines=False, padding=(0, 1))
        table.add_column("UID", style="dim", width=12)
        table.add_column("昵称", style="bold")
        table.add_column("粉丝", justify="right")
        table.add_column("简介", max_width=40)

        for u in users:
            uid_str = str(u.get("id", u.get("idstr", "")))
            name = u.get("screen_name", "")
            verified = " ✓" if u.get("verified") else ""
            follower_count = format_count(u.get("followers_count", 0))
            desc = (u.get("description", "") or "")[:40]
            table.add_row(uid_str, f"{name}{verified}", follower_count, desc)

        console.print(table)

    def _action(client):
        return client.get_followers(uid, page=page)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.argument("mblogid")
@click.option("--count", "-n", default=10, help="转发条数")
@click.option("--page", "-p", default=1, help="页码")
@structured_output_options
def reposts(mblogid, count, page, as_json, as_yaml):
    """查看微博转发 (weibo reposts <mblogid>)"""
    cred = require_auth()

    def _render(data):
        repost_list = data.get("data", []) if isinstance(data, dict) else data
        if not repost_list:
            console.print("[yellow]暂无转发[/yellow]")
            return

        for i, r in enumerate(repost_list[:count], 1):
            user = r.get("user", {})
            name = user.get("screen_name", "未知")
            text = strip_html(r.get("text", ""))
            created = r.get("created_at", "")

            console.print(f"  [bold]{name}[/bold]  [dim]{created}[/dim]")
            console.print(f"    {text}")
            console.print()

    def _action(client):
        # Get weibo detail to find numeric ID
        weibo = client.get_weibo_detail(mblogid)
        weibo_id = str(weibo.get("id", weibo.get("mid", "")))
        return client.get_reposts(weibo_id, page=page, count=count)

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)


@click.command()
@click.option("--count", "-n", default=20, help="条数 (1-50)")
@structured_output_options
def home(count, as_json, as_yaml):
    """查看关注者 Feed (weibo home) 🏠"""
    cred = require_auth()

    def _render(data):
        statuses = data.get("statuses", [])
        if not statuses:
            console.print("[yellow]暂无关注者微博[/yellow]")
            return

        for i, s in enumerate(statuses[:count], 1):
            user = s.get("user", {})
            name = user.get("screen_name", "未知")
            verified = " ✓" if user.get("verified") else ""
            text = strip_html(s.get("text_raw", s.get("text", "")))
            created = s.get("created_at", "")
            reposts_count = s.get("reposts_count", 0)
            comments_count = s.get("comments_count", 0)
            likes = s.get("attitudes_count", 0)
            mblogid = s.get("mblogid", "")

            content = f"[bold cyan]{name}{verified}[/bold cyan]  [dim]{created}[/dim]\n"
            content += f"{text[:200]}\n"
            if s.get("pic_ids"):
                content += f"[dim]📷 {len(s['pic_ids'])} 张图片[/dim]\n"
            content += f"[dim]💬 {comments_count}  🔁 {reposts_count}  ❤️ {likes}[/dim]"
            if mblogid:
                content += f"  [dim]ID: {mblogid}[/dim]"

            console.print(Panel(content, title=f"#{i}", border_style="green", padding=(0, 1)))

    def _action(client):
        return client.get_friends_timeline(count=min(count, 50))

    handle_command(cred, action=_action, render=_render, as_json=as_json, as_yaml=as_yaml)
