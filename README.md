# weibo-cli

[![CI](https://github.com/jackwener/weibo-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/jackwener/weibo-cli/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/kabi-weibo-cli.svg)](https://pypi.org/project/kabi-weibo-cli/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](https://pypi.org/project/kabi-weibo-cli/)

A CLI for Weibo (微博) — search, browse hot topics, read timelines, and explore user profiles from the terminal 🐦

[English](#english) | [中文](#中文)

## More Tools

- [twitter-cli](https://github.com/jackwener/twitter-cli) — Twitter/X CLI for timelines, bookmarks, and posting
- [xiaohongshu-cli](https://github.com/jackwener/xiaohongshu-cli) — Xiaohongshu (小红书) CLI for notes and account workflows
- [bilibili-cli](https://github.com/jackwener/bilibili-cli) — Bilibili CLI for videos, users, search, and feeds
- [discord-cli](https://github.com/jackwener/discord-cli) — Discord CLI for local-first sync, search, and export
- [tg-cli](https://github.com/jackwener/tg-cli) — Telegram CLI for local-first sync, search, and export

## English

### Features

**Read:**
- Hot search: browse real-time trending topics and hashtags
- Hot timeline: browse the trending feed
- Home feed: browse your following timeline
- Search: find weibos by keyword
- Search trends: real-time trending sidebar data
- Weibo detail: view a weibo with full text, media, and stats
- Comments: read comments on any weibo
- Reposts: view forwards/reposts of any weibo
- User profiles: view user info, stats, and bio
- User weibos: browse a user's published weibos
- Following: view a user's following list
- Followers: view a user's follower list
- Structured output: export any data as JSON or YAML for scripting and AI agent integration

> **AI Agent Tip:** Prefer `--yaml` for structured output unless strict JSON is required. Non-TTY stdout defaults to YAML automatically. Use `--count` to limit results.

**Auth & Anti-Detection:**
- Cookie auth: auto-extract from Arc/Chrome/Edge/Firefox/Brave/Chromium/Opera/Vivaldi
- QR code login: terminal-rendered QR code for Weibo App scan
- Credential persistence: auto-save to `~/.config/weibo-cli/credential.json` with 7-day TTL
- Anti-detection: Chrome 145 User-Agent, Gaussian jitter, exponential backoff
- Session auto-refresh: stale credentials trigger browser cookie re-extraction

### Installation

```bash
# Recommended: uv tool (fast, isolated)
uv tool install kabi-weibo-cli

# Alternative: pipx
pipx install kabi-weibo-cli
```

Upgrade to the latest version:

```bash
uv tool upgrade kabi-weibo-cli
```

Install from source:

```bash
git clone git@github.com:jackwener/weibo-cli.git
cd weibo-cli
uv sync
```

### Quick Start

```bash
# Login (auto-extract browser cookies or QR scan)
weibo login

# Browse hot search
weibo hot

# Search weibos by keyword
weibo search "科技"

# View hot timeline
weibo feed

# Check a weibo
weibo detail Qw06Kd98p
```

### Usage

```bash
# ─── Auth ─────────────────────────────────────────
weibo login                            # Extract cookies from browser / QR login
weibo login --qrcode                   # QR code login directly (skip browser)
weibo login --cookie-source chrome     # Extract from specific browser
weibo logout                           # Clear saved credentials
weibo status                           # Check login status
weibo me                               # Show current user profile

# ─── Hot & Trending ────────────────────────────
weibo hot                              # Hot search list (50+ topics)
weibo hot --count 10                   # Limit results
weibo hot --json                       # JSON output
weibo trending                         # Real-time search trends
weibo trending --count 10              # Limit results
weibo trending --yaml                  # YAML output

# ─── Search ─────────────────────────────────────
weibo search <keyword>                 # Search weibos by keyword
weibo search "科技" --count 5            # Limit results
weibo search "科技" --page 2 --json     # Paginate + JSON output

# ─── Feed ───────────────────────────────────────
weibo feed                             # Hot timeline
weibo feed --count 5                   # Limit results
weibo feed --json                      # JSON output
weibo home                             # Following timeline
weibo home --count 10                  # Limit count

# ─── Weibo Detail ───────────────────────────────
weibo detail <mblogid>                 # View weibo with full stats
weibo detail Qw06Kd98p --json          # JSON output

# ─── Comments & Reposts ─────────────────────────
weibo comments <mblogid>               # View comments
weibo comments Qw06Kd98p --count 10    # Limit count
weibo comments Qw06Kd98p --json        # JSON output
weibo reposts <mblogid>                # View reposts/forwards
weibo reposts Qw06Kd98p --count 5      # Limit count

# ─── User ───────────────────────────────────────
weibo profile <uid>                    # User profile
weibo profile 1699432410 --json        # JSON output
weibo weibos <uid>                     # User's weibos
weibo weibos 1699432410 --count 5      # Limit count
weibo following <uid>                  # User's following list
weibo followers <uid>                  # User's follower list
```

### Authentication

weibo-cli uses this auth priority:

1. **Saved credentials** — loads from `~/.config/weibo-cli/credential.json`
2. **Browser cookies** (recommended) — auto-extract from Arc/Chrome/Edge/Firefox/Brave/Chromium/Opera/Vivaldi/Safari/LibreWolf
3. **QR code login** — terminal QR code, scan with Weibo App

Browser extraction is recommended — it forwards ALL Weibo cookies and is closest to normal browser traffic.

Cookie TTL is **7 days** by default. After expiry, the client automatically attempts browser re-extraction.

### Troubleshooting

- `⚠️ 未登录` — Run `weibo login` to authenticate
- `会话已过期` — Cookie expired, run `weibo logout && weibo login`
- `Unable to get key for cookie decryption` (macOS Keychain):
  - **SSH sessions**: `security unlock-keychain ~/Library/Keychains/login.keychain-db`
  - **Local terminal**: Open **Keychain Access** → search **"Chrome Safe Storage"** → **Access Control** → add Terminal → **Save**
- Requests are slow — intentional Gaussian jitter delay (~1s) to avoid triggering Weibo's risk control

### Best Practices (Avoiding Bans)

- **Keep request volumes low** — use `--count 10` instead of `--count 100`
- **Don't run too frequently** — the built-in rate limiter adds randomized delays
- **Use browser cookie extraction** — provides full cookie fingerprint
- Cookie values are stored locally and never uploaded

### Output Modes

- Default **Rich table** for interactive terminal reading
- `--json` for scripts and agent pipelines
- `--yaml` for structured output (auto-detected when stdout is not a TTY)

### Development

```bash
# Install dev dependencies
uv sync --extra dev --extra yaml

# Lint + tests
uv run ruff check .
uv run pytest tests/ -v

# Smoke tests (require browser cookies)
uv run pytest tests/ -v -m smoke
```

### Project Structure

```text
weibo_cli/
├── __init__.py
├── cli.py             # Click entry point (16 commands)
├── client.py          # WeiboClient (17 API methods, rate-limit, retry)
├── auth.py            # QR login + browser-cookie3 + credential persistence
├── constants.py       # API endpoints, headers, Chrome 145 UA
├── exceptions.py      # WeiboApiError hierarchy (6 error types)
└── commands/
    ├── _common.py     # structured_output_options, handle_command, strip_html, format_count
    ├── auth.py        # login/logout/status/me
    ├── search.py      # hot/feed/detail/comments/trending/search
    └── personal.py    # profile/weibos/following/followers/reposts/home
```

### Use as AI Agent Skill

weibo-cli ships with a [`SKILL.md`](./SKILL.md) so AI agents can execute common Weibo workflows.

#### [Skills CLI](https://github.com/vercel-labs/skills) (Recommended)

```bash
npx skills add jackwener/weibo-cli
```

| Flag | Description |
| --- | --- |
| `-g` | Install globally (user-level, shared across projects) |
| `-a claude-code` | Target a specific agent |
| `-y` | Non-interactive mode |

#### Manual Install

```bash
mkdir -p .agents/skills
git clone git@github.com:jackwener/weibo-cli.git .agents/skills/weibo-cli
```

#### ~~OpenClaw / ClawHub~~ (Deprecated)

> ⚠️ ClawHub install method is deprecated and no longer supported. Use [Skills CLI](#skills-cli-recommended) or Manual Install above.

---

## 中文

### 功能特性

**阅读:**
- 🔥 热搜：实时热门话题和标签
- 📰 热门 Feed：热门时间线
- 🏠 关注者 Feed：关注用户的时间线
- 🔍 搜索：按关键词搜索微博
- 📈 搜索趋势：实时搜索趋势侧边栏
- 📝 微博详情：查看完整正文、媒体和统计数据
- 💬 评论：查看微博评论
- 🔁 转发：查看微博转发
- 👤 用户资料：用户信息和统计
- 📋 用户微博：浏览用户已发布的微博列表
- 👥 关注列表：查看用户的关注列表
- 👥 粉丝列表：查看用户的粉丝列表
- 📊 结构化输出：支持 JSON 和 YAML，便于脚本和 AI Agent 集成

> **AI Agent 提示：** 需要结构化输出时优先使用 `--yaml`，除非下游必须是 JSON。stdout 不是 TTY 时默认输出 YAML。

**认证与反风控:**
- Cookie 认证：支持 Arc/Chrome/Edge/Firefox/Brave 等 10+ 浏览器自动提取
- 二维码登录：终端渲染二维码，用微博 APP 扫码
- 凭证持久化：自动保存到 `~/.config/weibo-cli/credential.json`，7 天 TTL
- 反检测：Chrome 145 User-Agent、高斯抖动延迟、指数退避重试
- 会话自动刷新：过期凭证自动触发浏览器 Cookie 重提取

### 安装

```bash
# 推荐：uv tool（快速、隔离环境）
uv tool install kabi-weibo-cli

# 或者：pipx
pipx install kabi-weibo-cli
```

升级到最新版本：

```bash
uv tool upgrade kabi-weibo-cli
```

从源码安装：

```bash
git clone git@github.com:jackwener/weibo-cli.git
cd weibo-cli
uv sync
```

### 使用示例

```bash
# 认证
weibo login                            # 从浏览器提取 Cookie / 二维码扫码
weibo login --qrcode                   # 直接二维码扫码登录
weibo login --cookie-source chrome     # 指定浏览器提取
weibo logout                           # 清除已保存凭证
weibo status                           # 检查登录状态
weibo me                               # 查看当前用户信息

# 热搜
weibo hot                              # 热搜列表（50+ 条）
weibo hot --count 10                   # 限制数量
weibo hot --json                       # JSON 输出
weibo trending                         # 搜索趋势

# 搜索
weibo search "科技"                     # 按关键词搜索微博
weibo search "科技" --count 5           # 限制数量
weibo search "科技" --page 2            # 翻页

# Feed
weibo feed                             # 热门时间线
weibo feed --count 5                   # 限制数量
weibo home                             # 关注者时间线

# 微博详情与评论
weibo detail Qw06Kd98p                 # 查看微博
weibo comments Qw06Kd98p               # 查看评论
weibo reposts Qw06Kd98p                # 查看转发

# 用户
weibo profile 1699432410               # 用户资料
weibo weibos 1699432410                # 用户微博列表
weibo following 1699432410             # 用户关注列表
weibo followers 1699432410             # 用户粉丝列表
```

### 常见问题

- `⚠️ 未登录` — 执行 `weibo login` 认证
- `会话已过期` — Cookie 过期，执行 `weibo logout && weibo login`
- 请求较慢是正常的 — 内置高斯随机延迟（~1s）是为了模拟人类浏览行为，避免触发风控

### 作为 AI Agent Skill 使用

#### [Skills CLI](https://github.com/vercel-labs/skills)（推荐）

```bash
npx skills add jackwener/weibo-cli
```

| 参数 | 说明 |
| --- | --- |
| `-g` | 全局安装（用户级别，跨项目共享） |
| `-a claude-code` | 指定目标 Agent |
| `-y` | 非交互模式 |

#### 手动安装

```bash
mkdir -p .agents/skills
git clone git@github.com:jackwener/weibo-cli.git .agents/skills/weibo-cli
```

## License

Apache-2.0
