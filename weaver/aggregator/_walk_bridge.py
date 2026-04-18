"""Adapter between the aggregator fetcher and two walk backends:

  - `direct`  — calls `wayfinder.walk()` in this process (fast; tests use this).
  - `guardian` — asks Warden to spawn a `http_walker` Wayfinder; blocks for
    the result. Matches the "Warden mediates all privileged ops" model.

Both return the same `BridgedReport` shape the fetcher consumes, so the
fetcher doesn't need to know which ran.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

log = logging.getLogger(__name__)


@dataclass(slots=True)
class BridgedFetched:
    """Shape of a successful fetch as the fetcher needs it."""
    url: str
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class BridgedReport:
    successes: dict[str, BridgedFetched] = field(default_factory=dict)
    halted: bool = False
    halt_reason: str | None = None
    broken_hosts: list[str] = field(default_factory=list)
    failures_count: int = 0


Mode = Literal["direct", "guardian"]


def resolve_mode(http: Any | None, via_guardian: bool | None) -> Mode:
    """Pick the backend. Explicit override wins; otherwise: caller-supplied
    http → direct; warden running → guardian; else direct."""
    if via_guardian is True:
        return "guardian"
    if via_guardian is False:
        return "direct"
    if http is not None:
        return "direct"
    try:
        from weaver.guardian import warden_running
        return "guardian" if warden_running() else "direct"
    except Exception:  # noqa: BLE001
        return "direct"


def walk_bridged(
    targets: list[dict[str, Any]],
    *,
    policy: Any | None,
    mode: Mode,
    context: str,
    http: Any | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> BridgedReport:
    """Execute a walk in either mode and return a uniform BridgedReport."""
    if mode == "guardian":
        return _walk_via_guardian(targets, policy=policy, context=context,
                                   on_event=on_event)
    return _walk_direct(targets, policy=policy, http=http, on_event=on_event)


# ---- direct ----

def _walk_direct(targets, *, policy, http, on_event) -> BridgedReport:
    from wayfinder import FetchPolicy, HttpxAdapter, WalkTarget, walk

    http = http or HttpxAdapter(user_agent="weaver-aggregator/0.1")
    ts = [WalkTarget(url=t["url"], headers=dict(t.get("headers") or {}),
                     tag=t.get("tag")) for t in targets]
    report = walk(ts, policy or FetchPolicy(), http=http,
                   on_event=_adapt_event_cb(on_event))

    out = BridgedReport(
        halted=report.halted,
        halt_reason=report.halt_reason,
        broken_hosts=sorted(report.broken_hosts),
        failures_count=len(report.failures),
    )
    for url, evt in report.successes.items():
        out.successes[url] = BridgedFetched(
            url=url, status=int(evt.status or 0),
            body=evt.body or b"",
            headers=dict(evt.headers or {}),
        )
    return out


def _adapt_event_cb(on_event):
    """Wrap a dict-expecting callback so walker's WalkEvent objects fit."""
    if on_event is None:
        return None
    def _cb(walk_event: Any) -> None:
        try:
            on_event({
                "source": "direct",
                "kind": walk_event.kind.value if hasattr(walk_event.kind, "value")
                        else str(walk_event.kind),
                "url": walk_event.url,
                "status": walk_event.status,
                "host": walk_event.host,
                "retry_after_s": walk_event.retry_after_s,
                "error": walk_event.error,
            })
        except Exception:  # noqa: BLE001
            pass
    return _cb


# ---- guardian ----

def _walk_via_guardian(targets, *, policy, context, on_event) -> BridgedReport:
    from weaver.guardian import spawn_wayfinder

    # Translate policy dataclass to a dict of JSON-safe fields.
    policy_dict: dict[str, Any] | None = None
    if policy is not None:
        policy_dict = _policy_to_dict(policy)

    def _on_event(ev: dict[str, Any]) -> None:
        if on_event is not None:
            try:
                on_event({"source": "guardian", **ev.get("data", {}),
                          "kind": ev.get("kind"), "ts": ev.get("ts")})
            except Exception:  # noqa: BLE001
                pass

    inputs: dict[str, Any] = {"targets": targets}
    if policy_dict:
        inputs["policy"] = policy_dict

    final = spawn_wayfinder(
        "http_walker",
        context=context, inputs=inputs,
        on_event=_on_event,
    )
    output = final.get("output") or {}
    out = BridgedReport(
        halted=bool(output.get("halted")),
        halt_reason=output.get("halt_reason"),
        broken_hosts=list(output.get("broken_hosts") or []),
        failures_count=len(output.get("failures") or []),
    )
    for url, row in (output.get("successes") or {}).items():
        out.successes[url] = BridgedFetched(
            url=url,
            status=int(row.get("status") or 0),
            body=base64.b64decode(row.get("body_b64") or ""),
            headers=dict(row.get("headers") or {}),
        )
    # If spawn itself failed (e.g. policy denied), surface as halt.
    if final.get("status") not in ("completed", "terminated"):
        out.halted = True
        out.halt_reason = final.get("error") or "guardian spawn failed"
    return out


def _policy_to_dict(p: Any) -> dict[str, Any]:
    """FetchPolicy → plain dict. Only the fields HttpWalkerWayfinder accepts."""
    def _as_list(s: Any) -> list[int]:
        try:
            return sorted(int(x) for x in s)
        except Exception:  # noqa: BLE001
            return []
    return {
        "max_retries": getattr(p, "max_retries", 1),
        "backoff_base_s": getattr(p, "backoff_base_s", 1.0),
        "backoff_max_s": getattr(p, "backoff_max_s", 30.0),
        "timeout_s": getattr(p, "timeout_s", 20.0),
        "halt_on_status": _as_list(getattr(p, "halt_on_status", frozenset())),
        "halt_after_host_consecutive_failures":
            getattr(p, "halt_after_host_consecutive_failures", 3),
        "halt_after_global_failures": getattr(p, "halt_after_global_failures", 10),
        "respect_retry_after": getattr(p, "respect_retry_after", True),
        "failure_statuses": _as_list(getattr(p, "failure_statuses", frozenset())),
    }
