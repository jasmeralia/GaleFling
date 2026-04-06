"""Meta OAuth 2.0 connect flows for Threads, Instagram, and Facebook Page.

Implements:
- A temporary localhost HTTP server to capture the OAuth callback
- Authorization URL construction per platform
- Short-lived → long-lived token exchange
- Facebook Page listing and long-lived page token exchange
"""

import base64
import json
import queue
import secrets
import socket
import socketserver
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Literal
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests

from src.core.logger import get_logger

MetaProvider = Literal['meta_threads', 'meta_instagram', 'meta_facebook_page']

_CALLBACK_PATH = '/oauth/callback'
_FB_GRAPH_VERSION = 'v25.0'


# ── State helpers ─────────────────────────────────────────────────────────────


def make_state(port: int) -> str:
    """Return a base64url-encoded JSON state value embedding the CSRF token and port.

    The relay Lambda decodes the port to issue the localhost redirect.
    The full state value is forwarded unchanged so GaleFling can verify it on receipt.
    """
    payload = {'csrf': secrets.token_hex(16), 'port': port}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def parse_state(state: str) -> dict:
    """Decode a state value produced by ``make_state``."""
    return json.loads(base64.urlsafe_b64decode(state.encode()).decode())


# ── Port helpers ─────────────────────────────────────────────────────────────


def find_free_port(start: int = 8765, end: int = 8770) -> int:
    """Return the first free TCP port in [start, end].

    Raises RuntimeError if all ports in the range are busy.
    """
    for port in range(start, end + 1):
        with socket.socket() as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f'No free ports available in range {start}–{end}')


# ── Callback server ───────────────────────────────────────────────────────────


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures one OAuth callback request."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == _CALLBACK_PATH:
            params = parse_qs(parsed.query)
            code = params.get('code', [None])[0]
            state = params.get('state', [None])[0]
            error = params.get('error', [None])[0]
            self.server._callback_queue.put((code, state, error))  # type: ignore[attr-defined]
            self._send_close_page()
        else:
            self.send_response(404)
            self.end_headers()

    def _send_close_page(self) -> None:
        html = (
            '<!DOCTYPE html><html><head><title>GaleFling</title></head>'
            '<body style="font-family:sans-serif;text-align:center;padding:60px">'
            '<h2>Authorization complete</h2>'
            '<p>You can close this tab and return to GaleFling.</p>'
            '</body></html>'
        )
        body = html.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # suppress console output


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    pass


class MetaOAuthCallbackServer:
    """Temporary localhost HTTP server that captures a single OAuth callback."""

    def __init__(self, port: int) -> None:
        self._port = port
        self._callback_queue: queue.Queue[tuple[str | None, str | None, str | None]] = queue.Queue()
        self._server = _ThreadedHTTPServer(('localhost', port), _OAuthCallbackHandler)
        self._server._callback_queue = self._callback_queue  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def get_callback(self, timeout: int = 180) -> tuple[str | None, str | None, str | None] | None:
        """Block until a callback arrives or timeout expires.

        Returns (code, state, error) or None on timeout.
        """
        try:
            return self._callback_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def shutdown(self) -> None:
        self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=5)


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class FacebookPageInfo:
    """A Facebook Page with its long-lived page access token."""

    page_id: str
    page_name: str
    long_lived_page_access_token: str


@dataclass
class OAuthFlowResult:
    """Result of a completed (or failed) Meta OAuth flow."""

    success: bool
    provider: str
    account_id: str
    access_token: str | None = None
    expires_at: str | None = None
    external_account_id: str | None = None
    external_account_name: str | None = None
    granted_scopes: list[str] = field(default_factory=list)
    page_list: list[FacebookPageInfo] | None = None
    error_message: str | None = None


# ── Per-platform OAuth flow ───────────────────────────────────────────────────

_THREADS_SCOPES = 'threads_basic,threads_content_publish'
_INSTAGRAM_SCOPES = 'instagram_business_basic,instagram_business_content_publish'
_FACEBOOK_SCOPES = (
    'pages_manage_metadata,pages_manage_posts,pages_read_engagement,'
    'pages_show_list,pages_manage_engagement,publish_video'
)

_AUTH_URLS: dict[str, str] = {
    'meta_threads': 'https://api.instagram.com/oauth/authorize',
    'meta_instagram': 'https://www.instagram.com/oauth/authorize',
    'meta_facebook_page': 'https://www.facebook.com/dialog/oauth',
}
_SCOPES: dict[str, str] = {
    'meta_threads': _THREADS_SCOPES,
    'meta_instagram': _INSTAGRAM_SCOPES,
    'meta_facebook_page': _FACEBOOK_SCOPES,
}
_TOKEN_ENDPOINTS: dict[str, str] = {
    'meta_threads': 'https://api.instagram.com/oauth/access_token',
    'meta_instagram': 'https://api.instagram.com/oauth/access_token',
    'meta_facebook_page': f'https://graph.facebook.com/{_FB_GRAPH_VERSION}/oauth/access_token',
}
_LONG_LIVED_ENDPOINTS: dict[str, str] = {
    'meta_threads': 'https://graph.threads.net/access_token',
    'meta_instagram': 'https://graph.instagram.com/access_token',
    'meta_facebook_page': 'https://graph.facebook.com/oauth/access_token',
}
_LONG_LIVED_GRANT_TYPES: dict[str, str] = {
    'meta_threads': 'th_exchange_token',
    'meta_instagram': 'ig_exchange_token',
    'meta_facebook_page': 'fb_exchange_token',
}
_USER_INFO_BASES: dict[str, str] = {
    'meta_threads': 'https://graph.threads.net/v1.0',
    'meta_instagram': 'https://graph.instagram.com',
    'meta_facebook_page': 'https://graph.facebook.com',
}


class MetaOAuthFlow:
    """Handles the OAuth 2.0 authorization code flow for a single Meta provider."""

    def __init__(self, provider: str, app_id: str, app_secret: str) -> None:
        self._provider = provider
        self._app_id = app_id
        self._app_secret = app_secret

    # ── Public methods ────────────────────────────────────────────────

    def build_auth_url(self, redirect_uri: str, state: str) -> str:
        """Return the authorization URL to open in the user's browser."""
        params = {
            'client_id': self._app_id,
            'redirect_uri': redirect_uri,
            'scope': _SCOPES[self._provider],
            'response_type': 'code',
            'state': state,
        }
        return f'{_AUTH_URLS[self._provider]}?{urlencode(params)}'

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange an authorization code for a short-lived access token.

        Returns the parsed JSON response dict.
        Raises requests.HTTPError on a non-2xx response.
        """
        endpoint = _TOKEN_ENDPOINTS[self._provider]
        payload = {
            'client_id': self._app_id,
            'client_secret': self._app_secret,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'code': code,
        }
        if self._provider == 'meta_facebook_page':
            resp = requests.get(endpoint, params=payload, timeout=30)
        else:
            resp = requests.post(endpoint, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def exchange_long_lived(self, short_token: str) -> dict:
        """Exchange a short-lived token for a long-lived one.

        Returns the parsed JSON response dict.
        Raises requests.HTTPError on a non-2xx response.
        """
        endpoint = _LONG_LIVED_ENDPOINTS[self._provider]
        params = {
            'grant_type': _LONG_LIVED_GRANT_TYPES[self._provider],
            'client_secret': self._app_secret,
            'access_token': short_token,
        }
        if self._provider == 'meta_facebook_page':
            params['client_id'] = self._app_id
            params['fb_exchange_token'] = params.pop('access_token')
        resp = requests.get(endpoint, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_user_info(self, access_token: str) -> dict:
        """Fetch /me?fields=id,name for the authenticated user.

        Returns the parsed JSON response dict.
        Raises requests.HTTPError on a non-2xx response.
        """
        base = _USER_INFO_BASES[self._provider]
        url = urljoin(base + '/', 'me')
        resp = requests.get(
            url, params={'fields': 'id,name', 'access_token': access_token}, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_facebook_pages(self, long_lived_user_token: str) -> list[FacebookPageInfo]:
        """Return a list of Facebook Pages the user manages, each with a long-lived page token.

        Raises requests.HTTPError on a non-2xx response.
        """
        # Step 1: list pages
        url = f'https://graph.facebook.com/{_FB_GRAPH_VERSION}/me/accounts'
        resp = requests.get(url, params={'access_token': long_lived_user_token}, timeout=30)
        resp.raise_for_status()
        pages_data = resp.json().get('data', [])

        results: list[FacebookPageInfo] = []
        for page in pages_data:
            page_id = page.get('id', '')
            page_name = page.get('name', '')
            # Step 2: get long-lived page token for this page
            page_url = f'https://graph.facebook.com/{_FB_GRAPH_VERSION}/{page_id}'
            pr = requests.get(
                page_url,
                params={'fields': 'access_token', 'access_token': long_lived_user_token},
                timeout=30,
            )
            pr.raise_for_status()
            long_page_token = pr.json().get('access_token', page.get('access_token', ''))
            results.append(
                FacebookPageInfo(
                    page_id=page_id,
                    page_name=page_name,
                    long_lived_page_access_token=long_page_token,
                )
            )
            get_logger().debug(f'Fetched long-lived token for Facebook Page: {page_name}')

        return results
