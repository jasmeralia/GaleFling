"""Tests for concrete WebView platform implementations."""

import json
import sqlite3
from pathlib import Path

from src.platforms.fansly import FanslyPlatform
from src.platforms.fetlife import FetLifePlatform
from src.platforms.onlyfans import OnlyFansPlatform
from src.platforms.snapchat import SnapchatPlatform

# ── Snapchat ────────────────────────────────────────────────────────


def test_snapchat_platform_name():
    p = SnapchatPlatform(account_id='snapchat_1', profile_name='rin')
    assert p.get_platform_name() == 'Snapchat (rin)'


def test_snapchat_platform_name_no_profile():
    p = SnapchatPlatform(account_id='snapchat_1')
    assert p.get_platform_name() == 'Snapchat'


def test_snapchat_specs():
    p = SnapchatPlatform(account_id='snapchat_1')
    specs = p.get_specs()
    assert specs.platform_name == 'Snapchat'
    assert specs.api_type == 'webview'
    assert specs.max_accounts == 2
    assert specs.requires_user_confirm is True


def test_snapchat_composer_url():
    assert SnapchatPlatform.COMPOSER_URL == 'https://web.snapchat.com/'


def test_snapchat_is_webview():
    p = SnapchatPlatform(account_id='snapchat_1')
    result = p.post('Hello')
    assert result.success is False
    assert result.error_code == 'WV-PREFILL-FAILED'


def test_snapchat_does_not_restrict_webgl():
    # WebGL and accelerated canvas are intentionally left enabled.
    # Disabling them caused renderer ACCESS_VIOLATION crashes when the
    # expired-session redirect landed on www.snapchat.com (marketing site),
    # which uses GPU-heavy JavaScript.  The base class _configure_webview_page
    # is a no-op, so Snapchat inherits the default (unrestricted) settings.
    p = SnapchatPlatform(account_id='snapchat_1')
    assert (
        not hasattr(p, '_configure_webview_page')
        or p._configure_webview_page.__func__
        is SnapchatPlatform.__bases__[0]._configure_webview_page
    )


def _write_cookie(path: Path, host: str, name: str, expires_utc: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'CREATE TABLE IF NOT EXISTS cookies (host_key TEXT, name TEXT, expires_utc INTEGER)'
        )
        cursor.execute(
            'INSERT INTO cookies (host_key, name, expires_utc) VALUES (?, ?, ?)',
            (host, name, expires_utc),
        )
        conn.commit()


def test_snapchat_session_requires_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = SnapchatPlatform(account_id='snapchat_1')
    cookie_path = tmp_path / 'webprofiles' / 'snapchat_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    _write_cookie(cookie_path, '.snapchat.com', '_ga', future_expiry)
    assert platform.has_valid_session() is False

    _write_cookie(
        cookie_path,
        'accounts.snapchat.com',
        '__Host-sc-a-auth-session',
        future_expiry,
    )
    assert platform.has_valid_session() is True


# ── OnlyFans ────────────────────────────────────────────────────────


def test_onlyfans_platform_name():
    p = OnlyFansPlatform(account_id='onlyfans_1', profile_name='rinmodel')
    assert p.get_platform_name() == 'OnlyFans (rinmodel)'


def test_onlyfans_specs():
    p = OnlyFansPlatform(account_id='onlyfans_1')
    specs = p.get_specs()
    assert specs.platform_name == 'OnlyFans'
    assert specs.has_cloudflare is True
    assert specs.requires_user_confirm is True
    assert specs.max_accounts == 1
    assert specs.max_image_dimensions == (10000, 10000)
    assert specs.max_media_attachments == 40
    assert specs.supported_formats == ['JPEG', 'PNG', 'GIF']
    assert specs.supported_video_formats == [
        'MP4',
        'MOV',
        'M4V',
        'MPEG',
        'WMV',
        'AVI',
        'WEBM',
        'MKV',
    ]


def test_onlyfans_login_is_import_only():
    """OnlyFans must not offer embedded login: reCAPTCHA Enterprise rejects it."""
    specs = OnlyFansPlatform(account_id='onlyfans_1').get_specs()
    assert specs.supports_embedded_login is False
    assert specs.supports_session_import is True


def test_other_webview_platforms_keep_embedded_login():
    from src.platforms.fansly import FanslyPlatform
    from src.platforms.fetlife import FetLifePlatform
    from src.platforms.snapchat import SnapchatPlatform

    for platform_cls in (FanslyPlatform, FetLifePlatform, SnapchatPlatform):
        specs = platform_cls(account_id='acct_1').get_specs()
        assert specs.supports_embedded_login is True, platform_cls.__name__
        assert specs.supports_session_import is False, platform_cls.__name__


def test_onlyfans_prefill_delay():
    assert OnlyFansPlatform.PREFILL_DELAY_MS == 1500


def test_onlyfans_authenticate():
    p = OnlyFansPlatform(account_id='onlyfans_1')
    success, error = p.authenticate()
    assert success is True
    assert error is None


def test_onlyfans_session_requires_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = OnlyFansPlatform(account_id='onlyfans_1')
    cookie_path = tmp_path / 'webprofiles' / 'onlyfans_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    _write_cookie(cookie_path, '.onlyfans.com', '__cf_bm', future_expiry)
    assert platform.has_valid_session() is False

    _write_cookie(cookie_path, 'onlyfans.com', 'auth_id', future_expiry)
    assert platform.has_valid_session() is True


# ── Fansly ──────────────────────────────────────────────────────────


def test_fansly_platform_name():
    p = FanslyPlatform(account_id='fansly_1', profile_name='rinmodel')
    assert p.get_platform_name() == 'Fansly (rinmodel)'


def test_fansly_specs():
    p = FanslyPlatform(account_id='fansly_1')
    specs = p.get_specs()
    assert specs.platform_name == 'Fansly'
    assert specs.has_cloudflare is True
    assert specs.max_text_length == 3000


def test_fansly_prefill_delay():
    assert FanslyPlatform.PREFILL_DELAY_MS == 1500


def test_fansly_current_routes_and_session_expiry_selectors():
    assert FanslyPlatform.LOGIN_URL == 'https://fansly.com/'
    assert FanslyPlatform.COMPOSER_URL == 'https://fansly.com/home'
    assert '.nav-content-wrapper.not-logged-in' in FanslyPlatform.SESSION_EXPIRED_SELECTORS
    assert 'input[autocomplete="password"]' in FanslyPlatform.SESSION_EXPIRED_SELECTORS


def test_fansly_build_result_not_confirmed():
    p = FanslyPlatform(account_id='fansly_1', profile_name='model')
    result = p.build_result()
    assert result.success is False
    assert result.error_code == 'WV-SUBMIT-TIMEOUT'


def test_fansly_session_requires_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = FanslyPlatform(account_id='fansly_1')
    cookie_path = tmp_path / 'webprofiles' / 'fansly_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    _write_cookie(cookie_path, '.fansly.com', '_ga', future_expiry)
    assert platform.has_valid_session() is False

    _write_cookie(cookie_path, '.fansly.com', 'fansly-d', future_expiry)
    assert platform.has_valid_session() is True


# ── FetLife ─────────────────────────────────────────────────────────


def test_fetlife_platform_name():
    p = FetLifePlatform(account_id='fetlife_1', profile_name='rinmodel')
    assert p.get_platform_name() == 'FetLife (rinmodel)'


def test_fetlife_platform_name_no_profile():
    p = FetLifePlatform(account_id='fetlife_1')
    assert p.get_platform_name() == 'FetLife'


def test_fetlife_specs():
    p = FetLifePlatform(account_id='fetlife_1')
    specs = p.get_specs()
    assert specs.platform_name == 'FetLife'
    assert specs.has_cloudflare is False
    assert specs.max_text_length == 690


def test_fetlife_composer_url():
    assert FetLifePlatform.COMPOSER_URL == 'https://fetlife.com/home'


def test_fetlife_text_posts_target_the_status_composer():
    """Text posts are statuses on the feed, not writings.

    `/posts/new` is the writing composer and its form requires a `post[title]` that
    GaleFling has no field for, so submitting there fails validation silently.
    """
    assert FetLifePlatform.TEXT_COMPOSER_URL == 'https://fetlife.com/home'
    assert FetLifePlatform.TEXT_SELECTOR == 'textarea[name="body"]'
    assert FetLifePlatform.TEXT_SUBMIT_LABEL == 'Say It!'
    assert 'posts/new' not in FetLifePlatform.TEXT_COMPOSER_URL


def test_fetlife_injects_text_via_textarea_prototype_setter():
    """A direct `.value =` assignment leaves "Say It!" disabled; the setter does not."""
    platform, page = _fetlife_with_page()

    platform._inject_text('Hello status')

    assert len(page.js_calls) == 1
    script = page.js_calls[0]
    assert 'HTMLTextAreaElement.prototype' in script
    assert "'value'" in script
    assert 'setter.call(box' in script
    assert json.dumps(FetLifePlatform.TEXT_SELECTOR) in script
    assert 'Hello status' in script
    assert 'lexxy' not in script.lower()


def test_fetlife_login_url():
    assert FetLifePlatform.LOGIN_URL == 'https://fetlife.com/login'


def test_fetlife_navigate_to_login_handles_missing_view():
    p = FetLifePlatform(account_id='fetlife_1')
    p._view = None
    p.navigate_to_login()


def test_fetlife_navigate_to_login_handles_missing_page():
    class DummyView:
        def page(self):
            return None

    p = FetLifePlatform(account_id='fetlife_1')
    p._view = DummyView()
    p.navigate_to_login()


def test_fetlife_navigate_to_login_loads_login_url():
    class DummySignal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

    class DummyPage:
        def __init__(self):
            self.loadFinished = DummySignal()

    class DummyView:
        def __init__(self):
            self.loaded_urls = []
            self._page = DummyPage()

        def page(self):
            return self._page

        def load(self, url):
            self.loaded_urls.append(url.toString())

    p = FetLifePlatform(account_id='fetlife_1')
    view = DummyView()
    p._view = view
    p.navigate_to_login()

    assert view.loaded_urls == [FetLifePlatform.LOGIN_URL]
    assert view._page.loadFinished.callbacks == [p._on_load_finished]


def test_fetlife_selects_video_composer_url():
    p = FetLifePlatform(account_id='fetlife_1')
    p.prepare_post('hello', [Path('/tmp/sample.mp4')])
    assert p.get_composer_url() == 'https://fetlife.com/videos/new?source=Main+Navigation'


def test_fetlife_selects_image_composer_url():
    p = FetLifePlatform(account_id='fetlife_1')
    p.prepare_post('hello', [Path('/tmp/sample.png')])
    assert p.get_composer_url() == 'https://fetlife.com/pictures/new?source=Main+Navigation'


def test_fetlife_selects_text_composer_url_for_text_only():
    p = FetLifePlatform(account_id='fetlife_1')
    p.prepare_post('hello', [])
    assert p.get_composer_url() == 'https://fetlife.com/home'


class _RecordingPage:
    """Minimal QWebEnginePage stand-in that captures runJavaScript calls."""

    def __init__(self):
        self.js_calls = []

    def runJavaScript(self, script, callback=None):  # noqa: N802 - mirrors Qt API
        self.js_calls.append(script)
        if callback is not None:
            callback({'stub': True})


class _RecordingView:
    def __init__(self, page):
        self._page = page

    def page(self):
        return self._page


def _fetlife_with_page():
    platform = FetLifePlatform(account_id='fetlife_1')
    page = _RecordingPage()
    platform._view = _RecordingView(page)
    return platform, page


def test_fetlife_media_file_selector_routes_by_extension(tmp_path):
    platform = FetLifePlatform(account_id='fetlife_1')
    assert platform.get_media_file_selector() is None

    platform._image_path = tmp_path / 'photo.jpg'
    assert platform.get_media_file_selector() == FetLifePlatform.IMAGE_FILE_SELECTOR

    platform._image_path = tmp_path / 'clip.mp4'
    assert platform.get_media_file_selector() == FetLifePlatform.VIDEO_FILE_SELECTOR


def test_fetlife_attach_media_writes_file_then_state_totals_every_input(tmp_path):
    """The picture composer moves the file to a hidden named field and clears the picker.

    Verifying the input we wrote to would therefore report zero files on a successful
    attach, so _media_attachment_state() totals files across all file inputs.
    """
    photo = tmp_path / 'photo.jpg'
    photo.write_bytes(b'\xff\xd8\xff\xe0 fake jpeg')

    platform, page = _fetlife_with_page()
    platform._image_path = photo
    platform._attach_media(photo)

    assert len(page.js_calls) == 1
    script = page.js_calls[0]
    assert json.dumps(FetLifePlatform.IMAGE_FILE_SELECTOR) in script
    assert 'new DataTransfer()' in script
    assert 'photo.jpg' in script
    assert 'image/jpeg' in script

    # Acceptance is observed separately, because FetLife's hand-off to the named
    # field is asynchronous and cannot be read back from the attach call.
    platform._media_attachment_state()
    state_script = page.js_calls[1]
    assert 'querySelectorAll(\'input[type="file"]\')' in state_script
    assert 'holders' in state_script


def test_fetlife_attach_media_selects_video_input_for_video(tmp_path):
    clip = tmp_path / 'clip.mp4'
    clip.write_bytes(b'fake mp4')

    platform, page = _fetlife_with_page()
    platform._image_path = clip
    platform._attach_media(clip)

    assert json.dumps(FetLifePlatform.VIDEO_FILE_SELECTOR) in page.js_calls[0]
    assert 'video/mp4' in page.js_calls[0]


def test_fetlife_attach_media_reports_unreadable_file(tmp_path):
    platform, _ = _fetlife_with_page()
    results = []
    platform._attach_media(tmp_path / 'missing.jpg', callback=results.append)

    assert len(results) == 1
    assert results[0]['dispatched'] is False
    assert 'missing.jpg' in results[0]['reason']


def test_fetlife_consent_matches_certification_field_by_exact_name():
    """The avatar checkbox shares the form; only the certification field may be set."""
    selector = FetLifePlatform.CONSENT_CHECKBOX_SELECTOR
    assert 'picture[is_certified]' in selector
    assert 'video[is_certified]' in selector
    assert 'is_avatar' not in selector

    platform, page = _fetlife_with_page()
    platform._certify_upload_consent()

    script = page.js_calls[0]
    assert json.dumps(selector) in script
    # `certified` must reflect real checkbox state, not merely that we tried.
    assert 'boxes.every(' in script
    assert 'box.disabled' in script


def test_fetlife_media_methods_no_op_without_view(tmp_path):
    photo = tmp_path / 'photo.jpg'
    photo.write_bytes(b'x')
    platform = FetLifePlatform(account_id='fetlife_1')

    platform._attach_media(photo)
    platform._certify_upload_consent()  # must not raise without a view


def test_fetlife_success_url_pattern():
    import re

    pattern = FetLifePlatform.SUCCESS_URL_PATTERN
    assert re.search(pattern, 'https://fetlife.com/users/12345/statuses/67890')
    assert re.search(pattern, 'https://fetlife.com/users/12345/posts/67890')
    assert re.search(pattern, 'https://fetlife.com/posts/67890')
    assert re.search(pattern, 'https://fetlife.com/pictures/67890')
    assert re.search(pattern, 'https://fetlife.com/videos/67890')
    # Real FetLife permalinks are username-scoped — statuses and media alike.
    assert re.search(pattern, 'https://fetlife.com/Jasmeralia/s/11543410072')
    assert re.search(pattern, 'https://fetlife.com/Jasmeralia/pictures/222741611')
    assert re.search(pattern, 'https://fetlife.com/Jasmeralia/videos/12345')
    assert not re.search(pattern, 'https://fetlife.com/pictures/new?source=Main+Navigation')
    assert not re.search(pattern, 'https://fetlife.com/')
    assert not re.search(pattern, 'https://fetlife.com/home')
    assert not re.search(pattern, 'https://fetlife.com/posts/new?source=Feed')


def test_fetlife_session_requires_auth_cookie(monkeypatch, tmp_path):
    import src.platforms.base_webview as base_webview

    monkeypatch.setattr(base_webview, 'get_app_data_dir', lambda: tmp_path)
    platform = FetLifePlatform(account_id='fetlife_1')
    cookie_path = tmp_path / 'webprofiles' / 'fetlife_1' / 'Cookies'

    future_expiry = 20_000_000_000_000_000
    _write_cookie(cookie_path, '.fetlife.com', 'cf_clearance', future_expiry)
    assert platform.has_valid_session() is False

    _write_cookie(cookie_path, '.fetlife.com', '_fl_sessionid', future_expiry)
    assert platform.has_valid_session() is True


def test_fetlife_build_result_confirmed_with_url():
    p = FetLifePlatform(account_id='fetlife_1', profile_name='model')
    p._post_confirmed = True
    p._captured_post_url = 'https://fetlife.com/users/123/statuses/456'
    result = p.build_result()
    assert result.success is True
    assert result.post_url == 'https://fetlife.com/users/123/statuses/456'
    assert result.url_captured is True


def test_snapchat_redirect_interception_terminates(monkeypatch):
    """The www.snapchat.com/web interception must not navigate indefinitely.

    Snapchat bounces the web app between web.snapchat.com and
    www.snapchat.com/web. Each bounce re-enters _on_url_changed, which issues
    another navigation, so an unbounded rewrite turns one page load into a
    request loop — which Snapchat answers with HTTP 429.
    """
    import src.platforms.snapchat as snapchat_mod

    loads: list[str] = []

    class _View:
        def load(self, url):
            loads.append(url.toString())

    class _ImmediateTimer:
        @staticmethod
        def singleShot(_delay, callback):  # noqa: N802
            callback()

    monkeypatch.setattr(snapchat_mod, 'QTimer', _ImmediateTimer)

    platform = SnapchatPlatform(account_id='snapchat_1')
    platform._view = _View()
    monkeypatch.setattr(type(platform).__bases__[0], '_on_url_changed', lambda self, url: None)

    # Replay the bounce Snapchat actually performs, following each navigation
    # the platform requests, for far more rounds than a healthy flow needs.
    from PyQt6.QtCore import QUrl

    current = 'https://web.snapchat.com/'
    for _ in range(12):
        platform._on_url_changed(QUrl(current))
        platform._on_url_changed(QUrl('https://www.snapchat.com/web/'))
        if not loads:
            break
        current = loads[-1]

    assert len(loads) < 6, (
        f'redirect interception issued {len(loads)} navigations for one page load; '
        f'it is looping: {loads[:6]}'
    )
