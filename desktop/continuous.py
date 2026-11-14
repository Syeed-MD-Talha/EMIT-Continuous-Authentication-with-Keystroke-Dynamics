"""Continuous (free-typing) authentication session."""
from __future__ import annotations

import ctypes
import sys
from datetime import datetime

from features import window_features
from model import score, tier

MAX_SUSPICIOUS_IN_ROW = 3
EWMA_ALPHA = 0.4


def lock_workstation() -> bool:
    """Lock the Windows session. Returns False on non-Windows or on failure."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.user32.LockWorkStation())
    except Exception:
        return False


class ContinuousSession:
    """Score sliding keystroke windows and escalate to LOCKED on a bad run."""

    def __init__(
        self,
        db,
        email: str,
        profile: dict,
        typist: str = "Genuine",
        tester: str = "",
        lock_after: int = MAX_SUSPICIOUS_IN_ROW,
        alpha: float = EWMA_ALPHA,
    ):
        self.db = db
        self.email = email
        self.profile = profile
        self.typist = typist
        self.tester = tester
        self.lock_after = lock_after
        self.alpha = alpha
        self.ewma: float | None = None
        self.suspicious_run = 0
        self.locked = False
        self.history: list[dict] = []

    def feed_features(self, feats) -> dict | None:
        if self.locked:
            return None
        raw = score(self.profile, feats)
        if self.ewma is None:
            self.ewma = raw
        else:
            self.ewma = self.alpha * raw + (1.0 - self.alpha) * self.ewma

        final = tier(self.ewma, self.profile)
        if final == "SUSPICIOUS":
            self.suspicious_run += 1
        else:
            self.suspicious_run = 0
        if final == "SUSPICIOUS" and self.suspicious_run >= self.lock_after:
            final = "LOCKED"
        if final == "LOCKED":
            self.locked = True

        entry = {
            "score": self.ewma,
            "raw": raw,
            "tier": final,
            "t_susp": self.profile["t_susp"],
            "t_lock": self.profile["t_lock"],
        }
        self.history.append(entry)
        self.db.log_attempt(
            datetime.now().isoformat(timespec="seconds"),
            self.email,
            self.typist,
            self.tester,
            len(self.history),
            round(self.ewma, 4),
            final,
            round(self.profile["t_susp"], 4),
            round(self.profile["t_lock"], 4),
        )
        return entry

    def feed_window(self, events) -> dict | None:
        return self.feed_features(window_features(events))

    def reset(self) -> None:
        self.ewma = None
        self.suspicious_run = 0
        self.locked = False
        self.history = []
