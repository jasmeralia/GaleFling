#!/usr/bin/env python3
"""Re-mint the Threads *functional-test* access token, including the delete scope.

GaleFling's own connect flow requests ``threads_basic,threads_content_publish`` and
nothing more, because the application never deletes a post. The functional test suite
does: without ``threads_delete`` every mutating Threads run leaves its posts on the live
account, because ``DELETE /{threads-media-id}`` answers ``HTTP 500 / code 10 —
"Application does not have permission for this action"``.

Rather than widen the product's scopes for the sake of test cleanup, this tool mints a
separate, wider token for ``tests/functional/.env`` only. It reuses GaleFling's own OAuth
machinery (``src/core/meta_oauth.py``) — the relay callback, the localhost capture server,
and both token exchanges — so there is one implementation of the flow, not two.

Adding the scope in the App Dashboard is **not** sufficient on its own: an OAuth token
carries the scopes granted at authorization time, so an already-issued token keeps failing
until it is re-minted here.

Usage::

    .venv/bin/python tools/oauth/meta_threads_remint.py
    .venv/bin/python tools/oauth/meta_threads_remint.py --no-verify
    .venv/bin/python tools/oauth/meta_threads_remint.py --print-url

The token is written straight into ``tests/functional/.env`` and is never printed, logged,
or echoed (`AGENTS.md` rule 8). Credentials are read from ``tests/functional/creds_import.json``,
which is gitignored; nothing secret belongs in this file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.core import meta_oauth  # noqa: E402

CREDS_PATH = REPO_ROOT / 'tests' / 'functional' / 'creds_import.json'
ENV_PATH = REPO_ROOT / 'tests' / 'functional' / '.env'
ENV_KEY = 'META_THREADS_ACCESS_TOKEN'
THREADS_API_BASE = 'https://graph.threads.net/v1.0'

#: The product's scopes plus delete. Deliberately a superset of ``meta_oauth._THREADS_SCOPES``
#: rather than a change to it — see the module docstring.
TEST_SCOPES = 'threads_basic,threads_content_publish,threads_delete'


def _load_threads_credentials() -> tuple[str, str, str]:
    """Return (app_id, app_secret, redirect_uri) for the Threads app."""
    if not CREDS_PATH.is_file():
        raise SystemExit(f'Credentials file not found: {CREDS_PATH}')
    meta = json.loads(CREDS_PATH.read_text(encoding='utf-8')).get('meta') or {}
    threads = meta.get('threads') or {}
    app_id, app_secret = threads.get('app_id'), threads.get('app_secret')
    redirect_uri = meta.get('oauth_redirect_uri')
    missing = [
        name
        for name, value in (
            ('meta.threads.app_id', app_id),
            ('meta.threads.app_secret', app_secret),
            ('meta.oauth_redirect_uri', redirect_uri),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f'Missing from {CREDS_PATH.name}: {", ".join(missing)}')
    # The Threads app_id here is the use-case-scoped "Threads App ID", not the app's
    # top-level ID. Supplying the top-level one produces a confusing invalid-client error.
    return str(app_id), str(app_secret), str(redirect_uri)


def _authorize(flow: meta_oauth.MetaOAuthFlow, redirect_uri: str, print_url: bool) -> str:
    """Run the browser authorization leg and return the one-time authorization code."""
    port = meta_oauth.find_free_port()
    state = meta_oauth.make_state(port)
    server = meta_oauth.MetaOAuthCallbackServer(port)
    server.start()
    try:
        auth_url = flow.build_auth_url(redirect_uri, state)
        print(f'\nAuthorization URL (scopes: {TEST_SCOPES}):\n\n{auth_url}\n')
        if not print_url:
            webbrowser.open(auth_url)
            print('Opened in your browser. Approve the request, then return here.')
        print('Waiting for the callback (3 minute timeout)...')

        result = server.get_callback(timeout=180)
        if result is None:
            raise SystemExit('Timed out waiting for the OAuth callback.')
        code, returned_state, error = result
        if error:
            raise SystemExit(f'Authorization was denied or failed: {error}')
        if returned_state != state:
            raise SystemExit('State mismatch — refusing to continue (possible CSRF).')
        if not code:
            raise SystemExit('Callback carried no authorization code.')
        return code
    finally:
        server.shutdown()


def _write_env_token(token: str) -> None:
    """Replace (or append) the token line in .env, leaving every other line untouched."""
    if not ENV_PATH.is_file():
        raise SystemExit(f'{ENV_PATH} does not exist — create it before re-minting.')
    original = ENV_PATH.read_text(encoding='utf-8')
    line = f'{ENV_KEY}={token}'
    pattern = re.compile(rf'^{re.escape(ENV_KEY)}=.*$', re.MULTILINE)
    if pattern.search(original):
        updated = pattern.sub(lambda _: line, original, count=1)
    else:
        sep = '' if original.endswith('\n') or not original else '\n'
        updated = f'{original}{sep}{line}\n'
    ENV_PATH.write_text(updated, encoding='utf-8')


def _verify_delete_scope(token: str) -> bool:
    """Publish a throwaway post and delete it — the only proof the scope really landed.

    A DELETE against a nonexistent ID cannot answer this: Graph returns the same generic
    code 100 for "missing" as for "no permission". Only a real owned object distinguishes
    them, so this creates one and removes it.
    """
    # Neutral text, per AGENTS.md rule 14 — this reaches a live account.
    tag = uuid.uuid4().hex[:8]
    me = requests.get(
        f'{THREADS_API_BASE}/me', params={'fields': 'id', 'access_token': token}, timeout=20
    )
    me.raise_for_status()
    user_id = me.json()['id']

    created = requests.post(
        f'{THREADS_API_BASE}/{user_id}/threads',
        data={'media_type': 'TEXT', 'text': tag, 'access_token': token},
        timeout=30,
    )
    created.raise_for_status()
    container_id = created.json()['id']

    # A text container is not publishable the instant it is created; see _post_text().
    for _ in range(10):
        status = (
            requests.get(
                f'{THREADS_API_BASE}/{container_id}',
                params={'fields': 'status', 'access_token': token},
                timeout=20,
            )
            .json()
            .get('status')
        )
        if status == 'FINISHED':
            break
        time.sleep(3)

    published = requests.post(
        f'{THREADS_API_BASE}/{user_id}/threads_publish',
        data={'creation_id': container_id, 'access_token': token},
        timeout=30,
    )
    published.raise_for_status()
    post_id = published.json()['id']

    deleted = requests.delete(
        f'{THREADS_API_BASE}/{post_id}', params={'access_token': token}, timeout=20
    )
    if deleted.status_code == 200:
        print(f'  verify: published and deleted a throwaway post (tag {tag}) — scope works')
        return True

    error = deleted.json().get('error', {})
    print(
        f'  verify: FAILED — delete returned HTTP {deleted.status_code} '
        f'code={error.get("code")} {error.get("message")!r}'
    )
    print(f'  verify: the post tagged {tag} is still live and must be removed by hand')
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='Skip the publish-then-delete check (which briefly creates a real post)',
    )
    parser.add_argument(
        '--print-url',
        action='store_true',
        help='Print the authorization URL instead of opening a browser',
    )
    args = parser.parse_args()

    app_id, app_secret, redirect_uri = _load_threads_credentials()
    meta_oauth._SCOPES['meta_threads'] = TEST_SCOPES
    flow = meta_oauth.MetaOAuthFlow('meta_threads', app_id, app_secret)

    code = _authorize(flow, redirect_uri, args.print_url)

    short_lived = flow.exchange_code(code, redirect_uri)['access_token']
    long_lived = flow.exchange_long_lived(short_lived)
    token, expires_in = long_lived['access_token'], long_lived.get('expires_in', 0)

    info = requests.get(
        f'{THREADS_API_BASE}/me',
        params={'fields': 'id,username', 'access_token': token},
        timeout=20,
    )
    info.raise_for_status()
    username = info.json().get('username', '<unknown>')
    expiry = (datetime.now(UTC) + timedelta(seconds=int(expires_in))).date().isoformat()

    print(f'\n  account:  @{username}')
    print(f'  expires:  {expiry} ({int(expires_in) // 86400} days)')

    ok = True
    if not args.no_verify:
        ok = _verify_delete_scope(token)

    _write_env_token(token)
    print(f'  written:  {ENV_KEY} in {ENV_PATH.relative_to(REPO_ROOT)} (value not shown)\n')

    if not ok:
        print(
            'The token was written, but delete is still refused. Confirm threads_delete is '
            'enabled on the Threads use case, then re-run this tool.'
        )
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
