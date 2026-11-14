"""Telemetry plots for scores and enrollment cadence."""
from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from desktop.ui import icons, theme


def _plot_background(painter, rect):
    c = theme.colors()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(c["chart_bg"]))
    painter.setPen(QPen(QColor(c["border"]), 1))
    painter.drawRoundedRect(rect.adjusted(.5, .5, -.5, -.5), 8, 8)

    dots = QColor(c["chart_grid"])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(dots)
    for y in range(14, int(rect.height()) - 10, 13):
        for x in range(14, int(rect.width()) - 10, 13):
            painter.drawEllipse(QPointF(x, y), .75, .75)


def _draw_data(painter, plot, points):
    color = QColor(theme.colors()["chart_line"])
    if len(points) > 1:
        gradient = QLinearGradient(0, plot.top(), 0, plot.bottom())
        shade = QColor(color)
        shade.setAlpha(55)
        gradient.setColorAt(0, shade)
        shade.setAlpha(0)
        gradient.setColorAt(1, shade)
        area = [QPointF(points[0].x(), plot.bottom())] + points + [
            QPointF(points[-1].x(), plot.bottom())
        ]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPolygon(QPolygonF(area))
        pen = QPen(color, 2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(points))

    painter.setBrush(color)
    painter.setPen(QPen(QColor(theme.colors()["chart_bg"]), 1.5))
    painter.drawEllipse(points[-1], 4, 4)


def _text(painter, rect, text, size, color, *, align=Qt.AlignmentFlag.AlignLeft):
    painter.setFont(theme.mono_font(size))
    painter.setPen(QColor(color))
    painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, text)


class ScoreSparkline(QWidget):
    def __init__(self):
        super().__init__()
        self._scores = []
        self._t_susp = 0.0
        self._t_lock = 0.0
        self.setFixedHeight(184)
        self.setAccessibleName("Anomaly score history")
        theme.theme.changed.connect(lambda: self.update())

    def set_data(self, scores, t_susp: float, t_lock: float) -> None:
        self._scores = [float(value) for value in scores]
        self._t_susp = float(t_susp)
        self._t_lock = float(t_lock)
        self.setAccessibleDescription(
            f"{len(self._scores)} readings. Latest: {self._scores[-1]:.3f}."
            if self._scores else "No score history yet."
        )
        self.update()

    def paintEvent(self, event):
        c = theme.colors()
        painter = QPainter(self)
        rect = QRectF(self.rect())
        _plot_background(painter, rect)
        if not self._scores:
            center = rect.center()
            painter.drawPixmap(
                int(center.x()) - 11, int(center.y()) - 28,
                icons.pixmap("chart", c["accent"], 22),
            )
            _text(
                painter, QRectF(0, center.y() + 5, rect.width(), 22),
                "Waiting for the first reading", 12, c["text_muted"],
                align=Qt.AlignmentFlag.AlignHCenter,
            )
            return

        plot = rect.adjusted(55, 20, -17, -31)
        values = self._scores + [self._t_susp, self._t_lock]
        low, high = min(values), max(values)
        pad = (high - low) * .16 if high > low else .1
        low, high = low - pad, high + pad

        def y_for(value):
            return plot.bottom() - (value - low) / (high - low) * plot.height()

        for index in range(5):
            value = low + index * (high - low) / 4
            y = y_for(value)
            painter.setPen(QPen(QColor(c["chart_grid"]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            _text(painter, QRectF(4, y - 8, 44, 16), f"{value:.2f}", 10, c["text_faint"],
                  align=Qt.AlignmentFlag.AlignRight)

        step = plot.width() / max(len(self._scores) - 1, 1)
        points = [
            QPointF(plot.left() + idx * step, y_for(score))
            for idx, score in enumerate(self._scores)
        ] if len(self._scores) > 1 else [QPointF(plot.center().x(), y_for(self._scores[0]))]
        _draw_data(painter, plot, points)
        for threshold, token in ((self._t_susp, "warn_fg"), (self._t_lock, "err_fg")):
            y = y_for(threshold)
            painter.setPen(QPen(QColor(c[token]), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        _text(painter, QRectF(14, plot.bottom() + 5, plot.width(), 17),
              f"Readings: {len(points):,}", 11, c["text_muted"])
        _text(painter, QRectF(14, plot.bottom() + 5, rect.width() - 28, 17),
              f"Latest: {self._scores[-1]:.3f}", 11, c["accent"],
              align=Qt.AlignmentFlag.AlignRight)


class CadencePlot(QWidget):
    """Shows recent key hold durations without keeping key identities."""
    def __init__(self):
        super().__init__()
        self._samples = deque(maxlen=30)
        self.setMinimumHeight(69)
        self.setAccessibleName("Recent key hold times")
        self.setAccessibleDescription("Up to 30 recent key hold durations in milliseconds.")

    def record(self, duration: float) -> None:
        self._samples.append(duration)
        self.update()

    def clear(self) -> None:
        self._samples.clear()
        self.update()

    def paintEvent(self, event):
        c = theme.colors()
        painter = QPainter(self)
        rect = QRectF(self.rect())
        _plot_background(painter, rect)
        if not self._samples:
            _text(painter, rect, "No samples captured", 11, c["text_muted"],
                  align=Qt.AlignmentFlag.AlignHCenter)
            return
        plot = rect.adjusted(12, 9, -12, -18)
        high = max(max(self._samples) * 1.12, 1)
        step = plot.width() / (self._samples.maxlen - 1)
        _draw_data(painter, plot, [
            QPointF(plot.right() - (len(self._samples) - 1 - idx) * step,
                    plot.bottom() - sample / high * plot.height())
            for idx, sample in enumerate(self._samples)
        ])
        _text(painter, QRectF(12, rect.bottom() - 17, rect.width() - 24, 15),
              f"Latest hold: {self._samples[-1]:.0f} ms", 10, c["text_muted"],
              align=Qt.AlignmentFlag.AlignRight)
