import src.core.update_checker as update_checker


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_updates_skip_prerelease_when_disabled(monkeypatch):
    releases = [
        {'tag_name': 'v0.2.9-beta.1', 'prerelease': True, 'draft': False, 'assets': []},
        {'tag_name': 'v0.2.8', 'prerelease': False, 'draft': False, 'assets': []},
    ]

    monkeypatch.setattr(update_checker, 'APP_VERSION', '0.2.7')
    monkeypatch.setattr(
        update_checker.requests, 'get', lambda *_args, **_kwargs: _Response(releases)
    )

    update = update_checker.check_for_updates(include_prerelease=False)
    assert update is not None
    assert update.latest_version == '0.2.8'
    assert update.is_prerelease is False


def test_updates_include_prerelease_when_enabled(monkeypatch):
    releases = [
        {'tag_name': 'v0.2.9-beta.1', 'prerelease': True, 'draft': False, 'assets': []},
        {'tag_name': 'v0.2.8', 'prerelease': False, 'draft': False, 'assets': []},
    ]

    monkeypatch.setattr(update_checker, 'APP_VERSION', '0.2.7')
    monkeypatch.setattr(
        update_checker.requests, 'get', lambda *_args, **_kwargs: _Response(releases)
    )

    update = update_checker.check_for_updates(include_prerelease=True)
    assert update is not None
    assert update.latest_version == '0.2.9-beta.1'
    assert update.is_prerelease is True


def test_updates_ignore_drafts(monkeypatch):
    releases = [
        {'tag_name': 'v0.2.9', 'prerelease': False, 'draft': True, 'assets': []},
        {'tag_name': 'v0.2.8', 'prerelease': False, 'draft': False, 'assets': []},
    ]

    monkeypatch.setattr(update_checker, 'APP_VERSION', '0.2.7')
    monkeypatch.setattr(
        update_checker.requests, 'get', lambda *_args, **_kwargs: _Response(releases)
    )

    update = update_checker.check_for_updates(include_prerelease=False)
    assert update is not None
    assert update.latest_version == '0.2.8'


def test_updates_return_none_when_up_to_date(monkeypatch):
    releases = [
        {'tag_name': 'v0.2.8', 'prerelease': False, 'draft': False, 'assets': []},
    ]

    monkeypatch.setattr(update_checker, 'APP_VERSION', '0.2.8')
    monkeypatch.setattr(
        update_checker.requests, 'get', lambda *_args, **_kwargs: _Response(releases)
    )

    update = update_checker.check_for_updates(include_prerelease=False)
    assert update is None


def test_updates_http_error(monkeypatch):
    monkeypatch.setattr(
        update_checker.requests, 'get', lambda *_args, **_kwargs: _Response({}, status_code=500)
    )

    update = update_checker.check_for_updates()
    assert update is None


def test_updates_unexpected_payload(monkeypatch):
    monkeypatch.setattr(
        update_checker.requests, 'get', lambda *_args, **_kwargs: _Response({'error': 'bad'})
    )

    update = update_checker.check_for_updates()
    assert update is None


def test_updates_empty_tag(monkeypatch):
    releases = [
        {'tag_name': '', 'prerelease': False, 'draft': False, 'assets': []},
    ]
    monkeypatch.setattr(
        update_checker.requests, 'get', lambda *_args, **_kwargs: _Response(releases)
    )

    update = update_checker.check_for_updates()
    assert update is None


def test_updates_network_exception(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise ConnectionError('network down')

    monkeypatch.setattr(update_checker.requests, 'get', _raise)

    update = update_checker.check_for_updates()
    assert update is None


def test_updates_finds_installer_asset(monkeypatch):
    releases = [
        {
            'tag_name': 'v99.0.0',
            'prerelease': False,
            'draft': False,
            'html_url': 'https://github.com/test/releases/v99.0.0',
            'name': 'Version 99',
            'body': 'Release notes',
            'assets': [
                {
                    'name': 'GaleFlingSetup_99.0.0.exe',
                    'browser_download_url': 'https://dl/setup.exe',
                    'size': 5000,
                },
                {
                    'name': 'source.zip',
                    'browser_download_url': 'https://dl/source.zip',
                    'size': 1000,
                },
            ],
        },
    ]

    monkeypatch.setattr(update_checker, 'APP_VERSION', '0.0.1')
    monkeypatch.setattr(
        update_checker.requests, 'get', lambda *_args, **_kwargs: _Response(releases)
    )

    update = update_checker.check_for_updates()
    assert update is not None
    assert update.download_url == 'https://dl/setup.exe'
    assert update.download_size == 5000
    assert update.release_name == 'Version 99'
    assert update.release_notes == 'Release notes'
    assert update.browser_url == 'https://github.com/test/releases/v99.0.0'


def test_updates_no_matching_releases(monkeypatch):
    monkeypatch.setattr(update_checker.requests, 'get', lambda *_args, **_kwargs: _Response([]))

    update = update_checker.check_for_updates()
    assert update is None
