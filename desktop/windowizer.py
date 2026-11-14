"""Turn a raw keystroke stream into fixed-size sliding windows."""
from collections import deque


class Windowizer:
    """Buffer keystrokes and emit overlapping windows of a fixed size.

    A pause longer than ``idle_gap`` seconds starts a new burst, so a coffee
    break never becomes a multi-second inter-key delay feature.
    """

    def __init__(self, window: int = 100, stride: int = 50, idle_gap: float = 2.0):
        if window < 3:
            raise ValueError("window must be at least 3 keystrokes")
        if not 0 < stride <= window:
            raise ValueError("stride must be between 1 and window")
        self.window = window
        self.stride = stride
        self.idle_gap = idle_gap * 1000.0
        self._buffer: deque = deque()
        self._last_up: float | None = None

    @property
    def pending(self) -> int:
        return len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()
        self._last_up = None

    def feed(self, event: dict) -> list[list[dict]]:
        """event: {"d": keydown_ms, "u": keyup_ms}. Returns completed windows."""
        down = float(event["d"])
        up = float(event["u"])
        if self._last_up is not None and down - self._last_up > self.idle_gap:
            self._buffer.clear()
        self._last_up = up
        self._buffer.append({"d": down, "u": up})

        windows = []
        while len(self._buffer) >= self.window:
            windows.append(list(self._buffer)[: self.window])
            for _ in range(self.stride):
                self._buffer.popleft()
        return windows
