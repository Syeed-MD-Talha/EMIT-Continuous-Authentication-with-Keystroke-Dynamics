import getpass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from desktop import auth
from desktop.auth import AuthService, LiveSession
from desktop.capture import CaptureService
from desktop.continuous import ContinuousSession, lock_workstation
from desktop.storage import Database
from desktop.ui.keystroke_edit import KeystrokeEdit
from desktop.ui.sparkline import ScoreSparkline
from desktop.ui.widgets import (
    Card, Chip, CurrentPanelStack, Divider, Inset, PageHeader, Select, SessionBanner,
    StatCard, field_label, hint_label, label, make_button, page_layout, stat_row,
)
from desktop.windowizer import Windowizer

MODE_PASSWORD = 0
MODE_CONTINUOUS = 1
MODE_EMPTY = 2


class LivePage(QWidget):
    tierChanged = Signal(str)
    enrollRequested = Signal()

    def __init__(self, db: Database, auth_service: AuthService, capture: CaptureService,
                 monitor, enrollment=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.auth_service = auth_service
        self.capture = capture
        self.monitor = monitor
        self.enrollment = enrollment
        self.live: LiveSession | None = None
        self.continuous: ContinuousSession | None = None
        self._monitoring = False
        self._keys = 0
        self._windowizer = Windowizer(
            auth.WINDOW_SIZE, auth.MONITOR_STRIDE, auth.IDLE_GAP
        )
        self._build_ui()
        self.refresh_users()
        self.capture.keyCaptured.connect(self._on_key)
        self.monitor.decision.connect(self._on_background_decision)
        self.monitor.locked.connect(self._on_background_locked)
        if enrollment is not None:
            enrollment.progressChanged.connect(self._on_enrollment_progress)
            enrollment.periodCompleted.connect(self._on_enrollment_completed)

    def _build_ui(self) -> None:
        layout = page_layout(self)
        layout.addWidget(PageHeader(
            "Live session",
            "Verify your typing rhythm and review the latest biometric readings.",
            eyebrow="Session monitoring",
        ))
        self.enrollment_banner = hint_label("")
        self.enrollment_banner.hide()
        layout.addWidget(self.enrollment_banner)
        self.status_label = SessionBanner()
        layout.addWidget(self.status_label)

        columns = QHBoxLayout()
        columns.setSpacing(15)
        left = QVBoxLayout()
        left.setSpacing(15)
        left.addWidget(self._build_verification_card())
        left.addWidget(self._build_chart_card())
        left.addStretch(1)
        columns.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(15)
        right.addWidget(self._build_session_card())
        right.addWidget(self._build_threat_card())
        right.addStretch(1)
        columns.addLayout(right, 3)
        layout.addLayout(columns)
        layout.addStretch(1)

        self.user_combo.currentTextChanged.connect(self._start_session)
        self.typist_combo.currentTextChanged.connect(self._typist_changed)
        self.password_edit.attemptReady.connect(self._attempt)
        self.password_unlock_button.clicked.connect(self._unlock)
        self.monitor_button.clicked.connect(self._toggle_monitoring)
        self.monitor_unlock_button.clicked.connect(self._unlock)

    def _build_verification_card(self) -> Card:
        self.attempts_chip = Chip("No samples")
        card = Card("Verification", "keyboard", self.attempts_chip)
        self.verification_title = card.title_label
        self.mode_stack = CurrentPanelStack()
        self.mode_stack.addWidget(self._build_password_panel())
        self.mode_stack.addWidget(self._build_continuous_panel())
        empty = Inset()
        self.empty_hint = hint_label("Create a profile to start verifying your typing rhythm.")
        empty.body.addWidget(self.empty_hint)
        enroll = make_button("Enroll a profile")
        enroll.clicked.connect(self.enrollRequested)
        empty.body.addWidget(enroll, 0, Qt.AlignmentFlag.AlignLeft)
        self.mode_stack.addWidget(empty)
        card.body.addWidget(self.mode_stack)
        return card

    def _build_password_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.password_edit = KeystrokeEdit()
        layout.addWidget(field_label("Retype your practice password", self.password_edit))
        layout.addWidget(self.password_edit)
        self.password_message = hint_label("")
        layout.addWidget(self.password_message)
        self.password_unlock_button = make_button("Reset session", "secondary")
        self.password_unlock_button.hide()
        layout.addWidget(self.password_unlock_button, 0, Qt.AlignmentFlag.AlignLeft)
        return panel

    def _build_continuous_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        self.monitor_keys_stat = StatCard("Test keystrokes")
        self.monitor_windows_stat = StatCard("Windows scored")
        controls = stat_row(self.monitor_keys_stat, self.monitor_windows_stat)
        self.monitor_button = make_button("Start monitoring")
        controls.addWidget(self.monitor_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.monitor_unlock_button = make_button("Reset session", "secondary")
        self.monitor_unlock_button.hide()
        layout.addLayout(controls)
        layout.addWidget(self.monitor_unlock_button, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(hint_label(
            f"Type in any Windows app. EMIT scores each window of {auth.WINDOW_SIZE} keystrokes."
        ))
        return panel

    def _build_chart_card(self) -> Card:
        card = Card("Anomaly score history", "chart", Chip("Current session", "info"))
        card.body.addWidget(hint_label("Lower scores indicate a larger difference from your profile."))
        self.sparkline = ScoreSparkline()
        card.body.addWidget(self.sparkline)
        legend = QHBoxLayout()
        for text, kind in (
            ("●  Score", "info"),
            ("– –  Suspicious", "warn"),
            ("– –  Lock", "err"),
        ):
            legend.addWidget(Chip(text, kind))
        legend.addStretch(1)
        card.body.addLayout(legend)
        return card

    def _build_session_card(self) -> Card:
        self.session_chip = Chip("No profile")
        card = Card("Session details", "user", self.session_chip)
        self.user_combo = Select()
        self.user_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.user_combo.setMinimumContentsLength(12)
        self.user_combo.setPlaceholderText("No profiles yet")
        card.body.addWidget(field_label("Enrolled profile", self.user_combo))
        card.body.addWidget(self.user_combo)

        self.typist_combo = Select()
        self.typist_combo.addItems(["Genuine", "Impostor"])
        card.body.addWidget(field_label("Test mode", self.typist_combo))
        card.body.addWidget(self.typist_combo)

        self.tester_edit = QLineEdit(getpass.getuser())
        self.tester_label = field_label("Tester name", self.tester_edit)
        card.body.addWidget(self.tester_label)
        card.body.addWidget(self.tester_edit)
        self.tester_label.hide()
        self.tester_edit.hide()
        card.body.addWidget(hint_label("Impostor mode labels attempts made by someone other than the enrolled typist."))
        return card

    def _build_threat_card(self) -> Card:
        card = Card("Session assessment", "shield")
        well = Inset()
        row = QHBoxLayout()
        row.addWidget(label("Latest decision", "Subheading"), 1)
        self.threat_chip = Chip("Pending")
        row.addWidget(self.threat_chip)
        well.body.addLayout(row)
        well.body.addWidget(Divider())
        self.assessment_hint = hint_label("A decision appears when EMIT has enough typing data to score.")
        well.body.addWidget(self.assessment_hint)
        card.body.addWidget(well)
        card.body.addWidget(hint_label("Configure automatic responses for background monitoring in Settings."))
        return card

    def on_shown(self) -> None:
        self._refresh_enrollment_banner()
        self.refresh_users()

    def on_hidden(self) -> None:
        pass

    def _on_enrollment_progress(self, progress: dict) -> None:
        self._refresh_enrollment_banner(progress)

    def _on_enrollment_completed(self, email: str) -> None:
        self._refresh_enrollment_banner()
        self.refresh_users(select=email)

    def _refresh_enrollment_banner(self, progress: dict | None = None) -> None:
        if self.enrollment is None or not self.enrollment.active:
            self.enrollment_banner.hide()
            return
        progress = progress or self.enrollment.progress()
        if not progress.get("active"):
            self.enrollment_banner.hide()
            return
        remaining = int(progress.get("remaining_seconds") or 0)
        hours, remainder = divmod(remaining, 3600)
        minutes = remainder // 60
        left = f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"
        state = "extended" if progress.get("extended") else f"{left} remaining"
        self.enrollment_banner.setText(
            f"Enrollment in progress for {progress['email']} — "
            f"day {progress['day_index']} of {progress['days']} ({state}). "
            "EMIT will train automatically when the period ends."
        )
        self.enrollment_banner.show()

    def refresh_users(self, select: str | None = None) -> None:
        self._refresh_enrollment_banner()
        current = select or self.user_combo.currentText()
        users = self.db.list_users()
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        self.user_combo.addItems(users)
        if users:
            index = self.user_combo.findText(current)
            self.user_combo.setCurrentIndex(index if index >= 0 else 0)
        self.user_combo.blockSignals(False)

        if not users:
            self.live = None
            self.continuous = None
            self._stop_monitoring()
            self.mode_stack.setCurrentIndex(MODE_EMPTY)
            self.verification_title.setText("Verification")
            self.session_chip.set_text("No profile", "neutral")
            self.attempts_chip.set_text("No samples", "neutral")
            if self.enrollment is not None and self.enrollment.active:
                self.empty_hint.setText(
                    "Enrollment is in progress. Your profile will appear here after "
                    "EMIT finishes training."
                )
                self.status_label.set_state(
                    "empty", "Enrollment in progress. Monitoring starts after training."
                )
            else:
                self.empty_hint.setText(
                    "Create a profile to start verifying your typing rhythm."
                )
                self.status_label.set_state("empty", "Set up a typing profile to begin verification.")
            self.password_edit.setEnabled(False)
            self.user_combo.setEnabled(False)
            self.typist_combo.setEnabled(False)
            self.tester_edit.setEnabled(False)
            self.tester_label.hide()
            self.tester_edit.hide()
            self.password_unlock_button.setVisible(False)
            self.monitor_unlock_button.setVisible(False)
            self.sparkline.set_data([], 0.0, 0.0)
            self._clear_assessment()
            return

        email = self.user_combo.currentText()
        if self.live is None or self.live.email != email:
            self._start_session(email)
        elif not self._monitoring and self.continuous is None and not self.live.history:
            self._show_idle()

    def _start_session(self, email: str) -> None:
        if not email:
            self.live = None
            self.continuous = None
            return
        profile = self.auth_service.get_profile(email)
        self.live = LiveSession(self.db, email)
        self.live.typist = self.typist_combo.currentText()
        self.live.tester = self.tester_edit.text().strip() or getpass.getuser()
        self.continuous = None
        self._stop_monitoring()

        if profile.get("mode") == "continuous":
            self.mode_stack.setCurrentIndex(MODE_CONTINUOUS)
            self.verification_title.setText("Continuous verification")
            self.session_chip.set_text("Continuous", "info")
        else:
            self.mode_stack.setCurrentIndex(MODE_PASSWORD)
            self.verification_title.setText("Password verification")
            self.session_chip.set_text("Password retype", "info")
        self._set_locked(False)
        self._clear_readings()
        self.password_edit.clear()
        self._show_idle()

    def _typist_changed(self, typist: str) -> None:
        show_tester = self.live is not None and typist == "Impostor"
        self.tester_edit.setVisible(show_tester)
        self.tester_label.setVisible(show_tester)
        if self.live is not None:
            self.live.typist = typist
        if self.continuous is not None:
            self.continuous.typist = typist

    # --------------------------------------------------- password mode
    def _attempt(self, events, bad: bool) -> None:
        if self.live is None or self.live.locked:
            return
        self.live.typist = self.typist_combo.currentText()
        self.live.tester = self.tester_edit.text().strip() or getpass.getuser()
        result, error = self.auth_service.evaluate(self.live.email, events, bad)
        if error is not None:
            self.password_message.setText(error)
            self.password_message.show()
            return
        final_tier = self.live.record(result)
        self.password_message.hide()
        self.attempts_chip.set_text(f"Attempts: {len(self.live.history)}", "neutral")
        self.sparkline.set_data(
            [entry["score"] for entry in self.live.history],
            result["t_susp"],
            result["t_lock"],
        )
        self._show_status(final_tier, result["score"])
        if self.live.locked:
            self._set_locked(True)

    # ------------------------------------------------- continuous mode
    def _toggle_monitoring(self) -> None:
        if self._monitoring:
            self._stop_monitoring()
            self.status_label.set_state("idle", "Test monitoring paused. Start monitoring to run another test.")
        else:
            self._start_monitoring()

    def _start_monitoring(self) -> None:
        if self.live is None:
            return
        profile = self.auth_service.get_profile(self.live.email)
        if profile.get("mode") != "continuous":
            return
        self.continuous = ContinuousSession(
            self.db,
            self.live.email,
            profile,
            typist=self.typist_combo.currentText(),
            tester=self.tester_edit.text().strip() or getpass.getuser(),
        )
        self._windowizer.reset()
        self._keys = 0
        self._monitoring = True
        self.monitor_button.setText("Stop monitoring")
        self._clear_readings()
        self.status_label.set_state("monitoring", "Type normally in any Windows app.")

    def _stop_monitoring(self) -> None:
        self._monitoring = False
        self.monitor_button.setText("Start monitoring")

    def _on_key(self, code: int, down: float, up: float) -> None:
        if not self._monitoring or self.continuous is None:
            return
        self._keys += 1
        self.monitor_keys_stat.set_value(f"{self._keys}")
        for window in self._windowizer.feed({"d": down, "u": up}):
            entry = self.continuous.feed_window(window)
            if entry is not None:
                self._after_window(entry)

    def _on_background_decision(self, entry: dict) -> None:
        session = self.monitor.session
        if self.continuous is not None or not self._background_for_current_profile() or session is None:
            return
        self._show_window_score(session, entry)

    def _on_background_locked(self, entry: dict) -> None:
        if self.continuous is None and self._background_for_current_profile():
            self.status_label.set_state(
                "locked", "Background monitoring stopped after unusual typing.", entry["score"]
            )

    def _background_for_current_profile(self) -> bool:
        return (
            self.live is not None and self.mode_stack.currentIndex() == MODE_CONTINUOUS
            and self.live.email == self.monitor.email
        )

    def _show_window_score(self, session: ContinuousSession, entry: dict) -> None:
        self.monitor_windows_stat.set_value(str(len(session.history)))
        self.attempts_chip.set_text(f"Windows: {len(session.history)}", "neutral")
        self.sparkline.set_data(
            [item["score"] for item in session.history],
            entry["t_susp"],
            entry["t_lock"],
        )
        self._show_status(entry["tier"], entry["score"], broadcast=session is self.continuous)

    def _after_window(self, entry: dict) -> None:
        self._show_window_score(self.continuous, entry)
        if self.continuous.locked:
            self._stop_monitoring()
            self._set_locked(True)
            if self.db.get_setting("lock_on_anomaly", "0") == "1":
                lock_workstation()

    # ------------------------------------------------------------ shared
    def _show_status(self, tier: str, value: float, *, broadcast: bool = True) -> None:
        kind, detail = {
            "NORMAL": ("ok", "The latest sample matches the enrolled typing profile."),
            "SUSPICIOUS": ("warn", "The latest sample differs from the enrolled typing profile."),
            "LOCKED": ("err", "The session reached the lock threshold."),
        }[tier]
        self.status_label.set_state(tier.lower(), detail, value)
        self.threat_chip.set_text(tier.title(), kind)
        self.assessment_hint.setText(detail)
        if broadcast:
            self.tierChanged.emit(tier)

    def _show_idle(self) -> None:
        background = self.monitor.session if self._background_for_current_profile() else None
        continuous = self.mode_stack.currentIndex() == MODE_CONTINUOUS
        if background is not None and (self.monitor.active or background.locked):
            if background.history:
                entry = background.history[-1]
                self._show_window_score(background, entry)
                if background.locked:
                    self._on_background_locked(entry)
            else:
                self.status_label.set_state("monitoring", "Background monitoring is waiting for a complete typing sample.")
        elif continuous:
            self._clear_readings()
            self.status_label.set_state("idle", "Start monitoring to capture and score typing samples.")
        else:
            self.status_label.set_state("idle", "Retype your practice password to record a sample.")

    def _clear_assessment(self) -> None:
        self.threat_chip.set_text("Pending", "neutral")
        self.assessment_hint.setText("A decision appears when EMIT has enough typing data to score.")

    def _clear_readings(self) -> None:
        self.password_message.hide()
        self.attempts_chip.set_text(
            "Windows: 0" if self.mode_stack.currentIndex() == MODE_CONTINUOUS else "Attempts: 0",
            "neutral",
        )
        self.monitor_keys_stat.set_value("0")
        self.monitor_windows_stat.set_value("0")
        self._clear_assessment()
        self.sparkline.set_data([], 0.0, 0.0)

    def _set_locked(self, locked: bool) -> None:
        self.password_edit.setEnabled(not locked)
        self.user_combo.setEnabled(not locked)
        self.typist_combo.setEnabled(not locked)
        self.tester_edit.setEnabled(not locked)
        self._typist_changed(self.typist_combo.currentText())
        self.monitor_button.setEnabled(not locked)
        self.password_unlock_button.setVisible(locked)
        self.monitor_unlock_button.setVisible(locked)
        if locked:
            self.password_edit.clear()

    def _unlock(self) -> None:
        if self.continuous is not None:
            self.continuous.reset()
        if self.live is not None:
            self.live.reset()
        self._stop_monitoring()
        self.continuous = None
        self._set_locked(False)
        self._clear_readings()
        self.tierChanged.emit("IDLE")
        self._show_idle()
