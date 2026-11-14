"""Small, theme-aware vector icons for the desktop interface."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "pulse": '<path d="M2 12h5l3-7 4 14 3-7h5"/>',
    "fingerprint": '<path d="M4 7a9 9 0 0 1 16 3M3 13v-1m18 2v-2M7 18c-1-2-1-3-1-6a6 6 0 0 1 12 0v3m-8 5c-1-2-1-5-1-8a3 3 0 0 1 6 0c0 4 1 7 2 8m-4 2c-1-2-1-6-1-10m8 6 1 2"/>',
    "sliders": '<path d="M4 6h5m4 0h7M4 12h10m4 0h2M4 18h2m4 0h10M9 3v6m9 0v6M6 15v6"/>',
    "shield": '<path d="M12 22s7-3 7-10V5l-7-3-7 3v7c0 7 7 10 7 10Z"/><path d="m9 12 2 2 4-4"/>',
    "mark": '<path d="M12 22s8-3 8-10V5l-8-3-8 3v7c0 7 8 10 8 10Z"/><path d="M4 12h4l2-3 3 6 2-3h5"/>',
    "user": '<circle cx="12" cy="8" r="3.2"/><path d="M5 20v-1a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v1"/>',
    "chart": '<path d="M4 4v16h16M8 15l4-4 3 2 5-6"/><path d="M17 7h3v3"/>',
    "keyboard": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 13h.01M10 13h.01M14 13h.01M18 13h.01M9 16h6"/>',
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
    "moon": '<path d="M20.8 14.1A9 9 0 0 1 9.9 3.2a9 9 0 1 0 10.9 10.9Z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
    "steps": '<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>',
    "power": '<path d="M12 2v10M6 5a9 9 0 1 0 12 0"/>',
    "folder": '<path d="M3 18V6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "arrow": '<path d="M4 12h15m-6-6 6 6-6 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-8h.01"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
}


def pixmap(name: str, color: str, size: int) -> QPixmap:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">'
        f'{PATHS[name]}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("ascii")))
    # Render at double resolution for high DPI displays.
    result = QPixmap(size * 2, size * 2)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    renderer.render(painter)
    painter.end()
    result.setDevicePixelRatio(2)
    return result


def icon(name: str, color: str, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))
