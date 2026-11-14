"""Background continuous authentication.

Scores typing anywhere in Windows and raises a tray notification after every
window of keystrokes, so the user never has to open the app or type into it.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from desktop import auth
from desktop import response
from desktop.continuous import ContinuousSession
from desktop.windowizer import Windowizer


class BackgroundMonitor(QObject):
    """Always-on scorer driven by the system-wide capture service."""

    decision = Signal(dict)
    locked = Signal(dict)
    profileChanged = Signal(str)

    def __init__(self, db, auth_service, capture, parent=None):
        super().__init__(parent)
        self.db = db
        self.auth_service = auth_service
        self.capture = capture
        self.windowizer = Windowizer(
            auth.WINDOW_SIZE, auth.MONITOR_STRIDE, auth.IDLE_GAP
        )
        self.session: ContinuousSession | None = None
        self.email: str | None = None
        self.enabled = False
        capture.keyCaptured.connect(self._on_key)

    @property
    def active(self) -> bool:
        return self.enabled and self.session is not None

    def set_profile(self, email: str | None) -> bool:
        """Load a continuous profile. Returns False if it cannot be monitored."""
        self.email = email
        self.session = None
        self.windowizer.reset()
        if not email:
            return False
        try:
            profile = self.auth_service.get_profile(email)
        except KeyError:
            return False
        if profile.get("mode") != "continuous":
            return False
        self.session = ContinuousSession(
            self.db, email, profile, typist="Genuine", tester="background"
        )
        self.profileChanged.emit(email)
        return True

    def start(self) -> bool:
        if self.session is None:
            return False
        self.enabled = True
        self.windowizer.reset()
        return True

    def stop(self) -> None:
        self.enabled = False

    def reset(self) -> None:
        if self.session is not None:
            self.session.reset()
        self.windowizer.reset()

    def _on_key(self, code: int, down: float, up: float) -> None:
        if not self.active:
            return
        for window in self.windowizer.feed({"d": down, "u": up}):
            entry = self.session.feed_window(window)
            if entry is None:
                continue
            self.decision.emit(entry)
            if entry["tier"] == "LOCKED":
                self.enabled = False
                self.locked.emit(entry)
                action = self.db.get_setting("response_action", response.DEFAULT_ACTION)
                response.apply(action)
                return
