"""Platform selection checkboxes."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QLabel, QWidget

from src.utils.constants import PLATFORM_SPECS_MAP, AccountConfig


class PlatformSelector(QWidget):
    """Checkboxes for selecting which platform accounts to post to.

    Dynamically builds checkboxes from a list of AccountConfig entries.
    Unavailable platforms (no credentials/session) cannot be checked,
    but checked platforms can always be unchecked regardless of availability.
    """

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._accounts: list[AccountConfig] = []
        self._available: set[str] = set()
        self._format_restricted: set[str] = set()
        self._format_notice: QLabel | None = None
        self._init_ui()

    def _init_ui(self):
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(20)
        self._layout.setVerticalSpacing(4)

        self._label = QLabel('Post to:')
        self._label.setStyleSheet('font-weight: bold; font-size: 13px; color: palette(text);')
        self._layout.addWidget(self._label, 0, 0)

        self._format_notice = QLabel()
        self._format_notice.setStyleSheet(
            'color: #FF9800; font-size: 12px; font-style: italic; padding: 2px 0;'
        )
        self._format_notice.setWordWrap(True)
        self._format_notice.setVisible(False)
        self._layout.addWidget(self._format_notice, 0, 1)

    def set_accounts(self, accounts: list[AccountConfig]):
        """Rebuild checkboxes from account list."""
        # Clear existing
        for cb in self._checkboxes.values():
            cb.setParent(None)
            cb.deleteLater()
        self._checkboxes.clear()
        self._accounts = accounts
        self._available.clear()

        # Build checkboxes in a 2-column grid
        for i, account in enumerate(accounts):
            specs = PLATFORM_SPECS_MAP.get(account.platform_id)
            color = specs.platform_color if specs else '#000000'
            label = self._format_account_label(account)

            cb = QCheckBox(label)
            cb.setChecked(account.enabled)
            cb.setStyleSheet(f'font-size: 13px; color: {color};')
            cb.clicked.connect(
                lambda _checked, aid=account.account_id: self._on_checkbox_clicked(aid)
            )

            row = (i // 2) + 1  # row 0 is the "Post to:" label
            col = i % 2
            self._layout.addWidget(cb, row, col)
            self._checkboxes[account.account_id] = cb

    def _on_checkbox_clicked(self, account_id: str):
        cb = self._checkboxes.get(account_id)
        if not cb:
            return
        # Block checking unavailable or format-restricted platforms, allow unchecking
        if cb.isChecked() and (
            account_id not in self._available or account_id in self._format_restricted
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
        self._update_checkbox_style(account_id)

    def get_enabled(self) -> list[str]:
        return [name for name in self._checkboxes if name in self._available]

    def set_format_restriction(self, restricted_account_ids: set[str], notice_text: str = ''):
        """Restrict platforms that don't support the attached image format.

        Unchecks and dims any accounts in restricted_account_ids,
        and shows an explanatory notice. Pass an empty set to clear.
        """
        self._format_restricted = set(restricted_account_ids)
        show_notice = bool(self._format_restricted)
        if self._format_notice:
            self._format_notice.setText(notice_text)
            self._format_notice.setVisible(show_notice)

        for account_id in self._format_restricted:
            cb = self._checkboxes.get(account_id)
            if cb and cb.isChecked():
                cb.setChecked(False)

        for account_id in self._checkboxes:
            self._update_checkbox_style(account_id)

        if self._format_restricted:
            self.selection_changed.emit(self.get_selected())

    def set_platform_username(self, account_id: str, username: str | None):
        cb = self._checkboxes.get(account_id)
        if not cb:
            return
        account = self._get_account(account_id)
        if not account:
            return
        label = self._format_account_label(account, username_override=username)
        cb.setText(label)

    def _get_account(self, account_id: str) -> AccountConfig | None:
        for a in self._accounts:
            if a.account_id == account_id:
                return a
        return None

    def _update_checkbox_style(self, account_id: str):
        cb = self._checkboxes.get(account_id)
        if not cb:
            return
        account = self._get_account(account_id)
        specs = PLATFORM_SPECS_MAP.get(account.platform_id if account else '')
        color = specs.platform_color if specs else '#000000'
        if account_id in self._format_restricted:
            cb.setStyleSheet('font-size: 13px; color: #888888; font-style: italic;')
            cb.setToolTip('This platform does not support the attached image format.')
        elif account_id in self._available:
            cb.setStyleSheet(f'font-size: 13px; color: {color};')
            cb.setToolTip('')
        else:
            cb.setStyleSheet(f'font-size: 13px; color: {color}; font-style: italic;')
            cb.setToolTip('')

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
        cb = self._checkboxes.get(account_id)
        return cb.text() if cb else ''


def _format_platform_label(base: str, username: str | None, platform_id: str = '') -> str:
    """Format a platform label with optional username parenthetical."""
    if not username:
        return base
    trimmed = username.strip().lstrip('@')
    if platform_id == 'bluesky' and trimmed.endswith('.bsky.social'):
        trimmed = trimmed[: -len('.bsky.social')]
    if not trimmed:
        return base
    return f'{base} ({trimmed})'
