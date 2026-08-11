"""Unit tests for strict functional outcomes and renderer crash recording."""

import pytest

from tests.functional import conftest as functional_conftest

_RendererCrashMonitor = functional_conftest._RendererCrashMonitor


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, status, exit_code) -> None:
        for callback in self.callbacks:
            callback(status, exit_code)


class _FakeUrl:
    def toString(self) -> str:  # noqa: N802 - mirrors QUrl's API
        return 'https://example.test/composer'


class _FakePage:
    def __init__(self) -> None:
        self.renderProcessTerminated = _FakeSignal()

    def url(self) -> _FakeUrl:
        return _FakeUrl()


class _FakeStatus:
    name = 'CrashTerminationStatus'


def test_fail_or_skip_skips_in_legacy_mode(monkeypatch):
    monkeypatch.setattr(functional_conftest, '_STRICT_FUNCTIONAL', False)

    with pytest.raises(pytest.skip.Exception, match='missing selector'):
        functional_conftest.fail_or_skip('missing selector')


def test_fail_or_skip_fails_in_strict_mode(monkeypatch):
    monkeypatch.setattr(functional_conftest, '_STRICT_FUNCTIONAL', True)
    reason = 'OnlyFans selector not found: div[contenteditable="true"].b-make-post__text'

    with pytest.raises(pytest.fail.Exception) as failure:
        functional_conftest.fail_or_skip(reason)

    assert reason in str(failure.value)


def test_strict_functional_setting_reads_environment(monkeypatch):
    monkeypatch.setenv('GALEFLING_STRICT_FUNCTIONAL', '1')
    assert functional_conftest._strict_functional_enabled()

    monkeypatch.delenv('GALEFLING_STRICT_FUNCTIONAL')
    assert not functional_conftest._strict_functional_enabled()


def test_renderer_crash_monitor_records_status_exit_code_and_url():
    page = _FakePage()
    monitor = _RendererCrashMonitor()

    monitor.watch(page)
    monitor.watch(page)
    page.renderProcessTerminated.emit(_FakeStatus(), -1073741819)

    assert monitor.crashes == [
        'status=CrashTerminationStatus, exit_code=-1073741819, url=https://example.test/composer'
    ]
    assert len(page.renderProcessTerminated.callbacks) == 1

    with pytest.raises(
        pytest.fail.Exception,
        match='WebEngine renderer process terminated.*CrashTerminationStatus',
    ):
        monitor.fail_if_crashed()


def test_ensure_onlyfans_session_skips_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.delenv('ONLYFANS_AUTH_JSON', raising=False)

    with pytest.raises(pytest.skip.Exception, match='No OnlyFans session'):
        functional_conftest.ensure_onlyfans_session(tmp_path)


def test_ensure_onlyfans_session_returns_when_valid(monkeypatch, tmp_path):
    from unittest.mock import MagicMock, patch

    platform = MagicMock()
    platform.has_valid_session.return_value = True
    monkeypatch.delenv('ONLYFANS_AUTH_JSON', raising=False)

    with (
        patch('src.platforms.onlyfans.OnlyFansPlatform', return_value=platform),
        patch('src.platforms.base_webview.get_app_data_dir', return_value=tmp_path),
    ):
        assert functional_conftest.ensure_onlyfans_session(tmp_path) == 'onlyfans_1'


def test_ensure_onlyfans_session_imports_auth_json(monkeypatch, tmp_path):
    from unittest.mock import MagicMock, patch

    from src.core.webview_session_import import ImportedSession

    auth_path = tmp_path / 'auth.json'
    auth_path.write_text('{}', encoding='utf-8')
    session = ImportedSession(
        user_id='123',
        user_agent='Mozilla/5.0',
        x_bc='a' * 40,
        cookies={'auth_id': '123', 'sess': 'abc'},
    )
    platform = MagicMock()
    platform.has_valid_session.side_effect = [False, False]
    platform.import_session.return_value = (True, None)
    platform._get_profile_storage_path.return_value = tmp_path / 'webprofiles' / 'onlyfans_1'

    monkeypatch.setenv('ONLYFANS_AUTH_JSON', str(auth_path))

    with (
        patch('src.platforms.onlyfans.OnlyFansPlatform', return_value=platform),
        patch('src.platforms.base_webview.get_app_data_dir', return_value=tmp_path),
        patch(
            'src.core.webview_session_import.load_auth_json_file',
            return_value=session,
        ),
        patch('src.core.webview_session_import.session_recently_imported', return_value=True),
    ):
        assert functional_conftest.ensure_onlyfans_session(tmp_path) == 'onlyfans_1'
    platform.import_session.assert_called_once_with(session)
