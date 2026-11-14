from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup, QGridLayout, QHBoxLayout, QLineEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from desktop import autostart, response
from desktop.storage import Database
from desktop.ui import icons, theme
from desktop.ui.widgets import (
    Card, Chip, Divider, Inset, PageHeader, Switch, field_label, hint_label, label,
    make_button, page_layout,
)


RESPONSE_CHOICES = {
    response.ACTION_LOCK: ("Lock workstation", "Lock Windows and keep apps open.", "lock"),
    response.ACTION_NOTIFY: ("Notify only", "Show a notification without locking Windows.", "info"),
    response.ACTION_LOGOFF: ("Sign out", "End the Windows session.", "arrow"),
    response.ACTION_SHUTDOWN: ("Shut down", "Power off after a 30-second delay.", "power"),
    response.ACTION_RESTART: ("Restart", "Restart after a 30-second delay.", "pulse"),
}


class SettingsPage(QWidget):
    def __init__(self, db: Database, monitor=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.monitor = monitor
        self._build_ui()

    def _build_ui(self) -> None:
        layout = page_layout(self)
        layout.addWidget(PageHeader(
            "Security settings",
            "Choose how EMIT starts, monitors typing, and responds to unusual activity.",
            eyebrow="Preferences",
        ))

        columns = QHBoxLayout()
        columns.setSpacing(15)
        behavior = QVBoxLayout()
        behavior.setSpacing(15)
        behavior.addWidget(self._build_startup_card())
        behavior.addWidget(self._build_monitor_card())
        behavior.addWidget(self._build_storage_card())
        behavior.addStretch(1)
        columns.addLayout(behavior, 4)

        policies = QVBoxLayout()
        policies.setSpacing(15)
        policies.addWidget(self._build_response_card())
        policies.addWidget(self._build_privacy_card())
        policies.addStretch(1)
        columns.addLayout(policies, 5)
        layout.addLayout(columns)
        layout.addStretch(1)

        self.autostart_checkbox.toggled.connect(self._toggle_autostart)
        self.monitor_checkbox.toggled.connect(self._toggle_monitor)
        self._show_monitor_status()
        theme.theme.changed.connect(self._refresh_response_icons)

    def _build_startup_card(self) -> Card:
        self.autostart_checkbox = Switch("Launch EMIT at Windows sign-in")
        enabled = self.db.get_setting("autostart_enabled", "1") == "1"
        self.autostart_checkbox.setChecked(enabled)
        card = Card("Launch at sign-in", "power", self.autostart_checkbox)
        card.body.addWidget(hint_label("Start EMIT automatically when you sign in to Windows."))
        self.autostart_status = Chip()
        self._show_autostart_status(enabled)
        card.body.addWidget(self.autostart_status, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_monitor_card(self) -> Card:
        self.monitor_checkbox = Switch("Verify typing in the background")
        self.monitor_checkbox.setChecked(self.db.get_setting("monitor_on_start", "1") == "1")
        card = Card("Background monitoring", "pulse", self.monitor_checkbox)
        card.body.addWidget(hint_label(
            "Compare typing rhythms across Windows apps using an enrolled continuous profile."
        ))
        self.monitor_status = Chip()
        card.body.addWidget(self.monitor_status, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_response_card(self) -> Card:
        card = Card("Anomaly response", "shield")
        card.body.addWidget(hint_label(
            "Choose what EMIT does when background monitoring reaches the lock threshold."
        ))
        self.response_group = QButtonGroup(self)
        self._response_buttons = {}
        options = QGridLayout()
        options.setSpacing(8)
        options.setColumnStretch(0, 1)
        options.setColumnStretch(1, 1)
        current = self.db.get_setting("response_action", response.DEFAULT_ACTION)
        for index, (value, _) in enumerate(response.ACTIONS):
            name, description, _ = RESPONSE_CHOICES[value]
            button = make_button(name, "policy")
            button.setCheckable(True)
            button.setAccessibleDescription(description)
            button.setToolTip(description)
            button.setIconSize(QSize(16, 16))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.response_group.addButton(button)
            self._response_buttons[value] = button
            options.addWidget(button, index // 2, index % 2)
            button.clicked.connect(lambda checked=False, action=value: self._response_changed(action))
        card.body.addLayout(options)
        if current in self._response_buttons:
            self._response_buttons[current].setChecked(True)
        self._refresh_response_icons()
        self.response_detail = hint_label(RESPONSE_CHOICES.get(current, ("", "No action configured."))[1])
        card.body.addWidget(self.response_detail)
        note = Inset()
        note.body.addWidget(label("30-second grace period", "Subheading"))
        note.body.addWidget(hint_label(
            "For shutdown or restart, run shutdown /a in a terminal to cancel."
        ))
        card.body.addWidget(note)
        return card

    def _build_storage_card(self) -> Card:
        card = Card("Local database", "database", Chip("On this device", "ok"))
        card.body.addWidget(hint_label("EMIT stores profiles, timing features, and attempt history in SQLite."))
        path_edit = QLineEdit(str(self.db.path))
        path_edit.setReadOnly(True)
        path_edit.setToolTip(str(self.db.path))
        path_edit.setCursorPosition(0)
        path_edit.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        card.body.addWidget(field_label("Database file", path_edit))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(path_edit, 1)
        open_button = make_button("Open folder", "secondary")
        open_button.clicked.connect(self._open_folder)
        row.addWidget(open_button)
        card.body.addLayout(row)
        return card

    def _build_privacy_card(self) -> Card:
        card = Card("Privacy", "fingerprint")
        card.body.addWidget(label("Timing only", "Subheading"))
        card.body.addWidget(hint_label("EMIT saves typing timing features without saving the characters you type."))
        card.body.addWidget(Divider())
        card.body.addWidget(label("No desktop cloud sync", "Subheading"))
        card.body.addWidget(hint_label("Your desktop profiles and attempts stay in the local database."))
        return card

    def _response_changed(self, action: str) -> None:
        self.db.set_setting("response_action", action)
        self.response_detail.setText(RESPONSE_CHOICES[action][1])
        self._refresh_response_icons()

    def _refresh_response_icons(self) -> None:
        c = theme.colors()
        for action, button in self._response_buttons.items():
            button.setIcon(icons.icon(
                RESPONSE_CHOICES[action][2], c["accent" if button.isChecked() else "text_muted"], 16
            ))

    def _toggle_monitor(self, enabled: bool) -> None:
        self.db.set_setting("monitor_on_start", "1" if enabled else "0")
        if self.monitor is None:
            self._show_monitor_status()
            return
        if not enabled:
            self.monitor.stop()
        else:
            if self.monitor.session is None:
                for email in self.db.list_users():
                    try:
                        profile = self.monitor.auth_service.get_profile(email)
                    except KeyError:
                        continue
                    if profile.get("mode") == "continuous" and self.monitor.set_profile(email):
                        break
            self.monitor.start()
        self._show_monitor_status()

    def _show_monitor_status(self) -> None:
        if not self.monitor_checkbox.isChecked():
            self.monitor_status.set_text("Off", "neutral")
        elif self.monitor is not None and self.monitor.active:
            self.monitor_status.set_text("Monitoring", "ok")
        elif self.monitor is not None and self.monitor.session is not None:
            self.monitor_status.set_text("Standby", "neutral")
        else:
            self.monitor_status.set_text("Needs a continuous profile", "info")

    def _show_autostart_status(self, enabled: bool) -> None:
        self.autostart_status.set_text("Enabled" if enabled else "Off", "ok" if enabled else "neutral")

    def _toggle_autostart(self, enabled: bool) -> None:
        ok = autostart.enable() if enabled else autostart.disable()
        if not ok:
            self.autostart_checkbox.blockSignals(True)
            self.autostart_checkbox.setChecked(not enabled)
            self.autostart_checkbox.blockSignals(False)
            self.autostart_status.set_text("Could not update Windows startup", "warn")
            return
        self.db.set_setting("autostart_enabled", "1" if enabled else "0")
        self._show_autostart_status(enabled)

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.db.path.parent)))

    def on_shown(self) -> None:
        self._show_monitor_status()

    def on_hidden(self) -> None:
        pass
