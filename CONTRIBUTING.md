# Contributing to Linux Uninstaller

Thanks for your interest in contributing! This project is pure Python standard
library (plus vanilla HTML/CSS/JS for the web UI) — keeping it dependency-free
is a core goal.

## Getting Started

```bash
git clone https://github.com/subhanbhatti50134-jpg/app-sweeper.git
cd app-sweeper
python3 -m uninstaller --help      # CLI
python3 -m uninstaller tk          # Tkinter GUI
python3 -m uninstaller gui         # web app window
```

Run the self-tests before submitting a change:

```bash
python3 test_self.py
```

## How to Contribute

1. **Fork** the repository and create a feature branch from `main`:
   ```bash
   git checkout -b feature/my-change
   ```
2. **Make your changes** — follow the existing code style (4-space indent,
   stdlib only, no external dependencies).
3. **Test** on at least one package manager if you touched a backend
   (`dnf`, `apt`, `pacman`, `zypper`, `snap`, `flatpak`).
4. **Commit** with a clear message describing what and why.
5. **Open a Pull Request** against `main` with a short description of the
   change and how you tested it.

## What Belongs Here

- New package-manager backends or fixes for existing ones
- Safety improvements (protected paths, confirmations, dry-run)
- UI/UX polish across the GUI, TUI, web UI, and CLI
- Documentation and translation improvements
- Bug fixes with a clear reproduction

## What to Avoid

- New runtime dependencies (keep it stdlib)
- Changes that weaken safety guarantees (silent deletion, skipped confirmations)
- Unrelated refactors in the same PR as a bug fix

## Code Style

- Python: follow the style of the surrounding code; `black` and `flake8` are
  available as dev extras (`pip install -e ".[dev]"`)
- Web UI: plain HTML/CSS/JS, no frameworks or build step
- Comments only where intent isn't obvious

## Reporting Bugs

Open a GitHub issue with:

- What you ran and what you expected
- What actually happened (paste output/tracebacks)
- Distro, Python version, and package manager

## Security Issues

Please see [SECURITY.md](SECURITY.md) — report vulnerabilities privately by
email, not in public issues.

## Code of Conduct

By participating you agree to uphold our [Code of Conduct](CODE_OF_CONDUCT.md).
