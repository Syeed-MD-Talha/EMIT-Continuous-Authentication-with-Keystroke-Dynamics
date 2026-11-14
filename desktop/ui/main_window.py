from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from desktop import __version__, paths
from desktop.auth import AuthService
from desktop.capture import CaptureService
from desktop.monitor import BackgroundMonitor
from desktop.storage import Database
from desktop.ui import icons, theme
from desktop.ui.enroll_page import EnrollPage
from desktop.ui.live_page import LivePage
from desktop.ui.settings_page import SettingsPage
from desktop.ui.widgets import Chip, IconTile, label, make_button, scrollable

NAV_ITEMS = (
    ("pulse", "Live session"),
    ("fingerprint", "Enroll profile"),
    ("sliders", "Settings"),
)


class MainWindow(QMainWindow):
    tierChanged = Signal(str)

    def __init__(
        self, db: Database, auth_service: AuthService, capture: CaptureService,
        monitor: BackgroundMonitor, parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self.auth_service = auth_service
        self.capture = capture
        self.monitor = monitor
        self.setWindowTitle("EMIT Desktop")
        self.setWindowIcon(QIcon(str(paths.project_root() / "desktop" / "assets" / "emit.ico")))
        self.resize(1210, 820)
        self.setMinimumSize(980, 640)

        root = QWidget()
        root.setObjectName("AppRoot")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        workspace = QVBoxLayout()
        workspace.setSpacing(0)
        workspace.addWidget(self._build_toolbar())

        self.enroll_page = EnrollPage(db, auth_service, capture, monitor)
        self.live_page = LivePage(db, auth_service, capture, monitor)
        self.settings_page = SettingsPage(db, monitor)
        self.stack = QStackedWidget()
        self.stack.setObjectName("Pages")
        for page in (self.live_page, self.enroll_page, self.settings_page):
            self.stack.addWidget(scrollable(page))
        workspace.addWidget(self.stack, 1)
        outer.addLayout(workspace, 1)
        self.setCentralWidget(root)

        self.enroll_page.profileSaved.connect(self._profile_saved)
        self.live_page.tierChanged.connect(self.tierChanged)
        self.live_page.enrollRequested.connect(lambda: self._select(1))
        theme.theme.changed.connect(self._refresh_theme)
        self._refresh_theme()
        self._select(0 if self.db.list_users() else 1)
        self.nav_buttons[self.stack.currentIndex()].setFocus(Qt.FocusReason.OtherFocusReason)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(51)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(25, 0, 25, 0)
        layout.setSpacing(10)
        layout.addWidget(label("Workspace", "Breadcrumb"))
        layout.addWidget(label("/", "Breadcrumb"))
        self.breadcrumb = label("", "BreadcrumbCurrent")
        layout.addWidget(self.breadcrumb)
        layout.addStretch(1)
        layout.addWidget(Chip("On-device", "info"))

        self.theme_button = make_button("", "ghost")
        self.theme_button.setToolTip("Switch between light and dark mode")
        self.theme_button.setIconSize(QSize(15, 15))
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)
        return bar

    def _toggle_theme(self) -> None:
        new_mode = (
            theme.MODE_DARK if theme.theme.mode == theme.MODE_LIGHT else theme.MODE_LIGHT
        )
        theme.theme.set_mode(new_mode)
        self.db.set_setting("ui_theme", new_mode)

    def _refresh_theme(self) -> None:
        is_dark = theme.theme.mode == theme.MODE_DARK
        self.theme_button.setText("Light mode" if is_dark else "Dark mode")
        self.theme_button.setIcon(
            icons.icon("sun" if is_dark else "moon", theme.colors()["text_muted"], 15)
        )

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 19, 14, 15)
        layout.setSpacing(5)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(IconTile("mark", 39, rail=True))
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("EMIT", "BrandTitle"))
        names.addWidget(label("Keystroke biometrics", "BrandSubtitle"))
        brand.addLayout(names)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(29)
        caption = label("WORKSPACE", "RailCaption")
        caption.setContentsMargins(9, 0, 0, 3)
        layout.addWidget(caption)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for index, (glyph, name) in enumerate(NAV_ITEMS):
            button = QPushButton(name)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(42)
            button.setIconSize(QSize(18, 18))
            button.setIcon(icons.icon(glyph, "#bacce2"))
            button.toggled.connect(
                lambda checked, b=button, i=glyph: b.setIcon(
                    icons.icon(i, "#a1efff" if checked else "#bacce2")
                )
            )
            button.clicked.connect(lambda checked=False, i=index: self._select(i))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        footer = QFrame()
        footer.setObjectName("RailFoot")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(10, 9, 10, 9)
        foot.addWidget(IconTile("shield", 27, rail=True))
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label("Local workspace", "RailFootTitle"))
        text.addWidget(label(f"EMIT Desktop  /  v{__version__}", "RailFootDetail"))
        foot.addLayout(text, 1)
        layout.addWidget(footer)
        return sidebar

    def _select(self, index: int) -> None:
        pages = (self.live_page, self.enroll_page, self.settings_page)
        previous = self.stack.currentIndex()
        if previous >= 0 and previous != index:
            pages[previous].on_hidden()
        pages[index].on_shown()
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)
        self.breadcrumb.setText(NAV_ITEMS[index][1])

    def _profile_saved(self, email: str) -> None:
        self.live_page.refresh_users(select=email)
        try:
            profile = self.auth_service.get_profile(email)
        except KeyError:
            profile = {}
        if profile.get("mode") == "continuous" and self.db.get_setting("monitor_on_start", "1") == "1":
            if self.monitor.set_profile(email):
                self.monitor.start()
        self._select(0)
