"""
Homebrew formula & cask update and uninstallation provider for macOS / Linux.
"""

import json
import shutil
import subprocess
from typing import Any
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class BrewProvider(BaseProvider):
    name = "brew"
    source_label = "brew"
    priority = 3

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("brew") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["brew", "outdated", "--json=v2"], capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)

                # Formulae
                for f in data.get("formulae", []):
                    name = f.get("name", "")
                    inst_vers = f.get("installed_versions", [])
                    curr_v = inst_vers[0] if inst_vers else "installed"
                    avail_v = f.get("current_version", "")
                    updates.append({
                        "id": f"brew_{name}",
                        "source": "brew",
                        "name": name,
                        "type": "formula",
                        "installed": curr_v,
                        "available": avail_v,
                        "title": f"Homebrew Formula: {name} {avail_v}",
                        "body": f"Homebrew formula update for {name} ({curr_v} -> {avail_v}).",
                        "url": f"https://formulae.brew.sh/formula/{name}"
                    })

                # Casks
                for c in data.get("casks", []):
                    name = c.get("name", "")
                    inst_vers = c.get("installed_versions", [])
                    curr_v = inst_vers[0] if inst_vers else "installed"
                    avail_v = c.get("current_version", "")
                    updates.append({
                        "id": f"brew_cask_{name}",
                        "source": "brew",
                        "name": name,
                        "type": "cask",
                        "installed": curr_v,
                        "available": avail_v,
                        "title": f"Homebrew Cask: {name} {avail_v}",
                        "body": f"Homebrew cask application update for {name} ({curr_v} -> {avail_v}).",
                        "url": f"https://formulae.brew.sh/cask/{name}"
                    })
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        name = item["name"]
        is_cask = item.get("type") == "cask"
        cmd = ["brew", "upgrade", "--cask", name] if is_cask else ["brew", "upgrade", name]
        label = f"[brew cask] {name}" if is_cask else f"[brew] {name}"
        print_info(f"Upgrading {label}...")
        res = subprocess.run(cmd, env=env)
        if res.returncode == 0:
            print_success(f"{label} upgraded to {item['available']}")
            return True
        print_error(f"Failed to upgrade {label}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        items = []
        try:
            res = subprocess.run(["brew", "list", "--versions"], capture_output=True, text=True, timeout=10)
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    name, ver = parts[0], parts[1]
                    items.append({
                        "id": f"brew_{name}",
                        "source": "brew",
                        "name": name,
                        "type": "formula",
                        "version": ver,
                        "size_bytes": 0,
                        "path": f"brew: {name}",
                        "homepage": f"https://formulae.brew.sh/formula/{name}",
                        "desc": f"Homebrew formula {name}",
                        "depends": [],
                        "rdepends": []
                    })

            # List casks
            cask_res = subprocess.run(["brew", "list", "--cask", "--versions"], capture_output=True, text=True, timeout=10)
            for line in cask_res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    name, ver = parts[0], parts[1]
                    items.append({
                        "id": f"brew_cask_{name}",
                        "source": "brew",
                        "name": name,
                        "type": "cask",
                        "version": ver,
                        "size_bytes": 0,
                        "path": f"brew cask: {name}",
                        "homepage": f"https://formulae.brew.sh/cask/{name}",
                        "desc": f"Homebrew cask application {name}",
                        "depends": [],
                        "rdepends": []
                    })
        except Exception:
            pass
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        is_cask = item.get("type") == "cask"
        cmd = ["brew", "uninstall", "--cask", name] if is_cask else ["brew", "uninstall", name]
        label = f"[brew cask] {name}" if is_cask else f"[brew] {name}"
        print_info(f"Uninstalling {label}...")
        res = subprocess.run(cmd)
        if res.returncode == 0:
            print_success(f"{label} uninstalled")
            return True
        print_error(f"Failed to uninstall {label}")
        return False
