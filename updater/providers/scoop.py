"""
Scoop package update and uninstallation provider for Windows.
"""

import shutil
import subprocess
from typing import Any
from updater.config import IS_WINDOWS
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class ScoopProvider(BaseProvider):
    name = "scoop"
    source_label = "scoop"
    priority = 3

    @classmethod
    def is_available(cls) -> bool:
        return IS_WINDOWS and shutil.which("scoop") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["scoop", "status"], capture_output=True, text=True, timeout=15)
            lines = res.stdout.splitlines()
            start = False
            for line in lines:
                if line.startswith("---") or "---" in line:
                    start = True
                    continue
                if start and line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        name, curr_v, avail_v = parts[0], parts[1], parts[2]
                        updates.append({
                            "id": f"scoop_{name}",
                            "source": "scoop",
                            "name": name,
                            "installed": curr_v,
                            "available": avail_v,
                            "title": f"Scoop Package: {name} ({curr_v} -> {avail_v})",
                            "body": f"Scoop application update for {name} ({curr_v} -> {avail_v})."
                        })
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[scoop] Updating {name} to {item['available']}...")
        res = subprocess.run(["scoop", "update", name], env=env)
        if res.returncode == 0:
            print_success(f"[scoop] {name} updated to {item['available']}")
            return True
        print_error(f"[scoop] Failed to update {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["scoop", "list"], capture_output=True, text=True, timeout=10)
            lines = res.stdout.splitlines()
            start = False
            for line in lines:
                if line.startswith("---") or "---" in line:
                    start = True
                    continue
                if start and line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        name, ver = parts[0], parts[1]
                        items.append({
                            "id": f"scoop_{name}",
                            "source": "scoop",
                            "name": name,
                            "version": ver,
                            "size_bytes": 0,
                            "path": f"scoop: {name}",
                            "homepage": "",
                            "desc": f"Scoop package {name}",
                            "depends": [],
                            "rdepends": []
                        })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[scoop] Uninstalling {name}...")
        res = subprocess.run(["scoop", "uninstall", name])
        if res.returncode == 0:
            print_success(f"[scoop] {name} uninstalled")
            return True
        print_error(f"[scoop] Failed to uninstall {name}")
        return False
