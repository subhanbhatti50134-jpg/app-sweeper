"""Launch the premium web UI as a native app window (zero pip deps)."""

import os
import shutil
import subprocess
import time
import webbrowser
from typing import List, Optional, Tuple

from uninstaller.utils.helpers import colorize

# Browsers that support true --app= windows (no tabs/address bar).
# {url} and {size} are substituted at launch time.
APP_BROWSERS = [
    ("chromium-browser", ["--app={url}", "--window-size={size}"]),
    ("chromium",         ["--app={url}", "--window-size={size}"]),
    ("google-chrome",    ["--app={url}", "--window-size={size}"]),
    ("google-chrome-stable", ["--app={url}", "--window-size={size}"]),
    ("brave-browser",    ["--app={url}", "--window-size={size}"]),
    ("vivaldi",          ["--app={url}", "--window-size={size}"]),
    ("microsoft-edge",   ["--app={url}", "--window-size={size}"]),
]
# Fallback: normal browser tab
TAB_BROWSERS = ["firefox", "xdg-open"]


def _pick_app_browser() -> Optional[Tuple[str, List[str]]]:
    for name, args in APP_BROWSERS:
        path = shutil.which(name)
        if path:
            return path, args
    return None


def _pick_tab_browser() -> Optional[str]:
    for name in TAB_BROWSERS:
        path = shutil.which(name)
        if path:
            return path
    return None


def _use_pkexec() -> None:
    """Ask for privileges via the desktop polkit dialog (GUI password prompt)."""
    if shutil.which("pkexec") and os.environ.get("UNINSTALLER_PRIV_TOOL") is None:
        os.environ["UNINSTALLER_PRIV_TOOL"] = "pkexec"


def _window_size() -> str:
    """Pick a window size that fits the current screen."""
    try:
        out = subprocess.run(["xdpyinfo"], capture_output=True, text=True,
                             timeout=5).stdout
        for line in out.splitlines():
            if "dimensions:" in line:
                # e.g. "dimensions:    1366x768 pixels"
                dims = line.split()[1].split("x")
                w, h = int(dims[0]), int(dims[1])
                # leave room for panels/taskbars
                w = min(1360, int(w * 0.94))
                h = min(900, int(h * 0.92))
                return f"{max(w, 900)}x{max(h, 600)}"
    except Exception:  # noqa: BLE001
        pass
    return "1280x800"


def run_webapp(dry_run: bool = False, manager: Optional[str] = None,
               headless_wait: Optional[float] = None) -> int:
    """
    Start the local server and open the app window.

    *headless_wait* — used by tests: don't wait for a browser, just keep the
    server alive for N seconds (the caller opened the window itself).
    """
    from uninstaller.server import WebServer

    _use_pkexec()

    server = WebServer()
    url = server.start()
    print(colorize(f"● UI server running at {url}", "cyan"))

    size = _window_size()
    try:
        browser = _pick_app_browser()
        if browser:
            path, argtmpl = browser
            args = [a.format(url=url, size=size) for a in argtmpl]
            # Chromium refuses to run as root without this flag
            if os.geteuid() == 0:
                args.append("--no-sandbox")
            print(colorize(f"● Opening app window ({os.path.basename(path)}, "
                           f"{size})…", "cyan"))
            proc = subprocess.Popen([path] + args,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            if headless_wait:
                time.sleep(headless_wait)
                return 0
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
            return 0

        tab = _pick_tab_browser()
        if tab:
            print(colorize("● No app-mode browser found; opening in a browser tab…",
                           "yellow"))
            subprocess.Popen([tab, url],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if headless_wait:
                time.sleep(headless_wait)
                return 0
            print(colorize("● Close the server with Ctrl+C", "dim"))
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            return 0

        # Last resort: open default handler
        print(colorize("● Opening default browser…", "yellow"))
        webbrowser.open(url)
        if headless_wait:
            time.sleep(headless_wait)
            return 0
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        server.stop()
        print(colorize("● Server stopped.", "dim"))
