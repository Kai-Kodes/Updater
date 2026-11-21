"""
Cross-platform Vencord / Vesktop bundle update and uninstallation provider.
"""

import os
import re
import shutil
import urllib.request
import json
from pathlib import Path
from typing import Any
from updater.config import TOKEN, get_vencord_search_dirs
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

class VencordProvider(BaseProvider):
    name = "vencord"
    source_label = "vencord"
    priority = 5

    def _find_vencord_dir_and_commit(self) -> tuple[Path | None, str | None]:
        for c in get_vencord_search_dirs():
            rf = c / "vencordDesktopRenderer.js"
            if rf.is_file():
                try:
                    with open(rf, "r", encoding="utf-8", errors="ignore") as f:
                        line = f.readline()
                        m = re.search(r'Vencord\s+([a-f0-9]{7,})', line)
                        if m:
                            return c, m.group(1)[:7]
                except Exception:
                    pass
        return None, None

    @classmethod
    def is_available(cls) -> bool:
        for c in get_vencord_search_dirs():
            if (c / "vencordDesktopRenderer.js").is_file():
                return True
        return False

    def check_updates(self) -> list[dict[str, Any]]:
        vdir, installed_commit = self._find_vencord_dir_and_commit()
        if not vdir or not installed_commit:
            return []

        headers = {"User-Agent": "updater/3.0"}
        if TOKEN:
            headers["Authorization"] = f"Bearer {TOKEN}"

        latest_commit = None
        body_lines = []
        try:
            url = "https://api.github.com/repos/Vendicated/Vencord/commits?per_page=10"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as resp:
                commits = json.load(resp)
                if commits:
                    latest_commit = commits[0]["sha"][:7]
                    for c in commits:
                        sha = c["sha"][:7]
                        msg = c["commit"]["message"].splitlines()[0]
                        body_lines.append(f"• `{sha}` - {msg}")
                        if sha == installed_commit:
                            break
        except Exception:
            pass

        if latest_commit and latest_commit != installed_commit:
            body = "\n".join(body_lines) if body_lines else f"New Vencord devbuild available: {latest_commit}"
            return [{
                "id": "vencord_bundle",
                "source": "vencord",
                "name": "vencord",
                "repo": "Vendicated/Vencord",
                "path": str(vdir),
                "installed": installed_commit,
                "available": latest_commit,
                "title": f"Vencord DevBuild ({installed_commit}..{latest_commit})",
                "body": body,
                "url": "https://github.com/Vendicated/Vencord"
            }]
        return []

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        vdir = Path(item["path"])
        name = item["name"]
        print_info(f"[vencord] Updating Vencord bundle ({item['installed']} -> {item['available']})...")
        vdir.mkdir(parents=True, exist_ok=True)

        files = [
            "vencordDesktopMain.js",
            "vencordDesktopPreload.js",
            "vencordDesktopRenderer.js",
            "vencordDesktopRenderer.css",
        ]
        base_url = "https://github.com/Vendicated/Vencord/releases/download/devbuild/"
        success = True

        for fn in files:
            file_url = base_url + fn
            tmp_path = vdir / f"{fn}.tmp"
            final_path = vdir / fn
            try:
                urllib.request.urlretrieve(file_url, str(tmp_path))
                os.replace(str(tmp_path), str(final_path))
            except Exception as e:
                print_error(f"[vencord] Failed to download {fn}: {e}")
                success = False
                break

        if success:
            pkg_json = vdir / "package.json"
            try:
                with open(pkg_json, "w", encoding="utf-8") as pf:
                    pf.write("{}\n")
            except Exception:
                pass
            print_success(f"[vencord] Vencord bundle updated to {item['available']}")
            return True

        return False

    def list_installed(self) -> list[dict[str, Any]]:
        vdir, installed_commit = self._find_vencord_dir_and_commit()
        if not vdir or not vdir.is_dir():
            return []

        total_sz = sum(
            f.stat().st_size for f in vdir.rglob("*") if f.is_file() and not f.is_symlink()
        )

        return [{
            "id": "vencord_bundle",
            "source": "vencord",
            "name": "vencord",
            "version": installed_commit or "installed",
            "size_bytes": total_sz,
            "path": str(vdir),
            "homepage": "https://github.com/Vendicated/Vencord",
            "desc": "Vencord client modification bundle for Discord/Vesktop",
            "depends": [],
            "rdepends": []
        }]

    def uninstall(self, item: dict[str, Any]) -> bool:
        vdir = Path(item["path"])
        name = item["name"]
        print_info(f"[vencord] Removing Vencord bundle ({vdir})...")
        try:
            if vdir.is_dir():
                shutil.rmtree(vdir)
            elif vdir.is_file():
                vdir.unlink()
            print_success(f"[vencord] Vencord bundle removed")
            return True
        except Exception as e:
            print_error(f"[vencord] Failed to remove {vdir}: {e}")
            return False
