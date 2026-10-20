"""Cleaner: remove leftover files/dirs safely."""

import shutil
from pathlib import Path
from typing import List, Tuple

from uninstaller.backends.base import LeftoverItem
from uninstaller.utils.helpers import colorize, confirm, get_path_size, human_size


class Cleaner:
    """Remove leftover files and directories."""

    #: Never delete these paths no matter what
    PROTECTED_PATHS = {
        "/", "/home", "/root", "/etc", "/usr", "/var", "/bin", "/sbin",
        "/lib", "/lib64", "/boot", "/dev", "/proc", "/sys", "/run",
        "/mnt", "/media", "/opt", "/srv", "/tmp",
    }

    def __init__(self, dry_run: bool = False, force: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.force = force
        self.verbose = verbose

    # ------------------------------------------------------------------
    def remove_items(self, items: List[LeftoverItem],
                     ask: bool = True) -> Tuple[int, int, List[str]]:
        """
        Remove a list of leftover items.

        Returns (files_removed, bytes_freed, errors).
        """
        removed = 0
        freed = 0
        errors: List[str] = []

        for item in items:
            path = Path(item.path)

            # Safety: never touch protected paths
            if str(path) in self.PROTECTED_PATHS:
                errors.append(f"SKIPPED (protected): {path}")
                continue

            # Safety: refuse to delete home itself or very shallow paths
            if path == Path.home() or (path.parent == Path("/") and path.name != "tmp"):
                errors.append(f"SKIPPED (dangerous): {path}")
                continue

            # In dry-run mode just report; only prompt when actually deleting
            if ask and not self.force and not self.dry_run:
                prompt = (f"  Delete {colorize(str(path), 'cyan')} "
                          f"({colorize(human_size(item.size), 'yellow')}, {item.kind})?")
                if not confirm(prompt, default=False):
                    continue

            if self.dry_run:
                print(f"  [DRY-RUN] Would remove: {path} ({human_size(item.size)})")
                removed += 1
                freed += item.size
                continue

            try:
                size = item.size or get_path_size(path)
                if path.is_symlink() or path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    shutil.rmtree(path, ignore_errors=False)
                else:
                    # Special files etc.
                    path.unlink(missing_ok=True)
                removed += 1
                freed += size
                if self.verbose:
                    print(f"  Removed: {path} ({human_size(size)})")
            except PermissionError as e:
                errors.append(f"Permission denied: {path} ({e})")
            except OSError as e:
                errors.append(f"Failed to remove {path}: {e}")

        return removed, freed, errors

    # ------------------------------------------------------------------
    def empty_trash(self, ask: bool = True) -> Tuple[int, int, List[str]]:
        """Empty the user's trash."""
        from uninstaller.core.scanner import LeftoverScanner
        scanner = LeftoverScanner()
        items = scanner.scan_trash()
        if not items:
            return 0, 0, []
        if ask and not self.force and not self.dry_run:
            total = sum(i.size for i in items)
            if not confirm(f"Empty trash? ({len(items)} items, {human_size(total)})",
                           default=False):
                return 0, 0, []
        return self.remove_items(items, ask=False)

    # ------------------------------------------------------------------
    def clean_cache(self, ask: bool = True) -> Tuple[int, int, List[str]]:
        """Clean the user's ~/.cache directory."""
        cache_dir = Path.home() / ".cache"
        if not cache_dir.is_dir():
            return 0, 0, []
        items = []
        try:
            for entry in cache_dir.iterdir():
                size = get_path_size(entry)
                items.append(LeftoverItem(
                    path=str(entry), size=size, kind="cache", app_hint="cache",
                ))
        except PermissionError as e:
            return 0, 0, [str(e)]

        items.sort(key=lambda i: i.size, reverse=True)
        if ask and not self.force and not self.dry_run:
            total = sum(i.size for i in items)
            if not confirm(f"Clean ~/.cache? ({len(items)} entries, {human_size(total)})",
                           default=False):
                return 0, 0, []
        return self.remove_items(items, ask=False)

    # ------------------------------------------------------------------
    def clean_temp(self, ask: bool = True) -> Tuple[int, int, List[str]]:
        """Clean /tmp and /var/tmp (needs root for system tmp)."""
        from uninstaller.core.scanner import LeftoverScanner
        scanner = LeftoverScanner()
        items = scanner.scan_temp()
        if not items:
            return 0, 0, []
        # Filter out our own process files and very recent files
        import time
        now = time.time()
        safe_items = []
        for item in items:
            p = Path(item.path)
            try:
                if now - p.stat().st_mtime < 3600:  # skip files modified in last hour
                    continue
            except OSError:
                continue
            safe_items.append(item)

        if ask and not self.force and not self.dry_run:
            total = sum(i.size for i in safe_items)
            if not confirm(f"Clean temp files? ({len(safe_items)} items, {human_size(total)})",
                           default=False):
                return 0, 0, []
        return self.remove_items(safe_items, ask=False)
