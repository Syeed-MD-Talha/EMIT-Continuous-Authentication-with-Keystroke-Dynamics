"""System-wide keystroke timing capture via Windows Raw Input.

Only scan codes and timestamps are kept. Characters are never stored.
Raw Input (RIDEV_INPUTSINK) is used instead of a WH_KEYBOARD_LL hook because
it does not look like a keylogger to antivirus software and needs no admin.
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget

from desktop.windowizer import Windowizer

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEKEYBOARD = 1
RIDEV_REMOVE = 0x00000001
RIDEV_INPUTSINK = 0x00000100
RI_KEY_BREAK = 0x01
RI_KEY_E0 = 0x02
RI_KEY_E1 = 0x04

# Shift, Ctrl, Alt, CapsLock, Win: modifiers distort hold times.
IGNORED_SCAN_CODES = {0x2A, 0x36, 0x1D, 0x38, 0x3A, 0x5B, 0x5C, 0x11D, 0x138}

user32 = ctypes.WinDLL("user32", use_last_error=True)


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("keyboard", RAWKEYBOARD)]


user32.GetRawInputData.argtypes = [
    wintypes.HANDLE,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.UINT),
    wintypes.UINT,
]
user32.GetRawInputData.restype = wintypes.UINT
user32.RegisterRawInputDevices.argtypes = [
    ctypes.POINTER(RAWINPUTDEVICE),
    wintypes.UINT,
    wintypes.UINT,
]
user32.RegisterRawInputDevices.restype = wintypes.BOOL


def _message_address(message) -> int:
    try:
        return int(message)
    except (TypeError, ValueError):
        return ctypes.cast(message, ctypes.c_void_p).value or 0


class _RawInputFilter(QAbstractNativeEventFilter):
    def __init__(self, on_input):
        super().__init__()
        self._on_input = on_input

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(_message_address(message))
            if msg.message == WM_INPUT:
                self._on_input(int(msg.lParam))
        return False, 0


class RawInputCapture(QObject):
    keyEvent = Signal(int, float, float)  # scan code, keydown ms, keyup ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self._open: dict[int, float] = {}
        self._filter = None
        self._host = None
        self._running = False

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        if self._running:
            return True
        if not self.supported:
            return False
        app = QApplication.instance()
        if app is None:
            return False

        self._host = QWidget()
        self._host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self._host.resize(1, 1)
        self._host.show()

        device = RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, int(self._host.winId()))
        if not user32.RegisterRawInputDevices(
            ctypes.byref(device), 1, ctypes.sizeof(RAWINPUTDEVICE)
        ):
            self._host.deleteLater()
            self._host = None
            return False

        self._filter = _RawInputFilter(self._handle_raw)
        app.installNativeEventFilter(self._filter)
        self._running = True
        return True

    def stop(self) -> None:
        if not self._running:
            return
        device = RAWINPUTDEVICE(0x01, 0x06, RIDEV_REMOVE, None)
        user32.RegisterRawInputDevices(
            ctypes.byref(device), 1, ctypes.sizeof(RAWINPUTDEVICE)
        )
        app = QApplication.instance()
        if app is not None and self._filter is not None:
            app.removeNativeEventFilter(self._filter)
        self._filter = None
        if self._host is not None:
            self._host.deleteLater()
            self._host = None
        self._open.clear()
        self._running = False

    def _handle_raw(self, handle: int) -> None:
        header_size = ctypes.sizeof(RAWINPUTHEADER)
        size = wintypes.UINT(0)
        user32.GetRawInputData(handle, RID_INPUT, None, ctypes.byref(size), header_size)
        if size.value < ctypes.sizeof(RAWINPUT):
            return

        buffer = ctypes.create_string_buffer(size.value)
        written = user32.GetRawInputData(
            handle, RID_INPUT, buffer, ctypes.byref(size), header_size
        )
        if written in (0, 0xFFFFFFFF):
            return

        raw = RAWINPUT.from_buffer(buffer)
        if raw.header.dwType != RIM_TYPEKEYBOARD:
            return

        keyboard = raw.keyboard
        code = int(keyboard.MakeCode)
        if keyboard.Flags & RI_KEY_E0:
            code |= 0x100
        if keyboard.Flags & RI_KEY_E1:
            code |= 0x200
        if code in IGNORED_SCAN_CODES:
            return

        now = time.perf_counter() * 1000.0
        if keyboard.Flags & RI_KEY_BREAK:
            down = self._open.pop(code, None)
            if down is not None:
                self.keyEvent.emit(code, down, now)
        elif code not in self._open:
            self._open[code] = now


class CaptureService(QObject):
    """Owns the raw listener and the sliding windowizer."""

    keyCaptured = Signal(int, float, float)
    windowReady = Signal(list)

    def __init__(self, window=100, stride=50, idle_gap=2.0, parent=None):
        super().__init__(parent)
        self.windowizer = Windowizer(window=window, stride=stride, idle_gap=idle_gap)
        self._capture = RawInputCapture(self)
        self._capture.keyEvent.connect(self._on_key)
        self.paused = False
        self.keystrokes = 0

    @property
    def supported(self) -> bool:
        return self._capture.supported

    @property
    def running(self) -> bool:
        return self._capture.running

    def start(self) -> bool:
        return self._capture.start()

    def stop(self) -> None:
        self._capture.stop()

    def reset(self) -> None:
        self.windowizer.reset()
        self.keystrokes = 0

    def _on_key(self, code: int, down: float, up: float) -> None:
        if self.paused:
            return
        self.keystrokes += 1
        self.keyCaptured.emit(code, down, up)
        for window in self.windowizer.feed({"d": down, "u": up}):
            self.windowReady.emit(window)
