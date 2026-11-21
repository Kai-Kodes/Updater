"""
Global Bun package update and uninstallation provider.
"""

import json
import shutil
import subprocess
import urllib.request
import concurrent.futures
from typing import Any
from updater.config import parse_ver_tuple
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

def _check_one_bun_pkg(pkg: str, curr_v: str) -> dict[str, Any] | None:
    try:
        url = f"https://registry.npmjs.org/{pkg}/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "updater/3.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            pdata = json.load(resp)
            latest_v = pdata.get("version")
            desc = pdata.get("description", "")
            if latest_v and parse_ver_tuple(latest_v) > parse_ver_tuple(curr_v):
                return {
                    "id": f"bun_{pkg.replace('/', '_').replace('@', '')}",
                    "source": "bun",
                    "name": pkg,
                    "installed": curr_v,
                    "available": latest_v,
                    "title": f"Bun Package: {pkg} {latest_v}",
                    "body": desc or f"Global Bun package update for {pkg}.",
                    "url": f"https://www.npmjs.com/package/{pkg}"
                }
    except Exception:
        pass
    return None

class BunProvider(BaseProvider):
    name = "bun"
    source_label = "bun"
    priority = 11

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("bun") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["bun", "pm", "ls", "-g", "--json"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                deps = data.get("dependencies", {}) or data.get("packages", {})
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = []
                    for pkg, info in deps.items():
                        curr_v = info.get("version") if isinstance(info, dict) else str(info)
                        if curr_v:
                            futures.append(executor.submit(_check_one_bun_pkg, pkg, curr_v))
                    for fut in concurrent.futures.as_completed(futures):
                        r = fut.result()
                        if r:
                            updates.append(r)
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[bun] Upgrading {name} to {item['available']}...")
        res = subprocess.run(["bun", "add", "-g", f"{name}@latest"], env=env)
        if res.returncode == 0:
            print_success(f"[bun] {name} upgraded to {item['available']}")
            return True
        print_error(f"[bun] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["bun", "pm", "ls", "-g", "--json"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                deps = data.get("dependencies", {}) or data.get("packages", {})
                for bpkg, binfo in deps.items():
                    bver = binfo.get("version") if isinstance(binfo, dict) else str(binfo)
                    items.append({
                        "id": f"bun_{bpkg.replace('/', '_').replace('@', '')}",
                        "source": "bun",
                        "name": bpkg,
                        "version": bver or "installed",
                        "size_bytes": 0,
                        "path": f"bun global: {bpkg}",
                        "homepage": f"https://www.npmjs.com/package/{bpkg}",
                        "desc": f"Global package managed by bun ({bpkg})",
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[bun] Removing {name}...")
        res = subprocess.run(["bun", "remove", "-g", name])
        if res.returncode == 0:
            print_success(f"[bun] {name} removed")
            return True
        print_error(f"[bun] Failed to remove {name}")
        return False
