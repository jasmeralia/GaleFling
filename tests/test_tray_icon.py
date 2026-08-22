from PyQt6.QtWidgets import QWidget

from src.gui.tray_icon import TrayIcon


def test_tray_actions_log_and_pending_count_updates(qtbot, monkeypatch):
    messages = []
    calls = []

    class Logger:
        def info(self, message):
            messages.append(message)

    monkeypatch.setattr('src.gui.tray_icon.get_logger', lambda: Logger())
    parent = QWidget()
    qtbot.addWidget(parent)
    tray = TrayIcon(
        parent,
        show_window=lambda: calls.append('show'),
        show_scheduled=lambda: calls.append('scheduled'),
        check_updates=lambda: calls.append('updates'),
        show_about=lambda: calls.append('about'),
        exit_app=lambda: calls.append('exit'),
    )

    tray.set_pending_count(4)
    scheduled = next(
        action for action in tray.contextMenu().actions() if action.text() == 'Scheduled Posts (4)'
    )
    scheduled.trigger()

    assert calls == ['scheduled']
    assert messages == ['User selected Tray > Scheduled Posts (4)']


def test_tray_failure_click_invokes_details_once(qtbot, monkeypatch):
    parent = QWidget()
    qtbot.addWidget(parent)
    tray = TrayIcon(
        parent,
        show_window=lambda: None,
        show_scheduled=lambda: None,
        check_updates=lambda: None,
        show_about=lambda: None,
        exit_app=lambda: None,
    )
    shown = []
    monkeypatch.setattr(tray, 'showMessage', lambda *args: shown.append(args))
    clicked = []

    tray.show_failure(['Twitter', 'Bluesky'], lambda: clicked.append('details'))
    tray._on_message_clicked()
    tray._on_message_clicked()

    assert shown[0][0] == 'Scheduled post failed'
    assert 'Twitter, Bluesky' in shown[0][1]
    assert clicked == ['details']
