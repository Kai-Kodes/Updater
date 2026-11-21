"""
Chocolatey package update and uninstallation provider for Windows.
"""

import shutil
import subprocess
from typing import Any
from updater.config import IS_WINDOWS
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class ChocoProvider(BaseProvider):
    name = "choco"
    source_label = "choco"
    priority = 4

    @classmethod
    def is_available(cls) -> bool:
        return IS_WINDOWS and shutil.which("choco") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["choco", "outdated", "--limit-output"], capture_output=True, text=True, timeout=15)
            for line in res.stdout.splitlines():
                parts = line.strip().split("|")
                if len(parts) >= 3:
                    name, curr_v, avail_v = parts[0], parts[1], parts[2]
                    updates.append({
                        "id": f"choco_{name}",
                        "source": "choco",
                        "name": name,
                        "installed": curr_v,
                        "available": avail_v,
                        "title": f"Chocolatey: {name} ({curr_v} -> {avail_v})",
                        "body": f"Chocolatey package update for {name} ({curr_v} -> {avail_v})."
                    })
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[choco] Upgrading {name} to {item['available']}...")
        res = subprocess.run(["choco", "upgrade", name, "-y"], env=env)
        if res.returncode == 0:
            print_success(f"[choco] {name} upgraded to {item['available']}")
            return True
        print_error(f"[choco] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["choco", "list", "--limit-output"], capture_output=True, text=True, timeout=10)
            for line in res.stdout.splitlines():
                parts = line.strip().split("|")
                if len(parts) >= 2:
                    name, ver = parts[0], parts[1]
                    items.append({
                        "id": f"choco_{name}",
                        "source": "choco",
                        "name": name,
                        "version": ver,
                        "size_bytes": 0,
                        "path": f"choco: {name}",
                        "homepage": "",
                        "desc": f"Chocolatey package {name}",
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[choco] Uninstalling {name}...")
        res = subprocess.run(["choco", "uninstall", name, "-y"])
        if res.returncode == 0:
            print_success(f"[choco] {name} uninstalled")
            return True
        print_error(f"[choco] Failed to uninstall {name}")
        return False
