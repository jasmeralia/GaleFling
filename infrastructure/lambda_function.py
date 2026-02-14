"""AWS Lambda function for receiving log uploads from GalePost.

Receives log bundles via API Gateway, stores them in S3, and sends
a notification email via SES.
"""

import base64
import json
import os
import uuid
from datetime import datetime

import boto3

s3 = boto3.client('s3')
ses = boto3.client('ses')

BUCKET_NAME = os.environ.get('LOG_BUCKET_NAME', 'galepost-logs')
NOTIFY_EMAIL = os.environ.get('NOTIFY_EMAIL', 'morgan@windsofstorm.net')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'noreply@jasmer.tools')


def lambda_handler(event, context):
    """Handle log upload from the desktop application.

    Expected POST body (JSON):
    {
        "app_version": "0.1.0",
        "error_code": "BS-AUTH-EXPIRED",
        "platform": "Bluesky",
        "user_id": "uuid",
        "log_files": [{"filename": "...", "content": "base64..."}],
        "screenshots": [{"filename": "...", "content": "base64..."}]
    }
    """
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return _cors_response(200, {'message': 'OK'})

    try:
        body = json.loads(event.get('body', '{}'))
    except (json.JSONDecodeError, TypeError):
        return _cors_response(400, {
            'success': False,
            'message': 'Invalid JSON body',
        })

    # Validate required fields
    if not body.get('user_id'):
        return _cors_response(400, {
            'success': False,
            'message': 'Missing required field: user_id',
        })

    upload_id = str(uuid.uuid4())[:12]
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    prefix = f"{timestamp}_{upload_id}"

    app_version = body.get('app_version', 'unknown')
    error_code = body.get('error_code', 'MANUAL')
    platform = body.get('platform', 'Unknown')
    user_id = body.get('user_id', 'unknown')

    uploaded_files = []

    # Save log files to S3
    for log_file in body.get('log_files', []):
        filename = log_file.get('filename', 'unknown.log')
        content = log_file.get('content', '')
        try:
            decoded = base64.b64decode(content)
            key = f"{prefix}/logs/{filename}"
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=decoded,
                ContentType='text/plain',
            )
            uploaded_files.append(key)
        except Exception as e:
            print(f"Failed to upload log {filename}: {e}")

    # Save screenshots to S3
    for screenshot in body.get('screenshots', []):
        filename = screenshot.get('filename', 'unknown.png')
        content = screenshot.get('content', '')
        try:
            decoded = base64.b64decode(content)
            key = f"{prefix}/screenshots/{filename}"
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=decoded,
                ContentType='image/png',
            )
            uploaded_files.append(key)
        except Exception as e:
            print(f"Failed to upload screenshot {filename}: {e}")

    # Save metadata
    metadata = {
        'upload_id': upload_id,
        'timestamp': timestamp,
        'app_version': app_version,
        'error_code': error_code,
        'platform': platform,
        'user_id': user_id,
        'files': uploaded_files,
    }
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=f"{prefix}/metadata.json",
        Body=json.dumps(metadata, indent=2),
        ContentType='application/json',
    )

    # Send notification email via SES
    try:
        file_list = '\n'.join(f"  - {f}" for f in uploaded_files)
        email_body = (
            f"New error report received from GalePost.\n\n"
            f"Upload ID: {upload_id}\n"
            f"Timestamp: {timestamp}\n"
            f"App Version: {app_version}\n"
            f"Error Code: {error_code}\n"
            f"Platform: {platform}\n"
            f"User ID: {user_id}\n\n"
            f"Files uploaded:\n{file_list}\n\n"
            f"S3 Bucket: {BUCKET_NAME}\n"
            f"S3 Prefix: {prefix}/\n"
        )

        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [NOTIFY_EMAIL]},
            Message={
                'Subject': {
                    'Data': f"[GalePost] Error Report: {error_code} on {platform}",
                    'Charset': 'UTF-8',
                },
                'Body': {
                    'Text': {
                        'Data': email_body,
                        'Charset': 'UTF-8',
                    },
                },
            },
        )
    except Exception as e:
        # Don't fail the request if email fails
        print(f"SES email failed: {e}")

    return _cors_response(200, {
        'success': True,
        'upload_id': upload_id,
        'message': 'Logs uploaded successfully',
    })


def _cors_response(status_code: int, body: dict) -> dict:
    """Return an API Gateway response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        },
        'body': json.dumps(body),
    }
