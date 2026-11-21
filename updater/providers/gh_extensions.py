"""
GitHub CLI extension update and uninstallation provider.
"""

import os
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any
from updater.config import HOME, TOKEN, normalize_compare_tag
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class GhExtProvider(BaseProvider):
    name = "gh-ext"
    source_label = "gh-ext"
    priority = 15

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("gh") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["gh", "extension", "list"], capture_output=True, text=True, timeout=5)
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3:
                    name, repo, ver = parts[0], parts[1], parts[2]
                    try:
                        headers = {"User-Agent": "updater/3.0"}
                        if TOKEN:
                            headers["Authorization"] = f"Bearer {TOKEN}"
                        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers=headers)
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            data = json.load(resp)
                            latest = data.get("tag_name", "")
                            if latest and normalize_compare_tag(latest) != normalize_compare_tag(ver):
                                updates.append({
                                    "id": f"gh_{name}",
                                    "source": "gh-ext",
                                    "name": name,
                                    "repo": repo,
                                    "installed": ver,
                                    "available": latest,
                                    "title": data.get("name", latest),
                                    "body": data.get("body", "")
                                })
                    except Exception:
                        pass
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[gh-ext] Upgrading {name}...")
        res = subprocess.run(["gh", "extension", "upgrade", name], env=env)
        if res.returncode == 0:
            print_success(f"[gh-ext] {name} upgraded to {item['available']}")
            return True
        print_error(f"[gh-ext] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["gh", "extension", "list"], capture_output=True, text=True, timeout=5)
            ext_dir = HOME / ".local" / "share" / "gh" / "extensions"
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3:
                    gname, grepo, gver = parts[0], parts[1], parts[2]
                    gpath = ext_dir / gname
                    total_sz = 0
                    if gpath.is_dir():
                        total_sz = sum(
                            f.stat().st_size for f in gpath.rglob("*") if f.is_file() and not f.is_symlink()
                        )
                    items.append({
                        "id": f"gh_{gname}",
                        "source": "gh-ext",
                        "name": gname,
                        "version": gver,
                        "size_bytes": total_sz,
                        "path": str(gpath),
                        "repo": grepo,
                        "homepage": f"https://github.com/{grepo}",
                        "desc": f"GitHub CLI extension ({grepo})",
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[gh-ext] Removing {name}...")
        res = subprocess.run(["gh", "extension", "remove", name])
        if res.returncode == 0:
            print_success(f"[gh-ext] {name} removed")
            return True
        print_error(f"[gh-ext] Failed to remove {name}")
        return False
