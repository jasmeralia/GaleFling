"""Snapchat platform implementation using WebView."""

import contextlib

from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings

from src.platforms.base_webview import BaseWebViewPlatform
from src.utils.constants import SNAPCHAT_SPECS, PlatformSpecs


class SnapchatPlatform(BaseWebViewPlatform):
    """Snapchat posting via embedded WebView at web.snapchat.com."""

    COMPOSER_URL = 'https://web.snapchat.com/'
    TEXT_SELECTOR = 'div[contenteditable="true"]'
    SUCCESS_URL_PATTERN = ''  # SPA — URL capture unlikely
    COOKIE_DOMAINS = ['snapchat.com']
    AUTH_COOKIE_NAMES = ['__Host-sc-a-auth-session']
    PREFILL_DELAY_MS = 500  # Snapchat SPA loads slowly

    def _configure_webview_page(self, page: QWebEnginePage) -> None:
        """Use safer rendering defaults for Snapchat to reduce renderer crashes."""
        settings = page.settings()
        if settings is None:
            return
        with contextlib.suppress(AttributeError):
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, False)
        with contextlib.suppress(AttributeError):
            settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, False)

    def get_platform_name(self) -> str:
        if self._profile_name:
            return f'Snapchat ({self._profile_name})'
        return 'Snapchat'

    def get_specs(self) -> PlatformSpecs:
        return SNAPCHAT_SPECS
