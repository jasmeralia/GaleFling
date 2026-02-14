"""Abstract base class for all social media platforms."""

from abc import ABC, abstractmethod
from pathlib import Path

from src.utils.constants import PlatformSpecs, PostResult


class BasePlatform(ABC):
    """All platforms must implement this interface."""

    @abstractmethod
    def authenticate(self) -> tuple[bool, str | None]:
        """Authenticate with platform. Returns (success, error_code)."""

    @abstractmethod
    def test_connection(self) -> tuple[bool, str | None]:
        """Test if credentials are valid. Returns (success, error_code)."""

    @abstractmethod
    def get_specs(self) -> PlatformSpecs:
        """Return platform requirements and constraints."""

    @abstractmethod
    def post(self, text: str, image_path: Path | None = None) -> PostResult:
        """Post content. Returns detailed result with clickable URL."""

    @abstractmethod
    def get_platform_name(self) -> str:
        """Return display name (e.g., 'Twitter', 'Bluesky')."""
