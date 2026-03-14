# weibo-cli

A CLI for Weibo (微博) — browse hot topics, search users, read timelines from the terminal.

## Installation

```bash
# Recommended
uv tool install weibo-cli

# Alternative
pipx install weibo-cli
```

## Quick Start

```bash
# Login via QR code
weibo login

# Check login status
weibo status

# View profile
weibo me

# Logout
weibo logout
```

## Authentication

weibo-cli supports three authentication methods (tried in order):

1. **Saved credentials** — `~/.config/weibo-cli/credential.json`
2. **Browser cookies** — Auto-extracted from Chrome/Firefox/Edge via `browser-cookie3`
3. **QR code login** — Scan with Weibo app (`weibo login`)

## License

Apache-2.0
