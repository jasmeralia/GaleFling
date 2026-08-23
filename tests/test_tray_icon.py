from PyQt6.QtWidgets import QWidget

from src.gui.tray_icon import TrayIcon


def _make_tray(qtbot):
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
    tray._test_parent = parent  # keep parent alive — its QMenu/QAction children depend on it
    return tray


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


def test_set_pending_count_toggles_icon_only_on_presence_change(qtbot, monkeypatch):
    tray = _make_tray(qtbot)
    calls = []
    monkeypatch.setattr(tray, 'setIcon', calls.append)

    tray.set_pending_count(0)
    assert calls == []

    tray.set_pending_count(3)
    assert len(calls) == 1

    tray.set_pending_count(5)  # still >0 — no redundant refresh
    assert len(calls) == 1

    tray.set_pending_count(0)
    assert len(calls) == 2


def test_failure_indicator_marked_and_cleared_independent_of_resolution(qtbot, monkeypatch):
    tray = _make_tray(qtbot)
    calls = []
    monkeypatch.setattr(tray, 'setIcon', calls.append)

    tray.mark_failure_unseen()
    assert len(calls) == 1
    tray.mark_failure_unseen()  # already flagged — no redundant refresh
    assert len(calls) == 1

    # Clearing must not depend on whether the underlying failure was fixed.
    tray.clear_failure_indicator()
    assert len(calls) == 2
    tray.clear_failure_indicator()
    assert len(calls) == 2


def test_compose_icon_draws_distinct_badges_per_state(qtbot):
    tray = _make_tray(qtbot)
    base = tray._compose_icon().pixmap(64, 64).toImage()

    tray._has_pending = True
    pending_icon = tray._compose_icon().pixmap(64, 64).toImage()
    assert pending_icon != base

    tray._has_pending = False
    tray._has_unseen_failure = True
    failure_icon = tray._compose_icon().pixmap(64, 64).toImage()
    assert failure_icon != base
    assert failure_icon != pending_icon

    tray._has_pending = True
    both_icon = tray._compose_icon().pixmap(64, 64).toImage()
    assert both_icon != pending_icon
    assert both_icon != failure_icon


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
