---
description: Manage protected vars (tokens, credentials) for weaver providers
argument-hint: [set|list|show|rm] <provider> <key> --context <ctx>
---

Secrets are stored in the OS keychain by default. Never pass values as CLI args.

```bash
weaver secret set gitlab token --context "$1"      # prompts hidden
weaver secret list --context "$1"
weaver secret show gitlab token --context "$1"     # metadata only, not value
weaver secret rm gitlab token --context "$1"
```

Auth precedence (tried in order on every provider call):
1. env var `WEAVER_<CTX>_<PROVIDER>_TOKEN`
2. stored api_token
3. cached oauth access
4. oauth refresh
5. basic auth
6. interactive oauth helper (TTY only)
7. Playwright scrape — **last resort**, requires `--dangerously-use-playwright-token` and per-context opt-in in `contexts/<ctx>/context.ini`
