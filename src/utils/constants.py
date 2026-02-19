"""Platform specifications, error codes, and application constants."""

from dataclasses import dataclass, field
from datetime import datetime

APP_NAME = 'GaleFling'
APP_VERSION = '0.2.55'
APP_ORG = 'GaleFling'
LOG_UPLOAD_ENDPOINT = 'https://galepost.jasmer.tools/logs/upload'

DRAFT_AUTO_SAVE_INTERVAL_SECONDS = 30


@dataclass
class PlatformSpecs:
    """Platform-specific constraints and capabilities."""

    platform_name: str
    max_image_dimensions: tuple[int, int]
    max_file_size_mb: float
    supported_formats: list[str]
    max_text_length: int
    requires_facets: bool = False
    platform_color: str = '#000000'
    api_type: str = ''
    auth_method: str = ''


TWITTER_SPECS = PlatformSpecs(
    platform_name='Twitter',
    max_image_dimensions=(4096, 4096),
    max_file_size_mb=5.0,
    supported_formats=['JPEG', 'PNG', 'GIF', 'WEBP'],
    max_text_length=280,
    requires_facets=False,
    platform_color='#1DA1F2',
    api_type='tweepy',
    auth_method='oauth1.0a',
)

BLUESKY_SPECS = PlatformSpecs(
    platform_name='Bluesky',
    max_image_dimensions=(2000, 2000),
    max_file_size_mb=1.0,
    supported_formats=['JPEG', 'PNG'],
    max_text_length=300,
    requires_facets=True,
    platform_color='#0085FF',
    api_type='atproto',
    auth_method='app_password',
)


@dataclass
class PostResult:
    """Result of a post attempt."""

    success: bool
    platform: str = ''
    post_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_response: dict | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


ERROR_CODES = {
    # Authentication (AUTH)
    'TW-AUTH-INVALID': 'Twitter credentials are invalid.',
    'TW-AUTH-EXPIRED': 'Twitter access token has expired.',
    'BS-AUTH-INVALID': 'Bluesky app password is invalid.',
    'BS-AUTH-EXPIRED': 'Bluesky session has expired.',
    'AUTH-MISSING': 'No credentials found for platform.',
    # Rate Limiting (RATE)
    'TW-RATE-LIMIT': 'Twitter rate limit exceeded.',
    'BS-RATE-LIMIT': 'Bluesky rate limit exceeded.',
    # Image Processing (IMG)
    'IMG-TOO-LARGE': 'Image file size exceeds platform limits.',
    'IMG-INVALID-FORMAT': 'Image format not supported.',
    'IMG-RESIZE-FAILED': 'Failed to resize image.',
    'IMG-UPLOAD-FAILED': 'Image upload to platform failed.',
    'IMG-NOT-FOUND': 'Image file does not exist.',
    'IMG-CORRUPT': 'Image file is corrupted or unreadable.',
    # Network (NET)
    'NET-TIMEOUT': 'Request timed out.',
    'NET-CONNECTION': 'Could not connect to platform.',
    'NET-DNS': 'DNS resolution failed.',
    'NET-SSL': 'SSL certificate verification failed.',
    # Post Submission (POST)
    'POST-TEXT-TOO-LONG': 'Post text exceeds character limit.',
    'POST-DUPLICATE': 'Platform rejected duplicate post.',
    'POST-FAILED': 'Post submission failed.',
    'POST-EMPTY': 'Post text cannot be empty.',
    # System (SYS)
    'SYS-CONFIG-MISSING': 'Configuration file not found.',
    'SYS-PERMISSION': 'Insufficient file system permissions.',
    'SYS-DISK-FULL': 'Disk full, cannot save logs.',
    'SYS-UNKNOWN': 'Unknown system error occurred.',
}

USER_FRIENDLY_MESSAGES = {
    'TW-AUTH-INVALID': "Your Twitter credentials don't seem to be working. Please check them in Settings.",
    'TW-AUTH-EXPIRED': "Your Twitter access token has expired. Click 'Open Settings' to update it.",
    'BS-AUTH-INVALID': 'Your Bluesky app password is incorrect. Please check it in Settings.',
    'BS-AUTH-EXPIRED': "Your Bluesky session expired. Click 'Open Settings' to reconnect.",
    'AUTH-MISSING': 'No credentials found. Please set up your account in Settings.',
    'TW-RATE-LIMIT': "Twitter says you're posting too fast. Try again in about 15 minutes.",
    'BS-RATE-LIMIT': "Bluesky says you're posting too fast. Try again in a few minutes.",
    'IMG-TOO-LARGE': 'This image is too big. The app will try to resize it automatically.',
    'IMG-INVALID-FORMAT': "This image format isn't supported. Please use JPEG or PNG.",
    'IMG-RESIZE-FAILED': "Couldn't resize the image to fit platform requirements.",
    'IMG-UPLOAD-FAILED': 'Image upload failed. Please try again.',
    'IMG-NOT-FOUND': "The selected image file can't be found. It may have been moved or deleted.",
    'IMG-CORRUPT': 'This image file appears to be corrupted. Please try a different image.',
    'NET-TIMEOUT': 'The request timed out. Please check your internet and try again.',
    'NET-CONNECTION': "Couldn't connect to the platform. Please check your internet connection.",
    'NET-DNS': 'DNS lookup failed. Please check your internet connection.',
    'NET-SSL': 'SSL error. Please check your system clock and internet connection.',
    'POST-TEXT-TOO-LONG': 'Your post is too long for this platform. Please shorten it.',
    'POST-DUPLICATE': 'This platform thinks this is a duplicate post. Try changing the text slightly.',
    'POST-FAILED': 'Post failed. Please try again.',
    'POST-EMPTY': 'Please enter some text before posting.',
    'SYS-CONFIG-MISSING': 'A configuration file is missing. Try reinstalling the app.',
    'SYS-PERMISSION': "The app doesn't have permission to write files. Try running as administrator.",
    'SYS-DISK-FULL': 'Your disk is full. Please free up some space.',
    'SYS-UNKNOWN': 'Something unexpected went wrong. Please send your logs to Jas.',
}
