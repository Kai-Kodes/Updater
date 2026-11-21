"""
Cargo / Rust binary crate update and uninstallation provider.
"""

import os
import re
import shutil
import subprocess
import urllib.request
import json
import concurrent.futures
from pathlib import Path
from typing import Any
from updater.config import HOME, parse_ver_tuple
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

def _check_one_cargo_crate(name: str, curr_v: str) -> dict[str, Any] | None:
    try:
        url = f"https://crates.io/api/v1/crates/{name}"
        req = urllib.request.Request(url, headers={"User-Agent": "updater/3.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.load(resp)
            latest_v = data.get("crate", {}).get("max_version")
            desc = data.get("crate", {}).get("description", "")
            if latest_v and parse_ver_tuple(latest_v) > parse_ver_tuple(curr_v):
                return {
                    "id": f"cargo_{name}",
                    "source": "cargo",
                    "name": name,
                    "installed": curr_v,
                    "available": latest_v,
                    "title": f"Cargo Crate: {name} {latest_v}",
                    "body": desc or f"Rust binary crate update for {name}.",
                    "url": f"https://crates.io/crates/{name}"
                }
    except Exception:
        pass
    return None

class CargoProvider(BaseProvider):
    name = "cargo"
    source_label = "cargo"
    priority = 12

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("cargo") is not None or (HOME / ".cargo" / ".crates.toml").is_file()

    def _get_installed_crates(self) -> dict[str, str]:
        crates = {}
        crates_toml = HOME / ".cargo" / ".crates.toml"
        if crates_toml.is_file():
            try:
                with open(crates_toml, "r", encoding="utf-8") as f:
                    for line in f:
                        m = re.match(r'^"(\S+)\s+(\S+)\s+\(registry\+', line.strip())
                        if m:
                            crates[m.group(1)] = m.group(2)
            except Exception:
                pass

        if not crates and shutil.which("cargo"):
            try:
                res = subprocess.run(["cargo", "install", "--list"], capture_output=True, text=True, timeout=5)
                for line in res.stdout.splitlines():
                    m = re.match(r'^(\S+)\s+v([0-9.]+):', line.strip())
                    if m:
                        crates[m.group(1)] = m.group(2)
            except Exception:
                pass
        return crates

    def check_updates(self) -> list[dict[str, Any]]:
        crates = self._get_installed_crates()
        updates = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(_check_one_cargo_crate, name, ver) for name, ver in crates.items()]
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                if res:
                    updates.append(res)
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        print_info(f"[cargo] Upgrading {name} to {item['available']}...")
        res = subprocess.run(["cargo", "install", name], env=env)
        if res.returncode == 0:
            print_success(f"[cargo] {name} upgraded to {item['available']}")
            return True
        print_error(f"[cargo] Failed to upgrade {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        crates = self._get_installed_crates()
        items = []
        cargo_bin_dir = HOME / ".cargo" / "bin"
        for cname, cver in crates.items():
            bin_p = cargo_bin_dir / cname
            c_sz = bin_p.stat().st_size if bin_p.is_file() else 0
            items.append({
                "id": f"cargo_{cname}",
                "source": "cargo",
                "name": cname,
                "version": cver,
                "size_bytes": c_sz,
                "path": str(bin_p),
                "homepage": f"https://crates.io/crates/{cname}",
                "desc": f"Rust binary crate installed via cargo ({cname})",
                "depends": [],
                "rdepends": []
            })
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        print_info(f"[cargo] Uninstalling {name}...")
        res = subprocess.run(["cargo", "uninstall", name])
        if res.returncode == 0:
            print_success(f"[cargo] {name} uninstalled")
            return True

        # Fallback binary deletion
        bin_p = Path(item["path"])
        if bin_p.is_file():
            try:
                bin_p.unlink()
                print_success(f"[cargo] {name} binary removed")
                return True
            except Exception as e:
                print_error(f"[cargo] Failed to remove {bin_p}: {e}")
        else:
            print_error(f"[cargo] Failed to uninstall {name}")
        return False
