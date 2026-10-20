"""Flatpak backend (Fedora, Ubuntu, etc.)."""

from typing import List

from uninstaller.backends import register
from uninstaller.backends.base import Backend, InstalledPackage, UninstallResult
from uninstaller.utils.helpers import run_cmd


@register
class FlatpakBackend(Backend):
    name = "flatpak"
    display_name = "Flatpak (Flathub)"

    def is_available(self) -> bool:
        return run_cmd(["which", "flatpak"], check=False).returncode == 0

    def list_packages(self, include_orphans: bool = False) -> List[InstalledPackage]:
        r = run_cmd(["flatpak", "list", "--app", "--columns=application,version,branch,installation"],
                    check=False)
        if r.returncode != 0:
            return []
        pkgs = []
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            app_id = parts[0]
            version = parts[1] if len(parts) > 1 else ""
            branch = parts[2] if len(parts) > 2 else ""
            install_type = parts[3] if len(parts) > 3 else "user"
            # Skip runtimes unless requested
            if not include_orphans and app_id.startswith(("org.freedesktop.", "org.gnome.", "org.kde.")):
                continue
            pkgs.append(InstalledPackage(
                name=app_id, version=version, manager=self.name,
                extras={"branch": branch, "installation": install_type},
            ))
        return pkgs

    def uninstall(self, package_name: str) -> UninstallResult:
        # Detect user vs system installation
        r = run_cmd(["flatpak", "info", package_name], check=False)
        if r.returncode != 0:
            return UninstallResult(False, package_name, self.name,
                                   f"Flatpak '{package_name}' is not installed.")
        # Try user first, then system
        r = run_cmd(["flatpak", "uninstall", "-y", "--user", package_name], check=False)
        if r.returncode != 0:
            r = run_cmd(["flatpak", "uninstall", "-y", "--system", package_name],
                        check=False, sudo=True)
        if r.returncode == 0:
            # Also clean up orphaned runtimes
            run_cmd(["flatpak", "uninstall", "-y", "--unused"], check=False, sudo=True)
            return UninstallResult(True, package_name, self.name,
                                   f"Successfully removed flatpak '{package_name}'.")
        return UninstallResult(False, package_name, self.name,
                               f"flatpak uninstall failed:\n{r.stderr or r.stdout}")

    def get_orphans(self) -> List[str]:
        # Flatpak has no traditional "orphans"; unused runtimes are cleaned
        # automatically after each app uninstall via `flatpak --unused`.
        return []

    def refresh(self) -> bool:
        return run_cmd(["flatpak", "update", "--appstream"], check=False).returncode == 0
