"""Tests for SetupWizard step progress rail."""

from PyQt6.QtWidgets import QWizard

from src.gui.setup_wizard import (
    _FIXED_WIZARD_STEP_LABELS,
    _META_PROVIDER_DEFS,
    SetupWizard,
    _available_webview_platform_defs,
)
from src.utils import tokens
from tests.test_setup_wizard_theme import DummyAuthManager


def test_step_rail_matches_registered_pages(qtbot):
    wizard = SetupWizard(DummyAuthManager())
    qtbot.addWidget(wizard)

    expected_labels = (
        _FIXED_WIZARD_STEP_LABELS
        + [display_name for _provider_id, display_name, _account_defs in _META_PROVIDER_DEFS]
        + [
            platform_name
            for _platform_id, platform_name, _account_id in _available_webview_platform_defs()
        ]
    )

    rail_labels = [label for label, _page_id in wizard._step_rail._steps]
    assert rail_labels == expected_labels
    assert len(rail_labels) == len(wizard.pageIds())


def test_step_rail_is_reparented_into_the_current_page_and_full_width(qtbot):
    """Regression test: the rail was once squashed into a ~100x56 cell because
    it relied on introspecting QWizard's internal (non-public) chrome layout,
    which produced a visually broken, overlapping rail on this Qt build even
    though every purely-internal-state assertion still passed. Assert real
    geometry, not just _step_rail's own tracked state.
    """
    wizard = SetupWizard(DummyAuthManager())
    qtbot.addWidget(wizard)
    wizard.show()
    qtbot.waitExposed(wizard)

    first_id = wizard.currentId()
    first_page = wizard.page(first_id)
    assert first_page is not None
    assert first_page.layout().indexOf(wizard._step_rail) == 0
    assert wizard._step_rail.width() > 200

    wizard.next()
    qtbot.waitUntil(lambda: wizard.currentId() != first_id)

    second_page = wizard.page(wizard.currentId())
    assert second_page is not None
    assert second_page.layout().indexOf(wizard._step_rail) == 0
    assert wizard._step_rail.width() > 200


def test_step_rail_updates_on_current_id_changed(qtbot):
    wizard = SetupWizard(DummyAuthManager())
    qtbot.addWidget(wizard)
    wizard.show()
    qtbot.waitExposed(wizard)

    first_id = wizard.currentId()
    assert wizard._step_rail._index_for_page_id(first_id) == 0
    assert tokens.ACCENT in wizard._step_rail._step_items[0]._label.styleSheet()

    wizard.next()
    qtbot.waitUntil(lambda: wizard.currentId() != first_id)

    second_id = wizard.currentId()
    assert wizard._step_rail._index_for_page_id(second_id) == 1
    assert second_id in wizard._visited_page_ids
    assert tokens.SUCCESS in wizard._step_rail._step_items[0]._label.styleSheet()
    assert tokens.ACCENT in wizard._step_rail._step_items[1]._label.styleSheet()

    wizard.back()
    qtbot.waitUntil(lambda: wizard.currentId() == first_id)

    assert tokens.ACCENT in wizard._step_rail._step_items[0]._label.styleSheet()
    assert tokens.TEXT_MUTED in wizard._step_rail._step_items[1]._label.styleSheet()


def test_setup_wizard_still_uses_modern_style(qtbot):
    wizard = SetupWizard(DummyAuthManager())
    qtbot.addWidget(wizard)
    assert wizard.wizardStyle() == QWizard.WizardStyle.ModernStyle
