"""Tests for the searchable emoji picker widgets."""

from emoji import EMOJI_DATA

from src.gui.emoji_picker import CATEGORY_NAMES, EmojiPickerButton, EmojiPickerPopup


def _make_popup(qtbot, recent: list[str] | None = None) -> EmojiPickerPopup:
    popup = EmojiPickerPopup(recent or [], EMOJI_DATA)
    qtbot.addWidget(popup)
    return popup


def _displayed_glyphs(popup: EmojiPickerPopup) -> list[str]:
    return [popup._emoji_list.item(index).text() for index in range(popup._emoji_list.count())]


def test_popup_builds_with_default_category(qtbot):
    popup = _make_popup(qtbot)

    assert popup._category_tabs.tabText(popup._category_tabs.currentIndex()) == (
        'Smileys & Emotion'
    )
    assert popup._emoji_list.count() > 0


def test_search_filters_and_clear_restores_category(qtbot):
    popup = _make_popup(qtbot)
    original = _displayed_glyphs(popup)

    popup._search_box.setText('grinning')

    filtered = _displayed_glyphs(popup)
    assert filtered
    assert len(filtered) < len(original)
    assert all('grinning' in popup._emoji_list.item(i).toolTip() for i in range(len(filtered)))
    assert not popup._category_tabs.isEnabled()

    popup._search_box.clear()

    assert _displayed_glyphs(popup) == original
    assert popup._category_tabs.isEnabled()


def test_selecting_item_emits_expected_glyph(qtbot):
    popup = _make_popup(qtbot)
    item = popup._emoji_list.item(0)

    with qtbot.waitSignal(popup.emoji_selected) as signal:
        popup._on_item_clicked(item)

    assert signal.args == [item.text()]


def test_selecting_item_keeps_popup_open(qtbot):
    popup = _make_popup(qtbot)
    popup.show()
    qtbot.waitUntil(popup.isVisible)

    popup._on_item_clicked(popup._emoji_list.item(0))

    assert popup.isVisible()


def test_category_switching_changes_items(qtbot):
    popup = _make_popup(qtbot)
    smileys = set(_displayed_glyphs(popup))

    popup._category_tabs.setCurrentIndex(CATEGORY_NAMES.index('Animals & Nature'))

    animals = set(_displayed_glyphs(popup))
    assert animals
    assert animals != smileys


def test_recent_emoji_round_trip_mru_dedup_and_cap(qtbot):
    button = EmojiPickerButton()
    qtbot.addWidget(button)
    recent = [f'emoji-{index}' for index in range(30)]

    button.set_recent_emoji([recent[0], recent[0], *recent[1:]])

    assert button.get_recent_emoji() == recent[:24]

    button._on_popup_emoji_selected(recent[5])
    assert button.get_recent_emoji() == [recent[5], *recent[:5], *recent[6:24]]

    button._on_popup_emoji_selected('\U0001f600')
    assert button.get_recent_emoji() == [
        '\U0001f600',
        recent[5],
        *recent[:5],
        *recent[6:23],
    ]
    assert len(button.get_recent_emoji()) == 24
