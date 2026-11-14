import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLineEdit

IGNORED_KEYS = {
    Qt.Key.Key_Shift,
    Qt.Key.Key_Control,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
    Qt.Key.Key_CapsLock,
    Qt.Key.Key_NumLock,
    Qt.Key.Key_ScrollLock,
    Qt.Key.Key_AltGr,
    Qt.Key.Key_Super_L,
    Qt.Key.Key_Super_R,
}


class KeystrokeEdit(QLineEdit):
    attemptReady = Signal(object, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setMaxLength(64)
        self.setAcceptDrops(False)
        self.setDragEnabled(False)
        self.setPlaceholderText("Type your password, then press Enter")
        self._open: dict[int, float] = {}
        self._events: list[dict[str, float]] = []
        self._bad = False

    def _code(self, event) -> int:
        return int(event.nativeScanCode()) or int(event.key())

    def _reset_attempt(self) -> None:
        self._open.clear()
        self._events = []
        self._bad = False

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._events:
                self.attemptReady.emit(list(self._events), self._bad)
            self._reset_attempt()
            self.clear()
            event.accept()
            return
        if event.isAutoRepeat():
            event.accept()
            return
        if event.key() in IGNORED_KEYS:
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self._bad = True
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._bad = True
        code = self._code(event)
        if code not in self._open:
            self._open[code] = time.perf_counter() * 1000.0
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            event.accept()
            return
        code = self._code(event)
        if code in self._open:
            down = self._open.pop(code)
            up = time.perf_counter() * 1000.0
            self._events.append({"d": down, "u": up})
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._reset_attempt()
        super().focusOutEvent(event)

    def contextMenuEvent(self, event):
        event.accept()
