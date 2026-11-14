"""Light and dark design tokens for the native EMIT workspace."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

MODE_LIGHT = "light"
MODE_DARK = "dark"

BODY_FONTS = ("Geist", "Inter", "Segoe UI Variable Text", "Segoe UI")
MONO_FONTS = ("JetBrains Mono", "Cascadia Mono", "Consolas", "Courier New")

LIGHT = {
    "base": "#f3f6fa", "raised": "#ffffff", "inset": "#f5f8fc", "hover": "#edf3fa",
    "border": "#dbe5ee", "outline": "#c7d6e4", "text": "#10223a",
    "text_body": "#344963", "text_muted": "#52677e", "text_faint": "#586f88",
    "primary": "#006fa8", "primary_dim": "#005d8e", "on_primary": "#ffffff",
    "accent": "#087cae", "tint": "#e7f4fd", "tint_border": "#b9deef",
    "hero_a": "#e8f6fd", "hero_b": "#f4f7ff", "hero_border": "#c8e2ef",
    "input": "#fbfdff", "track": "#dce7f0",
    "ok_bg": "#e6f6ef", "ok_fg": "#136951",
    "warn_bg": "#fef3df", "warn_fg": "#8d4809",
    "err_bg": "#fdebee", "err_fg": "#b12744",
    "neutral_bg": "#edf2f8", "neutral_fg": "#4e637b",
    "chart_bg": "#f6f9fd", "chart_grid": "#d3e0ec", "chart_line": "#087eae",
    "success": "#136951", "warning": "#8d4809",
}

DARK = {
    "base": "#101624", "raised": "#171f2e", "inset": "#111927", "hover": "#242e40",
    "border": "#29364a", "outline": "#3e4e67", "text": "#ecf4ff",
    "text_body": "#c4d2e5", "text_muted": "#a2b3c9", "text_faint": "#94aac1",
    "primary": "#54d8ef", "primary_dim": "#91edfa", "on_primary": "#092234",
    "accent": "#6fddf3", "tint": "#172f43", "tint_border": "#2b566a",
    "hero_a": "#153247", "hero_b": "#1b233c", "hero_border": "#2c4b61",
    "input": "#121a29", "track": "#28374c",
    "ok_bg": "#143a34", "ok_fg": "#81e7bb",
    "warn_bg": "#403120", "warn_fg": "#ffd088",
    "err_bg": "#412536", "err_fg": "#ff9db3",
    "neutral_bg": "#242e40", "neutral_fg": "#b3c3d8",
    "chart_bg": "#111928", "chart_grid": "#293950", "chart_line": "#61e0f5",
    "success": "#81e7bb", "warning": "#ffd088",
}

PALETTES = {MODE_LIGHT: LIGHT, MODE_DARK: DARK}


class ThemeManager(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._mode = MODE_LIGHT

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def colors(self) -> dict:
        return PALETTES[self._mode]

    def set_mode(self, mode: str) -> None:
        if mode in PALETTES and mode != self._mode:
            self._mode = mode
            if (app := QApplication.instance()) is not None:
                _apply_palette(app, self.colors)
            self.changed.emit(mode)


theme = ThemeManager()


def colors() -> dict:
    return theme.colors


def _family(candidates) -> str:
    if QApplication.instance() is not None:
        available = QFontDatabase.families()
        for name in candidates:
            if name in available:
                return name
    return candidates[-1]


def mono_font(size: int = 11, weight: int = 500) -> QFont:
    font = QFont(_family(MONO_FONTS))
    font.setPixelSize(size)
    font.setWeight(QFont.Weight(weight))
    return font


def build_stylesheet(c: dict) -> str:
    c = {**c, "font": _family(BODY_FONTS), "mono": _family(MONO_FONTS)}
    return """
QWidget { color: %(text)s; font-family: "%(font)s"; font-size: 14px; }
QMainWindow, #AppRoot, #Page, #Pages { background: %(base)s; }
QDialog, QMenu { background: %(raised)s; }

QFrame#Sidebar { background: #111d30; border-right: 1px solid #21334a; }
QLabel#BrandTitle { color: #f5faff; font-size: 19px; font-weight: 700; }
QLabel#BrandSubtitle { color: #a3b6ce; font-size: 11px; }
QLabel#RailCaption { color: #9bafc8; font-size: 10px; font-weight: 700; }
QFrame#RailFoot { background: #18283d; border: 1px solid #294059; border-radius: 10px; }
QLabel#RailFootTitle { color: #dbeafb; font-size: 12px; font-weight: 600; }
QLabel#RailFootDetail { color: #a3b6ce; font-size: 11px; }
QPushButton#NavButton {
    color: #bacce2; background: transparent; text-align: left;
    border: 1px solid transparent; border-radius: 8px; padding: 0 10px;
    font-weight: 600;
}
QPushButton#NavButton:hover { background: #1a2a41; color: #f4faff; }
QPushButton#NavButton:checked { background: #203b55; border-color: #2d4e68; color: #a1efff; }
QPushButton#NavButton:focus { border-color: #60c9e0; }

QFrame#Toolbar { background: %(raised)s; border-bottom: 1px solid %(border)s; }
QLabel#Breadcrumb { color: %(text_muted)s; font-size: 12px; }
QLabel#BreadcrumbCurrent { font-size: 12px; font-weight: 650; }

QLabel#PageTitle { font-size: 34px; font-weight: 700; }
QLabel#PageSubtitle { color: %(text_muted)s; font-size: 14px; }
QLabel#Eyebrow { color: %(accent)s; font-size: 11px; font-weight: 700; }
QLabel#SectionTitle { font-size: 17px; font-weight: 650; }
QLabel#Subheading { font-size: 13px; font-weight: 650; }
QLabel#FieldLabel { color: %(text_body)s; font-size: 12px; font-weight: 650; }
QLabel#Hint { color: %(text_muted)s; font-size: 13px; }
QLabel#Mono { color: %(text_faint)s; font-family: "%(mono)s"; font-size: 11px; }
QLabel#StatValue { font-size: 23px; font-weight: 700; }
QLabel#StatLabel { color: %(text_muted)s; font-size: 11px; font-weight: 600; }
QLabel#HeroLabel { color: %(accent)s; font-size: 11px; font-weight: 700; }
QLabel#HeroTitle { font-size: 22px; font-weight: 700; }
QLabel#HeroScore { font-family: "%(mono)s"; font-size: 25px; font-weight: 700; }

QFrame#Card { background: %(raised)s; border: 1px solid %(border)s; border-radius: 12px; }
QFrame#Inset, QFrame#StatCard {
    background: %(inset)s; border: 1px solid %(border)s; border-radius: 8px;
}
QFrame#Hero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 %(hero_a)s, stop:1 %(hero_b)s);
    border: 1px solid %(hero_border)s; border-radius: 12px;
}
QFrame#Divider { background: %(border)s; border: none; }
QLabel#Tile { background: %(tint)s; border: 1px solid %(tint_border)s; border-radius: 8px; }
QLabel#RailMark { background: #203d57; border: 1px solid #355a74; border-radius: 10px; }
QLabel#Step {
    color: %(accent)s; background: %(tint)s; border-radius: 7px;
    font-family: "%(mono)s"; font-weight: 650; font-size: 11px;
}

QLineEdit, QComboBox {
    background: %(input)s; color: %(text)s; border: 1px solid %(outline)s; border-radius: 7px;
    padding: 0 11px; min-height: 36px; selection-background-color: %(primary)s;
    selection-color: %(on_primary)s;
}
QLineEdit:focus, QComboBox:focus { border-color: %(primary)s; }
QLineEdit:disabled, QComboBox:disabled { background: %(inset)s; color: %(text_muted)s; border-color: %(border)s; }
QComboBox { padding-right: 28px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView {
    background: %(raised)s; color: %(text)s; border: 1px solid %(outline)s;
    padding: 3px; selection-background-color: %(tint)s; selection-color: %(text)s; outline: 0;
}
QComboBox QAbstractItemView::item { min-height: 28px; }

QPushButton {
    background: %(raised)s; color: %(text_body)s; border: 1px solid %(outline)s;
    border-radius: 7px; padding: 0 13px; min-height: 34px; font-weight: 600;
}
QPushButton:hover { background: %(hover)s; }
QPushButton:focus { border-color: %(primary)s; }
QPushButton:pressed { background: %(tint)s; }
QPushButton#PrimaryButton {
    background: %(primary)s; border-color: %(primary)s; color: %(on_primary)s; padding: 0 15px;
}
QPushButton#PrimaryButton:hover { background: %(primary_dim)s; border-color: %(primary_dim)s; }
QPushButton#PrimaryButton:focus { border-color: %(text)s; }
QPushButton#DangerButton { color: %(err_fg)s; border-color: %(err_fg)s; }
QPushButton#DangerButton:hover { background: %(err_bg)s; }
QPushButton#GhostButton { background: transparent; border-color: transparent; font-size: 12px; }
QPushButton#GhostButton:hover { background: %(hover)s; }
QPushButton#GhostButton:focus { border-color: %(primary)s; }
QPushButton#PolicyButton {
    background: %(inset)s; border-color: %(border)s; color: %(text_body)s;
    text-align: left; min-height: 39px; padding-left: 10px; font-size: 13px;
}
QPushButton#PolicyButton:hover { background: %(hover)s; border-color: %(outline)s; }
QPushButton#PolicyButton:checked { background: %(tint)s; color: %(accent)s; border-color: %(accent)s; }
QPushButton#PolicyButton:focus { border-color: %(text)s; }
QPushButton:disabled, QPushButton#PrimaryButton:disabled {
    color: %(text_muted)s; background: %(inset)s; border-color: %(border)s;
}

QProgressBar { background: %(track)s; border: none; border-radius: 4px; min-height: 8px; max-height: 8px; }
QProgressBar::chunk { background: %(primary)s; border-radius: 4px; }

QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px 2px 2px 0; }
QScrollBar::handle:vertical { background: %(outline)s; border-radius: 3px; min-height: 34px; }
QScrollBar::handle:vertical:hover { background: %(text_faint)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: %(raised)s; color: %(text)s; border: 1px solid %(outline)s; padding: 6px; }
""" % c


def _apply_palette(app: QApplication, c: dict) -> None:
    palette = app.style().standardPalette()
    for role, token in {
        "Window": "base", "WindowText": "text", "Base": "input", "Text": "text",
        "Button": "raised", "ButtonText": "text", "Highlight": "primary",
        "HighlightedText": "on_primary", "PlaceholderText": "text_muted",
    }.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(c[token]))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet(c))


def apply_theme(app: QApplication, mode: str = MODE_LIGHT) -> None:
    app.setStyle("Fusion")
    theme._mode = mode if mode in PALETTES else MODE_LIGHT
    app.setFont(QFont(_family(BODY_FONTS), 10))
    _apply_palette(app, theme.colors)
