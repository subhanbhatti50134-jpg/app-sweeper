"""Command-line interface for the Linux Uninstaller."""

import argparse
import os
import sys
from typing import List, Optional

from uninstaller import __version__
from uninstaller.backends import get_available_backends
from uninstaller.backends.base import InstalledPackage
from uninstaller.core.cleaner import Cleaner
from uninstaller.core.scanner import LeftoverScanner
from uninstaller.core.uninstaller import Uninstaller
from uninstaller.utils.helpers import colorize, confirm, human_size, run_cmd


# ======================================================================
# Pretty printing helpers
# ======================================================================
def _print_table(rows: List[List[str]], headers: List[str]) -> None:
    """Print a simple aligned table."""
    all_rows = [headers] + rows
    widths = [max(len(str(r[i])) for r in all_rows if i < len(r))
              for i in range(len(headers))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)

    header_line = fmt.format(*headers)
    print(colorize(header_line, "bold"))
    print(colorize("  ".join("-" * w for w in widths), "dim"))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))


def _print_pkgs(pkgs: List[InstalledPackage], show_size: bool = True) -> None:
    rows = []
    for p in pkgs:
        row = [p.name, p.version]
        if show_size:
            row.append(p.display_size())
        if p.description:
            row.append(p.description[:60])
        rows.append(row)
    headers = ["NAME", "VERSION"] + (["SIZE"] if show_size else []) + \
              (["DESCRIPTION"] if any(p.description for p in pkgs) else [])
    _print_table(rows, headers)
    print(f"\n{len(pkgs)} package(s) listed.")


# ======================================================================
# Subcommands
# ======================================================================
def cmd_list(args: argparse.Namespace) -> int:
    """List installed packages."""
    backends = get_available_backends()
    if not backends:
        print(colorize("No supported package manager found.", "red"))
        return 1

    if args.manager:
        backends = [b for b in backends if b.name == args.manager]
        if not backends:
            print(colorize(f"Manager '{args.manager}' not available.", "red"))
            return 1

    total = 0
    for backend in backends:
        if args.verbose or len(backends) > 1:
            print(colorize(f"\n--- {backend.display_name} ---", "cyan"))
        try:
            pkgs = backend.list_packages(include_orphans=args.all)
        except Exception as e:
            print(colorize(f"  Error listing packages: {e}", "red"))
            continue
        if args.name_filter:
            fl = args.name_filter.lower()
            pkgs = [p for p in pkgs if fl in p.name.lower()]
        if args.limit:
            pkgs = pkgs[:args.limit]
        _print_pkgs(pkgs, show_size=not args.no_size)
        total += len(pkgs)
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstall a package and clean its leftovers."""
    un = Uninstaller(
        backend_name=args.manager,
        dry_run=args.dry_run,
        force=args.yes,
        verbose=args.verbose,
        clean_leftovers=not args.no_clean,
    )
    if not un.available:
        print(colorize("No supported package manager found.", "red"))
        return 1

    # Step 1: scan and preview (nothing removed yet)
    leftovers = un.scan(args.package)
    _print_uninstall_preview(args.package, un, leftovers)

    # Step 2: confirm before touching anything
    if not args.yes and not args.dry_run:
        if not confirm(f"\nProceed with uninstalling '{args.package}'?", default=False):
            print(colorize("Aborted.", "yellow"))
            return 0

    # Step 3: uninstall + clean (pass pre-scanned leftovers)
    result = un.uninstall(args.package, leftovers=leftovers)

    print()
    if result.success:
        print(colorize(f"✓ {result.message}", "green"))
        if result.leftovers_removed:
            print(colorize(f"  Cleaned {len(result.leftovers_removed)} leftover item(s), "
                           f"freed {human_size(result.leftovers_bytes)}", "green"))
    else:
        print(colorize(f"✗ {result.message}", "red"))
        return 1
    return 0


def _print_uninstall_preview(package: str, un: "Uninstaller", leftovers: list) -> None:
    """Print what an uninstall would involve."""
    print(colorize(f"\n=== Uninstalling: {package} ===", "bold"))
    if un.backend:
        print(f"Package manager: {un.backend.display_name}")
    if un.dry_run:
        print(colorize("[DRY-RUN] No changes will be made.", "yellow"))
    if leftovers:
        total = sum(i.size for i in leftovers)
        print(f"\nLeftover files found "
              f"({colorize(str(len(leftovers)), 'yellow')} items, "
              f"{colorize(human_size(total), 'yellow')}):")
        for item in leftovers:
            icon = {"cache": "[C]", "config": "[>]", "temp": "[T]",
                    "log": "[L]", "data": "[D]"}.get(item.kind, "[ ]")
            print(f"  {icon} [{item.kind:6s}] {item.path} "
                  f"({colorize(item.display_size(), 'cyan')})")
    else:
        print(colorize("\nNo leftover files found.", "green"))


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan for leftover files of a specific app (without uninstalling)."""
    scanner = LeftoverScanner()
    if args.package:
        items = scanner.scan_for_app(args.package)
        if not items:
            print(f"No leftovers found for '{args.package}'.")
            return 0
        total = sum(i.size for i in items)
        print(colorize(f"Leftovers for '{args.package}' "
                       f"({len(items)} items, {human_size(total)}):", "bold"))
        for item in items:
            print(f"  [{item.kind:6s}] {item.path} ({item.display_size()})")
        return 0
    else:
        # Scan all orphaned data
        print(colorize("Scanning for orphaned app data...", "cyan"))
        results = scanner.scan_all_leftovers()
        if not results:
            print(colorize("No orphaned app data found. ✓", "green"))
            return 0
        total = sum(sum(i.size for i in items) for items in results.values())
        print(colorize(f"\nFound {len(results)} orphaned app(s), "
                       f"total {human_size(total)}:", "bold"))
        for name, items in sorted(results.items(),
                                  key=lambda kv: sum(i.size for i in kv[1]),
                                  reverse=True):
            sub = sum(i.size for i in items)
            print(f"\n  {colorize(name, 'yellow')} ({human_size(sub)}):")
            for item in items:
                print(f"    [{item.kind:6s}] {item.path} ({item.display_size()})")
        return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Clean cache, temp files, or trash."""
    cleaner = Cleaner(dry_run=args.dry_run, force=args.yes, verbose=args.verbose)
    what = args.what

    if what in ("cache", "all"):
        removed, freed, errors = cleaner.clean_cache(ask=not args.yes)
        print(f"Cache: removed {removed} item(s), freed {human_size(freed)}")
        for e in errors:
            print(colorize(f"  {e}", "red"))

    if what in ("temp", "all"):
        removed, freed, errors = cleaner.clean_temp(ask=not args.yes)
        print(f"Temp: removed {removed} item(s), freed {human_size(freed)}")
        for e in errors:
            print(colorize(f"  {e}", "red"))

    if what in ("trash", "all"):
        removed, freed, errors = cleaner.empty_trash(ask=not args.yes)
        print(f"Trash: removed {removed} item(s), freed {human_size(freed)}")
        for e in errors:
            print(colorize(f"  {e}", "red"))

    if what == "all":
        # Extra: system package manager caches
        _clean_system_caches(args.dry_run)
    return 0


def _clean_system_caches(dry_run: bool) -> None:
    """Best-effort system package-manager cache cleanup."""
    from uninstaller.utils.helpers import command_exists
    cmds = []
    if command_exists("dnf"):
        cmds.append(("DNF cache", ["dnf", "clean", "all"], True))
    if command_exists("apt-get"):
        cmds.append(("APT cache", ["apt-get", "clean"], True))
    if command_exists("pacman"):
        cmds.append(("Pacman cache", ["pacman", "-Sc", "--noconfirm"], True))
    if command_exists("zypper"):
        cmds.append(("Zypper cache", ["zypper", "clean", "--all"], True))
    if command_exists("flatpak"):
        cmds.append(("Flatpak unused", ["flatpak", "uninstall", "-y", "--unused"], False))

    for label, cmd, needs_sudo in cmds:
        if dry_run:
            print(colorize(f"[DRY-RUN] Would run: {' '.join(cmd)}", "yellow"))
            continue
        print(colorize(f"Cleaning {label}...", "cyan"))
        r = run_cmd(cmd, check=False, sudo=needs_sudo)
        if r.returncode == 0:
            print(colorize(f"  ✓ {label} cleaned", "green"))
        else:
            print(colorize(f"  ✗ {label}: {(r.stderr or r.stdout).strip()[:120]}", "red"))


def cmd_orphans(args: argparse.Namespace) -> int:
    """List orphaned / unused packages."""
    backends = get_available_backends()
    found = False
    for backend in backends:
        try:
            orphans = backend.get_orphans()
        except Exception:
            continue
        if not orphans:
            continue
        found = True
        print(colorize(f"\n--- Orphans in {backend.display_name} ---", "cyan"))
        for name in orphans:
            print(f"  {name}")
        print(f"{len(orphans)} orphaned package(s).")
    if not found:
        print(colorize("No orphaned packages found. ✓", "green"))
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """Show info about a package."""
    backends = get_available_backends()
    for backend in backends:
        pkg = backend.find_package(args.package)
        if pkg:
            print(colorize(f"Package:   {pkg.name}", "bold"))
            print(f"Version:   {pkg.version}")
            print(f"Manager:   {backend.display_name}")
            if pkg.size:
                print(f"Size:      {pkg.display_size()}")
            if pkg.description:
                print(f"Desc:      {pkg.description}")
            # Show leftovers
            scanner = LeftoverScanner()
            items = scanner.scan_for_app(pkg.name)
            if items:
                total = sum(i.size for i in items)
                print(f"\nLeftovers ({len(items)} items, {human_size(total)}):")
                for item in items:
                    print(f"  [{item.kind:6s}] {item.path} ({item.display_size()})")
            else:
                print("\nNo leftovers found.")
            return 0
    print(colorize(f"Package '{args.package}' not found in any manager.", "red"))
    return 1


def cmd_managers(args: argparse.Namespace) -> int:
    """Show available package managers."""
    all_b = get_available_backends()
    print(colorize("Available package managers:", "bold"))
    for b in all_b:
        print(f"  {colorize('●', 'green')} {b.name:10s} — {b.display_name}")
    if not all_b:
        print("  (none found)")
    return 0


def cmd_interactive(args: argparse.Namespace) -> int:
    """Launch the interactive TUI."""
    try:
        from uninstaller.tui import run_tui
        return run_tui(manager=args.manager, dry_run=args.dry_run)
    except ImportError:
        print(colorize("TUI module not available.", "red"))
        return 1


def cmd_gui(args: argparse.Namespace) -> int:
    """Launch the premium web UI (native app window)."""
    try:
        from uninstaller.webapp import run_webapp
        return run_webapp(dry_run=args.dry_run, manager=args.manager)
    except Exception as e:  # noqa: BLE001
        print(colorize(f"Could not start web app: {e}", "red"))
        print("Falling back to the Tkinter app…")
        return cmd_tk_gui(args)


def cmd_tk_gui(args: argparse.Namespace) -> int:
    """Launch the Tkinter desktop app."""
    try:
        from uninstaller.gui import run_gui
    except ImportError as e:
        print(colorize(f"GUI unavailable (tkinter missing?): {e}", "red"))
        print("Install it with:  sudo dnf install python3-tk  "
              "(or apt install python3-tk)")
        return 1
    try:
        return run_gui(dry_run=args.dry_run, manager=args.manager)
    except Exception as e:  # noqa: BLE001 — display errors etc.
        print(colorize(f"Could not start GUI: {e}", "red"))
        print("Falling back to terminal mode…")
        from uninstaller.tui import run_tui
        return run_tui(manager=args.manager, dry_run=args.dry_run)


def _has_display() -> bool:
    """True if a graphical session appears to be available."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def cmd_default(args: argparse.Namespace) -> int:
    """No subcommand: web app → Tk GUI → terminal UI."""
    if _has_display():
        try:
            from uninstaller.webapp import run_webapp
            return run_webapp(dry_run=args.dry_run, manager=args.manager)
        except ImportError:
            pass
        except Exception:  # noqa: BLE001 — fall back
            pass
        try:
            from uninstaller.gui import run_gui
            return run_gui(dry_run=args.dry_run, manager=args.manager)
        except ImportError:
            pass
        except Exception:  # noqa: BLE001
            pass
    from uninstaller.tui import run_tui
    return run_tui(manager=args.manager, dry_run=args.dry_run)


# ======================================================================
# Argument parser
# ======================================================================
def _add_global_flags(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    """
    Add global flags to a parser.

    When *suppress* is True (used for subparsers), defaults are SUPPRESSed so
    they don't overwrite values already parsed by the top-level parser.
    This lets flags work both before and after the subcommand.
    """
    d = argparse.SUPPRESS if suppress else False
    parser.add_argument("-v", "--verbose", action="store_true", default=d,
                        help="verbose output")
    parser.add_argument("--dry-run", action="store_true", default=d,
                        help="show what would be done without doing it")
    parser.add_argument("-y", "--yes", action="store_true", default=d,
                        help="assume yes to all prompts")
    parser.add_argument("--manager", "-m", metavar="NAME",
                        default=argparse.SUPPRESS if suppress else None,
                        help="package manager (apt, dnf, pacman, zypper, snap, flatpak)")


def _add_sub(sub: argparse._SubParsersAction, name: str, **kwargs) -> argparse.ArgumentParser:
    """Create a subparser that also accepts the global flags."""
    p = sub.add_parser(name, **kwargs)
    _add_global_flags(p, suppress=True)
    return p


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uninstaller",
        description="Linux app uninstaller that removes apps AND their leftover "
                    "cache, config, and temp files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  uninstaller list                          List installed packages
  uninstaller list --manager dnf            List only DNF packages
  uninstaller uninstall firefox             Uninstall Firefox + clean leftovers
  uninstaller uninstall code --yes          Uninstall without prompts
  uninstaller uninstall code --dry-run      Preview what would happen
  uninstaller scan                          Find ALL orphaned app data
  uninstaller scan gimp                     Find leftovers for a specific app
  uninstaller clean all --yes               Clean cache + temp + trash + pkg caches
  uninstaller clean cache                   Clean only ~/.cache
  uninstaller orphans                       List orphaned packages
  uninstaller info firefox                  Show package + leftover info
  uninstaller                               Launch interactive mode
""",
    )
    parser.add_argument("-V", "--version", action="version",
                        version=f"%(prog)s {__version__}")
    _add_global_flags(parser, suppress=False)

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # list
    p_list = _add_sub(sub, "list", help="list installed packages")
    p_list.add_argument("--all", action="store_true",
                        help="include libraries and base packages")
    p_list.add_argument("--no-size", action="store_true", help="hide size column")
    p_list.add_argument("--limit", type=int, default=0, help="limit output rows")
    p_list.add_argument("name_filter", nargs="?", default="",
                        help="filter packages by name substring")
    p_list.set_defaults(func=cmd_list)

    # uninstall
    p_un = _add_sub(sub, "uninstall", aliases=["rm", "remove"],
                    help="uninstall a package and clean leftovers")
    p_un.add_argument("package", help="package name to uninstall")
    p_un.add_argument("--no-clean", action="store_true",
                      help="do NOT remove leftover files")
    p_un.set_defaults(func=cmd_uninstall)

    # scan
    p_scan = _add_sub(sub, "scan", help="scan for leftover files")
    p_scan.add_argument("package", nargs="?", default="",
                        help="app name to scan (omit to scan for ALL orphans)")
    p_scan.set_defaults(func=cmd_scan)

    # clean
    p_clean = _add_sub(sub, "clean", help="clean cache/temp/trash")
    p_clean.add_argument("what", nargs="?", default="cache",
                         choices=["cache", "temp", "trash", "all"],
                         help="what to clean (default: cache)")
    p_clean.set_defaults(func=cmd_clean)

    # orphans
    p_orph = _add_sub(sub, "orphans", help="list orphaned/unused packages")
    p_orph.set_defaults(func=cmd_orphans)

    # info
    p_info = _add_sub(sub, "info", help="show package + leftover info")
    p_info.add_argument("package", help="package name")
    p_info.set_defaults(func=cmd_info)

    # managers
    p_mgr = _add_sub(sub, "managers", help="show available package managers")
    p_mgr.set_defaults(func=cmd_managers)

    # gui (premium web app in a native window)
    p_gui = _add_sub(sub, "gui", aliases=["app", "window", "web"],
                     help="launch the desktop app (premium web UI)")
    p_gui.set_defaults(func=cmd_gui)

    # classic Tkinter GUI
    p_tk = _add_sub(sub, "tk", aliases=["tkinter"],
                    help="launch the classic Tkinter desktop app")
    p_tk.set_defaults(func=cmd_tk_gui)

    # interactive (text UI)
    p_int = _add_sub(sub, "interactive", aliases=["i", "ui", "tui"],
                     help="launch the terminal interface (text UI)")
    p_int.set_defaults(func=cmd_interactive)

    return parser


# ======================================================================
# Entry point
# ======================================================================
def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Ensure global flags always exist (SUPPRESS may have removed some)
    for attr, default in (("verbose", False), ("dry_run", False),
                          ("yes", False), ("manager", None)):
        if not hasattr(args, attr):
            setattr(args, attr, default)

    # Default: no subcommand → GUI if a display exists, else text UI
    if not args.command:
        return cmd_default(args)

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n" + colorize("Interrupted.", "yellow"))
        return 130
    except EOFError:
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
