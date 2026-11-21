"""
Pipx Python CLI tool update and uninstallation provider.
"""

import json
import shutil
import subprocess
import urllib.request
import concurrent.futures
from pathlib import Path
from typing import Any
from updater.config import HOME, parse_ver_tuple
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

def _check_one_pipx_tool(name: str, curr_v: str) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(f"https://pypi.org/pypi/{name}/json", headers={"User-Agent": "updater/3.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            pypi_data = json.load(resp)
            latest_v = pypi_data.get("info", {}).get("version")
            summary = pypi_data.get("info", {}).get("summary", "Python CLI tool.")
            if latest_v and parse_ver_tuple(latest_v) > parse_ver_tuple(curr_v):
                return {
                    "id": f"pipx_{name}",
                    "source": "pipx",
                    "name": name,
                    "installed": curr_v,
                    "available": latest_v,
                    "title": f"Pipx Tool: {name} {latest_v}",
                    "body": summary,
                    "url": f"https://pypi.org/project/{name}"
                }
    except Exception:
        pass
    return None

class PipxProvider(BaseProvider):
    name = "pipx"
    source_label = "pipx"
    priority = 13

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("pipx") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["pipx", "list", "--json"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                venvs = data.get("venvs", {})
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = []
                    for name, venv in venvs.items():
                        pkg_info = venv.get("metadata", {}).get("main_package", {})
                        curr_v = pkg_info.get("package_version")
                        if curr_v:
                            futures.append(executor.submit(_check_one_pipx_tool, name, curr_v))
                    for fut in concurrent.futures.as_completed(futures):
                        res = fut.result()
                        if res:
                            updates.append(res)
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[pipx] Upgrading {name} to {item['available']}...")
        res = subprocess.run(["pipx", "upgrade", name], env=env)
        if res.returncode == 0:
            print_success(f"[pipx] {name} upgraded to {item['available']}")
            return True
        print_error(f"[pipx] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["pipx", "list", "--json"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                pdata = json.loads(res.stdout)
                pipx_home = HOME / ".local" / "pipx" / "venvs"
                for pname, pvenv in pdata.get("venvs", {}).items():
                    pver = pvenv.get("metadata", {}).get("main_package", {}).get("package_version", "installed")
                    vpath = pipx_home / pname
                    total_sz = 0
                    if vpath.is_dir():
                        total_sz = sum(
                            f.stat().st_size for f in vpath.rglob("*") if f.is_file() and not f.is_symlink()
                        )
                    items.append({
                        "id": f"pipx_{pname}",
                        "source": "pipx",
                        "name": pname,
                        "version": pver,
                        "size_bytes": total_sz,
                        "path": str(vpath),
                        "homepage": f"https://pypi.org/project/{pname}",
                        "desc": f"Python CLI tool managed by pipx ({pname})",
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[pipx] Uninstalling {name}...")
        res = subprocess.run(["pipx", "uninstall", name])
        if res.returncode == 0:
            print_success(f"[pipx] {name} uninstalled")
            return True
        print_error(f"[pipx] Failed to uninstall {name}")
        return False
