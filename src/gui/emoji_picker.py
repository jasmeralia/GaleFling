"""Searchable emoji picker widgets for the post composer."""

from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from emoji import EMOJI_DATA  # type: ignore[import-not-found, import-untyped]
from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent, QKeySequence, QShortcut, QShowEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.gui.icon_utils import tinted_icon
from src.resources.emoji_categories import EMOJI_CATEGORIES
from src.utils import tokens

CATEGORY_NAMES = (
    'Recent',
    'Smileys & Emotion',
    'People & Body',
    'Animals & Nature',
    'Food & Drink',
    'Travel & Places',
    'Activities',
    'Objects',
    'Symbols',
    'Flags',
)

_UI_ICONS_DIR = Path(__file__).resolve().parent.parent / 'resources' / 'icons' / 'ui'

_CATEGORY_ICONS: dict[str, str] = {
    'Recent': 'history.svg',
    'Smileys & Emotion': 'mood.svg',
    'People & Body': 'waving_hand.svg',
    'Animals & Nature': 'pets.svg',
    'Food & Drink': 'restaurant.svg',
    'Travel & Places': 'flight.svg',
    'Activities': 'insights.svg',
    'Objects': 'category.svg',
    'Symbols': 'emoji_symbols.svg',
    'Flags': 'flag.svg',
}

_RAIL_BUTTON_QSS = f"""
QToolButton {{
    background-color: {tokens.SURFACE};
    border: 1px solid {tokens.BORDER};
    border-radius: 4px;
    padding: 4px;
}}
QToolButton:hover {{
    border-color: {tokens.ACCENT};
}}
QToolButton:checked {{
    background-color: {tokens.SURFACE_RAISED};
    border-color: {tokens.ACCENT};
}}
QToolButton:disabled {{
    background-color: {tokens.SURFACE};
    border-color: {tokens.BORDER};
}}
"""

_SKIN_TONES = set(range(0x1F3FB, 0x1F400))
_HAIR_COMPONENTS = set(range(0x1F9B0, 0x1F9B4))
_GENDER_SIGNS = {0x2640, 0x2642}
_REGIONAL_INDICATORS = set(range(0x1F1E6, 0x1F200))


def _icon(name: str) -> QIcon:
    return tinted_icon(_UI_ICONS_DIR / name, tokens.TEXT_SECONDARY)


class _EmojiEntry(NamedTuple):
    glyph: str
    name: str
    search_terms: tuple[str, ...]
    category: str


class EmojiPickerPopup(QFrame):
    """Popup grid for browsing and searching the emoji dataset."""

    emoji_selected = pyqtSignal(str)

    def __init__(
        self,
        recent_emoji: list[str],
        emoji_data: Mapping[str, Mapping[str, object]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup)
        self._recent_emoji = list(recent_emoji)
        self._entries = self._build_entries(emoji_data)
        self._entries_by_glyph = {entry.glyph: entry for entry in self._entries}
        self._category_buttons: dict[str, QToolButton] = {}
        self._current_category = ''

        self.setFixedSize(360, 420)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText('Search emoji...')
        self._search_box.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_box)

        content = QHBoxLayout()
        content.setSpacing(4)

        rail_layout = QVBoxLayout()
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(2)

        category_group = QButtonGroup(self)
        category_group.setExclusive(True)

        for category in CATEGORY_NAMES:
            button = QToolButton()
            button.setIcon(_icon(_CATEGORY_ICONS[category]))
            button.setIconSize(QSize(20, 20))
            button.setCheckable(True)
            button.setFixedSize(32, 32)
            button.setToolTip(category)
            button.setStyleSheet(_RAIL_BUTTON_QSS)
            button.clicked.connect(
                lambda _checked, cat=category: self._on_category_clicked(cat),
            )
            category_group.addButton(button)
            self._category_buttons[category] = button
            rail_layout.addWidget(button)

        rail_layout.addStretch()
        content.addLayout(rail_layout)

        self._emoji_list = QListWidget()
        self._emoji_list.setViewMode(QListView.ViewMode.IconMode)
        self._emoji_list.setFlow(QListView.Flow.LeftToRight)
        self._emoji_list.setWrapping(True)
        self._emoji_list.setResizeMode(QListView.ResizeMode.Adjust)
        self._emoji_list.setUniformItemSizes(True)
        self._emoji_list.setSpacing(2)
        self._emoji_list.itemClicked.connect(self._on_item_clicked)
        content.addWidget(self._emoji_list, stretch=1)

        layout.addLayout(content, stretch=1)

        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.activated.connect(self.close)

        default_category = 'Recent' if self._recent_emoji else 'Smileys & Emotion'
        self._set_active_category(default_category)

    @staticmethod
    def _build_entries(
        emoji_data: Mapping[str, Mapping[str, object]],
    ) -> list[_EmojiEntry]:
        entries = []
        for glyph, metadata in emoji_data.items():
            if not EmojiPickerPopup._is_base_emoji(glyph, metadata):
                continue

            raw_name = metadata.get('en')
            if not isinstance(raw_name, str):
                continue
            name = raw_name.strip(':').replace('_', ' ')

            raw_aliases = metadata.get('alias', [])
            aliases: tuple[str, ...]
            if isinstance(raw_aliases, str):
                aliases = (raw_aliases.strip(':').replace('_', ' '),)
            elif isinstance(raw_aliases, (list, tuple)):
                aliases = tuple(
                    alias.strip(':').replace('_', ' ')
                    for alias in raw_aliases
                    if isinstance(alias, str)
                )
            else:
                aliases = ()
            entries.append(
                _EmojiEntry(
                    glyph=glyph,
                    name=name,
                    search_terms=(name, *aliases),
                    category=EMOJI_CATEGORIES.get(glyph, 'Objects'),
                )
            )
        return entries

    @staticmethod
    def _is_base_emoji(glyph: str, metadata: Mapping[str, object]) -> bool:
        if metadata.get('status') != 2:
            return False
        codepoints = {ord(char) for char in glyph}
        if codepoints & (_SKIN_TONES | _HAIR_COMPONENTS | _GENDER_SIGNS):
            return False
        return not (len(glyph) == 1 and codepoints & _REGIONAL_INDICATORS)

    def _set_active_category(self, category: str) -> None:
        self._current_category = category
        self._category_buttons[category].setChecked(True)
        self._show_category(category)

    def _show_entries(self, entries: list[_EmojiEntry]) -> None:
        self._emoji_list.clear()
        font = self._emoji_list.font()
        font.setPointSize(20)
        for entry in entries:
            item = QListWidgetItem(entry.glyph)
            item.setData(Qt.ItemDataRole.UserRole, entry.glyph)
            item.setToolTip(entry.name)
            item.setFont(font)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._emoji_list.addItem(item)

    def _show_category(self, category: str) -> None:
        if category == 'Recent':
            entries = [
                self._entries_by_glyph[glyph]
                for glyph in self._recent_emoji
                if glyph in self._entries_by_glyph
            ]
        else:
            entries = [entry for entry in self._entries if entry.category == category]
        self._show_entries(entries)

    def _on_category_clicked(self, category: str) -> None:
        if self._search_box.text():
            return
        self._current_category = category
        self._show_category(category)

    def _on_search_changed(self, text: str) -> None:
        query = text.strip().casefold()
        for button in self._category_buttons.values():
            button.setEnabled(not query)
        if not query:
            self._show_category(self._current_category)
            return
        matches = [
            entry
            for entry in self._entries
            if any(query in term.casefold() for term in entry.search_terms)
        ]
        self._show_entries(matches)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        glyph = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(glyph, str):
            self.emoji_selected.emit(glyph)

    def showEvent(self, event: QShowEvent | None) -> None:  # noqa: N802
        super().showEvent(event)
        self._search_box.setFocus()

    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802
        if event is None:
            return
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)


class EmojiPickerButton(QToolButton):
    """Tool button that owns the picker popup and its recent-emoji MRU."""

    emoji_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setIcon(_icon('mood.svg'))
        self.setIconSize(QSize(20, 20))
        self._recent_emoji: list[str] = []
        self._popup: EmojiPickerPopup | None = None
        self.clicked.connect(self._show_popup)

    def set_recent_emoji(self, recent: list[str]) -> None:
        self._recent_emoji = self._normalize_recent(recent)

    def get_recent_emoji(self) -> list[str]:
        return list(self._recent_emoji)

    @staticmethod
    def _normalize_recent(recent: list[str]) -> list[str]:
        normalized = []
        for glyph in recent:
            if isinstance(glyph, str) and glyph and glyph not in normalized:
                normalized.append(glyph)
            if len(normalized) == 24:
                break
        return normalized

    def _show_popup(self, _checked: bool = False) -> None:
        if self._popup is not None:
            self._popup.close()
        popup = EmojiPickerPopup(self._recent_emoji, EMOJI_DATA, self)
        popup.emoji_selected.connect(self._on_popup_emoji_selected)
        self._popup = popup
        # Anchor the popup's right edge to the button's right edge, so it
        # opens leftward instead of running off the window's right side.
        anchor = self.mapToGlobal(QPoint(self.width(), self.height()))
        popup.move(anchor.x() - popup.width(), anchor.y())
        popup.show()

    def _on_popup_emoji_selected(self, glyph: str) -> None:
        self._recent_emoji = self._normalize_recent([glyph, *self._recent_emoji])
        self.emoji_selected.emit(glyph)
