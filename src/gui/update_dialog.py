"""Update available dialog with release notes."""

import re

from PyQt6.QtWidgets import (
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
            prepared_notes = self._linkify_plain_urls(release_notes)
            if hasattr(notes, 'setMarkdown'):
                notes.setMarkdown(prepared_notes)
            else:
                notes.setPlainText(prepared_notes)
        else:
            notes.setPlainText('No release notes were provided.')
        layout.addWidget(notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        yes_button = buttons.button(QDialogButtonBox.StandardButton.Yes)
        if yes_button is not None:
            yes_button.setText('Download and Install')
        no_button = buttons.button(QDialogButtonBox.StandardButton.No)
        if no_button is not None:
            no_button.setText('Later')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _linkify_plain_urls(markdown_text: str) -> str:
        """Convert plain URLs to Markdown links so Qt keeps full hrefs."""
        pattern = re.compile(r'(?<!\]\()https?://[^\s<>)]+')

        def _replace(match: re.Match[str]) -> str:
            original = match.group(0)
            url = original.rstrip('.,;:')
            suffix = original[len(url) :]
            return f'[{url}]({url}){suffix}'

        return pattern.sub(_replace, markdown_text)
