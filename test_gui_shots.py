#!/usr/bin/env python3
"""Drive the GUI through its pages and screenshot each one (non-blocking)."""

import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from uninstaller.gui import UninstallerApp  # noqa: E402

SHOT_DIR = Path("/tmp/gui_shots")
SHOT_DIR.mkdir(exist_ok=True)


def shot(name: str) -> None:
    """Capture in a background thread so the Tk loop keeps running."""

    def run():
        subprocess.run(["spectacle", "-b", "-m", "-o", str(SHOT_DIR / f"{name}.png")],
                       capture_output=True, timeout=25)
        print(f"  captured {name}", flush=True)

    threading.Thread(target=run, daemon=True).start()


def main() -> int:
    app = UninstallerApp(dry_run=True)

    def t_apps():
        shot("1_apps")
        app._show_page("scan")
        app._run_orphan_scan()

    def t_scan():
        # scan has had ~40s; select rows
        kids = app.orphan_tree.get_children()
        print(f"  orphan rows: {len(kids)}", flush=True)
        if kids:
            app.orphan_tree.selection_set(kids[:3])
            app.orphan_tree.event_generate("<<TreeviewSelect>>")
        shot("2_scan")

    def t_cleaner():
        app._show_page("cleaner")
        shot("3_cleaner")

    def t_about():
        app._show_page("about")
        shot("4_about")
        app._show_page("apps")
        app.after(1500, app.quit)

    app.after(5000, t_apps)
    app.after(48000, t_scan)
    app.after(56000, t_cleaner)
    app.after(63000, t_about)
    app.mainloop()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
