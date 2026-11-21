"""
Global NPM package update and uninstallation provider.
"""

import os
import json
import shutil
import subprocess
import urllib.request
import concurrent.futures
from pathlib import Path
from typing import Any
from updater.config import parse_ver_tuple
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

def _check_one_npm_pkg(pkg: str, curr_v: str) -> dict[str, Any] | None:
    try:
        url = f"https://registry.npmjs.org/{pkg}/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "updater/3.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            pdata = json.load(resp)
            latest_v = pdata.get("version")
            desc = pdata.get("description", "")
            if latest_v and parse_ver_tuple(latest_v) > parse_ver_tuple(curr_v):
                safe_id = f"npm_{pkg.replace('/', '_').replace('@', '')}"
                return {
                    "id": safe_id,
                    "source": "npm",
                    "name": pkg,
                    "installed": curr_v,
                    "available": latest_v,
                    "title": f"npm Package: {pkg} {latest_v}",
                    "body": desc or f"Global npm package update for {pkg}.",
                    "url": f"https://www.npmjs.com/package/{pkg}"
                }
    except Exception:
        pass
    return None

class NpmProvider(BaseProvider):
    name = "npm"
    source_label = "npm"
    priority = 10

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("npm") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["npm", "list", "-g", "--depth=0", "--json"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                deps = data.get("dependencies", {})
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [
                        executor.submit(_check_one_npm_pkg, pkg, info.get("version", ""))
                        for pkg, info in deps.items()
                        if info.get("version")
                    ]
                    for fut in concurrent.futures.as_completed(futures):
                        r = fut.result()
                        if r:
                            updates.append(r)
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[npm] Upgrading {name} to {item['available']}...")
        res = subprocess.run(["npm", "install", "-g", f"{name}@latest"], env=env)
        if res.returncode == 0:
            print_success(f"[npm] {name} upgraded to {item['available']}")
            return True
        print_error(f"[npm] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["npm", "list", "-g", "--depth=0", "--json"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                try:
                    npm_root = Path(subprocess.check_output(["npm", "root", "-g"], text=True).strip())
                except Exception:
                    npm_root = Path.home() / ".npm-global" / "lib" / "node_modules"

                for pkg, info in data.get("dependencies", {}).items():
                    nver = info.get("version", "installed")
                    pkg_dir = npm_root / pkg
                    total_sz = 0
                    if pkg_dir.is_dir():
                        total_sz = sum(
                            f.stat().st_size for f in pkg_dir.rglob("*") if f.is_file() and not f.is_symlink()
                        )

                    ndesc = f"Global npm package {pkg}"
                    pjson = pkg_dir / "package.json"
                    if pjson.is_file():
                        try:
                            with open(pjson, "r", encoding="utf-8", errors="ignore") as pf:
                                pj = json.load(pf)
                                if pj.get("description"):
                                    ndesc = pj["description"]
                        except Exception:
                            pass

                    items.append({
                        "id": f"npm_{pkg.replace('/', '_').replace('@', '')}",
                        "source": "npm",
                        "name": pkg,
                        "version": nver,
                        "size_bytes": total_sz,
                        "path": str(pkg_dir),
                        "homepage": f"https://www.npmjs.com/package/{pkg}",
                        "desc": ndesc,
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[npm] Uninstalling {name}...")
        res = subprocess.run(["npm", "uninstall", "-g", name])
        if res.returncode == 0:
            print_success(f"[npm] {name} uninstalled")
            return True
        print_error(f"[npm] Failed to uninstall {name}")
        return False
