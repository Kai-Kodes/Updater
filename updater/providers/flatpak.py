"""
Flatpak application update and uninstallation provider.
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from updater.config import HOME, IS_LINUX
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class FlatpakProvider(BaseProvider):
    name = "flatpak"
    source_label = "flatpak"
    priority = 25

    @classmethod
    def is_available(cls) -> bool:
        return IS_LINUX and shutil.which("flatpak") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(
                ["flatpak", "remote-ls", "--updates", "--app", "--columns=name,application,version"],
                capture_output=True, text=True, timeout=10
            )
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    name, app_id = parts[0], parts[1]
                    avail = parts[2] if len(parts) >= 3 else "latest"
                    inst_res = subprocess.run(["flatpak", "info", app_id], capture_output=True, text=True, timeout=2)
                    inst_v = "installed"
                    desc = f"Flatpak application update for {name} ({app_id})."
                    for l in inst_res.stdout.splitlines():
                        if "Version:" in l:
                            inst_v = l.split("Version:")[1].strip()
                        if "Description:" in l:
                            desc = l.split("Description:")[1].strip()

                    updates.append({
                        "id": f"flatpak_{name.lower().replace(' ', '_')}",
                        "source": "flatpak",
                        "name": name,
                        "app_id": app_id,
                        "installed": inst_v,
                        "available": avail,
                        "title": f"Flatpak: {name}",
                        "body": desc
                    })
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        app_id = item.get("app_id") or item["name"]
        name = item["name"]
        print_info(f"[flatpak] Updating {name} ({app_id})...")
        res = subprocess.run(["flatpak", "update", "-y", app_id])
        if res.returncode == 0:
            print_success(f"[flatpak] {name} updated to {item['available']}")
            return True
        print_error(f"[flatpak] Failed to update {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(
                ["flatpak", "list", "--app", "--columns=name,application,version,size"],
                capture_output=True, text=True, timeout=5
            )
            for line in res.stdout.splitlines():
                parts = re.split(r'\t+|\s{2,}', line.strip())
                if len(parts) >= 2:
                    fn, fapp = parts[0], parts[1]
                    fver = parts[2] if len(parts) >= 3 else "installed"
                    fsz_str = parts[3] if len(parts) >= 4 else "Unknown"
                    sz_bytes = 0
                    sm = re.search(r'([0-9.]+)\s*([kMGTP]?B)', fsz_str)
                    if sm:
                        val, unit = float(sm.group(1)), sm.group(2)
                        multipliers = {"B": 1, "kB": 1000, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
                        sz_bytes = int(val * multipliers.get(unit, 1024**2))

                    items.append({
                        "id": f"flatpak_{fapp.replace('.', '_')}",
                        "source": "flatpak",
                        "name": fn,
                        "app_id": fapp,
                        "version": fver,
                        "size_bytes": sz_bytes,
                        "path": str(HOME / ".var" / "app" / fapp),
                        "homepage": f"https://flathub.org/apps/{fapp}",
                        "desc": f"Flatpak application {fn} ({fapp})",
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        app_id = item.get("app_id") or item["name"]
        name = item["name"]
        print_info(f"[flatpak] Uninstalling {name} ({app_id})...")
        res = subprocess.run(["flatpak", "uninstall", "-y", app_id])
        if res.returncode == 0:
            print_success(f"[flatpak] {name} uninstalled")
            return True
        print_error(f"[flatpak] Failed to uninstall {name}")
        return False
