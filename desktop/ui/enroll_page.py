from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QProgressBar, QVBoxLayout, QWidget

from desktop import auth
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
from desktop.windowizer import Windowizer
from features import window_features

MODE_CONTINUOUS = 0
MODE_PASSWORD = 1

STATE_IDLE = "idle"
STATE_COLLECTING = "collecting"
STATE_TRAINING = "training"
STATE_READY = "ready"


class EnrollPage(QWidget):
    """Enroll a local profile from free typing or fixed password samples."""

    profileSaved = Signal(str)

    def __init__(self, db: Database, auth_service: AuthService, capture: CaptureService,
                 monitor, parent=None):
        super().__init__(parent)
        self.db = db
        self.auth_service = auth_service
        self.capture = capture
        self.monitor = monitor
        self.session = EnrollmentSession("")
        self.continuous_rows: list[list[float]] = []
        self._windowizer = Windowizer(
            auth.WINDOW_SIZE, auth.ENROLL_STRIDE, auth.IDLE_GAP
        )
        self._keys = 0
        self._collecting = False
        self._state = STATE_IDLE
        self._build_ui()
        self.capture.keyCaptured.connect(self._on_key)
        theme.theme.changed.connect(self._refresh_theme)

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
        self.target_stat = StatCard("Target keystrokes", str(auth.MIN_CONTINUOUS_KEYS))
        layout.addLayout(stat_row(self.keys_stat, self.windows_stat, self.target_stat))

        self.continuous_progress = QProgressBar()
        self.continuous_progress.setAccessibleName("Keystroke collection progress")
        self.continuous_progress.setRange(0, auth.MIN_CONTINUOUS_KEYS)
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
        steps = (
            (
                ("Start training", "EMIT begins collecting typing timings."),
                ("Type as you normally would", "Use any Windows app while EMIT collects samples."),
                ("Let EMIT build your profile",
                 f"Training starts automatically after at least {auth.MIN_CONTINUOUS_KEYS} "
                 f"keystrokes and {auth.MIN_CONTINUOUS_WINDOWS} complete sample windows."),
            ) if continuous else (
                ("Choose a practice password",
                 f"Use the same {auth.MIN_PASSWORD_LEN}–{auth.MAX_PASSWORD_LEN} characters for each sample."),
                ("Retype it and press Enter", "Type each sample from scratch. Pasting or correcting it invalidates the attempt."),
                ("Train your profile", f"Save your profile after at least {auth.MIN_ATTEMPTS} valid samples."),
            )
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
        self._update_state()

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

    def _set_status(self, text: str, kind: str = "info") -> None:
        target = self.continuous_status if self._is_continuous() else self.status_label
        target.setProperty("statusKind", kind)
        self._style_status(target, kind)
        target.setText(text)
        target.setVisible(bool(text))

    def _set_state(self, state: str) -> None:
        self._state = state
        self.training_chip.set_text(*{
            STATE_IDLE: ("Ready", "neutral"),
            STATE_COLLECTING: ("Collecting", "info"),
            STATE_TRAINING: ("Training", "info"),
            STATE_READY: ("Saved", "ok"),
        }[state])
        editable = state not in (STATE_COLLECTING, STATE_TRAINING)
        self.email_edit.setEnabled(editable)
        self.mode_combo.setEnabled(editable)
        if state == STATE_COLLECTING:
            self.train_button.setText("Stop training")
            self.train_button.setEnabled(True)
            self._set_status(
                f"Collecting data for training... {self._keys} / "
                f"{auth.MIN_CONTINUOUS_KEYS} keystrokes. Type anywhere in Windows.",
                "busy",
            )
        elif state == STATE_TRAINING:
            self.train_button.setText("Training...")
            self.train_button.setEnabled(False)
            self._set_status("Training the model on your typing rhythm...", "busy")
        elif state == STATE_READY:
            self.train_button.setText("Start training")
            self.train_button.setEnabled(True)
        else:
            self.train_button.setText("Start training")
            self.train_button.setEnabled(True)
            self._set_status("Start training, then type in any Windows app.")

    def _mode_changed(self, index: int) -> None:
        self.sample_stack.setCurrentIndex(index)
        self.guide_stack.setCurrentIndex(index)
        self.continuous_rows = []
        self._keys = 0
        self._windowizer.reset()
        self.cadence.clear()
        self._collecting = False
        self._set_state(STATE_IDLE)
        if index == MODE_CONTINUOUS:
            self._set_status("Start training, then type in any Windows app.")
        else:
            self.train_button.setText("Train profile")
            self._set_status("")
        self._update_state()

    def _email_changed(self) -> None:
        email = self._current_email()
        if email != self.session.email:
            self.session = EnrollmentSession(email)
            if self._is_continuous():
                self._set_state(STATE_IDLE)
            else:
                self._set_status("")
        self._update_state()

    def _on_key(self, code: int, down: float, up: float) -> None:
        if not self._collecting:
            return
        self._keys += 1
        self.cadence.record(max(0, up - down))
        for window in self._windowizer.feed({"d": down, "u": up}):
            self.continuous_rows.append(window_features(window))
        self._update_counters()
        if self._ready():
            self._begin_training()

    def _ready(self) -> bool:
        return (
            self._keys >= auth.MIN_CONTINUOUS_KEYS
            and len(self.continuous_rows) >= auth.MIN_CONTINUOUS_WINDOWS
        )

    def _update_counters(self) -> None:
        if not self._is_continuous():
            return
        self.keys_stat.set_value(f"{self._keys}")
        self.windows_stat.set_value(f"{len(self.continuous_rows)}")
        self.target_stat.set_value(f"{auth.MIN_CONTINUOUS_KEYS}")
        self.continuous_progress.setMaximum(auth.MIN_CONTINUOUS_KEYS)
        self.continuous_progress.setValue(min(self._keys, auth.MIN_CONTINUOUS_KEYS))
        self.reset_button.setEnabled(self._keys > 0 and self._state != STATE_TRAINING)
        if self._state == STATE_COLLECTING:
            self._set_status(
                f"Collecting data for training... {self._keys} / "
                f"{auth.MIN_CONTINUOUS_KEYS} keystrokes. Type anywhere in Windows.",
                "busy",
            )

    def _update_state(self) -> None:
        email = self._current_email()
        valid = auth.valid_email(email)
        taken = valid and self.db.profile_exists(email)
        continuous = self._is_continuous()

        self.password_edit.setEnabled(valid and not taken and not continuous)

        if continuous:
            if self._state in (STATE_IDLE, STATE_READY):
                self.train_button.setEnabled(valid and not taken)
            self._update_counters()
        else:
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
            self._set_status("Enter an email-style identifier, such as you@local.host.", "warning")
        elif taken and self._state != STATE_READY:
            self._set_status(
                f"'{email}' is already enrolled. Use another name.", "warning"
            )

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
            if self._collecting:
                self._stop_collecting("Training cancelled.")
                return
            email = self._current_email()
            if self.db.profile_exists(email):
                self._set_status(
                    f"'{email}' is already enrolled. Use another name.", "warning"
                )
                return
            self._start_collecting()
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

    def _start_collecting(self) -> None:
        self.continuous_rows = []
        self._keys = 0
        self._windowizer.reset()
        self.cadence.clear()
        self._collecting = True
        self._set_state(STATE_COLLECTING)
        self._update_counters()

    def _stop_collecting(self, message: str) -> None:
        self._collecting = False
        self._set_state(STATE_IDLE)
        self._set_status(message, "warning")
        self._update_state()

    def _begin_training(self) -> None:
        self._collecting = False
        self._set_state(STATE_TRAINING)
        self.reset_button.setEnabled(False)
        QTimer.singleShot(400, self._finish_continuous)

    def _finish_continuous(self) -> None:
        email = self._current_email()
        keys = self._keys
        self.auth_service.save_continuous_profile(
            email, self.continuous_rows, auth.WINDOW_SIZE
        )
        self._set_state(STATE_READY)
        self._set_status(
            f"Training finished on {keys} keystrokes. Profile saved for '{email}'.",
            "success",
        )
        self.profileSaved.emit(email)

    def _reset(self) -> None:
        self.session = EnrollmentSession(self._current_email())
        self.continuous_rows = []
        self._keys = 0
        self._windowizer.reset()
        self.cadence.clear()
        self._collecting = False
        self._set_state(STATE_IDLE)
        if not self._is_continuous():
            self.train_button.setText("Train profile")
        self.password_edit.clear()
        self._set_status("Reset.")
        self._update_state()
