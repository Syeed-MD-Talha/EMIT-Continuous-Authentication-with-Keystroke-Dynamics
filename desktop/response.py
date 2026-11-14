"""Response actions taken when continuous monitoring detects a hijack.

Every action is opt-in through the ``response_action`` setting. Shutdown and
restart always use a grace period so the real user can abort with
``shutdown /a`` if the model produced a false alarm.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys

ACTION_NONE = "none"
ACTION_NOTIFY = "notify"
ACTION_LOCK = "lock"
ACTION_LOGOFF = "logoff"
ACTION_SHUTDOWN = "shutdown"
ACTION_RESTART = "restart"

ACTIONS = [
    (ACTION_LOCK, "Lock the workstation (recommended)"),
    (ACTION_NOTIFY, "Notify only"),
    (ACTION_LOGOFF, "Sign out"),
    (ACTION_SHUTDOWN, "Shut down (30 s grace period)"),
    (ACTION_RESTART, "Restart (30 s grace period)"),
]

DEFAULT_ACTION = ACTION_LOCK
GRACE_SECONDS = 30


def _run(args: list[str]) -> bool:
    try:
        subprocess.run(args, check=False, timeout=10)
        return True
    except Exception:
        return False


def lock_workstation() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.user32.LockWorkStation())
    except Exception:
        return False


def logoff() -> bool:
    if sys.platform != "win32":
        return False
    return _run(["shutdown", "/l"])


def shutdown(delay: int = GRACE_SECONDS) -> bool:
    if sys.platform != "win32":
        return False
    return _run(
        [
            "shutdown",
            "/s",
            "/t",
            str(delay),
            "/c",
            "EMIT detected an unauthorized typist. Run 'shutdown /a' to cancel.",
        ]
    )


def restart(delay: int = GRACE_SECONDS) -> bool:
    if sys.platform != "win32":
        return False
    return _run(
        [
            "shutdown",
            "/r",
            "/t",
            str(delay),
            "/c",
            "EMIT detected an unauthorized typist. Run 'shutdown /a' to cancel.",
        ]
    )


def cancel_pending() -> bool:
    """Abort a scheduled shutdown or restart."""
    if sys.platform != "win32":
        return False
    return _run(["shutdown", "/a"])


def apply(action: str) -> bool:
    """Run the configured response. Returns True when the action was attempted."""
    if action == ACTION_LOCK:
        return lock_workstation()
    if action == ACTION_LOGOFF:
        return logoff()
    if action == ACTION_SHUTDOWN:
        return shutdown()
    if action == ACTION_RESTART:
        return restart()
    return False
