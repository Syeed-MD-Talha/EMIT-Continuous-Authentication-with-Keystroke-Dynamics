"""Reusable panels and controls for EMIT Desktop."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QStyle, QStyleOptionComboBox, QVBoxLayout, QWidget,
)

from desktop.ui import icons, theme


def label(text: str, role: str, *, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(role)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    return widget


class IconTile(QLabel):
    def __init__(self, name: str, size: int = 32, rail: bool = False):
        super().__init__()
        self.name, self.rail = name, rail
        self.setObjectName("RailMark" if rail else "Tile")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh()
        theme.theme.changed.connect(self._refresh)

    def _refresh(self) -> None:
        color = "#9eefff" if self.rail else theme.colors()["accent"]
        self.setPixmap(icons.pixmap(self.name, color, round(self.width() * 0.55)))


class Card(QFrame):
    def __init__(self, title: str = "", icon: str = "", trailing: QWidget | None = None):
        super().__init__()
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(17, 15, 17, 16)
        self.body.setSpacing(11)
        if title:
            row = QHBoxLayout()
            row.setSpacing(9)
            if icon:
                row.addWidget(IconTile(icon))
            self.title_label = section_title(title)
            row.addWidget(self.title_label, 1)
            if trailing is not None:
                row.addWidget(trailing)
            self.body.addLayout(row)


class Inset(QFrame):
    def __init__(self, role: str = "Inset", margin: int = 11):
        super().__init__()
        self.setObjectName(role)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margin, margin, margin, margin)
        self.body.setSpacing(5)


class StatCard(Inset):
    def __init__(self, caption: str, value: str = "0"):
        super().__init__("StatCard")
        self.value_label = label(value, "StatValue")
        self.body.addWidget(label(caption, "StatLabel"))
        self.body.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class Chip(QLabel):
    def __init__(self, text: str = "", kind: str = "neutral"):
        super().__init__(text)
        self.setObjectName("Chip")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_kind(kind)
        theme.theme.changed.connect(self._refresh)

    def _refresh(self) -> None:
        self.set_kind(self._kind)

    def set_kind(self, kind: str) -> None:
        self._kind = kind if kind in ("ok", "warn", "err", "info", "neutral") else "neutral"
        c = theme.colors()
        bg, fg = (
            (c["tint"], c["accent"]) if self._kind == "info"
            else (c[f"{self._kind}_bg"], c[f"{self._kind}_fg"])
        )
        self.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 10px;"
            "padding: 3px 9px; font-size: 11px; font-weight: 650;"
        )

    def set_text(self, text: str, kind: str | None = None) -> None:
        self.setText(text)
        if kind is not None:
            self.set_kind(kind)


class Divider(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Divider")
        self.setFixedHeight(1)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str, eyebrow: str = ""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 3)
        layout.setSpacing(3)
        if eyebrow:
            layout.addWidget(label(eyebrow.upper(), "Eyebrow"))
        layout.addWidget(label(title, "PageTitle", wrap=True))
        layout.addWidget(label(subtitle, "PageSubtitle", wrap=True))


class SessionBanner(QFrame):
    STATES = {
        "empty": ("No profile enrolled", "Setup needed", "neutral"),
        "idle": ("Ready to verify", "Standby", "neutral"),
        "monitoring": ("Monitoring typing rhythm", "Monitoring", "info"),
        "normal": ("Typing rhythm matched", "Normal", "ok"),
        "suspicious": ("Unusual typing detected", "Suspicious", "warn"),
        "locked": ("Session flagged", "Locked", "err"),
    }

    def __init__(self):
        super().__init__()
        self.setObjectName("Hero")
        row = QHBoxLayout(self)
        row.setContentsMargins(17, 13, 17, 13)
        row.setSpacing(13)
        row.addWidget(IconTile("pulse", 44))
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.chip = Chip()
        self.title = label("", "HeroTitle", wrap=True)
        self.detail = hint_label("")
        copy.addWidget(self.title)
        copy.addWidget(self.detail)
        row.addLayout(copy, 1)
        row.addWidget(self.chip)
        box = Inset(margin=9)
        box.setMinimumWidth(104)
        box.body.setSpacing(0)
        box.body.addWidget(label("LATEST SCORE", "HeroLabel"))
        self.score = label("—", "HeroScore")
        box.body.addWidget(self.score)
        row.addWidget(box)

    def set_state(self, state: str, detail: str, score: float | None = None) -> None:
        title, status, kind = self.STATES[state]
        self.title.setText(title)
        self.detail.setText(detail)
        self.chip.set_text(status, kind)
        self.score.setText("—" if score is None else f"{score:.3f}")


class CurrentPanelStack(QWidget):
    """Give the active mode the space it needs without sizing to hidden controls."""
    def __init__(self):
        super().__init__()
        self._pages: list[QWidget] = []
        self._index = -1
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def addWidget(self, page: QWidget) -> None:
        self._pages.append(page)
        self._layout.addWidget(page)
        page.setVisible(len(self._pages) == 1)
        if self._index == -1:
            self._index = 0

    def setCurrentIndex(self, index: int) -> None:
        if index != self._index and 0 <= index < len(self._pages):
            self._pages[self._index].hide()
            self._index = index
            self._pages[index].show()

    def currentIndex(self) -> int:
        return self._index


class Select(QComboBox):
    """Draw a readable chevron in both palettes."""
    def paintEvent(self, event):
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxArrow, self
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(theme.colors()["text_muted"]), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        x, y = rect.center().x(), rect.center().y()
        painter.drawLine(x - 4, y - 2, x, y + 2)
        painter.drawLine(x, y + 2, x + 4, y - 2)


class Switch(QCheckBox):
    """A keyboard-accessible toggle with a visible focus ring."""
    def __init__(self, name: str):
        super().__init__()
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(42, 26)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event):
        c = theme.colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.hasFocus():
            painter.setPen(QPen(QColor(c["accent"]), 1))
            painter.drawRoundedRect(QRectF(0.5, 0.5, 41, 25), 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["primary"] if self.isChecked() else c["outline"]))
        painter.drawRoundedRect(QRectF(3, 3, 36, 20), 10, 10)
        painter.setBrush(QColor(c["on_primary"] if self.isChecked() else c["raised"]))
        painter.drawEllipse(QRectF(22 if self.isChecked() else 6, 6, 14, 14))


def field_label(text: str, field: QWidget | None = None) -> QLabel:
    result = label(text, "FieldLabel")
    if field is not None:
        result.setBuddy(field)
        field.setAccessibleName(text)
    return result


def hint_label(text: str) -> QLabel:
    return label(text, "Hint", wrap=True)


def mono_label(text: str) -> QLabel:
    return label(text, "Mono")


def section_title(text: str) -> QLabel:
    return label(text, "SectionTitle", wrap=True)


def make_button(text: str, kind: str = "primary") -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(f"{kind.title()}Button")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def stat_row(*cards: StatCard) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    for card in cards:
        row.addWidget(card, 1)
    return row


def page_layout(page: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout(page)
    layout.setContentsMargins(25, 20, 25, 24)
    layout.setSpacing(15)
    return layout


def scrollable(page: QWidget) -> QScrollArea:
    page.setObjectName("Page")
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(page)
    return scroll
