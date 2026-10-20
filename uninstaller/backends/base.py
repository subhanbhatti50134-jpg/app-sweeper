"""Package manager backend base class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class InstalledPackage:
    """Represents an installed package."""
    name: str
    version: str = ""
    description: str = ""
    size: int = 0  # bytes, 0 = unknown
    manager: str = ""  # e.g. "dnf", "apt", "flatpak"
    extras: dict = field(default_factory=dict)

    def display_size(self) -> str:
        from uninstaller.utils.helpers import human_size
        return human_size(self.size) if self.size else "?"


@dataclass
class LeftoverItem:
    """A leftover file/directory found after uninstall scan."""
    path: str
    size: int = 0
    kind: str = "data"  # cache | config | data | temp | log | other
    app_hint: str = ""  # best-guess owning app

    def display_size(self) -> str:
        from uninstaller.utils.helpers import human_size
        return human_size(self.size) if self.size else "?"


@dataclass
class UninstallResult:
    """Result of an uninstall operation."""
    success: bool
    package: str
    manager: str
    message: str = ""
    leftovers_removed: List[str] = field(default_factory=list)
    leftovers_bytes: int = 0


class Backend(ABC):
    """Abstract base for a package-manager backend."""

    #: unique id, e.g. "dnf"
    name: str = ""
    #: human-readable name, e.g. "DNF (Fedora/RHEL)"
    display_name: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this package manager is usable on this system."""

    @abstractmethod
    def list_packages(self, include_orphans: bool = False) -> List[InstalledPackage]:
        """Return installed packages."""

    @abstractmethod
    def uninstall(self, package_name: str) -> UninstallResult:
        """Uninstall a package. Should not remove user data (that's the cleaner's job)."""

    @abstractmethod
    def get_orphans(self) -> List[str]:
        """Return package names that look like orphans / unused deps."""

    def find_package(self, name: str) -> Optional[InstalledPackage]:
        """Find a single package by (partial) name."""
        name_l = name.lower()
        for pkg in self.list_packages():
            if pkg.name.lower() == name_l or name_l in pkg.name.lower():
                return pkg
        return None

    def refresh(self) -> bool:
        """Refresh package metadata. Optional; default no-op."""
        return True
