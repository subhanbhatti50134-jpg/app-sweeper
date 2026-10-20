"""Snap backend (Ubuntu, Fedora with snapd, etc.)."""

from typing import List

from uninstaller.backends import register
from uninstaller.backends.base import Backend, InstalledPackage, UninstallResult
from uninstaller.utils.helpers import run_cmd


@register
class SnapBackend(Backend):
    name = "snap"
    display_name = "Snap (Canonical)"

    def is_available(self) -> bool:
        return run_cmd(["which", "snap"], check=False).returncode == 0

    def list_packages(self, include_orphans: bool = False) -> List[InstalledPackage]:
        r = run_cmd(["snap", "list"], check=False)
        if r.returncode != 0:
            return []
        pkgs = []
        lines = r.stdout.splitlines()
        for line in lines[1:]:  # skip header
            parts = line.split()
            if len(parts) < 3:
                continue
            name, version = parts[0], parts[1]
            if name == "core" or name.startswith("core"):
                if not include_orphans:
                    continue
            pkgs.append(InstalledPackage(
                name=name, version=version, manager=self.name,
                extras={"publisher": parts[4] if len(parts) > 4 else ""},
            ))
        return pkgs

    def uninstall(self, package_name: str) -> UninstallResult:
        r = run_cmd(["snap", "list", package_name], check=False)
        if r.returncode != 0 or package_name not in r.stdout:
            return UninstallResult(False, package_name, self.name,
                                   f"Snap '{package_name}' is not installed.")
        r = run_cmd(["snap", "remove", package_name], check=False, sudo=True)
        if r.returncode == 0:
            return UninstallResult(True, package_name, self.name,
                                   f"Successfully removed snap '{package_name}'.")
        return UninstallResult(False, package_name, self.name,
                               f"snap remove failed:\n{r.stderr or r.stdout}")

    def get_orphans(self) -> List[str]:
        # Snap doesn't have orphans in the traditional sense
        return []

    def refresh(self) -> bool:
        return run_cmd(["snap", "refresh", "--list"], check=False).returncode == 0
