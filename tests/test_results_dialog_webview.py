"""Tests for results dialog with WebView platform states."""

from PyQt6.QtWidgets import QLabel

from src.gui.results_dialog import ResultsDialog
from src.utils.constants import PostResult


def test_webview_posted_with_url(qtbot):
    """Test WebView result with URL captured."""
    results = [
        PostResult(
            success=True,
            platform='FetLife',
            post_url='https://fetlife.com/posts/123456',
            url_captured=True,
            user_confirmed=True,
        )
    ]
    dialog = ResultsDialog(results)
    qtbot.addWidget(dialog)

    labels = dialog.findChildren(QLabel)
    assert any('https://fetlife.com/posts/123456' in label.text() for label in labels)
    assert any('Posted successfully!' in label.text() for label in labels)


def test_webview_posted_without_url(qtbot):
    """Test WebView result without URL captured (link unavailable)."""
    results = [
        PostResult(
            success=True,
            platform='OnlyFans',
            post_url=None,
            url_captured=False,
            user_confirmed=True,
        )
    ]
    dialog = ResultsDialog(results)
    qtbot.addWidget(dialog)

    labels = dialog.findChildren(QLabel)
    # Should show "Posted (link unavailable)"
    assert any('Posted' in label.text() and 'unavailable' in label.text() for label in labels)


def test_webview_not_confirmed(qtbot):
    """Test WebView result when user didn't click Post."""
    results = [
        PostResult(
            success=False,
            platform='Snapchat',
            post_url=None,
            url_captured=False,
            user_confirmed=False,
            error_code='WV-SUBMIT-TIMEOUT',
            error_message='Not confirmed',
        )
    ]
    dialog = ResultsDialog(results)
    qtbot.addWidget(dialog)

    labels = dialog.findChildren(QLabel)
    assert any(
        'Not confirmed' in label.text() or 'failed' in label.text().lower() for label in labels
    )


def test_mixed_api_and_webview_results(qtbot):
    """Test results dialog with mix of API and WebView platforms."""
    results = [
        # API platform with URL
        PostResult(
            success=True,
            platform='Twitter',
            post_url='https://twitter.com/user/status/123',
            url_captured=True,
            user_confirmed=False,  # API platforms don't need user confirmation
        ),
        # WebView with URL
        PostResult(
            success=True,
            platform='FetLife',
            post_url='https://fetlife.com/posts/456',
            url_captured=True,
            user_confirmed=True,
        ),
        # WebView without URL
        PostResult(
            success=True,
            platform='OnlyFans',
            post_url=None,
            url_captured=False,
            user_confirmed=True,
        ),
        # WebView not confirmed
        PostResult(
            success=False,
            platform='Fansly',
            post_url=None,
            url_captured=False,
            user_confirmed=False,
            error_code='WV-SUBMIT-TIMEOUT',
        ),
    ]
    dialog = ResultsDialog(results)
    qtbot.addWidget(dialog)

    labels = dialog.findChildren(QLabel)
    text = ' '.join(label.text() for label in labels)

    # All platforms should be mentioned
    assert 'Twitter' in text
    assert 'FetLife' in text
    assert 'OnlyFans' in text
    assert 'Fansly' in text

    # Should have 2 clickable URLs
    links = [label for label in labels if 'https://' in label.text()]
    assert len(links) >= 2


def test_webview_error_codes(qtbot):
    """Test that WebView-specific error codes are displayed."""
    results = [
        PostResult(
            success=False,
            platform='Snapchat',
            error_code='WV-LOAD-FAILED',
            error_message='Could not load platform website.',
        ),
        PostResult(
            success=False,
            platform='OnlyFans',
            error_code='WV-SESSION-EXPIRED',
            error_message='Platform session expired.',
        ),
    ]
    dialog = ResultsDialog(results)
    qtbot.addWidget(dialog)

    labels = dialog.findChildren(QLabel)
    text = ' '.join(label.text() for label in labels)

    assert 'WV-LOAD-FAILED' in text or 'load' in text.lower()
    assert 'WV-SESSION-EXPIRED' in text or 'session' in text.lower()
