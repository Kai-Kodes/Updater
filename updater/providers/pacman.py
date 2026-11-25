"""
CachyOS / Arch Linux system and AUR package update and uninstallation provider.
Uses paru -Syu (falling back to sudo pacman -Syu) and updates Flatpak if installed.
"""

import os
import re
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any
from updater.config import IS_ARCH, IS_CACHYOS, parse_ver_tuple
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error, print_warn

_SIZE_MULTIPLIERS = {
    "B": 1,
    "KIB": 1024,
    "KB": 1000,
    "MIB": 1024**2,
    "MB": 1000**2,
    "GIB": 1024**3,
    "GB": 1000**3,
    "TIB": 1024**4,
    "TB": 1000**4,
}


def _parse_pacman_size(raw: str) -> int:
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)", raw)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).upper()
    return int(val * _SIZE_MULTIPLIERS.get(unit, 1))


def _clean_dep_name(token: str) -> str:
    return re.split(r"[<>=:]", token, maxsplit=1)[0].strip()


def _parse_pacman_qi_blocks(stdout: str) -> dict[str, dict[str, Any]]:
    """Parse output of `LC_ALL=C pacman -Qi` into a dict keyed by package name."""
    pkgs: dict[str, dict[str, Any]] = {}
    cur: dict[str, Any] = {}
    last_key = ""

    for line in stdout.splitlines():
        if not line.strip():
            if cur.get("Name"):
                pkgs[cur["Name"]] = cur
            cur = {}
            last_key = ""
            continue
        if ":" in line and not line[0].isspace():
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            cur[key] = val
            last_key = key
        elif last_key and line[0].isspace():
            cur[last_key] = f"{cur[last_key]} {line.strip()}".strip()

    if cur.get("Name"):
        pkgs[cur["Name"]] = cur
    return pkgs


def _query_pacman_metadata(pkg_names: list[str] | None = None, explicit_only: bool = False) -> dict[str, dict[str, Any]]:
    """Query local pacman database metadata in a single subprocess call."""
    cmd = ["pacman", "-Qie" if explicit_only else "-Qi"]
    if pkg_names:
        cmd.extend(pkg_names)
    env = {**os.environ, "LC_ALL": "C"}
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=env)
        if res.stdout:
            return _parse_pacman_qi_blocks(res.stdout)
    except Exception:
        pass
    return {}


def _detect_unowned_resolve_version() -> str:
    """Read installed DaVinci Resolve version from /opt/resolve when not owned by pacman."""
    resolve_dir = Path("/opt/resolve")
    for doc_file in (resolve_dir / "docs" / "ReadMe.html", resolve_dir / "docs" / "Welcome.txt"):
        if doc_file.is_file():
            try:
                text = doc_file.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"DaVinci Resolve\s+([0-9]+(?:\.[0-9]+)+)", text)
                if m:
                    return m.group(1).strip()
            except Exception:
                pass
    return ""


def _check_unowned_davinci_resolve() -> dict[str, Any] | None:
    """
    If /opt/resolve exists and is not owned by pacman -Qo, check AUR RPC for updates
    so paru -S davinci-resolve can upgrade it when Blackmagic releases a new version.
    """
    resolve_dir = Path("/opt/resolve")
    if not resolve_dir.is_dir():
        return None

    env = {**os.environ, "LC_ALL": "C"}
    for cand in (str(resolve_dir), str(resolve_dir / "bin" / "resolve")):
        if Path(cand).exists():
            try:
                qres = subprocess.run(["pacman", "-Qo", cand], capture_output=True, text=True, timeout=3, env=env)
                if qres.returncode == 0 and " is owned by " in (qres.stdout or ""):
                    return None
            except Exception:
                pass

    inst_ver = _detect_unowned_resolve_version()
    if not inst_ver:
        return None

    try:
        req = urllib.request.Request(
            "https://aur.archlinux.org/rpc/v5/info?arg[]=davinci-resolve",
            headers={"User-Agent": "updater/3.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
            results = data.get("results", [])
            if not results:
                return None
            aur_info = results[0]
            aur_ver = str(aur_info.get("Version", "")).strip()
            aur_upstream = aur_ver.split("-", 1)[0]
            if aur_upstream and parse_ver_tuple(aur_upstream) > parse_ver_tuple(inst_ver):
                return {
                    "id": "pacman_davinci-resolve",
                    "source": "pacman",
                    "name": "davinci-resolve",
                    "pkg": "davinci-resolve",
                    "aur_pkg": "davinci-resolve",
                    "is_aur": True,
                    "path": str(resolve_dir),
                    "installed": inst_ver,
                    "available": aur_ver,
                    "title": f"AUR DaVinci Resolve: {aur_ver}",
                    "body": (
                        f"{aur_info.get('Description', 'DaVinci Resolve non-linear video editor.')}\n\n"
                        f"- **Repository:** `AUR (unmanaged /opt/resolve)`\n"
                        f"- **AUR Package:** `davinci-resolve`\n"
                        f"- **Homepage:** {aur_info.get('URL', '')}"
                    ),
                    "url": "https://aur.archlinux.org/packages/davinci-resolve",
                }
    except Exception:
        pass
    return None


class PacmanProvider(BaseProvider):
    name = "pacman"
    source_label = "pacman"
    priority = 30

    def __init__(self):
        self._sysupgrade_done = False
        self._sysupgrade_ok = False

    @classmethod
    def is_available(cls) -> bool:
        return IS_ARCH and shutil.which("pacman") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        pending: dict[str, tuple[str, str, bool]] = {}
        env = {**os.environ, "LC_ALL": "C"}

        # 1. Official repositories (prefer checkupdates to avoid partial-sync issues)
        if shutil.which("checkupdates"):
            try:
                res = subprocess.run(["checkupdates"], capture_output=True, text=True, timeout=25, env=env)
                for line in res.stdout.splitlines():
                    m = re.match(r"^(\S+)\s+(\S+)\s+->\s+(\S+)$", line.strip())
                    if m:
                        pending[m.group(1)] = (m.group(2), m.group(3), False)
            except Exception:
                pass
        else:
            try:
                res = subprocess.run(["pacman", "-Qu"], capture_output=True, text=True, timeout=15, env=env)
                for line in res.stdout.splitlines():
                    m = re.match(r"^(\S+)\s+(\S+)\s+->\s+(\S+)$", line.strip())
                    if m:
                        pending[m.group(1)] = (m.group(2), m.group(3), False)
            except Exception:
                pass

        # 2. AUR updates via paru if installed
        if shutil.which("paru"):
            try:
                res = subprocess.run(["paru", "-Qua"], capture_output=True, text=True, timeout=25, env=env)
                for line in res.stdout.splitlines():
                    m = re.match(r"^(\S+)\s+(\S+)\s+->\s+(\S+)$", line.strip())
                    if m:
                        pending[m.group(1)] = (m.group(2), m.group(3), True)
            except Exception:
                pass

        updates: list[dict[str, Any]] = []

        if "davinci-resolve" not in pending:
            resolve_update = _check_unowned_davinci_resolve()
            if resolve_update:
                updates.append(resolve_update)

        if not pending:
            return updates

        meta = _query_pacman_metadata(list(pending.keys()), explicit_only=False)
        distro_label = "CachyOS" if IS_CACHYOS else "Arch"

        for pkg, (old_v, new_v, is_aur) in pending.items():
            info = meta.get(pkg, {})
            desc = info.get("Description", f"{distro_label} package update for `{pkg}`.")
            url = info.get("URL", "")
            repo_from = info.get("Installed From", "AUR" if is_aur else "official")
            packager = info.get("Packager", "")

            body_parts = [desc]
            meta_lines = []
            if repo_from and repo_from != "None":
                meta_lines.append(f"- **Repository:** `{repo_from}`")
            if url and url != "None":
                meta_lines.append(f"- **Homepage:** {url}")
            if packager and packager != "None":
                meta_lines.append(f"- **Packager:** {packager}")
            if meta_lines:
                body_parts.append("\n" + "\n".join(meta_lines))

            updates.append({
                "id": f"pacman_{pkg}",
                "source": "pacman",
                "name": pkg,
                "pkg": pkg,
                "is_aur": is_aur,
                "installed": old_v,
                "available": new_v,
                "title": f"{distro_label} {'AUR' if is_aur else 'Package'}: {pkg}",
                "body": "\n\n".join(body_parts),
                "url": url if url and url != "None" else "",
            })

        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        """
        Run a full system upgrade once per update batch (paru -Syu, falling back to
        sudo pacman -Syu), followed by flatpak update -y if Flatpak is installed.
        """
        if item.get("aur_pkg"):
            aur_pkg = item["aur_pkg"]
            if shutil.which("paru"):
                print_info(f"[pacman] Upgrading {aur_pkg} from AUR via 'paru -S {aur_pkg}'...")
                res = subprocess.run(["paru", "-S", aur_pkg], env=env)
                if res.returncode == 0:
                    print_success(f"[pacman] {aur_pkg} upgraded to {item['available']}")
                    return True
                print_error(f"[pacman] Failed to upgrade {aur_pkg}")
                return False
            print_error(f"[pacman] paru is required to install/upgrade AUR package {aur_pkg}")
            return False

        if not self._sysupgrade_done:
            self._sysupgrade_done = True
            if shutil.which("paru"):
                print_info("[pacman] Running full CachyOS/Arch & AUR upgrade via 'paru -Syu'...")
                res = subprocess.run(["paru", "-Syu"], env=env)
            else:
                print_info("[pacman] paru not found; running 'sudo pacman -Syu'...")
                res = subprocess.run(["sudo", "pacman", "-Syu"], env=env)

            self._sysupgrade_ok = res.returncode == 0
            if self._sysupgrade_ok:
                print_success("[pacman] System packages upgraded successfully")
            else:
                print_error("[pacman] System upgrade failed")

            if self._sysupgrade_ok and shutil.which("flatpak"):
                print_info("[flatpak] Updating Flatpak packages via 'flatpak update -y'...")
                fres = subprocess.run(["flatpak", "update", "-y"], env=env)
                if fres.returncode == 0:
                    print_success("[flatpak] Flatpak packages up-to-date")
                else:
                    print_warn("[flatpak] 'flatpak update -y' returned a non-zero exit code")

        return self._sysupgrade_ok

    def list_installed(self) -> list[dict[str, Any]]:
        pkg_db = _query_pacman_metadata(explicit_only=True)
        if not pkg_db:
            return []

        items: list[dict[str, Any]] = []
        for pkg, info in pkg_db.items():
            raw_deps = info.get("Depends On", "None")
            deps = [] if raw_deps == "None" else [
                _clean_dep_name(d) for d in raw_deps.split() if _clean_dep_name(d)
            ]

            raw_rdeps = info.get("Required By", "None")
            rdepends = [] if raw_rdeps == "None" else [
                (r.strip(), "depends") for r in raw_rdeps.split() if r.strip()
            ]

            url = info.get("URL", "")
            items.append({
                "id": f"pacman_{pkg}",
                "source": "pacman",
                "name": pkg,
                "pkg": pkg,
                "version": info.get("Version", "installed"),
                "size_bytes": _parse_pacman_size(info.get("Installed Size", "")),
                "path": shutil.which(pkg) or f"/usr/bin/{pkg}",
                "homepage": url if url and url != "None" else "",
                "desc": info.get("Description", f"Arch/CachyOS package {pkg}"),
                "depends": deps,
                "rdepends": rdepends,
            })
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        pkg = item.get("pkg") or item["name"]
        print_info(f"[pacman] Removing {pkg} via 'sudo pacman -Rns'...")
        res = subprocess.run(["sudo", "pacman", "-Rns", "--noconfirm", pkg])
        if res.returncode == 0:
            print_success(f"[pacman] {pkg} removed successfully")
            return True
        print_error(f"[pacman] Failed to remove {pkg}")
        return False
