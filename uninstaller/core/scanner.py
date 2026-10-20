"""Scanner: find leftover files/dirs that belong to an app after uninstall."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set

from uninstaller.backends.base import LeftoverItem
from uninstaller.utils.helpers import get_home, get_path_size

# Directories that commonly hold per-user app data
USER_DATA_DIRS = [
    ".config",
    ".local/share",
    ".local/state",
    ".cache",
    ".local/share/Trash",
    ".thumbnails",
    ".mozilla",
    ".thunderbird",
    ".steam",
    ".local/share/flatpak",
    ".var/app",  # flatpak per-app sandbox data
    ".config/KDE",
    ".local/share/knotifications5",
    ".local/share/kservices5",
    ".local/share/applnk",
    ".emulator",
    ".android",
    ".java",
    ".dotnet",
    ".npm",
    ".cargo",
    ".rustup",
    ".gem",
    ".bundle",
    ".composer",
    ".pyenv",
    ".nvm",
    ".local/share/virtualenvs",
    ".local/share/Trash/files",
    ".local/share/Trash/info",
    ".local/share/recently-used.xbel",
]

# System-wide data dirs (need root)
SYSTEM_DATA_DIRS = [
    "/var/cache",
    "/var/lib",
    "/var/tmp",
    "/tmp",
    "/opt",
    "/usr/local/share",
    "/usr/local/lib",
    "/etc",
]

# Well-known app-name → directory mappings (case-insensitive substring match)
KNOWN_APP_PATHS: Dict[str, List[str]] = {
    "firefox": [".mozilla/firefox", ".cache/mozilla/firefox"],
    "chrome": [".config/google-chrome", ".cache/google-chrome",
               ".config/chromium", ".cache/chromium"],
    "chromium": [".config/chromium", ".cache/chromium"],
    "code": [".config/Code", ".vscode", ".cache/Code"],
    "vscode": [".config/Code", ".vscode", ".cache/Code"],
    "spotify": [".config/spotify", ".cache/spotify"],
    "slack": [".config/Slack", ".cache/Slack"],
    "discord": [".config/discord", ".cache/discord"],
    "telegram": [".config/TelegramDesktop", ".local/share/TelegramDesktop",
                 ".cache/telegram"],
    "steam": [".steam", ".local/share/Steam", ".steam/steam"],
    "gimp": [".config/GIMP", ".cache/GIMP", ".config/gimp"],
    "inkscape": [".config/inkscape", ".cache/inkscape"],
    "blender": [".config/blender", ".cache/blender", ".local/share/blender"],
    "obsidian": [".config/obsidian", ".config/Obsidian", ".local/share/obsidian"],
    "zoom": [".config/zoom", ".cache/zoom", ".zoom"],
    "teams": [".config/Microsoft/Microsoft Teams", ".cache/Microsoft/Microsoft Teams"],
    "skype": [".skype", ".config/Skype"],
    "node": [".npm", ".nvm", ".node-gyp", ".yarn", ".pnpm-store"],
    "docker": [".docker", "/var/lib/docker"],
    "kubernetes": [".kube", ".minikube"],
    "pip": [".cache/pip", ".local/share/pip"],
    "python": [".cache/pip", ".local/share/virtualenvs", ".pyenv"],
    "java": [".java", ".gradle", ".m2"],
    "android": [".android", ".gradle"],
    "vlc": [".config/vlc", ".cache/vlc"],
    "mpv": [".config/mpv", ".cache/mpv"],
    "audacity": [".config/audacity", ".cache/audacity"],
    "krita": [".config/krita", ".cache/krita"],
    "libreoffice": [".config/libreoffice", ".cache/libreoffice"],
    "thunderbird": [".thunderbird", ".cache/thunderbird"],
    "qbittorrent": [".config/qBittorrent", ".local/share/qBittorrent"],
    "transmission": [".config/transmission", ".cache/transmission"],
    "filezilla": [".config/filezilla", ".cache/filezilla"],
    "virtualbox": [".config/VirtualBox", ".virtualbox"],
    "vmware": [".vmware", ".config/vmware"],
}


class LeftoverScanner:
    """Scan the filesystem for files left behind by an app."""

    def __init__(self, home: Optional[Path] = None, dry_run: bool = False):
        self.home = home or get_home()
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def scan_for_app(self, app_name: str, extra_paths: Optional[List[str]] = None) -> List[LeftoverItem]:
        """
        Scan for leftover files matching *app_name*.

        Returns a list of LeftoverItem sorted by size (largest first).
        """
        items: List[LeftoverItem] = []
        seen: Set[str] = set()
        name_l = app_name.lower()

        # 1. Well-known paths
        for key, paths in KNOWN_APP_PATHS.items():
            if key in name_l or name_l in key:
                for rel in paths:
                    item = self._check_path(rel, app_name)
                    if item and item.path not in seen:
                        seen.add(item.path)
                        items.append(item)

        # 2. User data dirs — look for entries whose name contains app_name
        for rel_dir in USER_DATA_DIRS:
            base = self.home / rel_dir
            if not base.is_dir():
                continue
            try:
                for entry in base.iterdir():
                    if not entry.name or entry.name.startswith("."):
                        continue
                    if name_l in entry.name.lower():
                        resolved = str(entry)
                        if resolved in seen:
                            continue
                        seen.add(resolved)
                        size = get_path_size(entry)
                        kind = self._classify(rel_dir, entry.name)
                        items.append(LeftoverItem(
                            path=resolved, size=size, kind=kind, app_hint=app_name,
                        ))
            except PermissionError:
                continue

        # 3. System dirs (need root; only include if readable)
        for sys_dir in SYSTEM_DATA_DIRS:
            base = Path(sys_dir)
            if not base.is_dir() or not os.access(base, os.R_OK):
                continue
            try:
                for entry in base.iterdir():
                    if name_l in entry.name.lower():
                        resolved = str(entry)
                        if resolved in seen:
                            continue
                        seen.add(resolved)
                        size = get_path_size(entry)
                        items.append(LeftoverItem(
                            path=resolved, size=size, kind="data", app_hint=app_name,
                        ))
            except PermissionError:
                continue

        # 4. Explicit extra paths
        if extra_paths:
            for rel in extra_paths:
                item = self._check_path(rel, app_name)
                if item and item.path not in seen:
                    seen.add(item.path)
                    items.append(item)

        # 5. Desktop files & menu entries
        items.extend(self._scan_desktop_files(app_name, seen))

        # Sort by size descending
        items.sort(key=lambda i: i.size, reverse=True)
        return items

    def scan_all_leftovers(self) -> Dict[str, List[LeftoverItem]]:
        """
        Heuristic scan: find top-level entries in user data dirs that no
        longer correspond to an installed package.

        Returns {app_guess: [LeftoverItem, ...]}
        """
        from uninstaller.backends import get_available_backends

        installed_names: Set[str] = set()
        for backend in get_available_backends():
            try:
                for pkg in backend.list_packages(include_orphans=True):
                    installed_names.add(pkg.name.lower())
            except Exception:
                continue

        result: Dict[str, List[LeftoverItem]] = {}
        for rel_dir in USER_DATA_DIRS:
            if rel_dir.startswith(".local/share/Trash"):
                continue  # handle trash separately
            base = self.home / rel_dir
            if not base.is_dir():
                continue
            try:
                for entry in base.iterdir():
                    if entry.name.startswith("."):
                        continue
                    entry_l = entry.name.lower()
                    # If no installed package shares this name, it's a candidate
                    matched = any(entry_l in n or n in entry_l for n in installed_names)
                    if matched:
                        continue
                    size = get_path_size(entry)
                    if size < 1024:  # skip < 1 KiB
                        continue
                    kind = self._classify(rel_dir, entry.name)
                    result.setdefault(entry.name, []).append(LeftoverItem(
                        path=str(entry), size=size, kind=kind, app_hint=entry.name,
                    ))
            except PermissionError:
                continue

        return result

    def scan_trash(self) -> List[LeftoverItem]:
        """Scan the user's trash."""
        items = []
        trash_dirs = [
            self.home / ".local/share/Trash/files",
            self.home / ".Trash",
        ]
        for trash in trash_dirs:
            if not trash.is_dir():
                continue
            try:
                for entry in trash.iterdir():
                    size = get_path_size(entry)
                    items.append(LeftoverItem(
                        path=str(entry), size=size, kind="temp", app_hint="trash",
                    ))
            except PermissionError:
                continue
        return sorted(items, key=lambda i: i.size, reverse=True)

    def scan_temp(self) -> List[LeftoverItem]:
        """Scan /tmp and user temp."""
        items = []
        tmp_dirs = [Path("/tmp"), self.home / ".cache"]
        for tmp in tmp_dirs:
            if not tmp.is_dir():
                continue
            try:
                for entry in tmp.iterdir():
                    if entry.is_dir():
                        size = get_path_size(entry)
                        items.append(LeftoverItem(
                            path=str(entry), size=size, kind="temp", app_hint="temp",
                        ))
            except PermissionError:
                continue
        return sorted(items, key=lambda i: i.size, reverse=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _check_path(self, rel: str, app_name: str) -> Optional[LeftoverItem]:
        """Check whether a relative path exists under $HOME or is absolute."""
        path = Path(rel) if rel.startswith("/") else self.home / rel
        if not path.exists() and not path.is_symlink():
            return None
        size = get_path_size(path)
        kind = self._classify(str(path.parent), path.name)
        return LeftoverItem(path=str(path), size=size, kind=kind, app_hint=app_name)

    @staticmethod
    def _classify(parent_dir: str, name: str) -> str:
        parent_l = parent_dir.lower()
        name_l = name.lower()
        if "cache" in parent_l or name_l in (".cache", "cache", "caches"):
            return "cache"
        if "config" in parent_l or name_l in (".config", "config", "preferences"):
            return "config"
        if any(t in parent_l for t in ("tmp", "temp", "trash")):
            return "temp"
        if "log" in name_l or name_l.endswith(".log"):
            return "log"
        if "share" in parent_l or "data" in parent_l:
            return "data"
        return "other"

    def _scan_desktop_files(self, app_name: str, seen: Set[str]) -> List[LeftoverItem]:
        """Look for leftover .desktop files and icons."""
        items = []
        name_l = app_name.lower()
        patterns = [
            self.home / ".local/share/applications",
            self.home / ".local/share/icons",
            self.home / ".local/share/mime",
            Path("/usr/share/applications"),
            Path("/usr/share/icons"),
            Path("/usr/share/mime"),
            Path("/var/lib/flatpak/exports/share/applications"),
            self.home / ".local/share/flatpak/exports/share/applications",
        ]
        for d in patterns:
            if not d.is_dir():
                continue
            try:
                for entry in d.rglob("*"):
                    if name_l in entry.name.lower():
                        resolved = str(entry)
                        if resolved in seen:
                            continue
                        seen.add(resolved)
                        size = get_path_size(entry)
                        items.append(LeftoverItem(
                            path=resolved, size=size, kind="data", app_hint=app_name,
                        ))
            except PermissionError:
                continue
        return items
