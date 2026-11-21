"""
Standalone untracked application provider for ~/.local/opt, ~/Applications, etc.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Any
from updater.config import HOME, IS_WINDOWS, IS_MACOS
from updater.providers.base import BaseProvider
from updater.providers.eget import probe_binary_version, cleanup_desktop_and_symlinks
from updater.ui import print_info, print_success, print_error

class StandaloneProvider(BaseProvider):
    name = "standalone"
    source_label = "standalone"
    priority = 40

    @classmethod
    def is_available(cls) -> bool:
        return True

    def check_updates(self) -> list[dict[str, Any]]:
        # Unmanaged standalone apps update via their own mechanisms or eget
        return []

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        return True

    def list_installed(self) -> list[dict[str, Any]]:
        search_dirs = [
            HOME / ".local" / "opt",
            HOME / "Applications",
        ]
        if IS_MACOS:
            search_dirs.append(Path("/Applications"))
        if IS_WINDOWS:
            local_appdata = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local")))
            search_dirs.append(local_appdata / "Programs")

        items = []
        for sdir in search_dirs:
            if not sdir.is_dir():
                continue
            for entry in sdir.iterdir():
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                if (entry / ".git").is_dir():
                    continue

                full_p = str(entry.resolve())
                total_sz = sum(
                    f.stat().st_size for f in entry.rglob("*") if f.is_file() and not f.is_symlink()
                )
                v = probe_binary_version(entry)
                if not v:
                    m = re.search(r'([0-9]+\.[0-9]+(\.[0-9]+)?)', entry.name)
                    v = m.group(1) if m else "installed"
                disp_n = re.sub(r'-[0-9].*$', '', entry.name)

                items.append({
                    "id": f"standalone_{entry.name.replace('/', '_').replace('.', '_')}",
                    "source": "standalone",
                    "name": disp_n,
                    "version": v,
                    "size_bytes": total_sz,
                    "path": full_p,
                    "homepage": "",
                    "desc": f"Standalone application located at {full_p}",
                    "depends": [],
                    "rdepends": []
                })
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        target = Path(item["path"])
        name = item["name"]
        print_info(f"[standalone] Removing {name} ({target})...")
        try:
            if target.is_dir():
                shutil.rmtree(target)
            elif target.is_file():
                target.unlink()
            cleanup_desktop_and_symlinks(target, [name])
            print_success(f"[standalone] {name} removed successfully")
            return True
        except Exception as e:
            print_error(f"[standalone] Failed to remove {target}: {e}")
            return False
