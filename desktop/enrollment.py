"""Multi-day continuous enrollment campaigns.

Collect free-typing windows in the background, persist them in SQLite, and
train one continuous profile when the campaign deadline is reached.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal

from desktop import auth
from desktop.windowizer import Windowizer
from features import window_features


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


class EnrollmentService(QObject):
    """Owns the active campaign and its persisted samples."""

    progressChanged = Signal(dict)
    periodCompleted = Signal(str)
    periodExtended = Signal(dict)
    periodCancelled = Signal()
    periodFailed = Signal(str)

    def __init__(self, db, auth_service, capture, now_fn=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.auth_service = auth_service
        self.capture = capture
        self._now = now_fn or datetime.now
        self.period: dict | None = None
        self._keys = 0
        self._day_counts: dict[str, int] = {}
        self._last_error: str | None = None
        self._windowizer = Windowizer(
            auth.WINDOW_SIZE, auth.ENROLL_STRIDE, auth.IDLE_GAP
        )
        capture.keyCaptured.connect(self._on_key)

    @property
    def active(self) -> bool:
        return self.period is not None and self.period.get("status") == "active"

    # ------------------------------------------------------------- lifecycle
    def start(self, email: str, days: int) -> tuple[bool, str | None]:
        email = auth.normalize_email(email)
        if not auth.valid_email(email):
            return False, "Enter an email-style identifier, such as you@local.host."
        if self.active or self.db.get_active_enrollment_period() is not None:
            return False, "Another enrollment campaign is already in progress."
        if self.db.profile_exists(email):
            return False, f"'{email}' is already enrolled. Use another name."
        try:
            requirements = auth.campaign_requirements(days)
        except ValueError as exc:
            return False, str(exc)

        now = self._now()
        period_id = self.db.start_enrollment_period(
            email,
            days,
            now.isoformat(timespec="seconds"),
            (now + timedelta(days=days)).isoformat(timespec="seconds"),
            requirements["min_keys"],
            requirements["min_windows"],
            requirements["min_days"],
        )
        self.period = self.db.get_enrollment_period(period_id)
        self._keys = 0
        self._day_counts = {}
        self._last_error = None
        self._windowizer.reset()
        self._emit_progress()
        return True, None

    def resume(self) -> bool:
        """Reload an active campaign after an app restart."""
        period = self.db.get_active_enrollment_period()
        if period is None:
            self.period = None
            self._keys = 0
            self._day_counts = {}
            self._last_error = None
            self._windowizer.reset()
            return False
        self.period = period
        self._keys = int(period.get("keys_collected") or 0)
        self._day_counts = self.db.enrollment_daily_counts(period["id"])
        self._last_error = None
        self._windowizer.reset()

        if self._now() >= self._ends_at():
            if self._criteria_met():
                ok, _ = self.finish()
                if ok:
                    return False
            else:
                self._extend()
        self._emit_progress()
        return True

    def tick(self) -> None:
        """Check the deadline and finish or extend the campaign."""
        if not self.active:
            return
        self.flush()
        if self._now() >= self._ends_at():
            if self._criteria_met():
                ok, _ = self.finish()
                if ok:
                    return
            else:
                self._extend()
        self._emit_progress()

    def finish(self) -> tuple[bool, str | None]:
        if not self.active:
            return False, "No enrollment campaign is active."
        if not self._criteria_met():
            return False, "Not enough typing data has been collected yet."

        period_id = int(self.period["id"])
        email = self.period["email"]
        rows = self.db.load_enrollment_samples(period_id)
        self.db.update_enrollment_keys(period_id, self._keys)
        try:
            self.auth_service.save_continuous_profile(
                email, rows, auth.WINDOW_SIZE
            )
        except Exception as exc:  # keep the campaign alive if training fails
            message = f"Could not train the profile: {exc}"
            if message != self._last_error:
                self._last_error = message
                self.periodFailed.emit(message)
            return False, message

        self._last_error = None
        self.db.finish_enrollment_period(
            period_id, self._now().isoformat(timespec="seconds")
        )
        self.db.delete_enrollment_samples(period_id)
        self.period = None
        self._keys = 0
        self._day_counts = {}
        self._windowizer.reset()
        self.periodCompleted.emit(email)
        self.progressChanged.emit({"active": False, "email": email, "completed": True})
        return True, None

    def cancel(self) -> None:
        if not self.active:
            return
        period_id = int(self.period["id"])
        self.db.cancel_enrollment_period(period_id)
        self.period = None
        self._keys = 0
        self._day_counts = {}
        self._last_error = None
        self._windowizer.reset()
        self.periodCancelled.emit()
        self.progressChanged.emit({"active": False, "cancelled": True})

    def flush(self) -> None:
        if self.active:
            self.db.update_enrollment_keys(int(self.period["id"]), self._keys)

    # -------------------------------------------------------------- collection
    def _on_key(self, code: int, down: float, up: float) -> None:
        if not self.active:
            return
        self._keys += 1
        if self._keys % 25 == 0:
            self.flush()
        for window in self._windowizer.feed({"d": down, "u": up}):
            self._store_window(window)

    def _store_window(self, window) -> None:
        if not self.active:
            return
        now = self._now()
        day = now.strftime("%Y-%m-%d")
        if self._day_counts.get(day, 0) >= auth.MAX_WINDOWS_PER_DAY:
            return
        period_id = int(self.period["id"])
        features = window_features(window)
        self.db.add_enrollment_samples(
            period_id,
            self.period["email"],
            [(now.isoformat(timespec="seconds"), day, features)],
        )
        self._day_counts[day] = self._day_counts.get(day, 0) + 1
        self.period["windows_collected"] = (
            int(self.period.get("windows_collected") or 0) + 1
        )
        self.period["keys_collected"] = self._keys
        self._emit_progress()

        if self._now() >= self._ends_at() and self._criteria_met():
            self.finish()

    # ------------------------------------------------------------------ helpers
    def _ends_at(self) -> datetime:
        return _parse(self.period["ends_at"])

    def _criteria_met(self) -> bool:
        if not self.active:
            return False
        return (
            self._keys >= int(self.period["min_keys"])
            and int(self.period.get("windows_collected") or 0)
            >= int(self.period["min_windows"])
            and len(self._day_counts) >= int(self.period["min_days"])
        )

    def _extend(self) -> None:
        if not self.active or int(self.period.get("extended") or 0):
            return
        self.db.mark_enrollment_extended(int(self.period["id"]))
        self.period["extended"] = 1
        self.periodExtended.emit(self.progress())

    def _emit_progress(self) -> None:
        self.progressChanged.emit(self.progress())

    def progress(self) -> dict:
        if not self.active:
            return {"active": False}
        period = self.period
        now = self._now()
        started = _parse(period["started_at"])
        ends = self._ends_at()
        elapsed_days = max(0, (now.date() - started.date()).days)
        days = int(period["days"])
        return {
            "active": True,
            "email": period["email"],
            "period_id": int(period["id"]),
            "days": days,
            "day_index": min(days, elapsed_days + 1),
            "started_at": period["started_at"],
            "ends_at": period["ends_at"],
            "remaining_seconds": max(0, int((ends - now).total_seconds())),
            "deadline_passed": now >= ends,
            "keys": self._keys,
            "min_keys": int(period["min_keys"]),
            "windows": int(period.get("windows_collected") or 0),
            "min_windows": int(period["min_windows"]),
            "days_with_data": len(self._day_counts),
            "min_days": int(period["min_days"]),
            "extended": bool(int(period.get("extended") or 0)),
            "criteria_met": self._criteria_met(),
            "daily_counts": dict(self._day_counts),
        }
