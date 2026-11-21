"""
UV Python tool update and uninstallation provider.
"""

import os
import re
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any
from updater.config import HOME, parse_ver_tuple
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class UvProvider(BaseProvider):
    name = "uv"
    source_label = "uv"
    priority = 14

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("uv") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True, timeout=5)
            for line in res.stdout.splitlines():
                m = re.match(r'^([a-zA-Z0-9_\-]+)\s+v?([0-9.]+)', line.strip())
                if m:
                    name, curr_v = m.group(1), m.group(2)
                    try:
                        url = f"https://pypi.org/pypi/{name}/json"
                        req = urllib.request.Request(url, headers={"User-Agent": "updater/3.0"})
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            pdata = json.load(resp)
                            latest_v = pdata.get("info", {}).get("version")
                            summary = pdata.get("info", {}).get("summary", "Python CLI tool.")
                            if latest_v and parse_ver_tuple(latest_v) > parse_ver_tuple(curr_v):
                                updates.append({
                                    "id": f"uv_{name}",
                                    "source": "uv",
                                    "name": name,
                                    "installed": curr_v,
                                    "available": latest_v,
                                    "title": f"uv Tool: {name} {latest_v}",
                                    "body": summary,
                                    "url": f"https://pypi.org/project/{name}"
                                })
                    except Exception:
                        pass
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[uv] Upgrading {name} to {item['available']}...")
        res = subprocess.run(["uv", "tool", "upgrade", name], env=env)
        if res.returncode == 0:
            print_success(f"[uv] {name} upgraded to {item['available']}")
            return True
        print_error(f"[uv] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True, timeout=5)
            uv_tool_dir = HOME / ".local" / "share" / "uv" / "tools"
            for line in res.stdout.splitlines():
                m = re.match(r'^([a-zA-Z0-9_\-]+)\s+v?([0-9.]+)', line.strip())
                if m:
                    name, curr_v = m.group(1), m.group(2)
                    tpath = uv_tool_dir / name
                    total_sz = 0
                    if tpath.is_dir():
                        total_sz = sum(
                            f.stat().st_size for f in tpath.rglob("*") if f.is_file() and not f.is_symlink()
                        )
                    items.append({
                        "id": f"uv_{name}",
                        "source": "uv",
                        "name": name,
                        "version": curr_v,
                        "size_bytes": total_sz,
                        "path": str(tpath),
                        "homepage": f"https://pypi.org/project/{name}",
                        "desc": f"Python CLI tool managed by uv ({name})",
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[uv] Uninstalling {name}...")
        res = subprocess.run(["uv", "tool", "uninstall", name])
        if res.returncode == 0:
            print_success(f"[uv] {name} uninstalled")
            return True
        print_error(f"[uv] Failed to uninstall {name}")
        return False
