from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.core.scheduled_post_queue import ScheduledPostQueue


def _queue(tmp_path: Path) -> ScheduledPostQueue:
    return ScheduledPostQueue(tmp_path / 'scheduled.sqlite3')


def test_add_copies_media_and_lists_pending(tmp_path):
    source = tmp_path / 'source.jpg'
    source.write_bytes(b'image')
    processed = tmp_path / 'processed.jpg'
    processed.write_bytes(b'processed')
    queue = _queue(tmp_path)

    post = queue.add(
        text='caption',
        account_ids=['twitter_1'],
        media_paths=[source],
        processed_media={'twitter': [processed]},
        due_at=datetime.now(UTC) + timedelta(hours=1),
    )

    source.unlink()
    processed.unlink()
    assert queue.list_pending() == [post]
    assert post.media_paths[0].read_bytes() == b'image'
    assert post.processed_media['twitter'][0].read_bytes() == b'processed'


def test_claim_due_is_atomic_and_honors_deferred_ids(tmp_path):
    queue = _queue(tmp_path)
    due = datetime.now(UTC) - timedelta(minutes=1)
    first = queue.add(
        text='first',
        account_ids=['twitter_1'],
        media_paths=[],
        processed_media={},
        due_at=due,
    )
    second = queue.add(
        text='second',
        account_ids=['bluesky_1'],
        media_paths=[],
        processed_media={},
        due_at=due + timedelta(seconds=1),
    )

    claimed = queue.claim_due(exclude_ids={first.id})

    assert claimed is not None and claimed.id == second.id
    assert queue.claim_due(exclude_ids={first.id}) is None
    assert queue.get(first.id).state == 'pending'


def test_mark_results_and_recover_interrupted_post(tmp_path):
    queue = _queue(tmp_path)
    post = queue.add(
        text='caption',
        account_ids=['twitter_1'],
        media_paths=[],
        processed_media={},
        due_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert queue.claim_due().id == post.id
    assert queue.reset_in_flight() == 1
    assert queue.get(post.id).state == 'pending'

    assert queue.claim_due().id == post.id
    failed = queue.mark_results(post.id, [{'success': False, 'error_message': 'nope'}])
    assert failed.state == 'failed'
    assert queue.list_pending() == []


def test_update_replaces_owned_media_and_delete_cleans_directory(tmp_path):
    queue = _queue(tmp_path)
    first = tmp_path / 'first.png'
    first.write_bytes(b'first')
    post = queue.add(
        text='one',
        account_ids=['twitter_1'],
        media_paths=[first],
        processed_media={'twitter': [first]},
        due_at=datetime.now(UTC) + timedelta(hours=1),
    )
    old_path = post.media_paths[0]
    replacement = post.media_paths[0]

    updated = queue.update(
        post.id,
        text='two',
        account_ids=['bluesky_1'],
        media_paths=[replacement],
        processed_media={'bluesky': [replacement]},
        due_at=datetime.now(UTC) + timedelta(hours=2),
    )

    assert updated.text == 'two'
    assert updated.media_paths[0].read_bytes() == b'first'
    assert old_path == updated.media_paths[0]
    media_root = updated.media_paths[0].parents[1]
    assert queue.delete(post.id)
    assert not media_root.exists()
