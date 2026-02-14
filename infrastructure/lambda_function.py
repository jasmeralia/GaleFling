"""AWS Lambda function for receiving log uploads from GalePost.

Receives log bundles via API Gateway and sends
a notification email via SES.
"""

import base64
import json
import os
import uuid
from datetime import datetime

import boto3

ses = boto3.client('ses')

NOTIFY_EMAIL = os.environ.get('NOTIFY_EMAIL', 'morgan@windsofstorm.net')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'morgan@windsofstorm.net')


def lambda_handler(event, context):
    """Handle log upload from the desktop application.

    Expected POST body (JSON):
    {
        "app_version": "0.1.0",
        "error_code": "BS-AUTH-EXPIRED",
        "user_id": "uuid",
        "user_notes": "what the user was doing",
        "os_platform": "Windows-11-10.0.26100-SP0",
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
        return _cors_response(
            400,
            {
                'success': False,
                'message': 'Invalid JSON body',
            },
        )

    # Validate required fields
    if not body.get('user_id'):
        return _cors_response(
            400,
            {
                'success': False,
                'message': 'Missing required field: user_id',
            },
        )
    if not body.get('user_notes'):
        return _cors_response(
            400,
            {
                'success': False,
                'message': 'Missing required field: user_notes',
            },
        )

    upload_id = str(uuid.uuid4())[:12]
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    app_version = body.get('app_version', 'unknown')
    error_code = body.get('error_code', 'MANUAL')
    user_id = body.get('user_id', 'unknown')
    user_notes = body.get('user_notes', '')
    os_platform = body.get('os_platform', '')
    os_display = os_platform or 'Unknown OS'

    # Send notification email via SES (attachments preferred)
    try:
        attachments, skipped = _collect_attachments(body)
        file_list = '\n'.join(
            f'  - {item["filename"]} ({item["size"]} bytes)' for item in attachments
        )
        skipped_list = '\n'.join(f'  - {item}' for item in skipped)
        email_body = (
            f'New error report received from GalePost.\n\n'
            f'Upload ID: {upload_id}\n'
            f'Timestamp: {timestamp}\n'
            f'App Version: {app_version}\n'
            f'Error Code: {error_code}\n'
            f'User ID: {user_id}\n\n'
            f'User Notes:\n{user_notes}\n\n'
            f'OS Platform: {os_platform}\n\n'
            f'Files attached:\n{file_list or "  (none)"}\n\n'
            f'Files skipped due to size limits:\n{skipped_list or "  (none)"}\n'
        )

        if attachments:
            raw_message = _build_raw_email(
                subject=f'[GalePost] Error Report: {error_code} on {os_display}',
                body=email_body,
                sender=SENDER_EMAIL,
                recipient=NOTIFY_EMAIL,
                attachments=attachments,
            )
            ses.send_raw_email(
                Source=SENDER_EMAIL,
                Destination={'ToAddresses': [NOTIFY_EMAIL]},
                RawMessage={'Data': raw_message},
            )
        else:
            ses.send_email(
                Source=SENDER_EMAIL,
                Destination={'ToAddresses': [NOTIFY_EMAIL]},
                Message={
                    'Subject': {
                        'Data': f'[GalePost] Error Report: {error_code} on {os_display}',
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
        print(f'SES email failed: {e}')

    return _cors_response(
        200,
        {
            'success': True,
            'upload_id': upload_id,
            'message': 'Logs uploaded successfully',
        },
    )


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


def _collect_attachments(body: dict) -> tuple[list[dict], list[str]]:
    """Decode log files and screenshots into attachments within size limits."""
    max_total_bytes = 8 * 1024 * 1024
    attachments: list[dict] = []
    skipped: list[str] = []
    total_bytes = 0

    def add_attachment(filename: str, content_b64: str, content_type: str) -> None:
        nonlocal total_bytes
        if not content_b64:
            return
        try:
            decoded = base64.b64decode(content_b64)
        except Exception:
            skipped.append(filename)
            return
        size = len(decoded)
        if total_bytes + size > max_total_bytes:
            skipped.append(filename)
            return
        attachments.append(
            {
                'filename': filename,
                'content_type': content_type,
                'content': decoded,
                'size': size,
            }
        )
        total_bytes += size

    for log_file in body.get('log_files', []):
        add_attachment(
            log_file.get('filename', 'unknown.log'),
            log_file.get('content', ''),
            'text/plain',
        )

    for screenshot in body.get('screenshots', []):
        add_attachment(
            screenshot.get('filename', 'unknown.png'),
            screenshot.get('content', ''),
            'image/png',
        )

    return attachments, skipped


def _build_raw_email(
    subject: str, body: str, sender: str, recipient: str, attachments: list[dict]
) -> bytes:
    boundary = f'===={uuid.uuid4().hex}===='
    lines = [
        f'From: {sender}',
        f'To: {recipient}',
        f'Subject: {subject}',
        'MIME-Version: 1.0',
        f'Content-Type: multipart/mixed; boundary="{boundary}"',
        '',
        f'--{boundary}',
        'Content-Type: text/plain; charset="UTF-8"',
        'Content-Transfer-Encoding: 7bit',
        '',
        body,
        '',
    ]

    for attachment in attachments:
        encoded = base64.b64encode(attachment['content']).decode('ascii')
        lines.extend(
            [
                f'--{boundary}',
                f'Content-Type: {attachment["content_type"]}; name="{attachment["filename"]}"',
                'Content-Transfer-Encoding: base64',
                f'Content-Disposition: attachment; filename="{attachment["filename"]}"',
                '',
                encoded,
                '',
            ]
        )

    lines.append(f'--{boundary}--')
    lines.append('')
    return '\r\n'.join(lines).encode('utf-8')
