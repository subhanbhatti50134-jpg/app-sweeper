"""Zypper backend (openSUSE Leap/Tumbleweed)."""

import re
from typing import List

from uninstaller.backends import register
from uninstaller.backends.base import Backend, InstalledPackage, UninstallResult
from uninstaller.utils.helpers import run_cmd


@register
class ZypperBackend(Backend):
    name = "zypper"
    display_name = "Zypper (openSUSE)"

    def is_available(self) -> bool:
        return run_cmd(["which", "zypper"], check=False).returncode == 0

    def list_packages(self, include_orphans: bool = False) -> List[InstalledPackage]:
        r = run_cmd(["rpm", "-qa", "--qf", "%{NAME}\\t%{VERSION}-%{RELEASE}\\t%{SIZE}\\t%{SUMMARY}\\n"],
                    check=False)
        if r.returncode != 0:
            return []
        pkgs = []
        for line in r.stdout.splitlines():
            parts = line.split("\t", 3)
            if len(parts) < 2:
                continue
            name, version = parts[0], parts[1]
            if not include_orphans and self._skip_pkg(name):
                continue
            size = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            desc = parts[3] if len(parts) > 3 else ""
            pkgs.append(InstalledPackage(
                name=name, version=version, size=size,
                manager=self.name, description=desc,
            ))
        return pkgs

    @staticmethod
    def _skip_pkg(name: str) -> bool:
        skip_prefixes = (
            "kernel", "glibc", "bash", "coreutils", "systemd", "rpm",
            "zypper", "openSUSE-release", "filesystem", "aaa_base",
            "python3", "python3-", "glib2", "dbus", "audit", "firewalld",
            "NetworkManager", "pipewire", "Mesa", "liberation-fonts",
            "dejavu-fonts",
        )
        return name.startswith(skip_prefixes) or "-devel" in name or "-debuginfo" in name

    def uninstall(self, package_name: str) -> UninstallResult:
        r = run_cmd(["rpm", "-q", package_name], check=False)
        if r.returncode != 0:
            return UninstallResult(False, package_name, self.name,
                                   f"Package '{package_name}' is not installed.")
        r = run_cmd(["zypper", "--non-interactive", "remove", package_name], check=False, sudo=True)
        if r.returncode == 0:
            return UninstallResult(True, package_name, self.name,
                                   f"Successfully removed '{package_name}'.")
        return UninstallResult(False, package_name, self.name,
                               f"zypper remove failed:\n{r.stderr or r.stdout}")

    def get_orphans(self) -> List[str]:
        r = run_cmd(["zypper", "packages", "--orphaned"], check=False)
        if r.returncode != 0:
            return []
        names = []
        for line in r.stdout.splitlines():
            m = re.match(r"^\|?\s*\d+\s*\|\s*\S+\s*\|\s*(\S+)\s*\|", line)
            if m:
                names.append(m.group(1))
        return sorted(set(names))

    def refresh(self) -> bool:
        return run_cmd(["zypper", "refresh"], check=False, sudo=True).returncode == 0
