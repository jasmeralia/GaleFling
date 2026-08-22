from __future__ import annotations

from dataclasses import dataclass

import pytest
from PyQt6.QtWidgets import QDialog

from src.core.meta_oauth import FacebookPageInfo, OAuthFlowResult
from src.gui import meta_connect_dialog as module
from src.gui.meta_connect_dialog import MetaConnectDialog, MetaOAuthWorker, _compute_expires_at


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in self.callbacks:
            callback(*args)


class FakeDialogWorker:
    def __init__(self, *_args, **_kwargs):
        self.status_changed = Signal()
        self.success = Signal()
        self.failed = Signal()
        self.running = False
        self.terminated = False
        self.waited = False

    def start(self):
        self.running = True

    def isRunning(self):  # noqa: N802
        return self.running

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, _timeout):
        self.waited = True


class DummyAuthManager:
    def __init__(self):
        self.credentials = {}
        self.accounts = []

    def get_meta_oauth_redirect_uri(self):
        return 'https://oauth.example.com/callback'

    def save_account_credentials(self, account_id, credentials):
        self.credentials[account_id] = credentials

    def add_account(self, account):
        self.accounts.append(account)


@dataclass
class FakeFlow:
    short_token: str = 'short'
    long_token: str = 'long'
    pages: list[FacebookPageInfo] | None = None
    raise_on_info: bool = False

    def build_auth_url(self, redirect_uri, state):
        assert redirect_uri == 'https://oauth.example.com/callback'
        assert state == 'state'
        return 'https://meta.example.com/authorize'

    def exchange_code(self, code, redirect_uri):
        assert code == 'code'
        assert redirect_uri == 'https://oauth.example.com/callback'
        return {'access_token': self.short_token}

    def exchange_long_lived(self, token):
        assert token == 'short'
        return {'access_token': self.long_token, 'expires_in': 3600}

    def fetch_user_info(self, token):
        if self.raise_on_info:
            raise RuntimeError('profile unavailable')
        assert token == 'long'
        return {'id': 123, 'username': 'profile'}

    def fetch_facebook_pages(self, token):
        assert token == 'long'
        return self.pages or []


def _run_worker(monkeypatch, callback, *, provider='meta_threads', flow=None):
    servers = []

    class FakeServer:
        def __init__(self, port):
            assert port == 8765
            self.shutdown_called = False
            servers.append(self)

        def start(self):
            pass

        def get_callback(self, timeout):
            assert timeout == 180
            return callback

        def shutdown(self):
            self.shutdown_called = True

    monkeypatch.setattr(module, 'find_free_port', lambda: 8765)
    monkeypatch.setattr(module, 'make_state', lambda _port: 'state')
    monkeypatch.setattr(module, 'MetaOAuthCallbackServer', FakeServer)
    opened = []
    monkeypatch.setattr(module.webbrowser, 'open', opened.append)
    worker = MetaOAuthWorker(
        flow or FakeFlow(),
        provider,
        f'{provider}_1',
        'https://oauth.example.com/callback',
    )
    statuses = []
    successes = []
    failures = []
    worker.status_changed.connect(statuses.append)
    worker.success.connect(successes.append)
    worker.failed.connect(failures.append)
    worker.run()
    assert servers[0].shutdown_called
    return statuses, successes, failures, opened


def test_meta_oauth_worker_completes_threads_flow(monkeypatch):
    statuses, successes, failures, opened = _run_worker(monkeypatch, ('code', 'state', None))

    assert failures == []
    assert opened == ['https://meta.example.com/authorize']
    assert statuses[-1] == 'Fetching account information...'
    result = successes[0]
    assert result.provider == 'meta_threads'
    assert result.external_account_id == '123'
    assert result.external_account_name == 'profile'
    assert result.access_token == 'long'
    assert result.expires_at is not None


def test_meta_oauth_worker_fetches_facebook_pages(monkeypatch):
    page = FacebookPageInfo('page-1', 'Page One', 'page-token')
    statuses, successes, failures, _opened = _run_worker(
        monkeypatch,
        ('code', 'state', None),
        provider='meta_facebook_page',
        flow=FakeFlow(pages=[page]),
    )

    assert failures == []
    assert statuses[-1] == 'Fetching Facebook Pages...'
    assert successes[0].page_list == [page]


@pytest.mark.parametrize(
    ('callback', 'flow', 'expected'),
    [
        (None, FakeFlow(), 'Timed out waiting for authorization'),
        (('code', 'state', 'access_denied'), FakeFlow(), 'Authorization denied: access_denied'),
        (('code', 'wrong', None), FakeFlow(), 'State mismatch'),
        ((None, 'state', None), FakeFlow(), 'No authorization code received'),
        (('code', 'state', None), FakeFlow(short_token=''), 'no access_token'),
        (('code', 'state', None), FakeFlow(long_token=''), 'Long-lived token exchange failed'),
        (('code', 'state', None), FakeFlow(raise_on_info=True), 'profile unavailable'),
    ],
)
def test_meta_oauth_worker_reports_failure_paths(monkeypatch, callback, flow, expected):
    _statuses, successes, failures, _opened = _run_worker(monkeypatch, callback, flow=flow)

    assert successes == []
    assert expected in failures[0]


def test_compute_expires_at_handles_missing_and_numeric_values():
    assert _compute_expires_at(None) is None
    assert _compute_expires_at(0) is None
    assert _compute_expires_at('60') is not None


def _make_dialog(qtbot, monkeypatch, provider='meta_threads'):
    monkeypatch.setattr(module, 'MetaOAuthWorker', FakeDialogWorker)
    auth = DummyAuthManager()
    dialog = MetaConnectDialog(provider, object(), f'{provider}_1', auth)
    qtbot.addWidget(dialog)
    return dialog, auth


def test_meta_connect_dialog_saves_threads_account_and_finishes(qtbot, monkeypatch):
    dialog, auth = _make_dialog(qtbot, monkeypatch)
    result = OAuthFlowResult(
        success=True,
        provider='meta_threads',
        account_id='meta_threads_1',
        access_token='token',
        expires_at='expiry',
        external_account_id='user-1',
        external_account_name='profile',
        granted_scopes=['threads_basic'],
    )

    dialog._on_success(result)

    assert auth.credentials['meta_threads_1']['access_token'] == 'token'
    assert auth.credentials['meta_threads_1']['granted_scopes'] == ['threads_basic']
    assert auth.accounts[0].profile_name == 'profile'
    assert dialog._status_label.text() == 'Successfully connected: profile'
    assert dialog._cancel_btn.text() == 'Done'


def test_meta_connect_dialog_handles_zero_one_and_multiple_facebook_pages(qtbot, monkeypatch):
    empty_dialog, empty_auth = _make_dialog(qtbot, monkeypatch, 'meta_facebook_page')
    empty_dialog._on_success(
        OAuthFlowResult(
            True,
            'meta_facebook_page',
            'facebook_1',
            access_token='user-token',
            page_list=[],
        )
    )
    assert empty_auth.accounts == []
    assert empty_dialog._status_label.text() == 'Error: No Facebook Pages found for this account.'
    assert empty_dialog._cancel_btn.text() == 'Close'

    page_one = FacebookPageInfo('page-1', 'Page One', 'token-1')
    one_dialog, one_auth = _make_dialog(qtbot, monkeypatch, 'meta_facebook_page')
    one_dialog._on_success(
        OAuthFlowResult(
            True,
            'meta_facebook_page',
            'facebook_1',
            access_token='user-token',
            expires_at='expiry',
            page_list=[page_one],
        )
    )
    assert one_auth.credentials['facebook_1']['page_access_token'] == 'token-1'
    assert one_auth.accounts[0].profile_name == 'Page One'

    page_two = FacebookPageInfo('page-2', 'Page Two', 'token-2')
    multiple_dialog, multiple_auth = _make_dialog(qtbot, monkeypatch, 'meta_facebook_page')
    result = OAuthFlowResult(
        True,
        'meta_facebook_page',
        'facebook_1',
        access_token='user-token',
        page_list=[page_one, page_two],
    )
    multiple_dialog._confirm_page_selection(result)
    multiple_dialog._on_success(result)
    assert multiple_dialog._page_selector.selected_page() == page_one
    multiple_dialog._page_selector._list.clearSelection()
    multiple_dialog._page_selector._list.setCurrentItem(None)
    multiple_dialog._confirm_page_selection(result)
    assert multiple_auth.accounts == []
    multiple_dialog._page_selector._list.setCurrentRow(1)
    multiple_dialog._confirm_page_selection(result)
    assert multiple_auth.credentials['facebook_1']['page_id'] == 'page-2'
    assert multiple_dialog._status_label.text() == 'Successfully connected: Page Two'


def test_meta_connect_dialog_cancel_and_close_stop_running_worker(qtbot, monkeypatch):
    dialog, _auth = _make_dialog(qtbot, monkeypatch)
    worker = dialog._worker

    dialog._on_cancel()

    assert worker.terminated
    assert worker.waited
    assert dialog.result() == QDialog.DialogCode.Rejected

    dialog2, _auth2 = _make_dialog(qtbot, monkeypatch)
    worker2 = dialog2._worker
    dialog2.close()
    assert worker2.terminated
    assert worker2.waited
