from datetime import datetime, timedelta

from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolButton,
)

from src.core.scheduled_post_queue import ScheduledPostQueue
from src.gui.schedule_dialog import (
    MissedPostDialog,
    ScheduleDialog,
    ScheduledPostsDialog,
    _platform_badge,
)


def test_schedule_dialog_uses_combined_editor_and_separate_calendar_button(qtbot):
    dialog = ScheduleDialog(
        text='caption',
        account_names=['Twitter (profile)'],
        account_keys=['twitter'],
        media_count=1,
        autostart_enabled=False,
        due_at=datetime.now().astimezone() + timedelta(hours=1),
    )
    qtbot.addWidget(dialog)

    assert dialog._due_edit.displayFormat() == 'ddd, MMM d, yyyy  h:mm AP'
    assert dialog._due_edit.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    calendar_buttons = [
        button for button in dialog.findChildren(QToolButton) if button.toolTip() == 'Open calendar'
    ]
    assert len(calendar_buttons) == 1
    assert not calendar_buttons[0].icon().isNull()
    assert any(
        label.pixmap() and not label.pixmap().isNull() for label in dialog.findChildren(QLabel)
    )
    assert dialog.findChild(QCheckBox).isChecked()


def test_schedule_dialog_hides_autostart_prompt_when_already_enabled(qtbot):
    dialog = ScheduleDialog(
        text='caption',
        account_names=['Bluesky (profile)'],
        media_count=0,
        autostart_enabled=True,
    )
    qtbot.addWidget(dialog)

    assert dialog.findChild(QCheckBox) is None
    assert dialog.enable_autostart is False


def test_schedule_dialog_rejects_time_inside_five_minute_floor(qtbot, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        'warning',
        lambda *_args: warnings.append('warning') or QMessageBox.StandardButton.Ok,
    )
    dialog = ScheduleDialog(
        text='caption',
        account_names=['Twitter'],
        media_count=0,
        autostart_enabled=True,
    )
    qtbot.addWidget(dialog)
    dialog._due_edit.setDateTime(QDateTime.currentDateTime())

    dialog._validate_and_accept()

    assert warnings == ['warning']
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_scheduled_posts_dialog_edit_cancel_and_empty_state(qtbot, tmp_path, monkeypatch):
    queue = ScheduledPostQueue(tmp_path / 'queue.sqlite3')
    post = queue.add(
        text='caption',
        account_ids=['twitter_1'],
        media_paths=[],
        processed_media={},
        due_at=datetime.now().astimezone() + timedelta(hours=1),
    )
    dialog = ScheduledPostsDialog(
        queue,
        lambda _account_id: 'Twitter',
        None,
        platform_key=lambda _account_id: 'twitter',
    )
    qtbot.addWidget(dialog)
    edited = []
    dialog.edit_requested.connect(edited.append)

    edit = next(button for button in dialog.findChildren(QPushButton) if button.text() == 'Edit')
    edit.click()
    assert edited == [post]

    monkeypatch.setattr(
        QMessageBox,
        'question',
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    cancel = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == 'Cancel'
    )
    cancel.click()
    assert queue.list_pending() == []
    assert any(label.text() == 'No posts scheduled' for label in dialog.findChildren(QLabel))


def test_scheduled_posts_dialog_shows_history_with_state_specific_actions(qtbot, tmp_path):
    queue = ScheduledPostQueue(tmp_path / 'queue.sqlite3')
    posted = queue.add(
        text='posted caption',
        account_ids=['twitter_1'],
        media_paths=[],
        processed_media={},
        due_at=datetime.now().astimezone() - timedelta(minutes=5),
    )
    failed = queue.add(
        text='failed caption',
        account_ids=['bluesky_1'],
        media_paths=[],
        processed_media={},
        due_at=datetime.now().astimezone() - timedelta(minutes=3),
    )
    queue.claim_due()
    queue.mark_results(posted.id, [{'account_id': 'twitter_1', 'success': True}])
    queue.claim_due()
    queue.mark_results(failed.id, [{'account_id': 'bluesky_1', 'success': False}])

    dialog = ScheduledPostsDialog(
        queue,
        lambda _account_id: 'Account',
        None,
        platform_key=lambda _account_id: 'twitter',
    )
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(QLabel)]
    assert 'POSTED' in labels
    assert 'FAILED' in labels

    view_buttons = [
        button for button in dialog.findChildren(QPushButton) if button.text() == 'View Results'
    ]
    assert len(view_buttons) == 2

    retry_buttons = [
        button for button in dialog.findChildren(QPushButton) if button.text() == 'Edit && Retry'
    ]
    assert len(retry_buttons) == 1

    dismiss_buttons = [
        button for button in dialog.findChildren(QPushButton) if button.text() == 'Dismiss'
    ]
    assert len(dismiss_buttons) == 2

    viewed = []
    dialog.view_results_requested.connect(viewed.append)
    view_buttons[0].click()
    assert len(viewed) == 1
    assert viewed[0].id in {posted.id, failed.id}


def test_platform_badge_draws_danger_ring_only_when_failed():
    ok_image = _platform_badge('twitter', failed=False).toImage()
    failed_image = _platform_badge('twitter', failed=True).toImage()

    assert ok_image.size() == failed_image.size()
    # The badge circle itself doesn't reach the outermost pixels (they're
    # reserved as border space -- see _BADGE_BORDER), so this point is only
    # ever painted when the danger ring is drawn.
    top_center_x = ok_image.width() // 2
    assert ok_image.pixelColor(top_center_x, 1).alpha() == 0
    assert failed_image.pixelColor(top_center_x, 1).alpha() > 0


def test_scheduled_posts_dialog_marks_only_the_failed_account_in_a_mixed_result(qtbot, tmp_path):
    queue = ScheduledPostQueue(tmp_path / 'queue.sqlite3')
    post = queue.add(
        text='mixed caption',
        account_ids=['twitter_1', 'bluesky_1'],
        media_paths=[],
        processed_media={},
        due_at=datetime.now().astimezone() - timedelta(minutes=3),
    )
    queue.claim_due()
    queue.mark_results(
        post.id,
        [
            {'account_id': 'twitter_1', 'success': True},
            {'account_id': 'bluesky_1', 'success': False},
        ],
    )
    names = {'twitter_1': 'Twitter (main)', 'bluesky_1': 'Bluesky (main)'}

    dialog = ScheduledPostsDialog(
        queue,
        lambda account_id: names[account_id],
        None,
        platform_key=lambda account_id: account_id.split('_')[0],
    )
    qtbot.addWidget(dialog)

    tooltips = {label.toolTip() for label in dialog.findChildren(QLabel) if label.toolTip()}
    assert 'Bluesky (main) — failed to post' in tooltips
    assert 'Twitter (main)' in tooltips
    assert 'Twitter (main) — failed to post' not in tooltips


def test_scheduled_posts_dialog_dismiss_deletes_history_record(qtbot, tmp_path, monkeypatch):
    queue = ScheduledPostQueue(tmp_path / 'queue.sqlite3')
    post = queue.add(
        text='posted caption',
        account_ids=['twitter_1'],
        media_paths=[],
        processed_media={},
        due_at=datetime.now().astimezone() - timedelta(minutes=5),
    )
    queue.claim_due()
    queue.mark_results(post.id, [{'account_id': 'twitter_1', 'success': True}])

    dialog = ScheduledPostsDialog(
        queue,
        lambda _account_id: 'Account',
        None,
        platform_key=lambda _account_id: 'twitter',
    )
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QMessageBox, 'question', lambda *_args: QMessageBox.StandardButton.Yes)

    dismiss = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == 'Dismiss'
    )
    dismiss.click()

    assert queue.list_history() == []
    assert any(label.text() == 'No posts scheduled' for label in dialog.findChildren(QLabel))


def test_missed_post_dialog_actions(qtbot, tmp_path):
    queue = ScheduledPostQueue(tmp_path / 'queue.sqlite3')
    post = queue.add(
        text='late caption',
        account_ids=['twitter_1'],
        media_paths=[],
        processed_media={},
        due_at=datetime.now().astimezone() - timedelta(minutes=20),
    )
    dialog = MissedPostDialog(
        post,
        index=1,
        total=2,
        display_name=lambda _account_id: 'Twitter',
        platform_key=lambda _account_id: 'twitter',
    )
    qtbot.addWidget(dialog)

    post_all = next(
        button
        for button in dialog.findChildren(QPushButton)
        if button.text().startswith('Post All Remaining')
    )
    post_all.click()

    assert dialog.action == 'post_all'
    assert dialog.result() == QDialog.DialogCode.Accepted
