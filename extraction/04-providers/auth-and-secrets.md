# Auth & Secrets

How Weaver stores protected variables (tokens, usernames, passwords) and how providers acquire auth. This spec defines a **single precedence chain** every provider follows and an explicit opt-in — `dangerously_use_playwright_token` — for the last-resort Playwright scrape.

Related: [providers/README.md](README.md), [parsers.md](parsers.md), [install-wizard-config.md](../03-install-setup/install-wizard-config.md).

## Principles

1. **Secrets never land in config files or git.** Ever. No `.env` files committed, no `config.ini` with passwords.
2. **Secrets are per-context.** Each context has an isolated namespace; contexts cannot read each other's secrets.
3. **Prefer user-issued tokens over everything else.** API tokens, PATs, and official OAuth flows are always tried before browser scraping.
4. **Playwright-scraped tokens are labeled dangerous.** Usable, but opt-in per context + provider, loudly logged, session-scoped.
5. **Auth never runs inside the AI-assistant sandbox.** Token acquisition is a separate process (CDP watcher / auth helper); the main tool consumes, doesn't fetch.
6. **Fail loud, not fallback silent.** Auth failure returns a typed error with the exact command to re-auth.

## Secret Namespace

Every secret has a stable URI:

```
secret://<context>/<provider>/<key>

# examples
secret://team-platform/jira/api_token
secret://team-platform/github/pat
secret://team-platform/gitlab/oauth_refresh_token
secret://team-platform/confluence/scraped_session     # dangerous, labeled
secret://team-platform/service_now/basic_auth
```

The namespace is flat per (context, provider). Each secret has:

```python
@dataclass(slots=True, frozen=True)
class SecretRef:
    context: str                        # e.g. "team-platform"
    provider: str                       # e.g. "jira"
    key: str                            # e.g. "api_token"
    kind: SecretKind                    # see below
    origin: SecretOrigin                # see below
    created_at: datetime
    expires_at: datetime | None
```

### SecretKind

| Kind | Description |
|------|-------------|
| `api_token` | Provider-issued long-lived token (JIRA API token, GitLab PAT, GitHub PAT). |
| `oauth_refresh` | OAuth2 refresh token. |
| `oauth_access` | OAuth2 access token (short-lived; prefer not to persist). |
| `basic_auth` | Username + password pair. Serialized as `{"user": "...", "pass": "..."}`. |
| `scraped_session` | Cookie jar / bearer harvested via Playwright. **Dangerous.** |
| `ssh_key` | Passphrase for an existing on-disk SSH key. |

### SecretOrigin

Where the secret came from — drives the risk label and trust decisions:

| Origin | Risk | Notes |
|--------|------|-------|
| `user_issued` | `safe` | User went to provider UI, generated a token, pasted it in. |
| `oauth_official` | `standard` | Obtained via the provider's documented OAuth2 flow. |
| `basic_credentials` | `elevated` | User supplied raw username+password. Avoid; many providers disallow. |
| `playwright_scrape` | `dangerous` | Extracted from a live browser session. **Requires opt-in.** |
| `env_var` | `safe-if-ci` | Read from environment at process start (CI / ephemeral). |

## Storage Backends

One pluggable interface, multiple backends. Backend is chosen per-install; users don't pick per-secret.

```python
class SecretStore(ABC):
    name: str

    @abstractmethod
    def get(self, ref: SecretRef) -> bytes: ...
    @abstractmethod
    def put(self, ref: SecretRef, value: bytes) -> None: ...
    @abstractmethod
    def delete(self, ref: SecretRef) -> None: ...
    @abstractmethod
    def list(self, context: str, provider: str | None = None) -> list[SecretRef]: ...
    # Capability probe
    @abstractmethod
    def is_available(self) -> bool: ...
```

| Backend | Platform | Library | Notes |
|---------|----------|---------|-------|
| **macOS Keychain** | darwin | `keyring` + `keyring.backends.macOS` | Default on Mac. Values encrypted at rest by the OS. |
| **libsecret / Secret Service** | linux | `keyring` + `secretstorage` | DBus-backed; requires a running secret service (GNOME Keyring, KWallet). |
| **Windows Credential Manager** | win32 | `keyring` + `keyring.backends.Windows` | Default on Windows. |
| **Encrypted file** | any | `cryptography` (Fernet) + a master passphrase held in the OS keychain | Fallback when no OS keychain is present (headless Linux CI with no DBus). |
| **Environment variables** | any | stdlib `os.environ` | Read-only. For CI; never written. Keys: `WEAVER_<CONTEXT>_<PROVIDER>_<KEY>` (upper-cased). |

The master switch lives in `_config/defaults.ini`:

```ini
[secrets]
backend = auto                          # auto | keychain | libsecret | windows | encrypted_file | env
encrypted_file_path = _config/.secrets.enc
```

`auto` picks the first `is_available()` in platform order, falling back to `encrypted_file`, then `env`.

## Auth Precedence Chain

**Every provider uses the same resolver.** Providers do not pick their own auth — they declare which `SecretKind`s they accept, and the resolver walks the chain in a fixed order.

```python
class AuthResolver:
    def resolve(
        self,
        context: str,
        provider: str,
        *,
        dangerously_use_playwright_token: bool = False,
    ) -> AuthResult:
        """
        Fixed precedence — first match wins. Stop (don't cascade) on success.
        """
        # 1. Env var override (useful for CI, ephemeral overrides)
        if hit := self._from_env(context, provider): return hit

        # 2. User-issued API token / PAT
        if hit := self._load(context, provider, kind=SecretKind.api_token): return hit

        # 3. Cached OAuth access token (if still valid)
        if hit := self._load_valid_oauth_access(context, provider): return hit

        # 4. OAuth refresh -> access (standard flow, no browser)
        if hit := self._refresh_oauth(context, provider): return hit

        # 5. Basic auth (user + pass), if provider supports it
        if hit := self._load(context, provider, kind=SecretKind.basic_auth): return hit

        # 6. Trigger OAuth *official* interactive flow (auth helper, outside sandbox)
        if self._can_run_auth_helper():
            if hit := self._run_oauth_helper(context, provider): return hit

        # 7. Last resort — only if opted in
        if dangerously_use_playwright_token and self._playwright_enabled(provider):
            hit = self._scrape_via_playwright(context, provider)
            if hit: return hit

        raise AuthenticationError(
            context=context, provider=provider,
            hint=f"Run: weaver auth {provider} --context {context}",
        )
```

Steps 1–6 are "proper auth." Step 7 is the escape hatch for providers with no public API and no OAuth — it runs a headed browser, drives SSO, and captures the resulting session cookies/bearer from the authenticated browser context.

## The `dangerously_use_playwright_token` Flag

**Name intentionally long and ugly.** The shape matches other ecosystems' `dangerously*` patterns so it grep-bombs on review.

### How it gets enabled

Three layers, all required:

1. **Per-provider capability** — the provider's `capabilities()` includes `"playwright_scrape"`. Providers with no such adapter simply won't have it; no flag can turn it on.
2. **Per-context opt-in** — `contexts/<ctx>/config/context.ini`:
   ```ini
   [auth.providers.confluence]
   allow_playwright_scrape = true
   playwright_scrape_reason = "No API token available for on-prem Confluence 6.x"
   ```
3. **Per-call opt-in** — the caller passes `dangerously_use_playwright_token=True` (Python) or `--dangerously-use-playwright-token` (CLI).

All three must be present. Missing any one → `AuthenticationError` with a message pointing at which layer is off.

### What it costs

- Loud log line (`WARN auth: using playwright_scrape origin for confluence (context=team-platform)`).
- The resulting secret is stored with `origin=playwright_scrape` / `kind=scraped_session`.
- Default TTL is 8 hours (configurable, max 24). After TTL, forces re-scrape — no silent refresh.
- Non-interactive environments (CI, no TTY) refuse `playwright_scrape` unconditionally unless `WEAVER_ALLOW_PLAYWRIGHT_IN_CI=1` is explicitly set.
- Session artifacts written only to `_config/playwright/.auth/<context>/<provider>/` (chmod 600, gitignored).

### What it does NOT do

- Does not auto-refresh from inside the AI-assistant sandbox. Ever.
- Does not retry on failure. One attempt, then `AuthenticationError`.
- Does not store the provider password. The browser profile remembers SSO state; we harvest only the post-auth cookies/bearer.

## CLI Surface

All secret operations are explicit commands. No flag shoehorns raw values into history.

```bash
# Add / update — prompts interactively, never takes value as an argument
weaver secret set <provider> <key> [--context <ctx>] [--kind api_token|basic_auth|…]

# Inspect — shows metadata only (kind, origin, created/expires). Never the value.
weaver secret show <provider> <key> [--context <ctx>]

# Delete
weaver secret rm <provider> <key> [--context <ctx>]

# List all secrets for a context
weaver secret list [--context <ctx>] [--provider <name>]

# Walk the full precedence chain for a provider; report which step succeeded
weaver auth <provider> [--context <ctx>] [--dangerously-use-playwright-token]

# Check auth without triggering any network call
weaver auth check <provider> [--context <ctx>]

# Rotate: mark all secrets for provider as expired, force re-acquire on next use
weaver auth rotate <provider> [--context <ctx>]
```

Rules the CLI enforces:

- `secret set` reads values from a hidden prompt (`getpass`) or from `--from-stdin`. **Never** from `--value`. This keeps secrets out of shell history and `ps` output.
- `secret show` never prints the value. Add `--reveal` (prompts for confirmation) only when the backend supports it, and log the reveal.
- `auth …` without `--dangerously-use-playwright-token` never triggers a scrape, even if all other steps fail.

## Provider Integration

Providers do not call `SecretStore` directly — they call `AuthResolver.resolve(...)`. The resolver returns an opaque `AuthResult`:

```python
@dataclass(slots=True, frozen=True)
class AuthResult:
    bearer: str | None                  # "Authorization: Bearer …"
    basic: tuple[str, str] | None       # (user, pass) if basic auth
    cookies: dict[str, str] | None      # for scraped sessions
    origin: SecretOrigin                # so providers can log + refuse if needed
    expires_at: datetime | None
```

A provider can inspect `origin` and refuse to perform risky writes when origin is `playwright_scrape`:

```python
if action.is_write and auth.origin == SecretOrigin.playwright_scrape:
    raise UnsupportedAuthOriginForWrite(provider=self.name)
```

Default: scraped sessions are **read-only** across all providers unless the provider explicitly opts in.

## Safety Rules (Non-Negotiable)

1. **No secret ever appears in logs.** Logger has a redaction filter: any string matching a stored secret value is replaced with `***<kind>***`. Applied before write, not after.
2. **No secret in config files.** Enforced by a config validator that rejects known-sensitive keys (`password`, `token`, `api_key`, etc.).
3. **No secret in CLI arguments.** `secret set --value X` does not exist. Prompts or stdin only.
4. **Zero on drop.** `AuthResult` is a `@dataclass(slots=True, frozen=True)`; bytes buffers use `bytearray` + `secure_zero` on `__del__`.
5. **Short-lived OAuth access tokens are not persisted.** Only the refresh token is. Access is re-minted on demand.
6. **Scraped sessions are quarantined.** Stored under `_config/playwright/.auth/`, chmod 600, gitignored, TTL-enforced, never copied out.
7. **Non-interactive refuses escalation.** If `sys.stdin` is not a TTY and `WEAVER_ALLOW_PLAYWRIGHT_IN_CI` is unset, step 7 of the chain is skipped.
8. **Env-var override is explicit.** Providers do not read env vars themselves; the resolver does, under a fixed `WEAVER_<CTX>_<PROVIDER>_<KEY>` schema.

## File Layout

```
scripts/auth/
  __init__.py
  resolver.py                    # AuthResolver + AuthResult + AuthenticationError
  store.py                       # SecretStore ABC + registry
  backends/
    keychain.py                  # macOS Keychain (via `keyring`)
    libsecret.py                 # Linux Secret Service
    windows.py                   # Windows Credential Manager
    encrypted_file.py            # Fernet-encrypted fallback
    env.py                       # Read-only env-var backend
  oauth.py                       # Refresh + helper-launcher
  playwright_scrape.py           # The dangerous path (gated)
  redaction.py                   # Logger filter
_config/playwright/.auth/<ctx>/<provider>/   # scraped sessions (gitignored, chmod 600)
```

## Setup Wizard Touchpoints

Adding to the existing wizard (see [install-wizard-config.md](../03-install-setup/install-wizard-config.md)):

- Detect OS keychain availability; fall back to encrypted file with a one-time master passphrase prompt.
- For each configured provider, ask: "Do you have an API token?" → if yes, prompt and store. If no, offer OAuth flow. If neither available, ask whether to enable `allow_playwright_scrape` — explain the cost, require explicit `yes` typed in full.
- Emit a summary of all secrets stored (kind + origin + provider, never values) so the user knows what the install produced.

## Rotation & Revocation

- `weaver auth rotate <provider>` marks every secret for that provider as expired across the current context.
- Providers must call `AuthResolver.check_revoked(result)` before reuse of long-lived bearers — the resolver consults a small SQLite revocation log.
- On known-compromise workflow (user reports leak), `weaver secret rm --provider X --all --context Y` purges the backend entries and the revocation log records timestamps for audit.

## Why This Shape

- **One chain, not many.** Every provider having its own auth code is how sandbox-escape bugs happen. One resolver, one audit surface.
- **Opt-in by name, not by config default.** `dangerously_use_playwright_token` forces the caller to own the choice in code review.
- **Origin travels with the token.** Providers can make different decisions for writes vs. reads based on how the token was obtained.
- **Backends are platform-native first.** Users already trust their OS keychain; we don't reinvent key management.
- **The escape hatch is real but small.** We need Playwright scraping for old on-prem systems with no API. We just make sure it's loud, gated, and session-scoped.
