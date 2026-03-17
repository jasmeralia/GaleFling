"""Functional tests for Instagram — real Graph API calls against a test account.

Instagram requires a Business/Creator account with a linked Facebook Page.
Posts always require an image (no text-only posts).
"""

import uuid

import pytest
import requests

GRAPH_API_BASE = 'https://graph.facebook.com/v21.0'


@pytest.mark.functional
class TestInstagramConnection:
    """Auth and connection tests — run first to fail fast on bad credentials."""

    def test_authenticate(self, instagram_credentials):
        """Verify the access token can query the IG user profile."""
        resp = requests.get(
            f'{GRAPH_API_BASE}/{instagram_credentials["account_id"]}',
            params={
                'fields': 'username',
                'access_token': instagram_credentials['access_token'],
            },
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert 'username' in data


@pytest.mark.functional
class TestInstagramImagePost:
    """Image posting via the 3-step Graph API workflow."""

    def _upload_image_to_page(self, instagram_credentials, image_path):
        """Upload an image to the Facebook Page (unpublished) and return its hosted URL."""
        with open(image_path, 'rb') as f:
            resp = requests.post(
                f'{GRAPH_API_BASE}/{instagram_credentials["page_id"]}/photos',
                files={'source': f},
                data={
                    'published': 'false',
                    'access_token': instagram_credentials['access_token'],
                },
                timeout=60,
            )
        assert resp.status_code == 200, f'Image upload failed: {resp.text}'
        photo_id = resp.json()['id']

        url_resp = requests.get(
            f'{GRAPH_API_BASE}/{photo_id}',
            params={
                'fields': 'images',
                'access_token': instagram_credentials['access_token'],
            },
            timeout=15,
        )
        assert url_resp.status_code == 200
        images = url_resp.json().get('images', [])
        assert images, 'No hosted image URL returned'
        return images[0]['source']

    def _create_and_publish(self, instagram_credentials, image_url, caption):
        """Create a media container and publish it. Returns the media ID."""
        # Create container
        resp = requests.post(
            f'{GRAPH_API_BASE}/{instagram_credentials["account_id"]}/media',
            data={
                'image_url': image_url,
                'caption': caption,
                'access_token': instagram_credentials['access_token'],
            },
            timeout=30,
        )
        assert resp.status_code == 200, f'Container creation failed: {resp.text}'
        container_id = resp.json()['id']

        # Publish
        pub_resp = requests.post(
            f'{GRAPH_API_BASE}/{instagram_credentials["account_id"]}/media_publish',
            data={
                'creation_id': container_id,
                'access_token': instagram_credentials['access_token'],
            },
            timeout=30,
        )
        assert pub_resp.status_code == 200, f'Publish failed: {pub_resp.text}'
        return pub_resp.json()['id']

    def _get_permalink(self, instagram_credentials, media_id):
        resp = requests.get(
            f'{GRAPH_API_BASE}/{media_id}',
            params={
                'fields': 'permalink',
                'access_token': instagram_credentials['access_token'],
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get('permalink')
        return None

    def _delete_post(self, instagram_credentials, media_id):
        requests.delete(
            f'{GRAPH_API_BASE}/{media_id}',
            params={'access_token': instagram_credentials['access_token']},
            timeout=15,
        )

    def test_single_image_post(self, instagram_credentials, sample_jpeg):
        """Upload, create container, publish, verify permalink, then delete."""
        tag = uuid.uuid4().hex[:8]
        image_url = self._upload_image_to_page(instagram_credentials, sample_jpeg)
        caption = f'GaleFling functional test {tag} — safe to delete'

        media_id = self._create_and_publish(instagram_credentials, image_url, caption)
        assert media_id

        permalink = self._get_permalink(instagram_credentials, media_id)
        assert permalink is None or permalink.startswith('https://www.instagram.com/')

        # Cleanup
        self._delete_post(instagram_credentials, media_id)
