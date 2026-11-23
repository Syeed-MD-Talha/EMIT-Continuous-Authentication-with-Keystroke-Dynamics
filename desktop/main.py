import getpass
import hashlib
import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from desktop import auth, autostart, paths, storage
from desktop.auth import AuthService
from desktop.capture import CaptureService
from desktop.enrollment import EnrollmentService
from desktop.monitor import BackgroundMonitor
from desktop.ui.main_window import MainWindow
from desktop.ui import theme
from desktop.ui.theme import apply_theme
from desktop.ui.tray import TrayIcon

SERVER_NAME = "EMITDesktop-" + hashlib.sha1(getpass.getuser().encode("utf-8")).hexdigest()[:12]


def _notify_existing() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True
    return False


def _handle_connection(server: QLocalServer, callback) -> None:
    while server.hasPendingConnections():
        connection = server.nextPendingConnection()
        connection.disconnected.connect(connection.deleteLater)
        callback()


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("EMITDesktop")
    app.setApplicationDisplayName("EMIT Desktop")
    app.setOrganizationName("EMIT")
    apply_theme(app, theme.MODE_LIGHT)

    if _notify_existing():
        return 0

    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    db = storage.Database(paths.db_path())
    enabled = db.get_setting("autostart_enabled", "1") == "1"
    autostart.sync(enabled)

    saved_mode = db.get_setting("ui_theme", theme.MODE_LIGHT)
    theme.theme.set_mode(saved_mode)

    capture = CaptureService(
        window=auth.WINDOW_SIZE, stride=auth.MONITOR_STRIDE, idle_gap=auth.IDLE_GAP
    )
    capture.start()

    auth_service = AuthService(db)
    enrollment = EnrollmentService(db, auth_service, capture)
    monitor = BackgroundMonitor(db, auth_service, capture)

    window = MainWindow(db, auth_service, capture, monitor, enrollment)
    tray = TrayIcon(window, capture, enrollment)
    tray.show()
    window.tierChanged.connect(tray.set_tier)

    def on_decision(entry: dict) -> None:
        tier = entry["tier"]
        tray.set_tier(tier)
        window.tierChanged.emit(tier)
        if tier == "NORMAL":
            tray.notify(
                "EMIT - verified",
                f"Typing matches your profile (score {entry['score']:.2f}).",
                tier,
            )
        elif tier == "SUSPICIOUS":
            tray.notify(
                "EMIT - suspicious typing",
                f"Typing does not match your profile (score {entry['score']:.2f}).",
                tier,
            )

    def on_locked(entry: dict) -> None:
        tray.set_tier("LOCKED")
        window.tierChanged.emit("LOCKED")
        tray.notify(
            "EMIT - session locked",
            "Possible hijack detected. Monitoring stopped.",
            "LOCKED",
        )

    def on_enrollment_completed(email: str) -> None:
        tray.notify(
            "EMIT - training complete",
            f"Your typing profile for {email} is ready.",
            "NORMAL",
        )

    def on_enrollment_extended(progress: dict) -> None:
        tray.notify(
            "EMIT - training extended",
            "Not enough typing data yet. Keep typing; EMIT will train automatically.",
            "SUSPICIOUS",
        )

    monitor.decision.connect(on_decision)
    monitor.locked.connect(on_locked)
    enrollment.progressChanged.connect(tray.set_enrollment_progress)
    enrollment.periodCompleted.connect(on_enrollment_completed)
    enrollment.periodExtended.connect(on_enrollment_extended)
    enrollment.periodFailed.connect(lambda message: tray.notify(
        "EMIT - training failed", message, "SUSPICIOUS"
    ))
    window.hiddenToTray.connect(lambda: tray.notify(
        "EMIT - still running",
        "EMIT continues collecting typing data in the background. "
        "Quit from the tray menu to stop it.",
        "NORMAL",
    ))

    # Resume an active campaign (and train it if the deadline already passed).
    enrollment.resume()
    window.live_page.refresh_users()

    # Resume monitoring automatically for the most recent continuous profile.
    if (
        not enrollment.active
        and not monitor.active
        and db.get_setting("monitor_on_start", "1") == "1"
    ):
        for email in db.list_users():
            try:
                profile = auth_service.get_profile(email)
            except KeyError:
                continue
            if profile.get("mode") == "continuous":
                if monitor.set_profile(email):
                    monitor.start()
                break
        window.live_page.refresh_users()

    campaign_timer = QTimer()
    campaign_timer.setInterval(auth.CAMPAIGN_TICK_SECONDS * 1000)
    campaign_timer.timeout.connect(enrollment.tick)
    campaign_timer.start()

    def show_window() -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()

    server.newConnection.connect(lambda: _handle_connection(server, show_window))
    show_window()

    exit_code = app.exec()
    enrollment.flush()
    capture.stop()
    tray.hide()
    db.close()
    server.close()
    return exit_code
