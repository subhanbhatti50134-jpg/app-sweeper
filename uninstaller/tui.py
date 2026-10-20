"""Interactive terminal UI (pure stdlib, no external deps)."""

import os
from typing import List, Optional

from uninstaller.backends import get_available_backends
from uninstaller.backends.base import InstalledPackage
from uninstaller.core.cleaner import Cleaner
from uninstaller.core.scanner import LeftoverScanner
from uninstaller.core.uninstaller import Uninstaller
from uninstaller.utils.helpers import colorize, confirm, human_size


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _header(title: str) -> None:
    width = 60
    print(colorize("=" * width, "cyan"))
    print(colorize(f"  {title}".ljust(width), "bold"))
    print(colorize("=" * width, "cyan"))


def _pause() -> None:
    try:
        input(colorize("\n  Press Enter to continue...", "dim"))
    except (EOFError, KeyboardInterrupt):
        print()


def _choose(prompt: str, options: List[str]) -> Optional[int]:
    """Display numbered options, return chosen index (0-based) or None."""
    for i, opt in enumerate(options, 1):
        print(f"  {colorize(str(i), 'bright_cyan')}. {opt}")
    print(f"  {colorize('0', 'bright_red')}. Back / Cancel")
    try:
        raw = input(colorize(f"\n  {prompt}: ", "bold")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not raw:
        return None
    try:
        choice = int(raw)
    except ValueError:
        return None
    if choice == 0:
        return None
    if 1 <= choice <= len(options):
        return choice - 1
    return None


# ======================================================================
# Screens
# ======================================================================
def _screen_managers(dry_run: bool) -> None:
    _clear()
    _header("Available Package Managers")
    backends = get_available_backends()
    if not backends:
        print(colorize("  No supported package manager found.", "red"))
        _pause()
        return
    for b in backends:
        try:
            count = len(b.list_packages(include_orphans=False))
        except Exception:
            count = -1
        count_s = f"{count} packages" if count >= 0 else "?"
        print(f"  {colorize('●', 'green')} {b.name:10s} {b.display_name:30s} ({count_s})")
    _pause()


def _screen_list(manager: Optional[str], dry_run: bool) -> None:
    _clear()
    _header("Installed Applications")
    backends = get_available_backends()
    if manager:
        backends = [b for b in backends if b.name == manager]
    if not backends:
        print(colorize("  No package manager available.", "red"))
        _pause()
        return

    all_pkgs: List[InstalledPackage] = []
    for b in backends:
        try:
            all_pkgs.extend(b.list_packages(include_orphans=False))
        except Exception as e:
            print(colorize(f"  Error with {b.name}: {e}", "red"))

    if not all_pkgs:
        print("  No packages found.")
        _pause()
        return

    # Search filter
    print(f"\n  {len(all_pkgs)} packages loaded.")
    try:
        q = input(colorize("  Filter (Enter to show all): ", "bold")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if q:
        all_pkgs = [p for p in all_pkgs if q in p.name.lower() or
                    (q in p.description.lower() if p.description else False)]

    if not all_pkgs:
        print("  No matches.")
        _pause()
        return

    # Paginated display
    page = 0
    per_page = 20
    while True:
        _clear()
        _header(f"Installed Applications ({len(all_pkgs)} total)")
        start = page * per_page
        chunk = all_pkgs[start:start + per_page]
        for i, p in enumerate(chunk, 1):
            idx = start + i
            desc = f"  {colorize(p.description[:50], 'dim')}" if p.description else ""
            size = f" [{colorize(p.display_size(), 'yellow')}]" if p.size else ""
            print(f"  {colorize(str(idx), 'bright_cyan'):>5s}. {p.name:35s} "
                  f"{p.version:15s}{size}{desc}")

        pages = (len(all_pkgs) + per_page - 1) // per_page
        print(colorize(f"\n  Page {page + 1}/{pages}", "dim"))
        try:
            cmd = input(colorize(
                "  [n]ext  [p]rev  [u]ninstall#  [s]earch  [Enter]done: ", "bold"
            )).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if cmd == "n" and page + 1 < pages:
            page += 1
        elif cmd == "p" and page > 0:
            page -= 1
        elif cmd == "s":
            try:
                q = input(colorize("  New filter: ", "bold")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if q:
                all_pkgs = [p for p in all_pkgs if q in p.name.lower()]
                page = 0
        elif cmd == "u":
            try:
                num = int(input(colorize("  Package #: ", "bold")).strip())
            except (ValueError, EOFError, KeyboardInterrupt):
                continue
            if 1 <= num <= len(all_pkgs):
                _screen_uninstall(all_pkgs[num - 1], dry_run)
                return
        else:
            return


def _screen_uninstall(pkg: InstalledPackage, dry_run: bool) -> None:
    _clear()
    _header(f"Uninstall: {pkg.name}")
    print(f"  Version:    {pkg.version}")
    print(f"  Manager:    {pkg.manager}")
    if pkg.size:
        print(f"  Install size: {pkg.display_size()}")
    if pkg.description:
        print(f"  Description: {pkg.description}")

    # Scan leftovers
    print(colorize("\n  Scanning for leftover files...", "cyan"))
    scanner = LeftoverScanner()
    items = scanner.scan_for_app(pkg.name)
    if items:
        total = sum(i.size for i in items)
        print(colorize(f"\n  Found {len(items)} leftover item(s) "
                       f"({human_size(total)}):", "yellow"))
        for item in items:
            icon = {"cache": "🗂", "config": "⚙", "temp": "🗑",
                    "log": "📄", "data": "💾"}.get(item.kind, "•")
            print(f"    {icon} [{item.kind:6s}] {item.path} "
                  f"({colorize(item.display_size(), 'cyan')})")
    else:
        print(colorize("\n  No leftover files found.", "green"))

    # Confirm
    if dry_run:
        print(colorize("\n  [DRY-RUN] Nothing will be removed.", "yellow"))
        _pause()
        return

    if not confirm(f"\n  Uninstall '{pkg.name}' and remove leftovers?", default=False):
        print(colorize("  Aborted.", "yellow"))
        _pause()
        return

    un = Uninstaller(backend_name=pkg.manager, force=True, verbose=True)
    result = un.uninstall(pkg.name, leftovers=items)
    print()
    if result.success:
        print(colorize(f"  ✓ {result.message}", "green"))
        if result.leftovers_removed:
            print(colorize(f"  ✓ Freed {human_size(result.leftovers_bytes)}", "green"))
    else:
        print(colorize(f"  ✗ {result.message}", "red"))
    _pause()


def _screen_scan(dry_run: bool) -> None:
    _clear()
    _header("Orphaned App Data Scan")
    print(colorize("  Scanning (this may take a moment)...", "cyan"))
    scanner = LeftoverScanner()
    results = scanner.scan_all_leftovers()
    if not results:
        print(colorize("\n  ✓ No orphaned app data found.", "green"))
        _pause()
        return

    total = sum(sum(i.size for i in items) for items in results.values())
    names = sorted(results.keys())
    print(colorize(f"\n  Found {len(results)} orphaned app(s), "
                   f"total {human_size(total)}:", "yellow"))
    for i, name in enumerate(names, 1):
        sub = sum(i2.size for i2 in results[name])
        print(f"    {colorize(str(i), 'bright_cyan')}. {name:35s} "
              f"{colorize(human_size(sub), 'yellow')}")

    if dry_run:
        print(colorize("\n  [DRY-RUN] Nothing will be removed.", "yellow"))
        _pause()
        return

    choice = _choose("Enter # to delete (comma-separated), or 0 to cancel",
                     names)
    if choice is None:
        return
    target = names[choice]
    if confirm(f"  Delete ALL data for '{target}'?", default=False):
        cleaner = Cleaner(force=True, verbose=True)
        removed, freed, errors = cleaner.remove_items(results[target], ask=False)
        print(colorize(f"  ✓ Removed {removed} item(s), freed {human_size(freed)}",
                       "green"))
        for e in errors:
            print(colorize(f"  {e}", "red"))
    _pause()


def _screen_clean(dry_run: bool) -> None:
    _clear()
    _header("Cleaner")
    options = [
        "Cache (~/.cache)",
        "Temp files (/tmp)",
        "Trash (empty)",
        "All of the above",
        "System package caches (dnf/apt/pacman/zypper)",
    ]
    idx = _choose("What to clean", options)
    if idx is None:
        return
    cleaner = Cleaner(dry_run=dry_run, force=True, verbose=True)
    what = ["cache", "temp", "trash", "all", "syscache"][idx]

    if what in ("cache", "all"):
        removed, freed, errors = cleaner.clean_cache(ask=not dry_run)
        print(f"Cache: {removed} removed, {human_size(freed)} freed")
    if what in ("temp", "all"):
        removed, freed, errors = cleaner.clean_temp(ask=not dry_run)
        print(f"Temp: {removed} removed, {human_size(freed)} freed")
    if what in ("trash", "all"):
        removed, freed, errors = cleaner.empty_trash(ask=not dry_run)
        print(f"Trash: {removed} removed, {human_size(freed)} freed")
    if what in ("syscache", "all"):
        from uninstaller.cli import _clean_system_caches
        _clean_system_caches(dry_run)
    _pause()


def _screen_orphans(dry_run: bool) -> None:
    _clear()
    _header("Orphaned / Unused Packages")
    backends = get_available_backends()
    found = False
    for b in backends:
        try:
            orphans = b.get_orphans()
        except Exception:
            continue
        if not orphans:
            continue
        found = True
        print(colorize(f"\n  {b.display_name}:", "cyan"))
        for name in orphans:
            print(f"    • {name}")
        if not dry_run and confirm(f"\n  Remove {len(orphans)} orphan(s) from {b.name}?",
                                   default=False):
            for name in orphans:
                r = b.uninstall(name)
                mark = colorize("✓", "green") if r.success else colorize("✗", "red")
                print(f"    {mark} {name}")
    if not found:
        print(colorize("  ✓ No orphaned packages found.", "green"))
    _pause()


# ======================================================================
# Main loop
# ======================================================================
def run_tui(manager: Optional[str] = None, dry_run: bool = False) -> int:
    """Run the interactive terminal UI. Returns exit code."""
    while True:
        _clear()
        _header("Linux Uninstaller")
        if dry_run:
            print(colorize("  MODE: DRY-RUN (nothing will be changed)", "yellow"))
        print()
        options = [
            "Browse & uninstall applications",
            "Scan for orphaned app data",
            "Clean cache / temp / trash",
            "Remove orphaned packages",
            "Show available package managers",
            "Exit",
        ]
        choice = _choose("Select an option", options)
        if choice is None or choice == 5:
            print(colorize("\n  Goodbye!", "cyan"))
            return 0
        elif choice == 0:
            _screen_list(manager, dry_run)
        elif choice == 1:
            _screen_scan(dry_run)
        elif choice == 2:
            _screen_clean(dry_run)
        elif choice == 3:
            _screen_orphans(dry_run)
        elif choice == 4:
            _screen_managers(dry_run)
