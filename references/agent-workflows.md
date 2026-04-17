# Agent Workflow Examples

Multi-step workflows showing how to chain weibo-cli commands for common agent tasks.

## Browse hot topics and read details

```bash
# Get hot search topics
MBLOG=$(weibo hot --json | jq -r '.realtime[0].mblog_id // empty')
# Read a specific weibo
weibo detail Qw06Kd98p --json | jq '{text: .text_raw, likes: .attitudes_count, comments: .comments_count}'
```

## Analyze user profile

```bash
weibo profile 1699432410 --json | jq '.user | {name: .screen_name, followers: .followers_count, posts: .statuses_count}'
weibo weibos 1699432410 --count 3 --json
```

## Read comments on a weibo

```bash
weibo comments Qw06Kd98p --json | jq '.data[:5] | .[].text_raw'
```

## Daily monitoring workflow

```bash
# Top 10 hot topics
weibo hot --json | jq '.realtime[:10] | .[] | {rank, word, num}'

# Trending sidebar
weibo trending --yaml

# Hot feed
weibo feed --count 5 --json
```
