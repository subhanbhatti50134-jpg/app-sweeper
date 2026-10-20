"""APT / dpkg backend (Debian, Ubuntu, Mint, Pop!_OS, etc.)."""

import re
from typing import List

from uninstaller.backends import register
from uninstaller.backends.base import Backend, InstalledPackage, UninstallResult
from uninstaller.utils.helpers import run_cmd


@register
class AptBackend(Backend):
    name = "apt"
    display_name = "APT (Debian/Ubuntu)"

    def is_available(self) -> bool:
        return run_cmd(["which", "apt-get"], check=False).returncode == 0

    def _is_dpkg_package(self, name: str) -> bool:
        r = run_cmd(["dpkg", "-s", name], check=False)
        return r.returncode == 0 and "Status: install ok installed" in r.stdout

    def list_packages(self, include_orphans: bool = False) -> List[InstalledPackage]:
        r = run_cmd(["dpkg-query", "-W", "-f=${Package}\\t${Version}\\t${Installed-Size}\\t${Description}\\n"],
                    check=False)
        if r.returncode != 0:
            return []
        pkgs = []
        for line in r.stdout.splitlines():
            parts = line.split("\t", 3)
            if len(parts) < 2:
                continue
            name, version = parts[0], parts[1]
            # Skip essential/base packages unless orphans requested
            if not include_orphans and (name.startswith("lib") or
                                        name.startswith("base") or
                                        name.startswith("linux-") or
                                        name.startswith("glib") or
                                        name.startswith("python3-") or
                                        name.startswith("fonts-") or
                                        "-dev" in name or
                                        "-dbg" in name):
                continue
            size_kib = int(parts[2]) * 1024 if len(parts) > 2 and parts[2].isdigit() else 0
            desc = parts[3] if len(parts) > 3 else ""
            pkgs.append(InstalledPackage(
                name=name, version=version, size=size_kib,
                manager=self.name, description=desc,
            ))
        return pkgs

    def uninstall(self, package_name: str) -> UninstallResult:
        if not self._is_dpkg_package(package_name):
            return UninstallResult(False, package_name, self.name,
                                   f"Package '{package_name}' is not installed.")
        r = run_cmd(["apt-get", "purge", "-y", package_name], check=False, sudo=True)
        if r.returncode == 0:
            return UninstallResult(True, package_name, self.name,
                                   f"Successfully purged '{package_name}'.")
        return UninstallResult(False, package_name, self.name,
                               f"apt-get purge failed:\n{r.stderr or r.stdout}")

    def get_orphans(self) -> List[str]:
        r = run_cmd(["apt-get", "--just-print", "autoremove"], check=False)
        if r.returncode != 0:
            return []
        # Parse "Remv pkgname [version]" lines
        return sorted(set(re.findall(r"^\s*Remv\s+(\S+)", r.stdout, re.MULTILINE)))

    def refresh(self) -> bool:
        return run_cmd(["apt-get", "update"], check=False, sudo=True).returncode == 0
