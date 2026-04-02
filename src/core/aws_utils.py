"""AWS utility helpers for GaleFling.

Intentionally minimal — only the S3 connection test needed for Phase 2.
The MediaStager (Phase 5) will also live here.

boto3 is imported lazily inside functions so that:
- Unit tests can mock it without boto3 being installed.
- The module can be imported in environments where boto3 is absent
  (though the installed app always has it via requirements.txt).
"""

from __future__ import annotations


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
