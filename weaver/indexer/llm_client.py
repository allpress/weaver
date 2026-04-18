"""Local LLM client. Today: Ollama over HTTP.

We don't take a hard dep on the `ollama` package — we talk to its REST API
directly with httpx. If you ever want a remote provider, add another class
that matches the `LLMClient` protocol.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

_DEFAULT_HOST = "http://127.0.0.1:11434"


class OllamaError(RuntimeError):
    """Base for Ollama-related failures. Most callers catch this."""


class OllamaConnectionError(OllamaError):
    """Daemon unreachable or model not pulled. Halts the indexer — no point
    walking the rest of the cache when every item will fail identically."""


class OllamaValidationError(OllamaError):
    """LLM returned malformed JSON or schema-invalid output after retries.
    Per-item failure; the runner skips and continues."""


@dataclass(slots=True)
class LLMCompletion:
    """Normalized response shape regardless of backend."""
    model: str
    content: str                         # raw text Claude would have returned
    total_duration_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    model: str

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
    ) -> LLMCompletion: ...


class OllamaClient:
    """Synchronous Ollama client via /api/chat with JSON-mode output."""

    def __init__(
        self,
        *,
        model: str = "qwen2.5:7b",
        host: str = _DEFAULT_HOST,
        keep_alive: str = "5m",
        num_ctx: int | None = None,
    ) -> None:
        self.model = model
        self._host = host.rstrip("/")
        self._keep_alive = keep_alive
        self._num_ctx = num_ctx
        self._client: Any = None

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- public API ----

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
    ) -> LLMCompletion:
        """Send a chat request constrained to JSON output."""
        import httpx

        client = self._get_client()
        options: dict[str, Any] = {"temperature": temperature}
        if self._num_ctx is not None:
            options["num_ctx"] = self._num_ctx

        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",              # Ollama constrains output to valid JSON
            "keep_alive": self._keep_alive,
            "options": options,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = client.post("/api/chat", json=payload, timeout=timeout_s)
        except httpx.ConnectError as e:
            raise OllamaConnectionError(
                f"could not connect to Ollama at {self._host}. "
                "Is it running? Start: `ollama serve`"
            ) from e
        except httpx.TimeoutException as e:
            raise OllamaConnectionError(
                f"ollama request timed out after {timeout_s}s"
            ) from e

        if resp.status_code == 404:
            raise OllamaConnectionError(
                f"model {self.model!r} not found on Ollama host. "
                f"Pull it first: `ollama pull {self.model}`"
            )
        if resp.status_code >= 400:
            raise OllamaError(f"ollama HTTP {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        content = (data.get("message") or {}).get("content") or ""
        return LLMCompletion(
            model=str(data.get("model", self.model)),
            content=content,
            total_duration_ms=_maybe_ms(data.get("total_duration")),
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            extra={"done_reason": data.get("done_reason")},
        )

    def health(self) -> dict[str, Any]:
        """Confirm the daemon is reachable and return installed models."""
        import httpx
        client = self._get_client()
        try:
            resp = client.get("/api/tags", timeout=5.0)
        except httpx.ConnectError as e:
            raise OllamaConnectionError(
                f"could not connect to Ollama at {self._host}. "
                "Is it running? Start: `ollama serve`"
            ) from e
        resp.raise_for_status()
        data = resp.json()
        return {
            "host": self._host,
            "models": [m.get("name") for m in (data.get("models") or [])],
        }

    # ---- internals ----

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            self._client = httpx.Client(base_url=self._host)
        return self._client


def _maybe_ms(ns: Any) -> int | None:
    """Ollama returns durations in nanoseconds; convert to ms if present."""
    if ns is None:
        return None
    try:
        return int(int(ns) // 1_000_000)
    except (TypeError, ValueError):
        return None


# ---- JSON parse + retry helper ----

def parse_json_with_retry(
    client: LLMClient,
    *,
    system: str,
    user: str,
    validator,
    max_retries: int = 1,
    temperature: float = 0.0,
    timeout_s: float = 120.0,
):
    """Call the LLM with JSON mode; validate with `validator`. Retry once on failure.

    `validator` is any callable that takes a dict and returns a validated object
    (or raises). Pydantic's `Model.model_validate` works directly.
    """
    last_error: Exception | None = None
    last_raw: str = ""
    for attempt in range(max_retries + 1):
        completion = client.complete_json(
            system=system, user=user,
            temperature=temperature, timeout_s=timeout_s,
        )
        last_raw = completion.content
        try:
            parsed = json.loads(completion.content)
        except json.JSONDecodeError as e:
            last_error = e
            user = (
                f"{user}\n\n"
                f"Your previous response was not valid JSON ({e.msg} at position "
                f"{e.pos}). Return ONLY the JSON object matching the requested schema."
            )
            log.warning("ollama JSON parse failed (attempt %s): %s", attempt + 1, e)
            continue
        try:
            return validator(parsed), completion
        except Exception as e:  # noqa: BLE001 — validator might be any shape
            last_error = e
            user = (
                f"{user}\n\n"
                f"Your previous JSON didn't match the schema ({e}). Return ONLY the "
                "JSON object matching the schema — no extra keys, no prose."
            )
            log.warning("validation failed (attempt %s): %s", attempt + 1, e)
            continue
    raise OllamaValidationError(
        f"LLM output failed parse/validation after {max_retries + 1} attempts: "
        f"{last_error}. Last raw: {last_raw[:300]}"
    )
