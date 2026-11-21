"""
Snap package update and uninstallation provider.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any
from updater.config import IS_LINUX
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class SnapProvider(BaseProvider):
    name = "snap"
    source_label = "snap"
    priority = 26

    @classmethod
    def is_available(cls) -> bool:
        return IS_LINUX and shutil.which("snap") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["snap", "refresh", "--list"], capture_output=True, text=True, timeout=5)
            lines = res.stdout.splitlines()
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        name, ver, rev, publisher = parts[0], parts[1], parts[2], parts[3]
                        updates.append({
                            "id": f"snap_{name}",
                            "source": "snap",
                            "name": name,
                            "installed": "installed",
                            "available": ver,
                            "title": f"Snap Package: {name} ({ver})",
                            "body": f"Snap package update for {name} from publisher {publisher}."
                        })
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[snap] Refreshing {name}...")
        res = subprocess.run(["sudo", "snap", "refresh", name], env=env)
        if res.returncode == 0:
            print_success(f"[snap] {name} refreshed to {item['available']}")
            return True
        print_error(f"[snap] Failed to refresh {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["snap", "list"], capture_output=True, text=True, timeout=5)
            lines = res.stdout.splitlines()
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        name, ver, rev = parts[0], parts[1], parts[2]
                        if name in ("core", "core18", "core20", "core22", "core24", "bare", "snapd"):
                            continue
                        items.append({
                            "id": f"snap_{name}",
                            "source": "snap",
                            "name": name,
                            "version": ver,
                            "size_bytes": 0,
                            "path": f"/snap/{name}",
                            "homepage": f"https://snapcraft.io/{name}",
                            "desc": f"Snap application {name}",
                            "depends": [],
                            "rdepends": []
                        })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[snap] Removing {name}...")
        res = subprocess.run(["sudo", "snap", "remove", name])
        if res.returncode == 0:
            print_success(f"[snap] {name} removed")
            return True
        print_error(f"[snap] Failed to remove {name}")
        return False
