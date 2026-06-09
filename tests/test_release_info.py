"""Tests for scripts/release_info.py."""

from __future__ import annotations

from unittest.mock import patch

from scripts.release_info import head_release_tag, latest_tag, main, next_patch

# ── pure helpers ─────────────────────────────────────────────────────────────


def test_next_patch_increments_patch():
    assert next_patch('v1.8.15') == 'v1.8.16'


def test_next_patch_handles_no_tags():
    assert next_patch(None) == 'v1.0.0'


def test_latest_tag_returns_highest_semver(tmp_path):
    with patch('scripts.release_info._git', return_value='v1.8.15\nv1.8.14\nv1.8.13'):
        assert latest_tag() == 'v1.8.15'


def test_latest_tag_skips_non_semver(tmp_path):
    with patch('scripts.release_info._git', return_value='some-branch\nv1.8.14'):
        assert latest_tag() == 'v1.8.14'


def test_latest_tag_returns_none_when_no_tags():
    with patch('scripts.release_info._git', return_value=''):
        assert latest_tag() is None


def test_head_release_tag_returns_tag_when_present():
    with patch('scripts.release_info._git', return_value='v1.8.15\nsome-other-tag'):
        assert head_release_tag() == 'v1.8.15'


def test_head_release_tag_returns_none_when_no_semver_tag():
    with patch('scripts.release_info._git', return_value='some-other-tag'):
        assert head_release_tag() is None


# ── main() resolution logic ───────────────────────────────────────────────────


def _run(event: str, ref: str, dispatch_release: str = 'false') -> dict[str, str]:
    """Run main() with the given env and return the parsed outputs."""
    env = {'EVENT_NAME': event, 'REF': ref, 'DISPATCH_RELEASE': dispatch_release}
    outputs: dict[str, str] = {}

    def fake_emit(values: dict[str, str]) -> None:
        outputs.update(values)

    with (
        patch.dict('os.environ', env),
        patch('scripts.release_info.emit', side_effect=fake_emit),
    ):
        main()

    return outputs


def test_pull_request_is_not_a_release():
    out = _run('pull_request', 'refs/heads/feature-branch')
    assert out['is_release'] == 'false'


def test_push_master_untagged_head_creates_tag():
    with (
        patch('scripts.release_info.head_release_tag', return_value=None),
        patch('scripts.release_info.latest_tag', return_value='v1.8.15'),
    ):
        out = _run('push', 'refs/heads/master')

    assert out['is_release'] == 'true'
    assert out['create_tag'] == 'true'
    assert out['tag_name'] == 'v1.8.16'


def test_push_master_already_tagged_head_skips_release():
    with patch('scripts.release_info.head_release_tag', return_value='v1.8.15'):
        out = _run('push', 'refs/heads/master')

    assert out['is_release'] == 'false'
    assert out['tag_name'] == 'v1.8.15'


def test_push_tag_is_release_without_creating_tag():
    out = _run('push', 'refs/tags/v1.8.16')
    assert out['is_release'] == 'true'
    assert out['create_tag'] == 'false'
    assert out['tag_name'] == 'v1.8.16'


def test_push_tag_rejects_non_semver():
    env = {'EVENT_NAME': 'push', 'REF': 'refs/tags/not-a-version', 'DISPATCH_RELEASE': 'false'}
    with patch.dict('os.environ', env), patch('scripts.release_info.emit'):
        result = main()
    assert result == 1


def test_workflow_dispatch_no_release_skips():
    out = _run('workflow_dispatch', 'refs/heads/master', dispatch_release='false')
    assert out['is_release'] == 'false'


def test_workflow_dispatch_release_master_creates_tag():
    with (
        patch('scripts.release_info.head_release_tag', return_value=None),
        patch('scripts.release_info.latest_tag', return_value='v1.8.15'),
    ):
        out = _run('workflow_dispatch', 'refs/heads/master', dispatch_release='true')

    assert out['is_release'] == 'true'
    assert out['create_tag'] == 'true'
    assert out['tag_name'] == 'v1.8.16'


def test_workflow_dispatch_release_existing_tag():
    out = _run('workflow_dispatch', 'refs/tags/v1.8.14', dispatch_release='true')
    assert out['is_release'] == 'true'
    assert out['create_tag'] == 'false'
    assert out['tag_name'] == 'v1.8.14'


def test_workflow_dispatch_release_non_master_branch_errors():
    env = {
        'EVENT_NAME': 'workflow_dispatch',
        'REF': 'refs/heads/feature-branch',
        'DISPATCH_RELEASE': 'true',
    }
    with patch.dict('os.environ', env), patch('scripts.release_info.emit'):
        result = main()
    assert result == 1
