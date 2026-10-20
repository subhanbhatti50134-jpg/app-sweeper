"""Uninstaller orchestrator: uninstall a package AND clean its leftovers."""

from typing import List, Optional

from uninstaller.backends import get_available_backends, get_backend
from uninstaller.backends.base import Backend, LeftoverItem, UninstallResult
from uninstaller.core.cleaner import Cleaner
from uninstaller.core.scanner import LeftoverScanner
from uninstaller.utils.helpers import colorize, human_size


class Uninstaller:
    """High-level uninstall flow: scan → uninstall → clean leftovers."""

    def __init__(self, backend_name: Optional[str] = None,
                 dry_run: bool = False, force: bool = False,
                 verbose: bool = False, clean_leftovers: bool = True):
        self.dry_run = dry_run
        self.force = force
        self.verbose = verbose
        self.clean_leftovers = clean_leftovers
        self.scanner = LeftoverScanner(dry_run=dry_run)
        self.cleaner = Cleaner(dry_run=dry_run, force=force, verbose=verbose)

        if backend_name:
            self.backend: Optional[Backend] = get_backend(backend_name)
        else:
            backends = get_available_backends()
            self.backend = backends[0] if backends else None

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self.backend is not None

    # ------------------------------------------------------------------
    def scan(self, package_name: str) -> List[LeftoverItem]:
        """Scan for leftover files belonging to *package_name*."""
        return self.scanner.scan_for_app(package_name)

    # ------------------------------------------------------------------
    def uninstall(self, package_name: str,
                  leftovers: Optional[List[LeftoverItem]] = None) -> UninstallResult:
        """
        Full uninstall flow:

        1. Scan for leftovers (before uninstall — files may only exist now)
        2. Uninstall via the package manager
        3. Remove leftover files

        Returns a UninstallResult.
        """
        if self.backend is None:
            return UninstallResult(False, package_name, "",
                                   "No supported package manager found on this system.")

        # Step 1: scan (if not pre-supplied)
        if leftovers is None:
            if self.verbose:
                print(colorize(f"Scanning leftovers for '{package_name}'...", "cyan"))
            leftovers = self.scanner.scan_for_app(package_name)

        if leftovers and self.verbose:
            total = sum(i.size for i in leftovers)
            print(f"Found {len(leftovers)} leftover items "
                  f"({human_size(total)}):")
            for item in leftovers:
                print(f"  [{item.kind}] {item.path} ({item.display_size()})")

        # Step 2: uninstall
        if self.dry_run:
            print(colorize(f"[DRY-RUN] Would uninstall '{package_name}' "
                           f"via {self.backend.name}", "yellow"))
            result = UninstallResult(True, package_name, self.backend.name,
                                     "[dry-run] uninstall simulated")
        else:
            if self.verbose:
                print(colorize(f"Uninstalling '{package_name}' via "
                               f"{self.backend.display_name}...", "cyan"))
            result = self.backend.uninstall(package_name)

        # Step 3: clean leftovers
        if result.success and self.clean_leftovers and leftovers:
            if self.verbose:
                print(colorize("Cleaning leftover files...", "cyan"))
            removed, freed, errors = self.cleaner.remove_items(
                leftovers, ask=not self.force,
            )
            result.leftovers_removed = [i.path for i in leftovers[:removed]]
            result.leftovers_bytes = freed
            for err in errors:
                if self.verbose:
                    print(colorize(f"  {err}", "red"))

        return result

    # ------------------------------------------------------------------
    def uninstall_with_preview(self, package_name: str) -> UninstallResult:
        """Scan first, show the user what will be removed, then uninstall."""
        leftovers = self.scanner.scan_for_app(package_name)

        print(colorize(f"\n=== Uninstalling: {package_name} ===", "bold"))
        if self.backend:
            print(f"Package manager: {self.backend.display_name}")

        if leftovers:
            total = sum(i.size for i in leftovers)
            print(f"\nLeftover files found "
                  f"({colorize(str(len(leftovers)), 'yellow')} items, "
                  f"{colorize(human_size(total), 'yellow')}):")
            for item in leftovers:
                icon = {"cache": "🗂", "config": "⚙", "temp": "🗑",
                        "log": "📄", "data": "💾"}.get(item.kind, "•")
                print(f"  {icon} [{item.kind:6s}] {item.path} "
                      f"({colorize(item.display_size(), 'cyan')})")
        else:
            print(colorize("\nNo leftover files found.", "green"))

        return self.uninstall(package_name, leftovers=leftovers)
