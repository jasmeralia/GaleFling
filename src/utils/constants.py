"""Platform specifications, error codes, and application constants."""

from dataclasses import dataclass, field
from datetime import datetime

APP_NAME = 'GaleFling'
APP_VERSION = '1.5.2'
APP_ORG = 'Winds of Storm'
LOG_UPLOAD_ENDPOINT = 'https://galepost.jasmer.tools/logs/upload'

DRAFT_AUTO_SAVE_INTERVAL_SECONDS = 30

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
MAX_MEDIA_ATTACHMENTS = 4


@dataclass
class PlatformSpecs:
    """Platform-specific constraints and capabilities."""

    platform_name: str
    max_image_dimensions: tuple[int, int]
    max_file_size_mb: float
    supported_formats: list[str]
    max_text_length: int | None
    requires_facets: bool = False
    platform_color: str = '#000000'
    api_type: str = ''
    auth_method: str = ''
    max_accounts: int = 1
    requires_user_confirm: bool = False
    has_cloudflare: bool = False
    # Video support
    supported_video_formats: list[str] = field(default_factory=list)
    max_video_dimensions: tuple[int, int] | None = None
    max_video_file_size_mb: float | None = None
    max_video_duration_seconds: int | None = None
    # Whether the platform supports image posts (False = video-only, e.g. Snapchat web)
    supports_images: bool = True
    # Whether the platform ignores text (e.g. Snapchat web stories)
    supports_text: bool = True
    # Max media attachments per post (images; video is always 1)
    max_media_attachments: int = 1


@dataclass
class AccountConfig:
    """Configuration for a single platform account."""

    platform_id: str
    account_id: str
    profile_name: str
    enabled: bool = True


TWITTER_SPECS = PlatformSpecs(
    platform_name='Twitter',
    max_image_dimensions=(4096, 4096),
    max_file_size_mb=5.0,
    supported_formats=['JPEG', 'PNG', 'GIF', 'WEBP'],
    max_text_length=280,
    requires_facets=False,
    platform_color='#1DA1F2',
    api_type='tweepy',
    auth_method='oauth1.0a_pin',
    max_accounts=2,
    supported_video_formats=['MP4'],
    max_video_dimensions=(1920, 1200),
    max_video_file_size_mb=512.0,
    max_video_duration_seconds=140,
    max_media_attachments=4,
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
    max_accounts=2,
    supported_video_formats=['MP4'],
    max_video_dimensions=(1920, 1080),
    max_video_file_size_mb=50.0,
    max_video_duration_seconds=60,
    max_media_attachments=4,
)

INSTAGRAM_SPECS = PlatformSpecs(
    platform_name='Instagram',
    max_image_dimensions=(1440, 1440),
    max_file_size_mb=8.0,
    supported_formats=['JPEG', 'PNG'],
    max_text_length=2200,
    platform_color='#E1306C',
    api_type='graph_api',
    auth_method='oauth2',
    max_accounts=2,
    supported_video_formats=['MP4'],
    max_video_dimensions=(1920, 1080),
    max_video_file_size_mb=100.0,
    max_video_duration_seconds=60,
)

SNAPCHAT_SPECS = PlatformSpecs(
    platform_name='Snapchat',
    max_image_dimensions=(1080, 1920),
    max_file_size_mb=5.0,
    supported_formats=['JPEG', 'PNG'],
    max_text_length=None,
    platform_color='#FFFC00',
    api_type='webview',
    auth_method='session_cookie',
    max_accounts=2,
    requires_user_confirm=True,
    supported_video_formats=['MP4'],
    max_video_dimensions=(1080, 1920),
    max_video_file_size_mb=50.0,
    max_video_duration_seconds=60,
    supports_images=False,
    supports_text=False,
)

ONLYFANS_SPECS = PlatformSpecs(
    platform_name='OnlyFans',
    max_image_dimensions=(4096, 4096),
    max_file_size_mb=50.0,
    supported_formats=['JPEG', 'PNG', 'WEBP'],
    max_text_length=1000,
    platform_color='#00AFF0',
    api_type='webview',
    auth_method='session_cookie',
    max_accounts=1,
    requires_user_confirm=True,
    has_cloudflare=True,
    supported_video_formats=['MP4', 'MOV'],
    max_video_dimensions=(3840, 2160),
    max_video_file_size_mb=5120.0,
    max_media_attachments=4,
)

FANSLY_SPECS = PlatformSpecs(
    platform_name='Fansly',
    max_image_dimensions=(4096, 4096),
    max_file_size_mb=50.0,
    supported_formats=['JPEG', 'PNG', 'WEBP'],
    max_text_length=3000,
    platform_color='#0FABE5',
    api_type='webview',
    auth_method='session_cookie',
    max_accounts=1,
    requires_user_confirm=True,
    has_cloudflare=True,
    supported_video_formats=['MP4', 'MOV'],
    max_video_dimensions=(3840, 2160),
    max_video_file_size_mb=5120.0,
    max_media_attachments=4,
)

FETLIFE_SPECS = PlatformSpecs(
    platform_name='FetLife',
    max_image_dimensions=(4096, 4096),
    max_file_size_mb=20.0,
    supported_formats=['JPEG', 'PNG'],
    max_text_length=None,
    platform_color='#D4001A',
    api_type='webview',
    auth_method='session_cookie',
    max_accounts=1,
    requires_user_confirm=True,
    supported_video_formats=['MP4'],
    max_video_dimensions=(1920, 1080),
    max_video_file_size_mb=500.0,
)

PLATFORM_SPECS_MAP: dict[str, PlatformSpecs] = {
    'twitter': TWITTER_SPECS,
    'bluesky': BLUESKY_SPECS,
    'instagram': INSTAGRAM_SPECS,
    'snapchat': SNAPCHAT_SPECS,
    'onlyfans': ONLYFANS_SPECS,
    'fansly': FANSLY_SPECS,
    'fetlife': FETLIFE_SPECS,
}


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
    account_id: str | None = None
    profile_name: str | None = None
    url_captured: bool = False
    user_confirmed: bool = False


ERROR_CODES = {
    # Authentication (AUTH)
    'TW-AUTH-INVALID': 'Twitter credentials are invalid.',
    'TW-AUTH-EXPIRED': 'Twitter access token has expired.',
    'BS-AUTH-INVALID': 'Bluesky app password is invalid.',
    'BS-AUTH-EXPIRED': 'Bluesky session has expired.',
    'IG-AUTH-INVALID': 'Instagram credentials are invalid.',
    'IG-AUTH-EXPIRED': 'Instagram access token has expired.',
    'AUTH-MISSING': 'No credentials found for platform.',
    # Rate Limiting (RATE)
    'TW-RATE-LIMIT': 'Twitter rate limit exceeded.',
    'BS-RATE-LIMIT': 'Bluesky rate limit exceeded.',
    'IG-RATE-LIMIT': 'Instagram rate limit exceeded.',
    # Image Processing (IMG)
    'IMG-TOO-LARGE': 'Image file size exceeds platform limits.',
    'IMG-INVALID-FORMAT': 'Image format not supported.',
    'IMG-RESIZE-FAILED': 'Failed to resize image.',
    'IMG-UPLOAD-FAILED': 'Image upload to platform failed.',
    'IMG-NOT-FOUND': 'Image file does not exist.',
    'IMG-CORRUPT': 'Image file is corrupted or unreadable.',
    # Video Processing (VID)
    'VID-NOT-FOUND': 'Video file does not exist.',
    'VID-CORRUPT': 'Video file is corrupted or unreadable.',
    'VID-INVALID-FORMAT': 'Video format not supported by platform.',
    'VID-TOO-LONG': 'Video exceeds maximum duration for platform.',
    'VID-TOO-LARGE': 'Video file size exceeds platform limits.',
    'VID-RESIZE-FAILED': 'Failed to resize or compress video.',
    'VID-UPLOAD-FAILED': 'Video upload to platform failed.',
    'VID-FFMPEG-MISSING': 'ffmpeg binary not found — video processing unavailable.',
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
    # WebView-specific (WV)
    'WV-LOAD-FAILED': 'Could not load platform website.',
    'WV-PREFILL-FAILED': 'Could not pre-fill post composer.',
    'WV-SUBMIT-TIMEOUT': 'Post submission timed out waiting for confirmation.',
    'WV-SESSION-EXPIRED': 'Platform session expired — please log in again via Settings.',
    'WV-URL-CAPTURE-FAILED': 'Post was submitted but the link could not be captured.',
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
    'IG-AUTH-INVALID': 'Your Instagram credentials are not working. Please re-authorize in Settings.',
    'IG-AUTH-EXPIRED': "Your Instagram access token has expired. Click 'Open Settings' to reconnect.",
    'AUTH-MISSING': 'No credentials found. Please set up your account in Settings.',
    'TW-RATE-LIMIT': "Twitter says you're posting too fast. Try again in about 15 minutes.",
    'BS-RATE-LIMIT': "Bluesky says you're posting too fast. Try again in a few minutes.",
    'IG-RATE-LIMIT': "Instagram says you're posting too fast. Try again in a few minutes.",
    'IMG-TOO-LARGE': 'This image is too big. The app will try to resize it automatically.',
    'IMG-INVALID-FORMAT': "This image format isn't supported. Please use JPEG or PNG.",
    'IMG-RESIZE-FAILED': "Couldn't resize the image to fit platform requirements.",
    'IMG-UPLOAD-FAILED': 'Image upload failed. Please try again.',
    'IMG-NOT-FOUND': "The selected image file can't be found. It may have been moved or deleted.",
    'IMG-CORRUPT': 'This image file appears to be corrupted. Please try a different image.',
    'VID-NOT-FOUND': "The selected video file can't be found. It may have been moved or deleted.",
    'VID-CORRUPT': 'This video file appears to be corrupted. Please try a different video.',
    'VID-INVALID-FORMAT': "This video format isn't supported. Please use MP4.",
    'VID-TOO-LONG': 'This video is too long for the platform. It will be trimmed automatically.',
    'VID-TOO-LARGE': 'This video is too large. The app will try to compress it automatically.',
    'VID-RESIZE-FAILED': "Couldn't resize or compress the video to fit platform requirements.",
    'VID-UPLOAD-FAILED': 'Video upload failed. Please try again.',
    'VID-FFMPEG-MISSING': 'Video processing is unavailable because ffmpeg was not found.',
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
    'WV-LOAD-FAILED': 'The platform website failed to load. Please check your internet connection.',
    'WV-PREFILL-FAILED': 'Could not pre-fill the post composer. Please try again.',
    'WV-SUBMIT-TIMEOUT': 'The post confirmation timed out. Please try again.',
    'WV-SESSION-EXPIRED': 'Your session expired. Please log in again via Settings.',
    'WV-URL-CAPTURE-FAILED': 'Post was submitted but we could not capture the link.',
    'SYS-UNKNOWN': 'Something unexpected went wrong. Please send your logs to Jas.',
}
