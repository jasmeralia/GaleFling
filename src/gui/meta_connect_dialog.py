"""Dialog for completing a Meta OAuth connect flow.

Opens the system browser, waits for the localhost callback, exchanges tokens,
then saves the resulting credentials via AuthManager.
"""

from __future__ import annotations

import webbrowser

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.auth_manager import AuthManager
from src.core.logger import get_logger
from src.core.meta_oauth import (
    FacebookPageInfo,
    MetaOAuthCallbackServer,
    MetaOAuthFlow,
    OAuthFlowResult,
    find_free_port,
    make_state,
)
from src.utils.constants import AccountConfig

_PROVIDER_DISPLAY: dict[str, str] = {
    'meta_threads': 'Threads',
    'meta_instagram': 'Instagram',
    'meta_facebook_page': 'Facebook Page',
}


# ── Background worker ─────────────────────────────────────────────────────────


class MetaOAuthWorker(QThread):
    """Runs the full Meta OAuth flow on a background thread."""

    status_changed = pyqtSignal(str)
    success = pyqtSignal(object)  # OAuthFlowResult
    failed = pyqtSignal(str)

    def __init__(
        self,
        flow: MetaOAuthFlow,
        provider: str,
        account_id: str,
        oauth_redirect_uri: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._flow = flow
        self._provider = provider
        self._account_id = account_id
        self._oauth_redirect_uri = oauth_redirect_uri

    def run(self) -> None:
        server: MetaOAuthCallbackServer | None = None
        try:
            port = find_free_port()
            server = MetaOAuthCallbackServer(port)
            server.start()

            redirect_uri = self._oauth_redirect_uri
            state = make_state(port)
            auth_url = self._flow.build_auth_url(redirect_uri, state)

            self.status_changed.emit('Opening browser — please authorize in the browser window...')
            webbrowser.open(auth_url)

            self.status_changed.emit('Waiting for browser authorization...')
            callback = server.get_callback(timeout=180)

            if callback is None:
                self.failed.emit('Timed out waiting for authorization. Please try again.')
                return

            code, returned_state, error = callback

            if error:
                self.failed.emit(f'Authorization denied: {error}')
                return

            if returned_state != state:
                self.failed.emit('State mismatch — authorization may have been tampered with.')
                return

            if not code:
                self.failed.emit('No authorization code received.')
                return

            self.status_changed.emit('Exchanging authorization code for token...')
            short_token_data = self._flow.exchange_code(code, redirect_uri)
            short_token = short_token_data.get('access_token', '')
            if not short_token:
                self.failed.emit('Token exchange failed: no access_token in response.')
                return

            self.status_changed.emit('Upgrading to long-lived token...')
            long_token_data = self._flow.exchange_long_lived(short_token)
            long_token = long_token_data.get('access_token', '')
            if not long_token:
                self.failed.emit('Long-lived token exchange failed.')
                return

            expires_in = long_token_data.get('expires_in')
            expires_at = _compute_expires_at(expires_in)

            self.status_changed.emit('Fetching account information...')
            user_info = self._flow.fetch_user_info(long_token)
            external_id = str(user_info.get('id', ''))
            external_name = user_info.get('name', '') or user_info.get('username', '')

            result = OAuthFlowResult(
                success=True,
                provider=self._provider,
                account_id=self._account_id,
                access_token=long_token,
                expires_at=expires_at,
                external_account_id=external_id,
                external_account_name=external_name,
            )

            if self._provider == 'meta_facebook_page':
                self.status_changed.emit('Fetching Facebook Pages...')
                page_list = self._flow.fetch_facebook_pages(long_token)
                result.page_list = page_list
                result.access_token = long_token  # store user token for FB

            self.success.emit(result)

        except Exception as exc:
            get_logger().error(f'MetaOAuthWorker error: {exc}', exc_info=True)
            self.failed.emit(str(exc))
        finally:
            if server is not None:
                server.shutdown()


def _compute_expires_at(expires_in: int | None) -> str | None:
    """Return an ISO-8601 UTC expiry timestamp, or None if not provided."""
    if not expires_in:
        return None
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) + timedelta(seconds=int(expires_in))).isoformat()


# ── Page selector widget ──────────────────────────────────────────────────────


class _FacebookPageSelector(QWidget):
    """Inline widget for selecting a Facebook Page from a list."""

    def __init__(self, pages: list[FacebookPageInfo], parent=None) -> None:
        super().__init__(parent)
        self._pages = pages
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('Select the Facebook Page to connect:'))
        self._list = QListWidget()
        for page in pages:
            item = QListWidgetItem(page.page_name)
            item.setData(Qt.ItemDataRole.UserRole, page)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)
        layout.addWidget(self._list)

    def selected_page(self) -> FacebookPageInfo | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)


# ── Connect dialog ────────────────────────────────────────────────────────────


class MetaConnectDialog(QDialog):
    """Orchestrates a Meta OAuth connect flow with a progress UI."""

    def __init__(
        self,
        provider: str,
        flow: MetaOAuthFlow,
        account_id: str,
        auth_manager: AuthManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._account_id = account_id
        self._auth_manager = auth_manager
        self._worker: MetaOAuthWorker | None = None
        self._page_selector: _FacebookPageSelector | None = None

        display = _PROVIDER_DISPLAY.get(provider, provider)
        self.setWindowTitle(f'Connect {display} Account')
        self.setMinimumWidth(420)
        self.setModal(True)

        self._layout = QVBoxLayout(self)

        self._status_label = QLabel('Starting authorization flow...')
        self._status_label.setWordWrap(True)
        self._layout.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._layout.addWidget(self._progress)

        self._btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton('Cancel')
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._btn_row.addStretch()
        self._btn_row.addWidget(self._cancel_btn)
        self._layout.addLayout(self._btn_row)

        # Start worker immediately
        oauth_redirect_uri = auth_manager.get_meta_oauth_redirect_uri()
        self._worker = MetaOAuthWorker(flow, provider, account_id, oauth_redirect_uri, parent=self)
        self._worker.status_changed.connect(self._status_label.setText)
        self._worker.success.connect(self._on_success)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_success(self, result: OAuthFlowResult) -> None:
        self._progress.setVisible(False)

        if self._provider == 'meta_facebook_page' and result.page_list is not None:
            pages = result.page_list
            if len(pages) == 0:
                self._on_failed('No Facebook Pages found for this account.')
                return
            if len(pages) == 1:
                self._save_facebook_page(result, pages[0])
                self._finish_success(pages[0].page_name)
            else:
                # Show page selector
                self._page_selector = _FacebookPageSelector(pages)
                self._layout.insertWidget(self._layout.count() - 1, self._page_selector)
                self._status_label.setText('Multiple pages found. Select which page to connect:')
                # Swap Cancel → Connect
                self._cancel_btn.setText('Connect Selected Page')
                self._cancel_btn.clicked.disconnect()
                self._cancel_btn.clicked.connect(lambda: self._confirm_page_selection(result))
                # Add a separate Cancel before the stretch in the button row
                cancel2 = QPushButton('Cancel')
                cancel2.clicked.connect(self.reject)
                self._btn_row.insertWidget(0, cancel2)
        else:
            self._save_threads_instagram(result)
            display = result.external_account_name or result.external_account_id or 'account'
            self._finish_success(display)

    def _confirm_page_selection(self, result: OAuthFlowResult) -> None:
        if self._page_selector is None:
            return
        page = self._page_selector.selected_page()
        if page is None:
            return
        self._save_facebook_page(result, page)
        self._finish_success(page.page_name)

    def _on_failed(self, error_msg: str) -> None:
        self._progress.setVisible(False)
        self._status_label.setText(f'Error: {error_msg}')
        self._cancel_btn.setText('Close')
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.reject)

    def _on_cancel(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(3000)
        self.reject()

    # ── Credential persistence ─────────────────────────────────────────

    def _save_threads_instagram(self, result: OAuthFlowResult) -> None:
        creds = {
            'provider': result.provider,
            'access_token': result.access_token,
            'expires_at': result.expires_at,
            'granted_scopes': result.granted_scopes,
            'external_account_id': result.external_account_id,
            'external_account_name': result.external_account_name,
        }
        self._auth_manager.save_account_credentials(result.account_id, creds)
        profile_name = result.external_account_name or result.external_account_id or ''
        self._auth_manager.add_account(
            AccountConfig(
                platform_id=result.provider,
                account_id=result.account_id,
                profile_name=profile_name,
            )
        )
        get_logger().info(f'Connected {result.provider} account: {profile_name}')

    def _save_facebook_page(self, result: OAuthFlowResult, page: FacebookPageInfo) -> None:
        creds = {
            'provider': 'meta_facebook_page',
            'page_access_token': page.long_lived_page_access_token,
            'page_id': page.page_id,
            'page_name': page.page_name,
            'user_access_token': result.access_token,
            'user_token_expires_at': result.expires_at,
        }
        self._auth_manager.save_account_credentials(result.account_id, creds)
        self._auth_manager.add_account(
            AccountConfig(
                platform_id='meta_facebook_page',
                account_id=result.account_id,
                profile_name=page.page_name,
            )
        )
        get_logger().info(f'Connected Facebook Page: {page.page_name}')

    def _finish_success(self, display_name: str) -> None:
        self._status_label.setText(f'Successfully connected: {display_name}')
        self._cancel_btn.setText('Done')
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.accept)

    # ── Cleanup ────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(3000)
        super().closeEvent(event)
