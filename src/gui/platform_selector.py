"""Platform selection checkboxes."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget


class PlatformSelector(QWidget):
    """Checkboxes for selecting which platforms to post to."""

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checkboxes = {}
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel('Post to:')
        self._label.setStyleSheet('font-weight: bold; font-size: 13px; color: palette(text);')
        layout.addWidget(self._label)

        layout.addSpacing(10)

        self._tw_cb = QCheckBox('Twitter')
        self._tw_cb.setChecked(True)
        self._tw_cb.setStyleSheet('font-size: 13px; color: #1DA1F2;')
        self._tw_cb.stateChanged.connect(self._on_changed)
        layout.addWidget(self._tw_cb)
        self._checkboxes['twitter'] = self._tw_cb

        layout.addSpacing(20)

        self._bs_cb = QCheckBox('Bluesky')
        self._bs_cb.setChecked(True)
        self._bs_cb.setStyleSheet('font-size: 13px; color: #0085FF;')
        self._bs_cb.stateChanged.connect(self._on_changed)
        layout.addWidget(self._bs_cb)
        self._checkboxes['bluesky'] = self._bs_cb

        layout.addStretch()

    def _on_changed(self, _state):
        self.selection_changed.emit(self.get_selected())

    def get_selected(self) -> list[str]:
        return [name for name, cb in self._checkboxes.items() if cb.isChecked()]

    def set_selected(self, platforms: list[str]):
        for name, cb in self._checkboxes.items():
            cb.setChecked(name in platforms and cb.isEnabled())

    def set_platform_enabled(self, name: str, enabled: bool):
        cb = self._checkboxes.get(name)
        if not cb:
            return
        cb.setEnabled(enabled)
        if not enabled:
            cb.setChecked(False)

    def get_enabled(self) -> list[str]:
        return [name for name, cb in self._checkboxes.items() if cb.isEnabled()]

    def set_platform_username(self, name: str, username: str | None):
        cb = self._checkboxes.get(name)
        if not cb:
            return
        base = 'Twitter' if name == 'twitter' else 'Bluesky'
        label = self._format_platform_label(base, username)
        cb.setText(label)

    @staticmethod
    def _format_platform_label(base: str, username: str | None) -> str:
        if not username:
            return base
        trimmed = username.strip().lstrip('@')
        if base.lower() == 'bluesky' and trimmed.endswith('.bsky.social'):
            trimmed = trimmed[: -len('.bsky.social')]
        if not trimmed:
            return base
        return f'{base} ({trimmed})'

    def get_platform_label(self, name: str) -> str:
        cb = self._checkboxes.get(name)
        return cb.text() if cb else ''
