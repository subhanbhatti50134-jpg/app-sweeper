"""Shared utility functions."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Union


# ---------------------------------------------------------------------------
# Terminal colours
# ---------------------------------------------------------------------------
def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_cyan": "\033[96m",
}


def colorize(text: str, color: str) -> str:
    """Wrap text in ANSI colour codes if the terminal supports it."""
    if not _supports_color():
        return text
    code = _CODES.get(color, "")
    if not code:
        return text
    return f"{code}{text}{_CODES['reset']}"


# ---------------------------------------------------------------------------
# Size formatting
# ---------------------------------------------------------------------------
def human_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable string."""
    if size_bytes <= 0:
        return "0 B"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{int(size_bytes)} B"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PiB"


def get_path_size(path: Union[str, Path]) -> int:
    """Recursively get the total size of a file or directory in bytes."""
    p = Path(path)
    try:
        if p.is_file():
            return p.stat().st_size
        if p.is_symlink():
            return 0
        total = 0
        for entry in p.rglob("*"):
            try:
                if entry.is_file() and not entry.is_symlink():
                    total += entry.stat().st_size
            except (OSError, PermissionError):
                continue
        return total
    except (OSError, PermissionError):
        return 0


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------
def run_cmd(cmd: List[str], check: bool = False, sudo: bool = False,
            timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a command, optionally with sudo."""
    if sudo and os.geteuid() != 0:
        # Desktop apps use pkexec so the password prompt appears as a GUI
        # polkit dialog instead of failing without a terminal.
        tool = os.environ.get("UNINSTALLER_PRIV_TOOL", "sudo")
        cmd = [tool] + cmd
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=check,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(cmd, 127, "", f"Command not found: {cmd[0]}")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, -1, "", f"Command timed out after {timeout}s")


def command_exists(name: str) -> bool:
    """Check whether a command is on PATH."""
    return shutil.which(name) is not None


# ---------------------------------------------------------------------------
# Interactive helpers
# ---------------------------------------------------------------------------
def confirm(prompt: str, default: bool = False) -> bool:
    """Ask a yes/no question."""
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


def get_home() -> Path:
    """Return the user's home directory."""
    return Path.home()


# ---------------------------------------------------------------------------
# Desktop-entry parsing
# ---------------------------------------------------------------------------
def parse_desktop_name(desktop_file: Path) -> Optional[str]:
    """Extract the Name= field from a .desktop file."""
    try:
        for line in desktop_file.read_text(errors="ignore").splitlines():
            if line.startswith("Name="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None
