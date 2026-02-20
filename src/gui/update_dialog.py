"""Update available dialog with release notes."""

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
)


class UpdateAvailableDialog(QDialog):
    """Dialog showing update details and release notes."""

    def __init__(
        self,
        parent,
        *,
        title: str,
        latest_version: str,
        current_version: str,
        release_label: str,
        release_name: str,
        release_notes: str,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 520)

        layout = QVBoxLayout(self)

        header = QLabel(
            f'Version {latest_version} ({release_label}) is available.\n'
            f"You're currently using {current_version}."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        if release_name:
            name_label = QLabel(release_name)
            name_label.setWordWrap(True)
            layout.addWidget(name_label)

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMinimumHeight(260)
        if release_notes:
            if hasattr(notes, 'setMarkdown'):
                notes.setMarkdown(release_notes)
            else:
                notes.setPlainText(release_notes)
        else:
            notes.setPlainText('No release notes were provided.')
        layout.addWidget(notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
        yes_button = buttons.button(QDialogButtonBox.Yes)
        if yes_button is not None:
            yes_button.setText('Download and Install')
        no_button = buttons.button(QDialogButtonBox.No)
        if no_button is not None:
            no_button.setText('Later')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
