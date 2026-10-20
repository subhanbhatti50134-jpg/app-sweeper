"""Backend registry."""

from typing import List, Type

from uninstaller.backends.base import Backend

# Populated by _register_defaults()
_BACKEND_CLASSES: List[Type[Backend]] = []


def register(cls: Type[Backend]) -> Type[Backend]:
    """Class decorator to register a backend."""
    _BACKEND_CLASSES.append(cls)
    return cls


def _register_defaults() -> None:
    # Importing triggers the @register decorators in each module.
    from uninstaller.backends import (  # noqa: F401
        apt,
        dnf,
        pacman,
        zypper,
        snap,
        flatpak,
    )


def get_all_backends() -> List[Backend]:
    """Instantiate every registered backend."""
    if not _BACKEND_CLASSES:
        _register_defaults()
    return [cls() for cls in _BACKEND_CLASSES]


def get_available_backends() -> List[Backend]:
    """Return only backends usable on this system."""
    return [b for b in get_all_backends() if b.is_available()]


def get_backend(name: str) -> Backend:
    """Return a single backend by name, or raise KeyError."""
    for b in get_all_backends():
        if b.name == name:
            return b
    raise KeyError(f"Unknown package manager backend: {name!r}")
