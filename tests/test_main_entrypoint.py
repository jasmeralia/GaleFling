"""Additional coverage for src.main bootstrap and error-handling paths."""

from __future__ import annotations

import builtins
import contextlib
import sys
import threading
import types
from pathlib import Path

import pytest

from src import main as main_module


def _capture_exception() -> tuple[type[BaseException], BaseException, object]:
    try:
        raise RuntimeError('boom')
    except RuntimeError as exc:
        return type(exc), exc, exc.__traceback__


def test_abort_if_elevated_returns_early_on_non_windows(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module.sys, 'platform', 'linux')
    main_module._abort_if_elevated()


def test_abort_if_elevated_ignores_ctypes_failures(monkeypatch: pytest.MonkeyPatch):
    called: dict[str, bool] = {}

    monkeypatch.setattr(main_module.sys, 'platform', 'win32')
    monkeypatch.setitem(sys.modules, 'ctypes', types.SimpleNamespace())
    monkeypatch.setattr(
        main_module,
        'QMessageBox',
        type('Q', (), {'critical': lambda *_a, **_k: called.setdefault('shown', True)}),
    )

    main_module._abort_if_elevated()
    assert called == {}


def test_crash_log_writer_methods(tmp_path: Path):
    path = tmp_path / 'fatal_errors.log'
    with path.open('w+', encoding='utf-8') as fh:
        writer = main_module.CrashLogWriter(fh)
        writer.write('Fatal Python error: simulated\n')
        writer.write('stack line\n')
        writer.flush()
        assert writer.fileno() == fh.fileno()
        assert writer.writable() is True
        assert writer.isatty() is False
        writer.write_marker('marker')

    content = path.read_text(encoding='utf-8')
    assert 'Fatal Python error: simulated' in content
    assert 'marker' in content
    assert '[' in content  # timestamp prefix


def test_apply_app_icon_prefers_png(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    png = tmp_path / 'icon.png'
    ico = tmp_path / 'icon.ico'
    png.write_bytes(b'png')
    ico.write_bytes(b'ico')

    monkeypatch.setattr(
        main_module, 'get_resource_path', lambda name: png if name == 'icon.png' else ico
    )
    monkeypatch.setattr(main_module, 'QIcon', lambda value: f'ICON:{value}')

    class DummyApp:
        def __init__(self):
            self.icon = None

        def setWindowIcon(self, icon):  # noqa: N802
            self.icon = icon

    app = DummyApp()
    main_module._apply_app_icon(app)  # type: ignore[arg-type]
    assert str(png) in str(app.icon)


def test_apply_app_icon_falls_back_to_ico(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    ico = tmp_path / 'icon.ico'
    ico.write_bytes(b'ico')

    def _resource(name: str) -> Path:
        if name == 'icon.png':
            return tmp_path / 'missing.png'
        return ico

    monkeypatch.setattr(main_module, 'get_resource_path', _resource)
    monkeypatch.setattr(main_module, 'QIcon', lambda value: f'ICON:{value}')

    class DummyApp:
        def __init__(self):
            self.icon = None

        def setWindowIcon(self, icon):  # noqa: N802
            self.icon = icon

    app = DummyApp()
    main_module._apply_app_icon(app)  # type: ignore[arg-type]
    assert str(ico) in str(app.icon)


def test_enable_fault_handler_noop_when_already_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, '_FAULT_LOG_FILE', object())
    monkeypatch.setattr(
        main_module.faulthandler,
        'enable',
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('should not run')),
    )
    main_module._enable_fault_handler()


def test_enable_fault_handler_handles_open_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    stack = contextlib.ExitStack()
    monkeypatch.setattr(main_module, '_FAULT_LOG_STACK', stack)
    monkeypatch.setattr(main_module, '_FAULT_LOG_FILE', None)
    monkeypatch.setattr(main_module, 'get_logs_dir', lambda: tmp_path)
    monkeypatch.setattr(builtins, 'open', lambda *_a, **_k: (_ for _ in ()).throw(OSError('nope')))

    main_module._enable_fault_handler()
    assert main_module._FAULT_LOG_FILE is None
    stack.close()


def test_write_fatal_marker_handles_writer_errors(monkeypatch: pytest.MonkeyPatch):
    class BrokenWriter:
        def write_marker(self, _label: str) -> None:
            raise OSError('fail')

    monkeypatch.setattr(main_module, '_FAULT_LOG_FILE', BrokenWriter())
    main_module._write_fatal_marker('test-marker')


def test_flush_logger_ignores_flush_errors():
    called: list[str] = []

    class BrokenHandler:
        def flush(self) -> None:
            raise RuntimeError('fail')

    class GoodHandler:
        def flush(self) -> None:
            called.append('ok')

    logger = type('L', (), {'handlers': [BrokenHandler(), GoodHandler()]})()
    main_module._flush_logger(logger)
    assert called == ['ok']


def test_write_crash_log_includes_frozen_header(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(main_module, 'get_logs_dir', lambda: tmp_path)
    monkeypatch.setattr(main_module.sys, 'frozen', True, raising=False)
    exc_type, exc, tb = _capture_exception()

    main_module._write_crash_log(exc_type, exc, tb, context='test')

    crash_files = list(tmp_path.glob('crash_*.log'))
    assert crash_files
    content = crash_files[0].read_text(encoding='utf-8')
    assert 'Frozen: True' in content


def test_write_crash_log_swallows_failures(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main_module, 'get_logs_dir', lambda: (_ for _ in ()).throw(OSError('nope')))
    exc_type, exc, tb = _capture_exception()
    main_module._write_crash_log(exc_type, exc, tb, context='test')


def test_install_exception_logging_handles_thread_exceptions(monkeypatch: pytest.MonkeyPatch):
    class DummyLogger:
        def __init__(self):
            self.errors: list[str] = []
            self.handlers = []

        def error(self, message, **_kwargs):
            self.errors.append(message)

        def info(self, *_args, **_kwargs):
            return None

        def debug(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def critical(self, *_args, **_kwargs):
            return None

    logger = DummyLogger()
    crash_contexts: list[str] = []

    monkeypatch.setattr(main_module, 'get_logger', lambda: logger)
    monkeypatch.setattr(main_module, '_enable_fault_handler', lambda: None)
    monkeypatch.setattr(main_module, '_flush_logger', lambda _logger: None)
    monkeypatch.setattr(
        main_module,
        '_write_crash_log',
        lambda *_a, **kwargs: crash_contexts.append(kwargs['context']),
    )
    monkeypatch.setattr(main_module.QMessageBox, 'critical', lambda *_a, **_k: None)

    prev_sys_hook = sys.excepthook
    prev_thread_hook = getattr(threading, 'excepthook', None)
    main_module._install_exception_logging()
    try:
        args = types.SimpleNamespace(
            exc_type=RuntimeError,
            exc_value=RuntimeError('thread-fail'),
            exc_traceback=None,
        )
        threading.excepthook(args)
    finally:
        sys.excepthook = prev_sys_hook
        if prev_thread_hook is not None:
            threading.excepthook = prev_thread_hook

    assert 'Unhandled thread exception' in logger.errors
    assert 'thread' in crash_contexts


def test_install_qt_message_logging_installs_once(monkeypatch: pytest.MonkeyPatch):
    handlers = []

    class DummyLogger:
        def __init__(self):
            self.handlers = []
            self.infos: list[str] = []

        def info(self, message, *_args, **_kwargs):
            self.infos.append(message)

        def debug(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

        def critical(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(main_module, '_QT_MSG_HANDLER_INSTALLED', False)
    monkeypatch.setattr(main_module, '_QT_MSG_PREVIOUS_HANDLER', None)
    monkeypatch.setattr(main_module, 'get_logger', lambda: DummyLogger())
    monkeypatch.setattr(
        main_module, 'qInstallMessageHandler', lambda handler: handlers.append(handler)
    )

    main_module._install_qt_message_logging()
    main_module._install_qt_message_logging()

    assert len(handlers) == 1


def test_qt_message_handler_logs_and_writes_fatal_marker(monkeypatch: pytest.MonkeyPatch):
    installed = {}
    previous_calls: list[tuple[object, object, object]] = []
    fatal_markers: list[str] = []

    def previous_handler(msg_type, context, message):
        previous_calls.append((msg_type, context, message))

    class DummyLogger:
        def __init__(self):
            self.handlers = []
            self.warning_messages: list[str] = []
            self.critical_messages: list[str] = []
            self.info_messages: list[str] = []

        def info(self, message, *_args, **_kwargs):
            self.info_messages.append(message)

        def debug(self, *_args, **_kwargs):
            return None

        def warning(self, message, *_args, **_kwargs):
            self.warning_messages.append(message)

        def error(self, *_args, **_kwargs):
            return None

        def critical(self, message, *_args, **_kwargs):
            self.critical_messages.append(message)

    logger = DummyLogger()
    monkeypatch.setattr(main_module, '_QT_MSG_HANDLER_INSTALLED', False)
    monkeypatch.setattr(main_module, '_QT_MSG_PREVIOUS_HANDLER', None)
    monkeypatch.setattr(main_module, 'get_logger', lambda: logger)

    def install_handler(handler):
        installed['handler'] = handler
        return previous_handler

    monkeypatch.setattr(
        main_module,
        'qInstallMessageHandler',
        install_handler,
    )
    monkeypatch.setattr(main_module, '_flush_logger', lambda _logger: None)
    monkeypatch.setattr(
        main_module, '_write_fatal_marker', lambda label: fatal_markers.append(label)
    )

    main_module._install_qt_message_logging()

    context = types.SimpleNamespace(
        category='qt.test',
        file='test.cpp',
        line=12,
        function='f',
    )
    installed['handler'](main_module.QtMsgType.QtWarningMsg, context, 'warn message')
    installed['handler'](main_module.QtMsgType.QtFatalMsg, context, 'fatal message')

    assert any('Qt warning:' in msg for msg in logger.warning_messages)
    assert any('Qt fatal:' in msg for msg in logger.critical_messages)
    assert fatal_markers == ['Qt fatal: fatal message']
    assert len(previous_calls) == 2


def test_main_bootstrap_flow(monkeypatch: pytest.MonkeyPatch):
    class DummyConfig:
        debug_mode = True
        theme_mode = 'system'
        webview_compatibility_mode = False

    class DummyApp:
        def __init__(self, _args):
            self.name = ''
            self.org = ''

        def setApplicationName(self, value):  # noqa: N802
            self.name = value

        def setOrganizationName(self, value):  # noqa: N802
            self.org = value

        def exec(self):  # noqa: A003
            return 42

    class DummyWindow:
        def __init__(self):
            self.shown = False
            self.restored = False
            self.checked = False

        def show(self):
            self.shown = True

        def restore_draft(self):
            self.restored = True

        def check_for_updates_on_startup(self):
            self.checked = True

    window = DummyWindow()
    calls: dict[str, object] = {'theme_calls': []}

    monkeypatch.setattr(main_module, 'ConfigManager', lambda: DummyConfig())
    monkeypatch.setattr(main_module, 'GaleFlingApplication', DummyApp)
    monkeypatch.setattr(main_module, 'AuthManager', lambda: object())
    monkeypatch.setattr(main_module, 'MainWindow', lambda *_a, **_k: window)
    monkeypatch.setattr(
        main_module,
        'setup_logging',
        lambda debug_mode=False: calls.setdefault('debug_mode', debug_mode),
    )
    monkeypatch.setattr(
        main_module, '_install_exception_logging', lambda: calls.setdefault('installed', True)
    )
    monkeypatch.setattr(
        main_module, '_abort_if_elevated', lambda: calls.setdefault('abort_checked', True)
    )
    monkeypatch.setattr(
        main_module, '_apply_app_icon', lambda _app: calls.setdefault('icon_applied', True)
    )
    monkeypatch.setattr(
        main_module, 'apply_theme', lambda *_a: calls['theme_calls'].append(tuple(_a))
    )
    monkeypatch.setattr(main_module.sys, 'argv', ['galefling'])
    monkeypatch.setattr(
        main_module.sys, 'exit', lambda code=0: (_ for _ in ()).throw(SystemExit(code))
    )

    with pytest.raises(SystemExit) as exc:
        main_module.main()

    assert exc.value.code == 42
    assert calls['debug_mode'] is True
    assert calls.get('installed') is True
    assert calls.get('abort_checked') is True
    assert calls.get('icon_applied') is True
    assert window.shown is True
    assert window.restored is True
    assert window.checked is True


def test_apply_webview_compatibility_flags_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(main_module.os.environ, 'QTWEBENGINE_CHROMIUM_FLAGS', '--foo')
    main_module._apply_webview_compatibility_flags(True)
    flags = main_module.os.environ['QTWEBENGINE_CHROMIUM_FLAGS'].split()
    assert '--foo' in flags
    assert '--disable-gpu' in flags


def test_apply_webview_compatibility_flags_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(
        main_module.os.environ,
        'QTWEBENGINE_CHROMIUM_FLAGS',
        '--foo --disable-gpu',
    )
    main_module._apply_webview_compatibility_flags(False)
    flags = main_module.os.environ['QTWEBENGINE_CHROMIUM_FLAGS'].split()
    assert '--foo' in flags
    assert '--disable-gpu' not in flags
