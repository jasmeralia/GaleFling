"""Process-wide Qt WebEngine environment policy."""

import os
import re
import shlex

_DISABLED_WEBVIEW_FEATURES = {'WebAuthenticationConditionalUI'}


def chrome_compatible_user_agent(user_agent: str) -> str:
    """Return Qt's Chromium user agent without the QtWebEngine product token."""
    return re.sub(r'\s*QtWebEngine/[^\s]+', '', user_agent).strip()


def disable_conditional_passkey_ui() -> None:
    """Disable Chromium's automatic passkey UI without changing page APIs.

    Qt WebEngine reads ``QTWEBENGINE_CHROMIUM_FLAGS`` when Chromium starts, so
    callers must invoke this before creating the QApplication/WebEngine process.
    """
    existing = os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '').strip()
    flags = shlex.split(existing) if existing else []
    disabled_features: set[str] = set(_DISABLED_WEBVIEW_FEATURES)
    retained_flags: list[str] = []

    for flag in flags:
        if flag.startswith('--disable-features='):
            disabled_features.update(
                feature
                for feature in flag.removeprefix('--disable-features=').split(',')
                if feature
            )
        else:
            retained_flags.append(flag)

    retained_flags.append('--disable-features=' + ','.join(sorted(disabled_features)))
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = shlex.join(retained_flags)
