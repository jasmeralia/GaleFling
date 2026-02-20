from PyQt5.QtWidgets import QDialogButtonBox, QTextBrowser

from src.gui.update_dialog import UpdateAvailableDialog


def test_update_dialog_renders_markdown_links(qtbot):
    dialog = UpdateAvailableDialog(
        None,
        title='Update Available',
        latest_version='1.2.3',
        current_version='1.2.0',
        release_label='stable',
        release_name='Release 1.2.3',
        release_notes='See [notes](https://example.com).',
    )
    qtbot.addWidget(dialog)

    notes = dialog.findChild(QTextBrowser)
    assert notes is not None
    html = notes.toHtml()
    assert 'href="https://example.com"' in html
    assert notes.openExternalLinks() is True


def test_update_dialog_download_button_label(qtbot):
    dialog = UpdateAvailableDialog(
        None,
        title='Update Available',
        latest_version='1.2.3',
        current_version='1.2.0',
        release_label='stable',
        release_name='Release 1.2.3',
        release_notes='Notes',
    )
    qtbot.addWidget(dialog)

    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    yes_button = buttons.button(QDialogButtonBox.Yes)
    assert yes_button is not None
    assert yes_button.text() == 'Download and Install'
