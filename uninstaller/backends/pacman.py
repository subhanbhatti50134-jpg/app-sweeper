"""Pacman backend (Arch Linux, Manjaro, EndeavourOS)."""

from typing import List

from uninstaller.backends import register
from uninstaller.backends.base import Backend, InstalledPackage, UninstallResult
from uninstaller.utils.helpers import run_cmd


@register
class PacmanBackend(Backend):
    name = "pacman"
    display_name = "Pacman (Arch/Manjaro)"

    def is_available(self) -> bool:
        return run_cmd(["which", "pacman"], check=False).returncode == 0

    def list_packages(self, include_orphans: bool = False) -> List[InstalledPackage]:
        r = run_cmd(["pacman", "-Q"], check=False)
        if r.returncode != 0:
            return []
        pkgs = []
        for line in r.stdout.splitlines():
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            name, version = parts[0], parts[1]
            desc = parts[2] if len(parts) > 2 else ""
            if not include_orphans and self._skip_pkg(name):
                continue
            pkgs.append(InstalledPackage(
                name=name, version=version, manager=self.name, description=desc,
            ))
        return pkgs

    @staticmethod
    def _skip_pkg(name: str) -> bool:
        skip_prefixes = (
            "linux", "glibc", "bash", "coreutils", "systemd", "pacman",
            "filesystem", "iana-etc", "bash-completion", "python", "python-",
            "glib2", "dbus", "audit", "firewalld", "networkmanager",
            "pipewire", "mesa", "liberation-fonts", "dejavu-fonts",
            "archlinux-keyring", "filesystem",
        )
        return name.startswith(skip_prefixes) or "-devel" in name

    def uninstall(self, package_name: str) -> UninstallResult:
        r = run_cmd(["pacman", "-Q", package_name], check=False)
        if r.returncode != 0:
            return UninstallResult(False, package_name, self.name,
                                   f"Package '{package_name}' is not installed.")
        r = run_cmd(["pacman", "-Rns", "--noconfirm", package_name], check=False, sudo=True)
        if r.returncode == 0:
            return UninstallResult(True, package_name, self.name,
                                   f"Successfully removed '{package_name}'.")
        return UninstallResult(False, package_name, self.name,
                               f"pacman -Rns failed:\n{r.stderr or r.stdout}")

    def get_orphans(self) -> List[str]:
        r = run_cmd(["pacman", "-Qtdq"], check=False)
        if r.returncode != 0:
            return []
        return sorted(set(line.strip() for line in r.stdout.splitlines() if line.strip()))

    def refresh(self) -> bool:
        return run_cmd(["sudo", "pacman", "-Sy"], check=False).returncode == 0
