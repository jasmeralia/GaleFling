"""Unit tests for the API mutating-artifact cleanup policy.

These cover the decision logic — delete vs leave up, which outcome is reported, what
reaches the ledger — without any live credentials or network access.
"""

import json

import pytest

from tests.functional import functional_cleanup


@pytest.fixture(autouse=True)
def _isolated_cleanup_module(monkeypatch, tmp_path):
    """Detach the module from the ambient pytest run and from the real ledger."""
    monkeypatch.setattr(functional_cleanup, '_CONFIG', None)
    monkeypatch.setattr(functional_cleanup, 'LEDGER_PATH', tmp_path / '.artifacts.jsonl')
    monkeypatch.delenv(functional_cleanup.LEAVE_ARTIFACTS_ENV, raising=False)


def _ledger_records() -> list[dict]:
    path = functional_cleanup.LEDGER_PATH
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


# ── Tag recovery ────────────────────────────────────────────────────


def test_post_tag_recovers_the_tag_from_generated_text():
    """The inverse of ``mutating_post_text()`` — including its no-extra-parts form."""
    from tests.functional.conftest import mutating_post_tag, mutating_post_text

    tag = mutating_post_tag()
    assert functional_cleanup.post_tag(f'{tag} https://example.com') == tag
    assert functional_cleanup.post_tag(tag) == tag

    generated = mutating_post_text('https://example.com')
    assert functional_cleanup.post_tag(generated) == generated.split()[0]


def test_post_tag_tolerates_empty_text():
    assert functional_cleanup.post_tag('') == ''
    assert functional_cleanup.post_tag('   ') == ''


# ── Neutral live content (AGENTS.md rule 14) ────────────


def test_neutral_text_accepts_a_bare_tag():
    functional_cleanup.assert_neutral_live_text('Twitter', 'abc12345')
    functional_cleanup.assert_neutral_live_text('Bluesky', 'abc12345 https://example.com')


@pytest.mark.parametrize(
    'published',
    [
        'GaleFling PNG test 705f1a28 — safe to delete',
        'GaleFling functional test 789b2a6d — safe to delete',
        'abc12345 — safe to ignore',
        'galefling abc12345',  # lowercase must not slip through
    ],
)
def test_neutral_text_rejects_product_name_and_reader_instructions(published):
    """These are the exact shapes that reached live accounts before commit 45c56ca."""
    with pytest.raises(AssertionError, match='non-neutral content'):
        functional_cleanup.assert_neutral_live_text('Threads', published)


def test_neutral_text_catches_what_a_substring_tag_match_would_miss():
    """The read-backs assert ``tag in text``, which old-style captions satisfy.

    This is the whole reason the check reads published text rather than trusting the
    test's own input: a regression reintroducing the caption would pass every other
    assertion in the suite.
    """
    tag = '705f1a28'
    published = f'GaleFling PNG test {tag} — safe to delete'
    assert tag in published  # the existing assertion is happy

    with pytest.raises(AssertionError):
        functional_cleanup.assert_neutral_live_text('Threads', published)


# ── Flag resolution ─────────────────────────────────────────────────


def test_leave_artifacts_defaults_to_deleting():
    assert not functional_cleanup.leave_artifacts_enabled()


def test_leave_artifacts_honours_the_environment_variable(monkeypatch):
    monkeypatch.setenv(functional_cleanup.LEAVE_ARTIFACTS_ENV, '1')
    assert functional_cleanup.leave_artifacts_enabled()


def test_leave_artifacts_honours_the_pytest_option(monkeypatch):
    class _Config:
        def getoption(self, name, default=None):
            assert name == functional_cleanup.LEAVE_ARTIFACTS_OPTION
            return True

    monkeypatch.setattr(functional_cleanup, '_CONFIG', _Config())
    assert functional_cleanup.leave_artifacts_enabled()


# ── Delete path ─────────────────────────────────────────────────────


def test_successful_delete_runs_the_callback_and_writes_no_ledger_record(capsys):
    calls = []
    functional_cleanup.finish_mutating_artifact(
        'Twitter', 'abc12345 body', delete=lambda: calls.append('deleted')
    )

    assert calls == ['deleted']
    assert 'deleted (tag abc12345)' in capsys.readouterr().out
    assert _ledger_records() == []


def test_already_gone_is_reported_distinctly_from_a_failure(capsys):
    def _delete():
        raise functional_cleanup.ArtifactAlreadyGoneError

    functional_cleanup.finish_mutating_artifact('Threads', 'abc12345', delete=_delete)

    out = capsys.readouterr().out
    assert 'already gone (tag abc12345)' in out
    assert 'FAILED' not in out
    # Nothing is live, so a cleanup pass must not be handed this one.
    assert _ledger_records() == []


def test_failed_delete_reports_the_tag_url_and_ledgers_the_live_artifact(capsys):
    def _delete():
        raise functional_cleanup.ArtifactDeleteFailedError('HTTP 400')

    functional_cleanup.finish_mutating_artifact(
        'Instagram', 'abc12345 caption', delete=_delete, url='https://example.test/p/1'
    )

    out = capsys.readouterr().out
    assert 'delete FAILED (tag abc12345)' in out
    assert 'HTTP 400' in out
    assert 'https://example.test/p/1' in out
    assert [r['tag'] for r in _ledger_records()] == ['abc12345']


def test_unexpected_delete_error_is_reported_by_class_name_only(capsys):
    """A requests/tweepy error renders the request URL, which carries the token."""

    class _TokenBearingError(Exception):
        pass

    def _delete():
        raise _TokenBearingError('https://graph.example/123?access_token=SUPERSECRET')

    functional_cleanup.finish_mutating_artifact('Threads', 'abc12345', delete=_delete)

    out = capsys.readouterr().out
    assert '_TokenBearingError' in out
    assert 'SUPERSECRET' not in out
    assert 'access_token' not in out
    assert len(_ledger_records()) == 1


# ── Leave-up path ───────────────────────────────────────────────────


def test_leaving_artifacts_up_skips_the_delete_and_reports_tag_and_url(monkeypatch, capsys):
    monkeypatch.setenv(functional_cleanup.LEAVE_ARTIFACTS_ENV, '1')
    calls = []

    functional_cleanup.finish_mutating_artifact(
        'Bluesky',
        'abc12345 body',
        delete=lambda: calls.append('deleted'),
        url='https://bsky.app/profile/x/post/1',
    )

    assert calls == []
    out = capsys.readouterr().out
    assert 'left up (tag abc12345)' in out
    assert 'https://bsky.app/profile/x/post/1' in out


def test_missing_url_never_suppresses_the_tag_line(monkeypatch, capsys):
    """The tag is the only fallback for finding the post by hand, so it must always print."""
    monkeypatch.setenv(functional_cleanup.LEAVE_ARTIFACTS_ENV, '1')

    functional_cleanup.finish_mutating_artifact('Twitter', 'abc12345', delete=lambda: None)

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert 'left up (tag abc12345)' in lines[0]
    assert 'none reported' in lines[1]


def test_left_up_ledger_record_matches_the_shared_shape(monkeypatch):
    """Field names are fixed by task #420 so one cleanup pass can read both sources."""
    monkeypatch.setenv(functional_cleanup.LEAVE_ARTIFACTS_ENV, '1')
    monkeypatch.setenv(
        'PYTEST_CURRENT_TEST', 'tests/functional/test_twitter_post.py::TestX::test_y (call)'
    )

    functional_cleanup.finish_mutating_artifact(
        'Twitter', 'abc12345 body', delete=lambda: None, url=None, account_id='twitter_1'
    )

    (record,) = _ledger_records()
    assert set(record) == {'platform', 'account_id', 'tag', 'url', 'test', 'created_at'}
    assert record['platform'] == 'Twitter'
    assert record['account_id'] == 'twitter_1'
    assert record['tag'] == 'abc12345'
    assert record['url'] is None  # written as null, not omitted
    assert record['test'] == 'tests/functional/test_twitter_post.py::TestX::test_y'
    assert record['created_at'].endswith('+00:00')


def test_ledger_never_records_the_post_body(monkeypatch):
    """Only the tag is needed to find the post; the body may carry unrelated content."""
    monkeypatch.setenv(functional_cleanup.LEAVE_ARTIFACTS_ENV, '1')

    functional_cleanup.finish_mutating_artifact(
        'Bluesky', 'abc12345 the rest of the body', delete=lambda: None
    )

    assert 'the rest of the body' not in functional_cleanup.LEDGER_PATH.read_text(encoding='utf-8')


def test_ledger_write_failure_does_not_fail_the_test(monkeypatch, capsys, tmp_path):
    """Bookkeeping must never break a run — but it must not vanish silently either."""
    monkeypatch.setenv(functional_cleanup.LEAVE_ARTIFACTS_ENV, '1')
    # A directory where the file should be: open() for append raises IsADirectoryError.
    blocked = tmp_path / 'blocked.jsonl'
    blocked.mkdir()
    monkeypatch.setattr(functional_cleanup, 'LEDGER_PATH', blocked)

    functional_cleanup.finish_mutating_artifact('Twitter', 'abc12345', delete=lambda: None)

    out = capsys.readouterr().out
    assert 'ledger write failed' in out
    assert 'tag abc12345' in out
