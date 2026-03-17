"""Functional tests for Bluesky — real API calls against a test account."""

import uuid

import pytest
from atproto import Client as BskyClient


@pytest.mark.functional
class TestBlueskyConnection:
    """Auth and connection tests — run first to fail fast on bad credentials."""

    def test_login(self, bluesky_credentials):
        """Verify that the configured credentials can log in."""
        client = BskyClient()
        profile = client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        assert profile.handle
        assert profile.did

    def test_get_profile(self, bluesky_credentials):
        """Verify we can fetch our own profile after login."""
        client = BskyClient()
        client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        profile = client.get_profile(client.me.did)
        assert profile.handle == client.me.handle


@pytest.mark.functional
class TestBlueskyTextPost:
    """Text-only posting and deletion."""

    def test_text_post_and_delete(self, bluesky_credentials):
        """Create a text post, verify it has a URI, then delete it."""
        client = BskyClient()
        client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        tag = uuid.uuid4().hex[:8]
        text = f'GaleFling functional test {tag} — safe to delete'

        post = client.send_post(text=text)
        assert post.uri
        assert post.cid

        # Cleanup
        client.delete_post(post.uri)

    def test_post_with_url_facets(self, bluesky_credentials):
        """Post text containing a URL and verify facet detection works end-to-end."""
        from src.platforms.bluesky import detect_urls

        client = BskyClient()
        client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        tag = uuid.uuid4().hex[:8]
        text = f'GaleFling test {tag} https://example.com — safe to delete'
        facets = detect_urls(text)
        assert len(facets) == 1

        from datetime import UTC, datetime

        record = {
            '$type': 'app.bsky.feed.post',
            'text': text,
            'createdAt': datetime.now(UTC).isoformat(),
            'facets': facets,
        }
        response = client.com.atproto.repo.create_record(
            data={
                'repo': client.me.did,
                'collection': 'app.bsky.feed.post',
                'record': record,
            }
        )
        assert response.uri

        # Cleanup
        client.delete_post(response.uri)

    def test_character_limit_enforcement(self, bluesky_credentials):
        """Verify the platform rejects posts exceeding 300 graphemes."""
        client = BskyClient()
        client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        # 301 characters should be rejected by the API
        text = 'A' * 301
        posted = False
        try:
            client.send_post(text=text)
            posted = True
        except Exception:
            pass
        assert not posted, 'Expected Bluesky to reject post exceeding 300 characters'


@pytest.mark.functional
class TestBlueskyImagePost:
    """Image upload and posting."""

    def test_single_image_post(self, bluesky_credentials, sample_jpeg):
        """Upload a single image and post it, then delete."""
        client = BskyClient()
        client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        tag = uuid.uuid4().hex[:8]
        img_data = sample_jpeg.read_bytes()
        upload = client.upload_blob(img_data)
        assert upload.blob

        from datetime import UTC, datetime

        record = {
            '$type': 'app.bsky.feed.post',
            'text': f'GaleFling image test {tag} — safe to delete',
            'createdAt': datetime.now(UTC).isoformat(),
            'embed': {
                '$type': 'app.bsky.embed.images',
                'images': [{'alt': 'test image', 'image': upload.blob}],
            },
        }
        response = client.com.atproto.repo.create_record(
            data={
                'repo': client.me.did,
                'collection': 'app.bsky.feed.post',
                'record': record,
            }
        )
        assert response.uri

        # Cleanup
        client.delete_post(response.uri)

    def test_multiple_images_post(self, bluesky_credentials, sample_jpeg, sample_png):
        """Upload two images in a single post, then delete."""
        client = BskyClient()
        client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        tag = uuid.uuid4().hex[:8]
        images = []
        for path in [sample_jpeg, sample_png]:
            upload = client.upload_blob(path.read_bytes())
            images.append({'alt': '', 'image': upload.blob})

        from datetime import UTC, datetime

        record = {
            '$type': 'app.bsky.feed.post',
            'text': f'GaleFling multi-image test {tag} — safe to delete',
            'createdAt': datetime.now(UTC).isoformat(),
            'embed': {
                '$type': 'app.bsky.embed.images',
                'images': images,
            },
        }
        response = client.com.atproto.repo.create_record(
            data={
                'repo': client.me.did,
                'collection': 'app.bsky.feed.post',
                'record': record,
            }
        )
        assert response.uri

        # Cleanup
        client.delete_post(response.uri)


@pytest.mark.functional
class TestBlueskyVideoPost:
    """Video upload and posting."""

    def test_video_post(self, bluesky_credentials, sample_video):
        """Upload a short video and post it, then delete."""
        client = BskyClient()
        client.login(
            bluesky_credentials['identifier'],
            bluesky_credentials['app_password'],
        )
        tag = uuid.uuid4().hex[:8]
        video_data = sample_video.read_bytes()
        upload = client.upload_blob(video_data)
        assert upload.blob

        from datetime import UTC, datetime

        record = {
            '$type': 'app.bsky.feed.post',
            'text': f'GaleFling video test {tag} — safe to delete',
            'createdAt': datetime.now(UTC).isoformat(),
            'embed': {
                '$type': 'app.bsky.embed.video',
                'video': upload.blob,
            },
        }
        response = client.com.atproto.repo.create_record(
            data={
                'repo': client.me.did,
                'collection': 'app.bsky.feed.post',
                'record': record,
            }
        )
        assert response.uri

        # Cleanup
        client.delete_post(response.uri)
