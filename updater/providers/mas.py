"""
Mac App Store (mas-cli) update provider for macOS.
"""

import re
import shutil
import subprocess
from typing import Any
from updater.config import IS_MACOS
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class MasProvider(BaseProvider):
    name = "mas"
    source_label = "mas"
    priority = 4

    @classmethod
    def is_available(cls) -> bool:
        return IS_MACOS and shutil.which("mas") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["mas", "outdated"], capture_output=True, text=True, timeout=10)
            for line in res.stdout.splitlines():
                # Format: 497799835 Xcode (15.2 -> 15.3)
                m = re.match(r'^(\d+)\s+(.+?)\s+\((.+?)\s+->\s+(.+?)\)', line.strip())
                if m:
                    app_id, name, curr_v, avail_v = m.group(1), m.group(2), m.group(3), m.group(4)
                    updates.append({
                        "id": f"mas_{app_id}",
                        "source": "mas",
                        "name": name,
                        "app_id": app_id,
                        "installed": curr_v,
                        "available": avail_v,
                        "title": f"Mac App Store: {name} {avail_v}",
                        "body": f"Mac App Store application update for {name} ({curr_v} -> {avail_v})."
                    })
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        app_id = item.get("app_id")
        name = item["name"]
        print_info(f"[mas] Upgrading {name} ({app_id})...")
        res = subprocess.run(["mas", "upgrade", app_id], env=env)
        if res.returncode == 0:
            print_success(f"[mas] {name} upgraded to {item['available']}")
            return True
        print_error(f"[mas] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["mas", "list"], capture_output=True, text=True, timeout=10)
            for line in res.stdout.splitlines():
                m = re.match(r'^(\d+)\s+(.+?)\s+\((.+?)\)', line.strip())
                if m:
                    app_id, name, ver = m.group(1), m.group(2), m.group(3)
                    items.append({
                        "id": f"mas_{app_id}",
                        "source": "mas",
                        "name": name,
                        "app_id": app_id,
                        "version": ver,
                        "size_bytes": 0,
                        "path": f"mas: {app_id}",
                        "homepage": f"https://apps.apple.com/app/id{app_id}",
                        "desc": f"Mac App Store application {name}",
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        # Mac App Store CLI does not support automated uninstall
        print_error("[mas] Mac App Store apps must be removed via Finder or Launchpad.")
        return False
