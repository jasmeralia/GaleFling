"""GaleFling - Application entry point."""

import contextlib
import faulthandler
import os
import sys
import threading
import traceback
from datetime import datetime

# Ensure src is importable when running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.core.logger import get_logger, setup_logging
from src.gui.main_window import MainWindow
from src.utils.constants import APP_NAME, APP_ORG
from src.utils.helpers import get_logs_dir, get_resource_path
from src.utils.theme import apply_theme


def _abort_if_elevated():
    if sys.platform != 'win32':
        return
    try:
        import ctypes

        shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]
        if shell32.IsUserAnAdmin() != 0:
            QMessageBox.critical(
                None,
                'Administrator Mode Not Supported',
                f'{APP_NAME} cannot run as administrator. Please launch it normally.',
            )
            sys.exit(1)
    except Exception:
        return


_FAULT_LOG_FILE = None
_FAULT_LOG_STACK = contextlib.ExitStack()


class CrashLogWriter:
    def __init__(self, file_handle):
        self._file = file_handle
        self._pending_timestamp = True

    def write(self, text):
        if self._pending_timestamp and (
            'Windows fatal exception' in text or 'Fatal Python error' in text
        ):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self._file.write(f'\n[{timestamp}] ')
            self._pending_timestamp = False
        self._file.write(text)

    def flush(self):
        self._file.flush()

    def fileno(self):
        return self._file.fileno()

    def writable(self):
        return True

    def isatty(self):
        return False


class GaleFlingApplication(QApplication):
    def notify(self, receiver, event):  # noqa: D401
        """Trap exceptions raised inside Qt events to ensure they are logged."""
        try:
            return super().notify(receiver, event)
        except Exception:
            exc_type, exc, tb = sys.exc_info()
            logger = get_logger()
            logger.error('Unhandled Qt exception', exc_info=(exc_type, exc, tb))
            _flush_logger(logger)
            _write_crash_log(exc_type, exc, tb, context='qt')
            return False


def main():
    # Initialize config first
    config = ConfigManager()

    # Set up logging
    setup_logging(debug_mode=config.debug_mode)
    _install_exception_logging()

    # Create Qt application
    app = GaleFlingApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    _apply_app_icon(app)
    apply_theme(app, None, config.theme_mode)
    _abort_if_elevated()

    # Enable high DPI support
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    # Initialize auth
    auth_manager = AuthManager()

    # Create and show main window
    window = MainWindow(config, auth_manager)
    window.show()
    apply_theme(app, window, config.theme_mode)

    # Post-show actions
    window.restore_draft()
    window.check_for_updates_on_startup()

    sys.exit(app.exec_())


def _install_exception_logging():
    logger = get_logger()
    _enable_fault_handler()

    def handle_exception(exc_type, exc, tb):
        logger.error('Unhandled exception', exc_info=(exc_type, exc, tb))
        _flush_logger(logger)
        _write_crash_log(exc_type, exc, tb, context='sys')
        QMessageBox.critical(
            None,
            'Unexpected Error',
            'An unexpected error occurred. Please send your logs to Jas for support.',
        )

    def handle_thread_exception(args):
        logger.error(
            'Unhandled thread exception',
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        _flush_logger(logger)
        _write_crash_log(args.exc_type, args.exc_value, args.exc_traceback, context='thread')

    sys.excepthook = handle_exception
    if hasattr(threading, 'excepthook'):
        threading.excepthook = handle_thread_exception


def _apply_app_icon(app: QApplication) -> None:
    icon_path = get_resource_path('icon.png')
    if not icon_path.exists():
        icon_path = get_resource_path('icon.ico')
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))


def _enable_fault_handler():
    global _FAULT_LOG_FILE
    if _FAULT_LOG_FILE is not None:
        return
    try:
        crash_dir = get_logs_dir()
        crash_dir.mkdir(parents=True, exist_ok=True)
        fault_path = crash_dir / 'fatal_errors.log'
        raw_file = _FAULT_LOG_STACK.enter_context(
            open(fault_path, 'a', encoding='utf-8')  # noqa: SIM115
        )
        _FAULT_LOG_FILE = CrashLogWriter(raw_file)
        faulthandler.enable(file=_FAULT_LOG_FILE, all_threads=True)
    except Exception:
        return


def _flush_logger(logger):
    for handler in list(logger.handlers):
        try:
            handler.flush()
        except Exception:
            continue


def _write_crash_log(exc_type, exc, tb, *, context: str):
    try:
        crash_dir = get_logs_dir()
        crash_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        crash_file = crash_dir / f'crash_{timestamp}.log'
        details = ''.join(traceback.format_exception(exc_type, exc, tb))
        header = [
            f'Context: {context}',
            f'Exception: {getattr(exc_type, "__name__", str(exc_type))}',
            f'Message: {exc}',
        ]
        if getattr(sys, 'frozen', False):
            header.append('Frozen: True')
        crash_file.write_text('\n'.join(header) + '\n\n' + details, encoding='utf-8')
    except Exception:
        return


if __name__ == '__main__':
    main()
