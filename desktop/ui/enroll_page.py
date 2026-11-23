from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QProgressBar, QVBoxLayout, QWidget

from desktop import auth, autostart
from desktop.auth import AuthService, EnrollmentSession
from desktop.capture import CaptureService
from desktop.storage import Database
from desktop.ui import theme
from desktop.ui.keystroke_edit import KeystrokeEdit
from desktop.ui.sparkline import CadencePlot
from desktop.ui.widgets import (
    Card, Chip, CurrentPanelStack, Divider, Inset, PageHeader, Select, StatCard,
    field_label, hint_label, label, make_button, mono_label, page_layout, stat_row,
)

MODE_CONTINUOUS = 0
MODE_PASSWORD = 1

STATE_IDLE = "idle"
STATE_COLLECTING = "collecting"
STATE_TRAINING = "training"
STATE_READY = "ready"


def _format_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "deadline passed"
    hours, remainder = divmod(int(seconds), 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


class EnrollPage(QWidget):
    """Enroll a local profile from multi-day free typing or fixed passwords."""

    profileSaved = Signal(str)

    def __init__(self, db: Database, auth_service: AuthService, capture: CaptureService,
                 monitor, enrollment=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.auth_service = auth_service
        self.capture = capture
        self.monitor = monitor
        self.enrollment = enrollment
        self.session = EnrollmentSession("")
        self._state = STATE_IDLE
        self._progress: dict | None = None
        self._build_ui()
        self.capture.keyCaptured.connect(self._on_key)
        theme.theme.changed.connect(self._refresh_theme)
        if enrollment is not None:
            enrollment.progressChanged.connect(self._on_progress)
            enrollment.periodCompleted.connect(self._on_completed)
            enrollment.periodExtended.connect(self._on_extended)
            enrollment.periodCancelled.connect(self._on_cancelled)
            enrollment.periodFailed.connect(self._on_failed)
        self._sync_campaign()

    def _build_ui(self) -> None:
        layout = page_layout(self)
        layout.addWidget(PageHeader(
            "Enroll a profile",
            "Teach EMIT your typing rhythm to create a biometric profile on this device.",
            eyebrow="Biometric setup",
        ))

        columns = QHBoxLayout()
        columns.setSpacing(15)
        left = QVBoxLayout()
        left.setSpacing(15)
        left.addWidget(self._build_identity_card())
        left.addWidget(self._build_progress_card())
        left.addStretch(1)
        columns.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(15)
        self.guide_stack = CurrentPanelStack()
        self.guide_stack.addWidget(self._build_guide_card(continuous=True))
        self.guide_stack.addWidget(self._build_guide_card(continuous=False))
        right.addWidget(self.guide_stack)
        right.addWidget(self._build_signature_card())
        right.addStretch(1)
        columns.addLayout(right, 2)
        layout.addLayout(columns)
        layout.addStretch(1)

        self.email_edit.textChanged.connect(self._email_changed)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.password_edit.attemptReady.connect(self._attempt)
        self.train_button.clicked.connect(self._train)
        self.reset_button.clicked.connect(self._reset)
        self._mode_changed(MODE_CONTINUOUS)

    def _build_identity_card(self) -> Card:
        card = Card("Profile identity", "user")
        self.email_edit = QLineEdit()
        self.email_edit.setMaxLength(auth.MAX_EMAIL_LEN)
        self.email_edit.setPlaceholderText(auth.default_email())
        card.body.addWidget(field_label("Profile identifier", self.email_edit))
        card.body.addWidget(self.email_edit)
        card.body.addWidget(hint_label(
            "Use an email-style name or leave this blank to use your Windows account."
        ))

        self.mode_combo = Select()
        self.mode_combo.addItems(["Continuous · Free typing", "Password retype"])
        self.mode_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.mode_combo.setMinimumContentsLength(18)
        card.body.addWidget(field_label("Enrollment mode", self.mode_combo))
        card.body.addWidget(self.mode_combo)

        self.period_combo = Select()
        for days, name in auth.TRAINING_PERIOD_CHOICES.items():
            self.period_combo.addItem(name, days)
        try:
            saved_days = int(
                self.db.get_setting("enrollment_days", str(auth.DEFAULT_TRAINING_DAYS))
            )
        except (TypeError, ValueError):
            saved_days = auth.DEFAULT_TRAINING_DAYS
        index = self.period_combo.findData(saved_days)
        self.period_combo.setCurrentIndex(index if index >= 0 else 0)
        self.period_label = field_label("Training period", self.period_combo)
        card.body.addWidget(self.period_label)
        card.body.addWidget(self.period_combo)
        card.body.addWidget(hint_label(
            "EMIT collects timing features in the background and trains when the period ends."
        ))
        return card

    def _build_progress_card(self) -> Card:
        self.training_chip = Chip("Ready")
        card = Card("Calibration", "chart", self.training_chip)
        self.sample_stack = CurrentPanelStack()
        self.sample_stack.addWidget(self._build_continuous_panel())
        self.sample_stack.addWidget(self._build_password_panel())
        card.body.addWidget(self.sample_stack)

        actions = QHBoxLayout()
        actions.setSpacing(9)
        self.reset_button = make_button("Reset samples", "secondary")
        self.train_button = make_button("Start training")
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        actions.addWidget(self.train_button)
        card.body.addLayout(actions)
        return card

    def _build_continuous_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.keys_stat = StatCard("Keystrokes")
        self.windows_stat = StatCard("Sample windows")
        self.days_stat = StatCard("Days with data")
        self.period_stat = StatCard("Training day")
        layout.addLayout(stat_row(
            self.keys_stat, self.windows_stat, self.days_stat, self.period_stat
        ))

        self.continuous_progress = QProgressBar()
        self.continuous_progress.setAccessibleName("Keystroke collection progress")
        self.continuous_progress.setRange(0, 1)
        self.continuous_progress.setTextVisible(False)
        layout.addWidget(self.continuous_progress)
        self.continuous_status = hint_label("")
        layout.addWidget(self.continuous_status)

        row = QHBoxLayout()
        row.addWidget(field_label("Key hold time"))
        row.addStretch(1)
        row.addWidget(mono_label("Last 30 keystrokes"))
        layout.addLayout(row)
        self.cadence = CadencePlot()
        layout.addWidget(self.cadence)
        return panel

    def _build_password_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.password_edit = KeystrokeEdit()
        layout.addWidget(field_label("Typing sample", self.password_edit))
        layout.addWidget(self.password_edit)
        self.progress = QProgressBar()
        self.progress.setAccessibleName("Recorded password attempts")
        self.progress.setRange(0, auth.MAX_ATTEMPTS)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.progress_label = hint_label("")
        layout.addWidget(self.progress_label)
        self.status_label = hint_label("")
        layout.addWidget(self.status_label)
        return panel

    def _build_signature_card(self) -> Card:
        card = Card("What EMIT measures", "fingerprint", Chip("Local only", "ok"))
        card.body.addWidget(hint_label("Your profile describes timing patterns. Typed characters aren’t saved."))
        well = Inset()
        for index, (title, description) in enumerate((
            ("Key hold", "How long you press each key."),
            ("Flight time", "The gap between releasing one key and pressing the next."),
            ("Digraph timing", "The timing of two consecutive key presses."),
        )):
            if index:
                well.body.addWidget(Divider())
            well.body.addWidget(label(title, "Subheading"))
            well.body.addWidget(hint_label(description))
        card.body.addWidget(well)
        return card

    def _build_guide_card(self, continuous: bool) -> Card:
        card = Card("How to enroll", "steps")
        if continuous:
            one = auth.campaign_requirements(1)
            three = auth.campaign_requirements(3)
            steps = (
                ("Choose a training period",
                 "Pick 1 day or 3 days, then press Start training."),
                ("Type normally across the period",
                 "Use any Windows app. EMIT collects timing features in the background."),
                ("EMIT trains automatically",
                 f"1 day needs {one['min_keys']} keystrokes and {one['min_windows']} windows. "
                 f"3 days needs {three['min_keys']} keystrokes, {three['min_windows']} windows, "
                 f"and {three['min_days']} days with data. Low-data campaigns extend automatically."),
            )
        else:
            steps = (
                ("Choose a practice password",
                 f"Use the same {auth.MIN_PASSWORD_LEN}–{auth.MAX_PASSWORD_LEN} characters for each sample."),
                ("Retype it and press Enter",
                 "Type each sample from scratch. Pasting or correcting it invalidates the attempt."),
                ("Train your profile",
                 f"Save your profile after at least {auth.MIN_ATTEMPTS} valid samples."),
            )
        for number, (title, body) in enumerate(steps, 1):
            row = QHBoxLayout()
            row.setSpacing(9)
            badge = label(f"{number:02}", "Step")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(29, 27)
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            copy = QVBoxLayout()
            copy.setSpacing(2)
            copy.addWidget(label(title, "Subheading", wrap=True))
            copy.addWidget(hint_label(body))
            row.addLayout(copy, 1)
            card.body.addLayout(row)
        return card

    def on_shown(self) -> None:
        self._sync_campaign()

    def on_hidden(self) -> None:
        pass

    def _refresh_theme(self) -> None:
        for target in (self.continuous_status, self.status_label):
            self._style_status(target, target.property("statusKind") or "info")
        self.cadence.update()

    @staticmethod
    def _style_status(target, kind: str) -> None:
        c = theme.colors()
        token = {"info": "text_muted", "success": "success", "warning": "warning", "busy": "accent"}
        target.setStyleSheet(f"color: {c[token[kind]]};")

    def _current_email(self) -> str:
        raw = auth.normalize_email(self.email_edit.text())
        return raw or auth.default_email()

    def _is_continuous(self) -> bool:
        return self.mode_combo.currentIndex() == MODE_CONTINUOUS

    def _selected_days(self) -> int:
        value = self.period_combo.currentData()
        return int(value) if value is not None else auth.DEFAULT_TRAINING_DAYS

    def _set_status(self, text: str, kind: str = "info") -> None:
        target = self.continuous_status if self._is_continuous() else self.status_label
        target.setProperty("statusKind", kind)
        self._style_status(target, kind)
        target.setText(text)
        target.setVisible(bool(text))

    # ------------------------------------------------------------ campaign sync
    def _sync_campaign(self) -> None:
        if self.enrollment is not None and self.enrollment.active:
            self._on_progress(self.enrollment.progress())
        else:
            if self._state == STATE_COLLECTING:
                self._state = STATE_IDLE
            self._progress = None
            self._update_state()

    def _on_progress(self, progress: dict) -> None:
        if progress and progress.get("active"):
            self._progress = progress
            self._state = STATE_COLLECTING
            self._update_state()
            self._set_status(
                self._campaign_status(progress),
                "warning" if progress.get("extended") else "busy",
            )
        else:
            self._progress = None
            if self._state == STATE_COLLECTING:
                self._state = STATE_IDLE
            self._update_state()

    def _on_extended(self, progress: dict) -> None:
        self._on_progress(progress)
        self._set_status(self._campaign_status(progress), "warning")

    def _on_completed(self, email: str) -> None:
        self._progress = None
        self._state = STATE_READY
        self._update_state()
        self._set_status(f"Training finished. Profile saved for '{email}'.", "success")
        self.profileSaved.emit(email)

    def _on_cancelled(self) -> None:
        self._progress = None
        self._state = STATE_IDLE
        self._update_state()
        self._set_status("Training cancelled. Samples deleted.", "warning")

    def _on_failed(self, message: str) -> None:
        self._update_state()
        self._set_status(message, "warning")

    @staticmethod
    def _campaign_status(progress: dict) -> str:
        if progress.get("extended"):
            return (
                "Training extended: "
                f"{progress['keys']}/{progress['min_keys']} keystrokes, "
                f"{progress['windows']}/{progress['min_windows']} windows, "
                f"{progress['days_with_data']}/{progress['min_days']} days. Keep typing."
            )
        if progress.get("deadline_passed"):
            return "Deadline reached. Waiting for enough typing data..."
        return (
            f"Day {progress['day_index']} of {progress['days']} · "
            f"{_format_remaining(progress['remaining_seconds'])} remaining. "
            "Type normally in any Windows app."
        )

    # ------------------------------------------------------------ state/UI sync
    def _update_state(self) -> None:
        email = self._current_email()
        valid = auth.valid_email(email)
        taken = valid and self.db.profile_exists(email)
        continuous = self._is_continuous()
        active = bool(self.enrollment and self.enrollment.active)

        editable = not active and self._state != STATE_TRAINING
        self.email_edit.setEnabled(editable)
        self.mode_combo.setEnabled(editable)
        self.period_combo.setEnabled(editable)
        self.period_label.setVisible(continuous)
        self.period_combo.setVisible(continuous)

        self.password_edit.setEnabled(valid and not taken and not continuous and not active)

        if continuous:
            if active:
                self.training_chip.set_text(
                    "Extended" if (self._progress or {}).get("extended") else "Collecting",
                    "warn" if (self._progress or {}).get("extended") else "info",
                )
                self.train_button.setText("Stop training")
                self.train_button.setEnabled(True)
                self.reset_button.setEnabled(True)
                self._update_counters(self._progress)
            else:
                self.training_chip.set_text(
                    "Saved" if self._state == STATE_READY else "Ready",
                    "ok" if self._state == STATE_READY else "neutral",
                )
                self.train_button.setText("Start training")
                self.train_button.setEnabled(valid and not taken)
                self.reset_button.setEnabled(False)
                self._update_counters(None)
            if not active:
                if not valid:
                    self._set_status(
                        "Enter an email-style identifier, such as you@local.host.",
                        "warning",
                    )
                elif taken and self._state != STATE_READY:
                    self._set_status(
                        f"'{email}' is already enrolled. Use another name.", "warning"
                    )
        else:
            self.training_chip.set_text("Ready", "neutral")
            self.train_button.setText("Train profile")
            self.train_button.setEnabled(
                self.session.can_train() and valid and not taken
            )
            self.reset_button.setEnabled(bool(self.session.rows))
            count = len(self.session.rows)
            self.progress.setValue(count)
            self.progress_label.setText(
                f"{count} of {auth.MAX_ATTEMPTS} samples · Minimum {auth.MIN_ATTEMPTS} to train"
            )
            if not valid:
                self._set_status(
                    "Enter an email-style identifier, such as you@local.host.",
                    "warning",
                )
            elif taken:
                self._set_status(
                    f"'{email}' is already enrolled. Use another name.", "warning"
                )

    def _update_counters(self, progress: dict | None) -> None:
        if progress:
            keys = int(progress["keys"])
            min_keys = int(progress["min_keys"])
            windows = int(progress["windows"])
            min_windows = int(progress["min_windows"])
            self.keys_stat.set_value(f"{keys} / {min_keys}")
            self.windows_stat.set_value(f"{windows} / {min_windows}")
            self.days_stat.set_value(
                f"{progress['days_with_data']} / {progress['min_days']}"
            )
            self.period_stat.set_value(
                f"{progress['day_index']} / {progress['days']}"
            )
            self.continuous_progress.setMaximum(max(1, min_keys))
            self.continuous_progress.setValue(min(keys, min_keys))
        else:
            self.keys_stat.set_value("0")
            self.windows_stat.set_value("0")
            self.days_stat.set_value("0")
            self.period_stat.set_value("—")
            self.continuous_progress.setMaximum(1)
            self.continuous_progress.setValue(0)

    def _email_changed(self) -> None:
        email = self._current_email()
        if email != self.session.email:
            self.session = EnrollmentSession(email)
        if not (self.enrollment is not None and self.enrollment.active):
            self._state = STATE_IDLE
        self._update_state()

    def _mode_changed(self, index: int) -> None:
        self.sample_stack.setCurrentIndex(index)
        self.guide_stack.setCurrentIndex(index)
        self.period_label.setVisible(index == MODE_CONTINUOUS)
        self.period_combo.setVisible(index == MODE_CONTINUOUS)
        self.cadence.clear()
        active = bool(self.enrollment and self.enrollment.active)
        if not active:
            self._state = STATE_IDLE
        self._update_state()
        if index == MODE_CONTINUOUS:
            if not active:
                self._set_status("Choose a training period, then start training.")
        else:
            self._set_status("")

    # ------------------------------------------------------------ collection
    def _on_key(self, code: int, down: float, up: float) -> None:
        if self.enrollment is not None and self.enrollment.active:
            self.cadence.record(max(0, up - down))

    # ------------------------------------------------------------ actions
    def _attempt(self, events, bad: bool) -> None:
        email = self._current_email()
        if self.db.profile_exists(email):
            self._set_status(
                f"'{email}' is already enrolled. Use another name.", "warning"
            )
            return
        if self.session.email != email:
            self.session = EnrollmentSession(email)
        ok, error = self.session.add_attempt(events, bad)
        if ok:
            self._set_status(f"Attempt {len(self.session.rows)} recorded.", "success")
        else:
            self._set_status(error or "Attempt ignored.", "warning")
        self._update_state()

    def _train(self) -> None:
        if self._is_continuous():
            self._train_campaign()
            return

        email = self._current_email()
        if self.db.profile_exists(email):
            self._set_status(
                f"'{email}' is already enrolled. Use another name.", "warning"
            )
            return
        if not self.session.can_train():
            self._set_status(
                f"Record at least {auth.MIN_ATTEMPTS} valid attempts before training.",
                "warning",
            )
            return
        self.auth_service.save_profile(email, self.session.rows, self.session.password_len)
        self._reset()
        self._set_status(f"Profile saved for '{email}'. Live session is ready.", "success")
        self.profileSaved.emit(email)

    def _train_campaign(self) -> None:
        if self.enrollment is None:
            self._set_status("Enrollment service is unavailable.", "warning")
            return
        if self.enrollment.active:
            self.enrollment.cancel()
            return

        email = self._current_email()
        days = self._selected_days()
        ok, error = self.enrollment.start(email, days)
        if not ok:
            self._set_status(error or "Could not start training.", "warning")
            self._update_state()
            return
        self.db.set_setting("enrollment_days", str(days))
        if self.monitor is not None:
            self.monitor.stop()
        progress = self.enrollment.progress()
        self._on_progress(progress)
        hint = (
            ""
            if autostart.is_enabled()
            else " Enable launch at sign-in in Settings so collection survives a restart."
        )
        self._set_status(
            f"Training started. {self._campaign_status(progress)}{hint}", "success"
        )

    def _reset(self) -> None:
        if self._is_continuous():
            if self.enrollment is not None and self.enrollment.active:
                self.enrollment.cancel()
                self.cadence.clear()
                return
            self.cadence.clear()
            self._state = STATE_IDLE
            self._update_state()
            self._set_status("Reset.")
            return

        self.session = EnrollmentSession(self._current_email())
        self.password_edit.clear()
        self._update_state()
        self._set_status("Reset.")
