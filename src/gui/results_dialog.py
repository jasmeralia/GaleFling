"""Post results dialog with clickable links and copy buttons."""

import re
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from src.core.error_handler import format_error_details
from src.utils import tokens
from src.utils.constants import PLATFORM_SPECS_MAP, PostResult

_ICONS_DIR = Path(__file__).resolve().parent.parent / 'resources' / 'icons'

_PLATFORM_ALIASES = {
    'twitter': 'twitter',
    'bluesky': 'bluesky',
    'snapchat': 'snapchat',
    'onlyfans': 'onlyfans',
    'fansly': 'fansly',
    'fetlife': 'fetlife',
    'threads': 'meta_threads',
    'instagram': 'meta_instagram',
    'facebook page': 'meta_facebook_page',
}

_BRAND_ICON_FILES = {
    'twitter': 'twitter.svg',
    'bluesky': 'bluesky.svg',
    'meta_threads': 'threads.svg',
    'meta_instagram': 'instagram.svg',
    'meta_facebook_page': 'facebook.svg',
}


def _normalize_platform_display(platform_display: str) -> str:
    return re.sub(r'\s*\(.*\)$', '', platform_display).strip().lower()


def _resolve_platform_key(platform_display: str) -> str | None:
    return _PLATFORM_ALIASES.get(_normalize_platform_display(platform_display))


def _render_svg_colored(svg_path: Path, size: int, color: QColor) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(svg_path))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap


def _build_result_badge(result: PostResult, *, success: bool) -> QPixmap:
    spec_key = _resolve_platform_key(result.platform)
    spec = PLATFORM_SPECS_MAP.get(spec_key) if spec_key else None

    pixmap = QPixmap(36, 36)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    base_color = QColor(spec.platform_color) if spec else QColor(tokens.BORDER)
    base_center_x = 18
    base_center_y = 18
    base_diameter = 32
    base_radius = base_diameter // 2
    painter.setBrush(base_color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(
        base_center_x - base_radius,
        base_center_y - base_radius,
        base_diameter,
        base_diameter,
    )

    if spec_key and spec_key in _BRAND_ICON_FILES:
        icon_path = _ICONS_DIR / 'brands' / _BRAND_ICON_FILES[spec_key]
        icon_size = 18
        icon_pixmap = _render_svg_colored(icon_path, icon_size, QColor(tokens.TEXT))
        icon_offset = (base_diameter - icon_size) // 2
        painter.drawPixmap(
            base_center_x - base_radius + icon_offset,
            base_center_y - base_radius + icon_offset,
            icon_pixmap,
        )
    else:
        if spec:
            monogram = spec.platform_name[0]
        else:
            stripped = re.sub(r'\s*\(.*\)$', '', result.platform).strip()
            monogram = stripped[0] if stripped else '?'
        font = QFont()
        font.setBold(True)
        font.setPixelSize(14)
        painter.setFont(font)
        painter.setPen(QColor(tokens.TEXT))
        painter.drawText(
            base_center_x - base_radius,
            base_center_y - base_radius,
            base_diameter,
            base_diameter,
            int(Qt.AlignmentFlag.AlignCenter),
            monogram.upper(),
        )

    status_diameter = 14
    status_radius = status_diameter // 2
    status_center_x = base_center_x + base_radius - status_radius
    status_center_y = base_center_y + base_radius - status_radius
    status_color = QColor(tokens.SUCCESS if success else tokens.DANGER)
    painter.setBrush(status_color)
    painter.drawEllipse(
        status_center_x - status_radius,
        status_center_y - status_radius,
        status_diameter,
        status_diameter,
    )

    status_icon_name = 'check.svg' if success else 'warning.svg'
    status_icon_size = 9
    status_icon = _render_svg_colored(
        _ICONS_DIR / 'ui' / status_icon_name,
        status_icon_size,
        QColor(tokens.TEXT),
    )
    status_icon_offset = (status_diameter - status_icon_size) // 2
    painter.drawPixmap(
        status_center_x - status_radius + status_icon_offset,
        status_center_y - status_radius + status_icon_offset,
        status_icon,
    )

    painter.end()
    return pixmap


class ResultsDialog(QDialog):
    """Display posting results with clickable URLs and copy buttons."""

    def __init__(self, results: list[PostResult], parent=None):
        super().__init__(parent)
        self._results = results
        self._send_logs_requested = False

        self.setWindowTitle('Post Results')
        self.setMinimumWidth(550)

        layout = QVBoxLayout(self)

        for result in results:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame_layout = QVBoxLayout(frame)
            # Contents margins, not frame.setStyleSheet('QFrame { padding; margin }') --
            # that combination corrupts this frame's descendant layout under the
            # offscreen Qt platform, shrinking the platform badge to a few px with no
            # icon detail (see docs/images/results-dialog.png before this fix).
            frame_layout.setContentsMargins(8, 8, 8, 8)

            if result.success:
                self._add_success_row(frame_layout, result)
            else:
                self._add_failure_row(frame_layout, result)

            layout.addWidget(frame)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        # "Send Logs to Jas" if any failures
        has_failure = any(not r.success for r in results)
        if has_failure:
            send_btn = QPushButton('Send Logs to Jas')
            send_btn.clicked.connect(self._on_send_logs)
            btn_layout.addWidget(send_btn)

        # "Copy All Links" if any successes
        success_results = [r for r in results if r.success and r.post_url]
        if success_results:
            copy_all_btn = QPushButton('Copy All Links')
            copy_all_btn.clicked.connect(lambda: self._copy_all_links(success_results))
            btn_layout.addWidget(copy_all_btn)

        btn_layout.addStretch()

        close_btn = QPushButton('Close')
        close_btn.setMinimumWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _add_badge(self, row_layout: QHBoxLayout, result: PostResult, *, success: bool) -> None:
        badge = QLabel()
        badge.setPixmap(_build_result_badge(result, success=success))
        badge.setFixedSize(36, 36)
        row_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

    def _add_success_row(self, layout: QVBoxLayout, result: PostResult):
        row_layout = QHBoxLayout()
        self._add_badge(row_layout, result, success=True)

        content_layout = QVBoxLayout()

        if result.user_confirmed and not result.url_captured:
            header = QLabel(
                f'<span style="color: {tokens.SUCCESS}; font-size: 14px;">'
                f'{result.platform} - Posted (link unavailable)</span>'
            )
        else:
            header = QLabel(
                f'<span style="color: {tokens.SUCCESS}; font-size: 14px;">'
                f'{result.platform} - Posted successfully!</span>'
            )
        content_layout.addWidget(header)

        if result.post_url:
            link = QLabel(f'<a href="{result.post_url}">{result.post_url}</a>')
            link.setOpenExternalLinks(True)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            content_layout.addWidget(link)

            copy_btn = QPushButton('Copy Link')
            copy_btn.setMaximumWidth(100)
            post_url = result.post_url
            copy_btn.clicked.connect(lambda _, url=post_url: self._copy_text(url))
            # Without an explicit alignment, this button's maximumWidth becomes
            # content_layout's own maximumWidth (a QVBoxLayout's max width is the
            # min of its children's), which starves its stretch=1 share in
            # row_layout and pushes the badge out of its flush-left position.
            content_layout.addWidget(copy_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        row_layout.addLayout(content_layout, 1)
        layout.addLayout(row_layout)

    def _add_failure_row(self, layout: QVBoxLayout, result: PostResult):
        row_layout = QHBoxLayout()
        self._add_badge(row_layout, result, success=False)

        content_layout = QVBoxLayout()

        header = QLabel(
            f'<span style="color: {tokens.DANGER}; font-size: 14px;">'
            f'{result.platform} - Failed to post</span>'
        )
        content_layout.addWidget(header)

        msg = QLabel(result.error_message or 'Unknown error')
        msg.setWordWrap(True)
        content_layout.addWidget(msg)

        if result.error_code:
            code_label = QLabel(f'<b>Error Code:</b> {result.error_code}')
            content_layout.addWidget(code_label)

        time_label = QLabel(f'<b>Time:</b> {result.timestamp}')
        content_layout.addWidget(time_label)

        btn_row = QHBoxLayout()

        copy_err_btn = QPushButton('Copy Error Details')
        copy_err_btn.clicked.connect(lambda: self._copy_text(format_error_details(result)))
        btn_row.addWidget(copy_err_btn)

        settings_btn = QPushButton('Open Settings')
        settings_btn.clicked.connect(self._on_open_settings)
        btn_row.addWidget(settings_btn)

        btn_row.addStretch()
        content_layout.addLayout(btn_row)

        row_layout.addLayout(content_layout, 1)
        layout.addLayout(row_layout)

    def _copy_text(self, text: str | None):
        if not text:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _copy_all_links(self, results: list[PostResult]):
        lines = [f'{r.platform}: {r.post_url}' for r in results if r.post_url]
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText('\n'.join(lines))

    def _on_send_logs(self):
        self._send_logs_requested = True
        self.accept()

    def _on_open_settings(self):
        # The main window handles this via the dialog result
        self.done(2)  # Custom result code for "open settings"

    @property
    def send_logs_requested(self) -> bool:
        return self._send_logs_requested
