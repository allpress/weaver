"""Cross-project service layer. One place that answers:
  - Is warden running?
  - Where does weaver live?
  - Can we spawn warden in the background?
  - Can we get a client connected?

All callers go through here so tests can monkeypatch one surface.
"""
from __future__ import annotations

import os
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass(slots=True)
class Health:
    warden_socket_exists: bool
    warden_pid_alive: bool
    warden_token_present: bool
    warden_policy_present: bool
    weaver_importable: bool
    warden_importable: bool


def warden_home() -> Path:
    override = os.environ.get("WARDEN_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".warden"


def warden_socket() -> Path:
    override = os.environ.get("WARDEN_SOCKET")
    if override:
        return Path(override).expanduser()
    return warden_home() / "sock"


def warden_token_path() -> Path:
    return warden_home() / "cap.token"


def warden_policy_path() -> Path:
    return warden_home() / "policy.yaml"


def warden_pid_path() -> Path:
    return warden_home() / "warden.pid"


def _pid_alive(pid_file: Path) -> bool:
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def health() -> Health:
    try:
        import weaver  # noqa: F401
        weaver_ok = True
    except ImportError:
        weaver_ok = False
    try:
        import warden  # noqa: F401
        warden_ok = True
    except ImportError:
        warden_ok = False
    return Health(
        warden_socket_exists=warden_socket().exists(),
        warden_pid_alive=_pid_alive(warden_pid_path()),
        warden_token_present=warden_token_path().exists(),
        warden_policy_present=warden_policy_path().exists(),
        weaver_importable=weaver_ok,
        warden_importable=warden_ok,
    )


def warden_running() -> bool:
    return warden_socket().exists() and _pid_alive(warden_pid_path())


def warden_initialized() -> bool:
    return warden_token_path().exists() and warden_policy_path().exists()


# --- starting the daemon ---

def spawn_warden_detached() -> subprocess.Popen[bytes]:
    """Run `warden serve` in a new session so it survives this process."""
    return subprocess.Popen(
        ["warden", "serve"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wait_for_warden(*, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if warden_running():
            return True
        time.sleep(0.2)
    return False


def warden_init_via_cli() -> int:
    """Shell out to `warden init` so the user sees any prompts."""
    return subprocess.call(["warden", "init"])


# --- client helper ---

@contextmanager
def warden_client() -> Iterator[object]:
    """Yield a connected WardenClient, or raise with actionable guidance."""
    try:
        from warden.client import WardenClient
    except ImportError as e:
        raise RuntimeError(
            "warden package not installed in this environment. "
            "Install it: pip install -e path/to/warden"
        ) from e
    if not warden_initialized():
        raise RuntimeError(
            "warden not initialized. Run: weaver setup  (or: warden init)"
        )
    if not warden_running():
        raise RuntimeError(
            "warden daemon not running. Start it: weaver serve  (or: warden serve)"
        )
    with WardenClient.connect() as c:
        yield c


# --- wayfinder spawn helper ---

def spawn_wayfinder(
    type_name: str,
    *,
    context: str,
    inputs: dict[str, Any],
    on_event: Any | None = None,
    poll_interval_s: float = 0.25,
    timeout_s: float = 600.0,
) -> dict[str, Any]:
    """Spawn a wayfinder through Warden and block until it finishes.

    Streams events back via `on_event(event_dict)` at `poll_interval_s`.
    Returns the final status dict (same shape as `wayfinder.status`).
    Raises on connection problems or if warden isn't running.
    """
    deadline = time.time() + timeout_s
    with warden_client() as c:
        spawn = c.call("wayfinder.spawn",    # type: ignore[attr-defined]
                        context=context, type=type_name, inputs=inputs)
        spawn_id = spawn["spawn_id"]
        seen = 0
        while True:
            if on_event is not None:
                more = c.call(                # type: ignore[attr-defined]
                    "wayfinder.events",
                    spawn_id=spawn_id, since=seen, limit=500,
                )
                for ev in more.get("events", []):
                    try:
                        on_event(ev)
                    except Exception:   # noqa: BLE001
                        pass
                seen += len(more.get("events", []))

            status = c.call("wayfinder.status", spawn_id=spawn_id)  # type: ignore[attr-defined]
            if status["status"] != "running":
                # Drain any remaining events one last time.
                if on_event is not None:
                    more = c.call("wayfinder.events",    # type: ignore[attr-defined]
                                    spawn_id=spawn_id, since=seen, limit=2000)
                    for ev in more.get("events", []):
                        try:
                            on_event(ev)
                        except Exception:   # noqa: BLE001
                            pass
                return status

            if time.time() > deadline:
                try:
                    c.call("wayfinder.kill", spawn_id=spawn_id)    # type: ignore[attr-defined]
                except Exception:   # noqa: BLE001
                    pass
                raise RuntimeError(
                    f"wayfinder spawn {spawn_id} exceeded {timeout_s}s timeout"
                )

            time.sleep(poll_interval_s)
