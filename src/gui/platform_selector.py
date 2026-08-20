"""Platform selection checkboxes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.utils import tokens
from src.utils.constants import PLATFORM_SPECS_MAP, AccountConfig
from src.utils.helpers import get_resource_path

_PLATFORM_ICON_ALIASES: dict[str, str] = {
    'meta_instagram': 'instagram',
    'meta_threads': 'threads',
    'meta_facebook_page': 'facebook',
}


class _ToggleSwitch(QCheckBox):
    """A checkbox painted as a track-and-knob switch instead of a native indicator.

    QSS alone can't move a knob between two positions, and a plain colored
    pill (no knob at all) reads as a button rather than a toggle. This paints
    both explicitly so on/off is unambiguous at a glance.
    """

    _WIDTH = 40
    _HEIGHT = 22
    _MARGIN = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self._WIDTH, self._HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        checked = self.isChecked()
        if not self.isEnabled():
            track_color = QColor(tokens.SURFACE)
            border_color = QColor(tokens.BORDER)
            knob_color = QColor(tokens.TEXT_MUTED)
        elif checked:
            track_color = QColor(tokens.ACCENT)
            border_color = QColor(tokens.ACCENT)
            knob_color = QColor(tokens.CANVAS)
        else:
            track_color = QColor(tokens.SURFACE_INSET)
            border_color = QColor(tokens.TEXT_SECONDARY)
            knob_color = QColor(tokens.TEXT_SECONDARY)

        track_rect = QRectF(0.5, 0.5, self._WIDTH - 1, self._HEIGHT - 1)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(track_color)
        radius = track_rect.height() / 2
        painter.drawRoundedRect(track_rect, radius, radius)

        knob_diameter = self._HEIGHT - 2 * self._MARGIN
        knob_x = float(self._WIDTH - self._MARGIN - knob_diameter if checked else self._MARGIN)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(QRectF(knob_x, self._MARGIN, knob_diameter, knob_diameter))

        painter.end()


@dataclass
class _AccountRowWidgets:
    frame: QFrame
    toggle: QCheckBox
    name_label: QLabel
    handle_label: QLabel
    status_pill: QLabel


class PlatformSelector(QWidget):
    """Checkboxes for selecting which platform accounts to post to.

    Dynamically builds checkboxes from a list of AccountConfig entries.
    Unavailable platforms (no credentials/session) cannot be checked,
    but checked platforms can always be unchecked regardless of availability.
    """

    selection_changed = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._rows: dict[str, _AccountRowWidgets] = {}
        self._labels: dict[str, str] = {}
        self._accounts: list[AccountConfig] = []
        self._available: set[str] = set()
        self._format_restricted: set[str] = set()
        self._count_restricted: set[str] = set()
        self._init_ui()

    def _init_ui(self) -> None:
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

        self._label = QLabel('Post to:')
        self._label.setStyleSheet('font-weight: bold; font-size: 13px; color: palette(text);')
        self._layout.addWidget(self._label)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        self._layout.addLayout(self._rows_layout)

    def set_accounts(self, accounts: list[AccountConfig]):
        """Rebuild checkboxes from account list."""
        for row in self._rows.values():
            row.frame.setParent(None)
            row.frame.deleteLater()
        self._checkboxes.clear()
        self._rows.clear()
        self._labels.clear()
        # Drop platforms that are not offered at all.  Their specs remain
        # resolvable so stored accounts and config still load; they simply
        # cannot be selected as a post target.
        accounts = [
            account
            for account in accounts
            if getattr(PLATFORM_SPECS_MAP.get(account.platform_id), 'available', True)
        ]
        self._accounts = sorted(accounts, key=self._account_sort_key)
        self._available.clear()

        for account in self._accounts:
            row = self._build_account_row(account)
            self._rows_layout.addWidget(row.frame)
            self._checkboxes[account.account_id] = row.toggle
            self._rows[account.account_id] = row
            self._update_row_style(account.account_id)

    def _build_account_row(self, account: AccountConfig) -> _AccountRowWidgets:
        specs = PLATFORM_SPECS_MAP.get(account.platform_id)
        color = specs.platform_color if specs else tokens.TEXT
        text_color = tokens.legible_accent(color)

        label_text = self._format_account_label(account)
        self._labels[account.account_id] = label_text
        platform_name, handle_text = self._split_label_for_display(account)

        frame = QFrame()
        frame.setObjectName('platformRow')
        frame.setStyleSheet(
            f"""
            QFrame#platformRow {{
                background-color: {tokens.SURFACE};
                border: 1px solid {tokens.BORDER};
                border-radius: 8px;
            }}
            """
        )

        row_layout = QHBoxLayout(frame)
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(10)

        badge = self._build_badge(account.platform_id, color, platform_name)
        row_layout.addWidget(badge)

        labels_layout = QVBoxLayout()
        labels_layout.setContentsMargins(0, 0, 0, 0)
        labels_layout.setSpacing(2)

        name_label = QLabel(platform_name)
        name_label.setObjectName('platformName')
        name_label.setStyleSheet(f'font-size: 13px; font-weight: bold; color: {text_color};')

        handle_label = QLabel(handle_text)
        handle_label.setObjectName('platformHandle')
        handle_label.setStyleSheet(
            f'font-size: 12px; font-weight: 600; color: {tokens.TEXT_SECONDARY};'
        )
        handle_label.setVisible(bool(handle_text))

        labels_layout.addWidget(name_label)
        labels_layout.addWidget(handle_label)
        row_layout.addLayout(labels_layout, stretch=1)

        status_pill = QLabel('Ready')
        status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_pill.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_layout.addWidget(status_pill)

        toggle = _ToggleSwitch()
        toggle.setChecked(account.enabled)
        toggle.clicked.connect(
            lambda _checked, aid=account.account_id: self._on_checkbox_clicked(aid)
        )
        row_layout.addWidget(toggle)

        return _AccountRowWidgets(
            frame=frame,
            toggle=toggle,
            name_label=name_label,
            handle_label=handle_label,
            status_pill=status_pill,
        )

    def _build_badge(self, platform_id: str, color: str, platform_name: str) -> QLabel:
        badge = QLabel()
        badge.setFixedSize(32, 32)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_path = self._brand_icon_path(platform_id)
        if icon_path is not None:
            badge.setPixmap(QIcon(str(icon_path)).pixmap(18, 18))
            badge.setStyleSheet(
                f"""
                background-color: {color};
                border-radius: 16px;
                """
            )
        else:
            monogram = platform_name[:1].upper() if platform_name else '?'
            badge.setText(monogram)
            badge.setStyleSheet(
                f"""
                background-color: {color};
                border-radius: 16px;
                color: {tokens.TEXT};
                font-size: 14px;
                font-weight: bold;
                """
            )
        return badge

    @staticmethod
    def _brand_icon_path(platform_id: str) -> Path | None:
        icon_name = _PLATFORM_ICON_ALIASES.get(platform_id, platform_id)
        path = get_resource_path(f'icons/brands/{icon_name}.svg')
        if path.exists():
            return path
        return None

    @staticmethod
    def _split_label_for_display(
        account: AccountConfig,
        username_override: str | None = None,
    ) -> tuple[str, str]:
        specs = PLATFORM_SPECS_MAP.get(account.platform_id)
        base = specs.platform_name if specs else account.platform_id.title()
        username = username_override if username_override is not None else account.profile_name
        trimmed = PlatformSelector._normalized_username(username, account.platform_id)
        handle = f'@{trimmed}' if trimmed else ''
        return base, handle

    def _on_checkbox_clicked(self, account_id: str):
        cb = self._checkboxes.get(account_id)
        if not cb:
            return
        # Block checking unavailable, format-restricted, or count-restricted platforms
        if cb.isChecked() and (
            account_id not in self._available
            or account_id in self._format_restricted
            or account_id in self._count_restricted
        ):
            cb.setChecked(False)
            return
        self.selection_changed.emit(self.get_selected())

    def get_selected(self) -> list[str]:
        return [name for name, cb in self._checkboxes.items() if cb.isChecked()]

    def set_selected(self, account_ids: list[str]):
        for name, cb in self._checkboxes.items():
            cb.setChecked(name in account_ids and name in self._available)
        self.selection_changed.emit(self.get_selected())

    def set_platform_enabled(self, account_id: str, enabled: bool):
        cb = self._checkboxes.get(account_id)
        if not cb:
            return
        if enabled:
            self._available.add(account_id)
        else:
            self._available.discard(account_id)
        self._update_row_style(account_id)

    def get_enabled(self) -> list[str]:
        return [name for name in self._checkboxes if name in self._available]

    def set_format_restriction(self, restricted_account_ids: set[str], notice_text: str = ''):
        """Restrict platforms that don't support the attached image format.

        Unchecks and dims any accounts in restricted_account_ids,
        then updates selection state. Pass an empty set to clear.
        """
        self._format_restricted = set(restricted_account_ids)

        for account_id in self._format_restricted:
            cb = self._checkboxes.get(account_id)
            if cb and cb.isChecked():
                cb.setChecked(False)

        for account_id in self._checkboxes:
            self._update_row_style(account_id)

        if self._format_restricted:
            self.selection_changed.emit(self.get_selected())

    def set_count_restriction(self, restricted_account_ids: set[str], notice_text: str = ''):
        """Restrict platforms that don't support the number of attachments.

        Unchecks and dims any accounts in restricted_account_ids,
        then updates selection state. Pass an empty set to clear.
        """
        self._count_restricted = set(restricted_account_ids)

        for account_id in self._count_restricted:
            cb = self._checkboxes.get(account_id)
            if cb and cb.isChecked():
                cb.setChecked(False)

        for account_id in self._checkboxes:
            self._update_row_style(account_id)

        if self._count_restricted:
            self.selection_changed.emit(self.get_selected())

    def set_platform_username(self, account_id: str, username: str | None):
        row = self._rows.get(account_id)
        if not row:
            return
        account = self._get_account(account_id)
        if not account:
            return
        label = self._format_account_label(account, username_override=username)
        self._labels[account_id] = label
        platform_name, handle_text = self._split_label_for_display(
            account,
            username_override=username,
        )
        row.name_label.setText(platform_name)
        row.handle_label.setText(handle_text)
        row.handle_label.setVisible(bool(handle_text))
        self._resort_checkboxes()

    def _get_account(self, account_id: str) -> AccountConfig | None:
        for a in self._accounts:
            if a.account_id == account_id:
                return a
        return None

    def _update_row_style(self, account_id: str):
        row = self._rows.get(account_id)
        cb = self._checkboxes.get(account_id)
        if not row or not cb:
            return
        account = self._get_account(account_id)
        specs = PLATFORM_SPECS_MAP.get(account.platform_id if account else '')
        color = specs.platform_color if specs else tokens.TEXT
        text_color = tokens.legible_accent(color)

        if account_id in self._format_restricted:
            row.name_label.setStyleSheet(
                f'font-size: 13px; font-weight: bold; color: {tokens.TEXT_MUTED};'
                ' font-style: italic;'
            )
            row.handle_label.setStyleSheet(
                f'font-size: 12px; font-weight: 600; color: {tokens.TEXT_SECONDARY}; font-style: italic;'
            )
            row.status_pill.setText('Restricted')
            row.status_pill.setStyleSheet(self._status_pill_style(tokens.WARNING))
            cb.setToolTip('This platform does not support the attached media format.')
        elif account_id in self._count_restricted:
            row.name_label.setStyleSheet(
                f'font-size: 13px; font-weight: bold; color: {tokens.TEXT_MUTED};'
                ' font-style: italic;'
            )
            row.handle_label.setStyleSheet(
                f'font-size: 12px; font-weight: 600; color: {tokens.TEXT_SECONDARY}; font-style: italic;'
            )
            row.status_pill.setText('Restricted')
            row.status_pill.setStyleSheet(self._status_pill_style(tokens.WARNING))
            cb.setToolTip('Too many attachments for this platform.')
        elif account_id in self._available:
            row.name_label.setStyleSheet(
                f'font-size: 13px; font-weight: bold; color: {text_color};'
            )
            row.handle_label.setStyleSheet(
                f'font-size: 12px; font-weight: 600; color: {tokens.TEXT_SECONDARY};'
            )
            row.status_pill.setText('Ready')
            row.status_pill.setStyleSheet(self._status_pill_style(tokens.SUCCESS))
            cb.setToolTip(f'Include {row.name_label.text()} when posting')
        else:
            row.name_label.setStyleSheet(
                f'font-size: 13px; font-weight: bold; color: {text_color}; font-style: italic;'
            )
            row.handle_label.setStyleSheet(
                f'font-size: 12px; font-weight: 600; color: {tokens.TEXT_SECONDARY}; font-style: italic;'
            )
            row.status_pill.setText('Unavailable')
            row.status_pill.setStyleSheet(self._status_pill_style(tokens.TEXT_MUTED))
            cb.setToolTip(f'{row.name_label.text()} is not connected — set it up in Settings.')

    @staticmethod
    def _status_pill_style(color: str) -> str:
        return (
            f'color: {color}; border: 1px solid {color}; border-radius: 10px;'
            f' padding: 2px 10px; font-size: 12px; font-weight: 600;'
            f' background-color: {tokens.with_alpha(color, 0.16)};'
        )

    @staticmethod
    def _format_account_label(
        account: AccountConfig,
        username_override: str | None = None,
    ) -> str:
        specs = PLATFORM_SPECS_MAP.get(account.platform_id)
        base = specs.platform_name if specs else account.platform_id.title()
        username = username_override or account.profile_name
        return _format_platform_label(base, username, account.platform_id)

    def get_platform_label(self, account_id: str) -> str:
        return self._labels.get(account_id, '')

    def _resort_checkboxes(self):
        """Reorder checkboxes when account labels change."""
        self._accounts = sorted(self._accounts, key=self._account_display_sort_key)
        existing = self._checkboxes
        existing_rows = self._rows
        self._checkboxes = {
            account.account_id: existing[account.account_id]
            for account in self._accounts
            if account.account_id in existing
        }
        self._rows = {
            account.account_id: existing_rows[account.account_id]
            for account in self._accounts
            if account.account_id in existing_rows
        }

        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                self._rows_layout.removeWidget(widget)

        for account in self._accounts:
            row = self._rows.get(account.account_id)
            if row:
                self._rows_layout.addWidget(row.frame)

    def _account_display_sort_key(self, account: AccountConfig) -> tuple[str, str]:
        label = self._labels.get(account.account_id)
        if label:
            return (label.strip().casefold(), account.account_id.casefold())
        base, has_username, username, account_id = self._account_sort_key(account)
        return (f'{base}:{has_username}:{username}', account_id)

    @staticmethod
    def _account_sort_key(account: AccountConfig) -> tuple[str, int, str, str]:
        specs = PLATFORM_SPECS_MAP.get(account.platform_id)
        base = specs.platform_name if specs else account.platform_id.title()
        username = PlatformSelector._normalized_username(account.profile_name, account.platform_id)
        has_username = 0 if username else 1
        return (base.casefold(), has_username, username.casefold(), account.account_id.casefold())

    @staticmethod
    def _normalized_username(username: str | None, platform_id: str = '') -> str:
        if not username:
            return ''
        trimmed = username.strip().lstrip('@')
        if platform_id == 'bluesky' and trimmed.endswith('.bsky.social'):
            trimmed = trimmed[: -len('.bsky.social')]
        return trimmed


def _format_platform_label(base: str, username: str | None, platform_id: str = '') -> str:
    """Format a platform label with optional username parenthetical."""
    trimmed = PlatformSelector._normalized_username(username, platform_id)
    if not trimmed:
        return base
    return f'{base} ({trimmed})'
