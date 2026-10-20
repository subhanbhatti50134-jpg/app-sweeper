# Linux Uninstaller

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Code of Conduct](https://img.shields.io/badge/Code%20of%20Conduct-Contributor%20Covenant-ff69b4.svg)](CODE_OF_CONDUCT.md)

A comprehensive Linux app uninstaller that removes applications **and** their leftover cache, config, temp, and data files — in one step. Ships as a **premium desktop app** (a local web UI opened in its own app window) plus a full CLI and terminal UI.

Most Linux package managers remove the binaries but leave behind `~/.cache`, `~/.config`, `~/.local/share`, and other orphaned files. This tool scans for those leftovers, shows you exactly what they are, and cleans them up safely.

## Features

- **Premium desktop app** — a locally-served web UI (pure HTML/CSS/JS, no frameworks) launched as a native Chromium/Firefox app window: clean flat-dark design, live search over all package managers.
- **Uninstall + Clean in one step** — removes the package via the package manager, then finds and deletes leftover files.
- **Leftover scanner** — finds orphaned app data across `~/.config`, `~/.local/share`, `~/.cache`, `/var`, `/opt`, and more.
- **Multi-package-manager support** — automatically detects and uses whichever is available:
  - `dnf` / `rpm` (Fedora, RHEL, CentOS)
  - `apt` / `dpkg` (Debian, Ubuntu, Mint, Pop!_OS)
  - `pacman` (Arch, Manjaro, EndeavourOS)
  - `zypper` (openSUSE)
  - `snap`
  - `flatpak`
- **Three interfaces** — premium web app window, interactive terminal UI, and full CLI (plus a classic Tkinter GUI as `uninstaller tk` fallback).
- **Safety first** — protected-path list, dry-run mode, confirmation prompts, no blind `rm -rf`.
- **Cleaner** — empty trash, clear `~/.cache`, clear `/tmp`, purge package-manager caches.
- **Orphan detection** — list unused/orphaned packages your package manager can auto-remove.
- **Zero dependencies** — pure Python standard library for everything server-side; the web UI is vanilla HTML/CSS/JS. Only a browser is needed for the app window.

## Requirements

- Python **3.8+**
- A web browser for the app window (Chromium, Firefox, …) — optional; the Tk GUI and TUI work without one
- Linux with at least one supported package manager

## Installation

```bash
cd Uninstaller
chmod +x install.sh uninstall.sh
./install.sh
```

This installs:
- `uninstaller` — CLI (auto-launches the GUI when run with no arguments on a desktop)
- `uninstaller-gui` — desktop app launcher
- App icon + menu entry (Applications → Linux Uninstaller)

**Or run without installing:**

```bash
python3 -m uninstaller gui    # premium app window (web UI)
python3 -m uninstaller        # same, or terminal UI over SSH
python3 -m uninstaller tk     # classic Tkinter GUI
```

## The desktop app

Open it from the applications menu, or run `uninstaller-gui` / `uninstaller gui`. A tiny local server (stdlib `http.server`) serves the UI on `127.0.0.1`; your browser opens it as a frameless app window. The server dies when the window closes.

| Page | What it does |
|---|---|
| **Apps** | Live search over installed apps from every package manager (server-side cached, infinite-scroll table). Select one to preview leftover files, then **Uninstall & Clean**. |
| **Orphan Scan** | Scans for data left behind by apps that are no longer installed. Select rows → **Clean Selected**. |
| **Cleaner** | Cards for User Cache, Trash, Temp Files, and Package Caches — each shows its size and a Clean button. |
| **About** | Version, features, detected package managers. |

Destructive actions pop a confirmation dialog with a full path list before anything is removed. Elevated removals prompt for your password via `pkexec`.

## CLI usage

### Terminal UI (default when no GUI display)

```bash
uninstaller interactive
```

Opens a menu-driven terminal UI:

```
============================================================
  Linux Uninstaller
============================================================

  1. Browse & uninstall applications
  2. Scan for orphaned app data
  3. Clean cache / temp / trash
  4. Remove orphaned packages
  5. Show available package managers
  0. Back / Cancel
```

### CLI commands

| Command | Description |
|---|---|
| `uninstaller list` | List installed packages |
| `uninstaller list --manager dnf` | List only DNF packages |
| `uninstaller list firefox` | Filter packages by name |
| `uninstaller uninstall <pkg>` | Uninstall a package **and** clean leftovers |
| `uninstaller uninstall <pkg> --yes` | Skip confirmation prompts |
| `uninstaller uninstall <pkg> --dry-run` | Preview only — change nothing |
| `uninstaller uninstall <pkg> --no-clean` | Uninstall but keep leftover files |
| `uninstaller scan` | Find **all** orphaned app data on the system |
| `uninstaller scan <app>` | Find leftovers for a specific app |
| `uninstaller clean cache` | Clear `~/.cache` |
| `uninstaller clean temp` | Clear stale `/tmp` files |
| `uninstaller clean trash` | Empty the trash |
| `uninstaller clean all --yes` | Clean everything incl. package caches |
| `uninstaller orphans` | List orphaned/unused packages |
| `uninstaller info <pkg>` | Show package info + leftover files |
| `uninstaller managers` | Show detected package managers |
| `uninstaller gui` | Launch the premium app window (web UI) |
| `uninstaller tk` | Launch the classic Tkinter GUI |
| `uninstaller interactive` | Force-launch the terminal UI |

### Global flags

```
-y, --yes        Assume yes to all prompts
--dry-run        Show what would be done without doing it
-v, --verbose    Extra output
-m, --manager    Force a specific package manager (apt/dnf/pacman/...)
```

## Examples

```bash
# Uninstall Firefox and clean all its leftovers
uninstaller uninstall firefox

# Preview what would be removed (safe)
uninstaller uninstall code --dry-run

# Find everything orphaned, then clean it
uninstaller scan
uninstaller clean all --yes

# Clear system package manager caches too
uninstaller clean all --yes
```

## How it works

1. **Scan** — looks in well-known app paths (`~/.config`, `~/.local/share`, `~/.cache`, `/var/cache`, `/opt`, desktop entries, icons) for directories/files matching the app name.
2. **Uninstall** — invokes the correct package manager (`dnf remove`, `apt-get purge`, `pacman -Rns`, `flatpak uninstall`, …).
3. **Clean** — deletes the leftover items found in step 1, with a protected-path list to prevent accidents.

Everything is shown before it happens; `--dry-run` lets you preview without changes.

## Safety

- A `PROTECTED_PATHS` list blocks deletion of `/`, `/home`, `/etc`, `/usr`, etc.
- Refuses to delete your home directory or paths directly under `/`.
- Confirmation prompts on every destructive action (bypass with `--yes`).
- `--dry-run` previews the full flow with zero changes.
- Never runs package-manager commands without `sudo` prompt when needed.

## Project structure

```
Uninstaller/
├── uninstaller/
│   ├── __init__.py
│   ├── __main__.py          # python -m uninstaller
│   ├── cli.py               # argparse CLI + subcommands
│   ├── gui.py               # classic Tkinter GUI (fallback)
│   ├── tui.py               # terminal UI
│   ├── server.py            # stdlib HTTP server + JSON API
│   ├── webapp.py            # launches the UI as a browser app window
│   ├── webui/
│   │   ├── index.html       # premium UI structure
│   │   ├── style.css        # flat dark design system
│   │   └── app.js           # SPA logic, API calls
│   ├── backends/
│   │   ├── __init__.py      # backend registry
│   │   ├── base.py          # Backend ABC, data classes
│   │   ├── apt.py
│   │   ├── dnf.py
│   │   ├── pacman.py
│   │   ├── zypper.py
│   │   ├── snap.py
│   │   └── flatpak.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── scanner.py       # leftover-file scanner
│   │   ├── cleaner.py       # safe file removal
│   │   └── uninstaller.py   # orchestration
│   └── utils/
│       ├── __init__.py
│       └── helpers.py       # colors, sizes, subprocess
├── assets/
│   ├── icon.png             # app icon (512px)
│   └── icon-64.png
├── install.sh               # installs GUI + CLI launchers, icon, menu entry
├── uninstall.sh
├── test_self.py             # CLI/core self-tests
├── test_gui_shots.py        # GUI screenshot smoke test
├── pyproject.toml
├── LICENSE
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
└── README.md
```

## Uninstalling the tool itself

```bash
./uninstall.sh
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for
setup, style guidelines, and PR expectations, and note that this project follows
a [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability? Please report it privately — see [SECURITY.md](SECURITY.md).
Do not open a public issue for security reports.

## License

MIT — see [LICENSE](LICENSE).
