"""
Base provider abstraction for package managers and update sources.
"""

from abc import ABC, abstractmethod
from typing import Any

class BaseProvider(ABC):
    name: str = "base"
    source_label: str = "base"
    priority: int = 50

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Check if provider is available on current system."""
        pass

    @abstractmethod
    def check_updates(self) -> list[dict[str, Any]]:
        """Return list of available updates."""
        pass

    @abstractmethod
    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        """Apply an update for a single item or handle batch."""
        pass

    @abstractmethod
    def list_installed(self) -> list[dict[str, Any]]:
        """Return list of installed packages for uninstaller."""
        pass

    @abstractmethod
    def uninstall(self, item: dict[str, Any]) -> bool:
        """Uninstall an item."""
        pass
