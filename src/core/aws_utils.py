"""AWS utility helpers for GaleFling.

boto3 is imported lazily inside functions so that:
- Unit tests can mock it without boto3 being installed.
- The module can be imported in environments where boto3 is absent
  (though the installed app always has it via requirements.txt).
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path


def check_s3_connection(
    access_key_id: str,
    secret_access_key: str,
    region: str,
    bucket: str,
) -> tuple[bool, str]:
    """Attempt a PutObject to verify S3 credentials and bucket access.

    Uploads a tiny probe object under the key
    ``staging/.galefling-connection-test``. The object is intentionally
    not deleted after the test — the bucket lifecycle policy (1-day
    incomplete-multipart + 7-day object expiry) will clean it up, and
    the IAM user has PutObject-only access (no DeleteObject).

    Returns ``(True, '')`` on success or ``(False, error_message)`` on failure.
    """
    try:
        import boto3
        import botocore.exceptions
    except ImportError:
        return False, 'boto3 is not installed. Please reinstall GaleFling.'

    probe_key = 'staging/.galefling-connection-test'
    try:
        client = boto3.client(
            's3',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )
        client.put_object(
            Bucket=bucket,
            Key=probe_key,
            Body=b'galefling-connection-test',
            ContentType='text/plain',
        )
        return True, ''
    except botocore.exceptions.ClientError as exc:
        code = exc.response.get('Error', {}).get('Code', 'Unknown')
        msg = exc.response.get('Error', {}).get('Message', str(exc))
        return False, f'AWS error ({code}): {msg}'
    except botocore.exceptions.NoCredentialsError:
        return False, 'No AWS credentials provided.'
    except Exception as exc:  # noqa: BLE001
        return False, f'Unexpected error: {exc}'


# ── MediaStager ───────────────────────────────────────────────────────────────


class MediaStagingError(Exception):
    """Raised when a media file cannot be staged to S3."""


class MediaStager:
    """Upload media files to S3 for Meta API staging.

    Instagram and Threads require a publicly accessible URL at publish
    time — they do not accept binary uploads in the API payload.  This
    class uploads each file to the configured S3 bucket under the key
    scheme ``staging/{iso-date}/{uuid}/{filename}`` and returns the
    resulting public HTTPS URL.

    The bucket must be configured with a public-read bucket policy and a
    7-day object lifecycle rule (see the CloudFormation stack in
    ``infrastructure/galefling-media-staging.yaml``).  No explicit
    deletion is performed here; the lifecycle policy handles cleanup.
    """

    _CONTENT_TYPES: dict[str, str] = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
    }

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        region: str,
        bucket: str,
    ) -> None:
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._region = region
        self._bucket = bucket

    def upload_media(self, file_path: Path) -> str:
        """Upload *file_path* to S3 and return its public URL.

        Raises ``MediaStagingError`` on any failure (boto3 not installed,
        bucket inaccessible, network error, file read error, etc.).
        """
        try:
            import boto3
            import botocore.exceptions
        except ImportError as exc:
            raise MediaStagingError('boto3 is not installed. Please reinstall GaleFling.') from exc

        key = self._build_key(file_path)
        content_type = self._detect_content_type(file_path)

        try:
            client = boto3.client(
                's3',
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name=self._region,
            )
            with open(file_path, 'rb') as fh:
                client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=fh,
                    ContentType=content_type,
                )
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get('Error', {}).get('Code', 'Unknown')
            msg = exc.response.get('Error', {}).get('Message', str(exc))
            raise MediaStagingError(f'AWS error ({code}): {msg}') from exc
        except botocore.exceptions.NoCredentialsError as exc:
            raise MediaStagingError('No AWS credentials provided.') from exc
        except OSError as exc:
            raise MediaStagingError(f'Could not read file for upload: {exc}') from exc
        except Exception as exc:  # noqa: BLE001
            raise MediaStagingError(f'Unexpected error during S3 upload: {exc}') from exc

        return f'https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}'

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_key(file_path: Path) -> str:
        """Return the S3 object key for *file_path*.

        Format: ``staging/{iso-date}/{uuid}/{filename}``
        """
        iso_date = date.today().isoformat()
        unique_id = str(uuid.uuid4())
        return f'staging/{iso_date}/{unique_id}/{file_path.name}'

    @classmethod
    def _detect_content_type(cls, file_path: Path) -> str:
        """Return a MIME type for *file_path* based on its extension."""
        return cls._CONTENT_TYPES.get(file_path.suffix.lower(), 'application/octet-stream')
