"""FetLife platform implementation using WebView."""

from PyQt6.QtCore import QUrl

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import FETLIFE_SPECS, VIDEO_EXTENSIONS, PlatformSpecs


class FetLifePlatform(BaseWebViewPlatform):
    """FetLife posting via embedded WebView (traditional MPA)."""

    LOGIN_URL = 'https://fetlife.com/login'
    TEXT_COMPOSER_URL = 'https://fetlife.com/posts/new?source=Feed'
    IMAGE_COMPOSER_URL = 'https://fetlife.com/pictures/new?source=Main+Navigation'
    VIDEO_COMPOSER_URL = 'https://fetlife.com/videos/new?source=Main+Navigation'
    COMPOSER_URL = TEXT_COMPOSER_URL
    TEXT_SELECTOR = 'textarea#status_body'
    SUCCESS_URL_PATTERN = r'fetlife\.com/(?:users/\d+/(?:statuses|posts|pictures|videos)/\d+|(?:posts|pictures|videos)/\d+)'
    SUCCESS_SELECTOR = ''
    COOKIE_DOMAINS = ['fetlife.com']
    AUTH_COOKIE_NAMES = ['_fl_sessionid', 'remember_user_token', '_fl_session_remember_me']
    PREFILL_DELAY_MS = 200  # Traditional server-rendered pages load fast

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'FetLife ({self._profile_name})'
        return 'FetLife'

    def get_specs(self) -> PlatformSpecs:
        return FETLIFE_SPECS

    def navigate_to_login(self):
        if not self._view:
            return
        page = self._view.page()
        if not page:
            return
        page.loadFinished.connect(self._on_load_finished)
        self._view.load(QUrl(self.LOGIN_URL))

    def get_composer_url(self) -> str:
        if not self._image_path:
            return self.TEXT_COMPOSER_URL
        if self._image_path.suffix.lower() in VIDEO_EXTENSIONS:
            return self.VIDEO_COMPOSER_URL
        return self.IMAGE_COMPOSER_URL
