"""
Windows Package Manager (winget) update and uninstallation provider.
"""

import re
import shutil
import subprocess
from typing import Any
from updater.config import IS_WINDOWS
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class WingetProvider(BaseProvider):
    name = "winget"
    source_label = "winget"
    priority = 2

    @classmethod
    def is_available(cls) -> bool:
        return IS_WINDOWS and shutil.which("winget") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(
                ["winget", "upgrade", "--include-unknown"],
                capture_output=True, text=True, timeout=20
            )
            # Find the header separator line (e.g. -----   -----)
            lines = res.stdout.splitlines()
            start_idx = -1
            for idx, line in enumerate(lines):
                if line.startswith("---") or "---" in line:
                    start_idx = idx + 1
                    break

            if start_idx != -1 and start_idx < len(lines):
                for line in lines[start_idx:]:
                    if not line.strip() or line.startswith("<") or "upgrades available" in line.lower():
                        continue
                    # Winget columns are fixed-width or space-delimited
                    parts = re.split(r'\s{2,}', line.strip())
                    if len(parts) >= 4:
                        name, pkg_id, curr_v, avail_v = parts[0], parts[1], parts[2], parts[3]
                        updates.append({
                            "id": f"winget_{pkg_id.replace('.', '_')}",
                            "source": "winget",
                            "name": name,
                            "pkg_id": pkg_id,
                            "installed": curr_v,
                            "available": avail_v,
                            "title": f"winget: {name} ({curr_v} -> {avail_v})",
                            "body": f"Windows package update for {name} ({pkg_id}) from winget repository.",
                            "url": f"https://github.com/microsoft/winget-pkgs/tree/master/manifests/{pkg_id[0].lower()}/{pkg_id.replace('.', '/')}"
                        })
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        pkg_id = item.get("pkg_id") or item["name"]
        name = item["name"]
        print_info(f"[winget] Upgrading {name} ({pkg_id})...")
        cmd = [
            "winget", "upgrade", "--id", pkg_id, "--exact",
            "--accept-package-agreements", "--accept-source-agreements"
        ]
        res = subprocess.run(cmd, env=env)
        if res.returncode == 0:
            print_success(f"[winget] {name} upgraded to {item['available']}")
            return True
        print_error(f"[winget] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["winget", "list"], capture_output=True, text=True, timeout=20)
            lines = res.stdout.splitlines()
            start_idx = -1
            for idx, line in enumerate(lines):
                if line.startswith("---") or "---" in line:
                    start_idx = idx + 1
                    break
            if start_idx != -1 and start_idx < len(lines):
                for line in lines[start_idx:]:
                    parts = re.split(r'\s{2,}', line.strip())
                    if len(parts) >= 3:
                        name, pkg_id, ver = parts[0], parts[1], parts[2]
                        items.append({
                            "id": f"winget_{pkg_id.replace('.', '_')}",
                            "source": "winget",
                            "name": name,
                            "pkg_id": pkg_id,
                            "version": ver,
                            "size_bytes": 0,
                            "path": f"winget: {pkg_id}",
                            "homepage": "",
                            "desc": f"Windows package managed by winget ({pkg_id})",
                            "depends": [],
                            "rdepends": []
                        })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        pkg_id = item.get("pkg_id") or item["name"]
        name = item["name"]
        print_info(f"[winget] Uninstalling {name} ({pkg_id})...")
        res = subprocess.run(["winget", "uninstall", "--id", pkg_id])
        if res.returncode == 0:
            print_success(f"[winget] {name} uninstalled")
            return True
        print_error(f"[winget] Failed to uninstall {name}")
        return False
