"""DNF / RPM backend (Fedora, RHEL, CentOS, openSUSE with dnf)."""

import re
from typing import List

from uninstaller.backends import register
from uninstaller.backends.base import Backend, InstalledPackage, UninstallResult
from uninstaller.utils.helpers import run_cmd


@register
class DnfBackend(Backend):
    name = "dnf"
    display_name = "DNF (Fedora/RHEL)"

    def is_available(self) -> bool:
        return run_cmd(["which", "dnf"], check=False).returncode == 0

    def list_packages(self, include_orphans: bool = False) -> List[InstalledPackage]:
        # `rpm -qa` is the canonical source and always works on RPM systems
        r = run_cmd(["rpm", "-qa",
                     "--qf", "%{NAME}\\t%{VERSION}-%{RELEASE}\\t%{SIZE}\\t%{SUMMARY}\\n"],
                    check=False)
        if r.returncode != 0 or not r.stdout.strip():
            # Fall back to dnf output if rpm is unavailable
            return self._list_via_dnf(include_orphans)

        pkgs = []
        seen = set()
        for line in r.stdout.splitlines():
            parts = line.split("\t", 3)
            if len(parts) < 2:
                continue
            name, version = parts[0], parts[1]
            if name in seen:
                continue
            seen.add(name)
            if not include_orphans and self._skip_pkg(name):
                continue
            size = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            desc = parts[3] if len(parts) > 3 else ""
            pkgs.append(InstalledPackage(
                name=name, version=version, size=size,
                manager=self.name, description=desc,
            ))
        return pkgs

    def _list_via_dnf(self, include_orphans: bool) -> List[InstalledPackage]:
        """Fallback: parse `dnf list installed` output."""
        r = run_cmd(["dnf", "list", "installed"], check=False)
        if r.returncode != 0:
            return []
        pkgs, seen = [], set()
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith(("Installed", "Last", "Updating",
                                            "Repositories", "No matches")):
                continue
            m = re.match(r"^(\S+)\s+(\S+)\s+(\S+)$", line)
            if not m:
                continue
            name_arch, version, _repo = m.groups()
            name = name_arch.rsplit(".", 1)[0]
            if name in seen:
                continue
            seen.add(name)
            if not include_orphans and self._skip_pkg(name):
                continue
            pkgs.append(InstalledPackage(name=name, version=version,
                                         manager=self.name))
        return pkgs

    @staticmethod
    def _skip_pkg(name: str) -> bool:
        skip_prefixes = (
            "kernel", "glibc", "bash", "coreutils", "systemd", "rpm",
            "dnf", "fedora-release", "filesystem", "setup", "basesystem",
            "python3", "python3-", "glib2", "dbus", "audit", "selinux",
            "policycoreutils", "firewalld", "NetworkManager", "pipewire",
            "mesa-", "liberation-", "dejavu-", "google-", "alsa-",
        )
        return name.startswith(skip_prefixes) or "-devel" in name or "-debuginfo" in name

    def uninstall(self, package_name: str) -> UninstallResult:
        # Verify installed
        r = run_cmd(["rpm", "-q", package_name], check=False)
        if r.returncode != 0:
            return UninstallResult(False, package_name, self.name,
                                   f"Package '{package_name}' is not installed.")
        r = run_cmd(["dnf", "remove", "-y", package_name], check=False, sudo=True)
        if r.returncode == 0:
            return UninstallResult(True, package_name, self.name,
                                   f"Successfully removed '{package_name}'.")
        return UninstallResult(False, package_name, self.name,
                               f"dnf remove failed:\n{r.stderr or r.stdout}")

    def get_orphans(self) -> List[str]:
        # `--unneeded` = leaf packages nothing depends on (safe to remove)
        r = run_cmd(["dnf", "repoquery", "--unneeded",
                     "--qf", "%{name}\\n"], check=False)
        if r.returncode != 0 or not r.stdout.strip():
            r = run_cmd(["dnf", "repoquery", "--leaves",
                         "--qf", "%{name}\\n"], check=False)
        if r.returncode != 0:
            return []
        names = set()
        for tok in r.stdout.replace("\n", " ").split():
            tok = tok.strip()
            if tok and not tok.startswith(("error", "Updating", "Repositories")):
                names.add(tok)
        return sorted(names)

    def refresh(self) -> bool:
        return run_cmd(["dnf", "makecache"], check=False, sudo=True).returncode == 0
