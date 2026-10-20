#!/usr/bin/env python3
"""Self-test for the Linux Uninstaller. Uses a fake $HOME — touches nothing real."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label} {detail}")


def main() -> int:
    fake_home = Path(tempfile.mkdtemp(prefix="uninstallertest_"))
    print(f"Fake HOME: {fake_home}\n")

    # ---- Setup fake leftovers ----------------------------------------
    app_name = "testapp"
    targets = [
        fake_home / ".config" / "TestApp",
        fake_home / ".cache" / "testapp",
        fake_home / ".local/share" / "testapp",
    ]
    for t in targets:
        t.mkdir(parents=True, exist_ok=True)
        (t / "data.bin").write_bytes(b"x" * 5000)

    from uninstaller.core.scanner import LeftoverScanner
    from uninstaller.core.cleaner import Cleaner

    # ---- Test 1: scanner finds leftovers -----------------------------
    print("Scanner:")
    scanner = LeftoverScanner(home=fake_home)
    items = scanner.scan_for_app(app_name)
    paths = {i.path for i in items}
    found_all = all(str(t) in paths for t in targets)
    check("finds all 3 fake leftover dirs", found_all, f"got {paths}")
    check("reports nonzero sizes", all(i.size >= 5000 for i in items if i.app_hint == app_name))

    # ---- Test 2: cleaner removes them (force) ------------------------
    print("\nCleaner:")
    cleaner = Cleaner(dry_run=False, force=True, verbose=False)
    removed, freed, errors = cleaner.remove_items(items, ask=False)
    check("removed >= 3 items", removed >= 3, f"removed={removed}")
    check("freed bytes > 0", freed > 0, f"freed={freed}")
    check("no errors", not errors, str(errors))
    check("dirs actually gone", not any(t.exists() for t in targets),
          f"still exist: {[t for t in targets if t.exists()]}")

    # ---- Test 3: protected paths are refused -------------------------
    print("\nSafety:")
    from uninstaller.backends.base import LeftoverItem
    evil = LeftoverItem(path="/home", size=1, kind="data")
    cleaner2 = Cleaner(dry_run=False, force=True)
    r, f, errs = cleaner2.remove_items([evil], ask=False)
    check("protected path /home refused", r == 0 and errs, f"r={r} errs={errs}")
    check("/home still exists", Path("/home").exists())

    # ---- Test 4: dry-run removes nothing -----------------------------
    (fake_home / ".config" / "DryApp").mkdir(parents=True, exist_ok=True)
    (fake_home / ".config" / "DryApp" / "f").write_bytes(b"y" * 2000)
    items2 = scanner.scan_for_app("DryApp")
    cleaner3 = Cleaner(dry_run=True, force=True)
    r, f, e = cleaner3.remove_items(items2, ask=False)
    check("dry-run reports but keeps files",
          r >= 1 and (fake_home / ".config" / "DryApp").exists())

    # ---- Test 5: human_size ------------------------------------------
    print("\nHelpers:")
    from uninstaller.utils.helpers import human_size
    check("human_size(0)", human_size(0) == "0 B", human_size(0))
    check("human_size(1024)", human_size(1024) == "1.0 KiB", human_size(1024))
    check("human_size(5*1024**3)", human_size(5 * 1024 ** 3) == "5.0 GiB",
          human_size(5 * 1024 ** 3))

    # ---- Test 6: backend registry ------------------------------------
    print("\nBackends:")
    from uninstaller.backends import get_all_backends, get_available_backends
    names = {b.name for b in get_all_backends()}
    check("6 backends registered", len(names) == 6, str(names))
    avail = {b.name for b in get_available_backends()}
    check("at least one available", len(avail) >= 1, str(avail))

    # ---- Test 7: CLI parses (dry-run, no side effects) ---------------
    print("\nCLI:")
    from uninstaller.cli import main as cli_main
    rc = cli_main(["managers"])
    check("`managers` exits 0", rc == 0, f"rc={rc}")
    try:
        rc = cli_main(["--version"])
    except SystemExit:
        rc = 0  # argparse's version action prints then exits 0
    check("`--version` exits 0", rc == 0, f"rc={rc}")

    # ---- Test 8: GUI module (needs a display) --------------------------
    print("\nGUI:")
    has_display = bool(os.environ.get("DISPLAY") or
                       os.environ.get("WAYLAND_DISPLAY"))
    import importlib.util
    if not has_display:
        print("  [SKIP] no display available")
    elif importlib.util.find_spec("tkinter") is None:
        print("  [SKIP] tkinter not installed")
    else:
        try:
            from uninstaller.gui import UninstallerApp, run_gui
            check("run_gui callable", callable(run_gui))
            app_obj = UninstallerApp(dry_run=True)
            errors = []
            app_obj.report_callback_exception = lambda *a: errors.append(a)
            for page_name in ("apps", "scan", "cleaner", "about"):
                app_obj._show_page(page_name)
                built = page_name in app_obj.pages
                check(f"page '{page_name}' builds", built)
            check("no callback errors", not errors, str(errors))
            app_obj.after(300, app_obj.destroy)
            app_obj.update()
            check("window constructs + destroys", True)
        except ImportError:
            print("  [SKIP] tkinter not installed")
        except Exception as exc:  # noqa: BLE001
            check("GUI smoke test", False, f"{type(exc).__name__}: {exc}")

    # ---- Test 9: web server + API ------------------------------------
    print("\nWeb server:")
    try:
        import json as _json
        import urllib.request
        from uninstaller.server import WebServer

        ws = WebServer()
        base = ws.start()
        try:
            with urllib.request.urlopen(base + "/", timeout=10) as r:
                html = r.read().decode()
                check("GET / serves index.html",
                      r.status == 200 and "Uninstaller" in html)
            with urllib.request.urlopen(base + "/api/status", timeout=10) as r:
                st = _json.loads(r.read())
                check("GET /api/status has version",
                      "version" in st, str(st))
            with urllib.request.urlopen(base + "/api/packages?q=ssh", timeout=60) as r:
                pk = _json.loads(r.read())
                check("GET /api/packages returns list",
                      isinstance(pk.get("packages"), list), str(pk)[:80])
            req = urllib.request.Request(
                base + "/api/nope", method="GET")
            try:
                urllib.request.urlopen(req, timeout=5)
                check("unknown route 404", False, "no exception")
            except urllib.error.HTTPError as err:
                check("unknown route 404", err.code == 404, f"code={err.code}")
        finally:
            ws.stop()
        check("server stops cleanly", True)
    except Exception as exc:  # noqa: BLE001
        check("web server smoke test", False, f"{type(exc).__name__}: {exc}")

    # ---- Cleanup ------------------------------------------------------
    shutil.rmtree(fake_home, ignore_errors=True)

    print(f"\n{'='*40}\n  {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
