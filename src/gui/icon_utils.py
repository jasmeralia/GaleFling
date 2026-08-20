"""Recoloring for the monochrome UI icon set.

Icons under resources/icons/ under a plain black fill with no theme
awareness (Material Symbols exported with no `fill` attribute), so used
as-is they render invisibly against this app's near-black dark surfaces.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap


def tinted_pixmap(svg_path: Path | str, color: str, size: int = 24) -> QPixmap | None:
    """Rasterize a monochrome SVG icon and recolor it, ignoring its own fill."""
    path = Path(svg_path)
    if not path.is_file():
        return None
    icon = QIcon(str(path))
    if icon.isNull():
        return None
    base = icon.pixmap(size, size)
    if base.isNull():
        return None
    tinted = QPixmap(base.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.drawPixmap(0, 0, base)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    return tinted


def tinted_icon(svg_path: Path | str, color: str, size: int = 24) -> QIcon:
    """Same as `tinted_pixmap`, wrapped as a QIcon (empty QIcon on failure)."""
    pixmap = tinted_pixmap(svg_path, color, size)
    return QIcon(pixmap) if pixmap is not None else QIcon()
