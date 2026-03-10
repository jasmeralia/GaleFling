"""Tests for the WebView confirmation panel dialog."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from src.gui.webview_panel import WebViewPanel, _StatusRow
from src.utils.constants import PostResult


class FakeWebViewPlatform:
    def __init__(
        self,
        account_id: str,
        profile_name: str,
        *,
        confirmed: bool = False,
        captured_url: str | None = None,
    ):
        self.account_id = account_id
        self.profile_name = profile_name
        self._confirmed = confirmed
        self._captured_url = captured_url
        self.navigate_calls = 0
        self.start_poll_calls = 0
        self.stop_poll_calls = 0
        self.mark_confirmed_calls = 0

    def get_platform_name(self) -> str:
        return f'FakePlatform ({self.account_id})'

    def create_webview(self, parent=None) -> QWidget:
        return QWidget(parent)

    def navigate_to_composer(self):
        self.navigate_calls += 1

    def start_success_polling(self):
        self.start_poll_calls += 1

    def stop_success_polling(self):
        self.stop_poll_calls += 1

    def build_result(self) -> PostResult:
        if self._confirmed:
            return PostResult(
                success=True,
                platform=self.get_platform_name(),
                post_url=self._captured_url,
                account_id=self.account_id,
                profile_name=self.profile_name,
                user_confirmed=True,
                url_captured=self._captured_url is not None,
            )
        return PostResult(
            success=False,
            platform=self.get_platform_name(),
            error_code='WV-SUBMIT-TIMEOUT',
            error_message='Post was not confirmed.',
            account_id=self.account_id,
            profile_name=self.profile_name,
            user_confirmed=False,
        )

    def mark_confirmed(self):
        self.mark_confirmed_calls += 1
        self._confirmed = True

    @property
    def is_post_confirmed(self) -> bool:
        return self._confirmed

    @property
    def captured_post_url(self) -> str | None:
        return self._captured_url


def test_status_row_transitions(qtbot):
    row = _StatusRow('Example')
    qtbot.addWidget(row)

    row.set_pending('Posting...')
    assert row._status.text() == 'Posting...'
    row.set_success('Posted!')
    assert row._status.text() == 'Posted!'
    row.set_failure('Failed')
    assert row._status.text() == 'Failed'


def test_webview_panel_initializes_api_and_webview_sections(qtbot):
    api_results = [
        PostResult(success=True, platform='Twitter', profile_name='tw-main'),
        PostResult(
            success=False,
            platform='Bluesky',
            error_code='POST-FAILED',
            error_message='error',
            profile_name='bsky-main',
        ),
    ]
    platform_a = FakeWebViewPlatform('snap_1', 'snap-main')
    platform_b = FakeWebViewPlatform('of_1', 'of-main')

    panel = WebViewPanel(api_results, [platform_a, platform_b])
    qtbot.addWidget(panel)

    assert panel._tabs.count() == 2
    assert platform_a.navigate_calls == 1
    assert platform_a.start_poll_calls == 1
    assert platform_b.navigate_calls == 1
    assert platform_b.start_poll_calls == 1
    assert panel._status_rows['snap_1']._status.text() == 'Waiting for you to post...'


def test_webview_panel_mark_current_done_updates_current_tab(qtbot):
    platform_a = FakeWebViewPlatform('snap_1', 'snap-main')
    platform_b = FakeWebViewPlatform('of_1', 'of-main')
    panel = WebViewPanel([], [platform_a, platform_b])
    qtbot.addWidget(panel)

    panel._tabs.setCurrentIndex(1)
    panel._mark_current_done()

    assert platform_a.mark_confirmed_calls == 0
    assert platform_b.mark_confirmed_calls == 1
    assert panel._status_rows['of_1']._status.text() == 'Posted (link unavailable)'


def test_webview_panel_mark_current_done_no_platforms_is_noop(qtbot):
    panel = WebViewPanel([], [])
    qtbot.addWidget(panel)

    panel._mark_current_done()
    assert panel._check_timer.isActive() is True


def test_webview_panel_check_confirmed_emits_when_all_done(qtbot):
    platform_a = FakeWebViewPlatform(
        'snap_1', 'snap-main', confirmed=True, captured_url='https://x/y'
    )
    platform_b = FakeWebViewPlatform('of_1', 'of-main', confirmed=False)
    panel = WebViewPanel([], [platform_a, platform_b])
    qtbot.addWidget(panel)

    emitted = []
    panel.all_confirmed.connect(lambda: emitted.append(True))

    panel._check_confirmed()
    assert emitted == []
    assert panel._check_timer.isActive() is True

    platform_b._confirmed = True
    panel._check_confirmed()
    assert emitted == [True]
    assert panel._check_timer.isActive() is False


def test_webview_panel_update_status_handles_missing_row_and_checkmark(qtbot):
    platform = FakeWebViewPlatform(
        'snap_1', 'snap-main', confirmed=True, captured_url='https://x/y'
    )
    panel = WebViewPanel([], [platform])
    qtbot.addWidget(panel)

    panel._update_status(platform)
    assert panel._tabs.tabText(0).startswith('✔ ')

    # Calling again should not duplicate the checkmark.
    panel._update_status(platform)
    assert panel._tabs.tabText(0).count('✔') == 1

    missing = FakeWebViewPlatform('missing', 'none', confirmed=True)
    panel._update_status(missing)


def test_webview_panel_get_results_stops_polling_and_collects_results(qtbot):
    platform_a = FakeWebViewPlatform(
        'snap_1', 'snap-main', confirmed=True, captured_url='https://x/y'
    )
    platform_b = FakeWebViewPlatform('of_1', 'of-main', confirmed=False)
    panel = WebViewPanel([], [platform_a, platform_b])
    qtbot.addWidget(panel)

    results = panel.get_results()

    assert len(results) == 2
    assert platform_a.stop_poll_calls == 1
    assert platform_b.stop_poll_calls == 1
    assert results[0].success is True
    assert results[1].success is False


def test_webview_panel_close_event_stops_timers_and_platform_polling(qtbot):
    platform = FakeWebViewPlatform('snap_1', 'snap-main')
    panel = WebViewPanel([], [platform])
    qtbot.addWidget(panel)

    panel.close()

    assert panel._check_timer.isActive() is False
    assert platform.stop_poll_calls >= 1
