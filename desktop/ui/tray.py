from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from desktop.continuous import lock_workstation

COLORS = {
    "IDLE": "#64748b",
    "NORMAL": "#16a34a",
    "SUSPICIOUS": "#f97316",
    "LOCKED": "#dc2626",
}


def _icon(color: str) -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(5, 5, 22, 22)
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QObject):
    """Status dot in the notification area with pause and lock actions."""

    def __init__(self, window, capture, enrollment=None, parent=None):
        super().__init__(parent)
        self.window = window
        self.capture = capture
        self.enrollment = enrollment
        self._tier = "IDLE"
        self._enrollment_text: str | None = None
        self.tray = QSystemTrayIcon(_icon(COLORS["IDLE"]), self)
        self.tray.setToolTip("EMIT Desktop - idle")

        menu = QMenu()
        open_action = QAction("Open EMIT", menu)
        open_action.triggered.connect(self._open)
        menu.addAction(open_action)

        self.pause_action = QAction("Pause capture", menu)
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._toggle_pause)
        menu.addAction(self.pause_action)

        lock_action = QAction("Lock workstation", menu)
        lock_action.triggered.connect(lock_workstation)
        menu.addAction(lock_action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._activated)

    def show(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def hide(self) -> None:
        self.tray.hide()

    def set_tier(self, tier: str) -> None:
        self._tier = tier
        self.tray.setIcon(_icon(COLORS.get(tier, COLORS["IDLE"])))
        self._refresh_tooltip()

    def set_enrollment_progress(self, progress: dict) -> None:
        if progress and progress.get("active"):
            state = "extended" if progress.get("extended") else "collecting"
            self._enrollment_text = (
                f"training {state} - day {progress['day_index']} of {progress['days']}"
            )
            if self.pause_action.isChecked():
                self.pause_action.setChecked(False)
            self.pause_action.setEnabled(False)
        else:
            self._enrollment_text = None
            self.pause_action.setEnabled(True)
        self._refresh_tooltip()

    def _refresh_tooltip(self) -> None:
        if self._enrollment_text:
            self.tray.setToolTip(f"EMIT Desktop - {self._enrollment_text}")
        else:
            self.tray.setToolTip(f"EMIT Desktop - {self._tier.lower()}")

    def notify(self, title: str, message: str, tier: str = "NORMAL") -> None:
        """Show a Windows notification balloon. Works while the window is hidden."""
        if not QSystemTrayIcon.supportsMessages():
            return
        icon = {
            "NORMAL": QSystemTrayIcon.MessageIcon.Information,
            "SUSPICIOUS": QSystemTrayIcon.MessageIcon.Warning,
            "LOCKED": QSystemTrayIcon.MessageIcon.Critical,
        }.get(tier, QSystemTrayIcon.MessageIcon.Information)
        self.tray.showMessage(title, message, icon, 6000)

    def _open(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _toggle_pause(self, paused: bool) -> None:
        if paused and self.enrollment is not None and self.enrollment.active:
            self.pause_action.setChecked(False)
            return
        self.capture.paused = paused
        self.tray.setToolTip(
            "EMIT Desktop - paused" if paused else "EMIT Desktop - monitoring"
        )

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open()

    def _quit(self) -> None:
        if self.enrollment is not None and self.enrollment.active:
            answer = QMessageBox.question(
                None,
                "EMIT - training in progress",
                "A multi-day enrollment campaign is still collecting data. "
                "Quit anyway? Collection stops until EMIT starts again.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.window.allow_close = True
        self.capture.stop()
        QApplication.instance().quit()
