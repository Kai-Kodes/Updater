"""
Staged GitHub Debian package update and uninstallation provider.
"""

import os
import shutil
import tomllib
import subprocess
import urllib.request
from pathlib import Path
from typing import Any
from updater.config import (
    HOME, EGET_CONFIG_PATH, DEB_DIR, TOKEN, IS_LINUX, IS_ARCH,
    normalize_compare_tag
)
from updater.providers.base import BaseProvider
from updater.providers.eget import comment_out_eget_entry
from updater.ui import print_info, print_success, print_error, print_warn

KNOWN_DEB_PACKAGES = {
    "genspark-ai/genoffice": "genoffice",
    "FreeTubeApp/FreeTube": "freetube",
    "lolitemaultes/Gridline": "gridline",
    "cjpais/Handy": "handy",
    "koreader/koreader": "koreader",
    "ruizhi-lab/latte-dock-ng": "latte-dock-ng",
    "obsidianmd/obsidian-releases": "obsidian",
    "ONLYOFFICE/DesktopEditors": "onlyoffice-desktopeditors",
    "zquestz/plank-reloaded": "plank-reloaded",
    "LizardByte/Sunshine": "sunshine",
    "johannesjo/super-productivity": "superproductivity",
    "alexpasmantier/television": "television",
    "H-M-H/Weylus": "weylus",
    "th-ch/youtube-music": "youtube-music",
    "storytold/effectcraft": "effectcraft",
    "storytold/figcraft": "figcraft",
    "storytold/filmcraft": "filmcraft",
    "storytold/gridcraft": "gridcraft",
    "storytold/photocraft": "photocraft",
    "storytold/wordcraft": "wordcraft",
    "Vencord/Vesktop": "vesktop",
}

def get_dpkg_version(pkg_name: str) -> str:
    try:
        res = subprocess.run(["dpkg-query", "-W", "-f=${Version}", pkg_name], capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return ""

def resolve_deb_pkg(repo: str, opts: dict[str, Any]) -> str:
    if repo in KNOWN_DEB_PACKAGES:
        return KNOWN_DEB_PACKAGES[repo]
    app_base = repo.split("/")[-1].lower()
    if DEB_DIR.is_dir():
        for f in DEB_DIR.iterdir():
            if f.suffix == ".deb" and app_base in f.name.lower():
                try:
                    p = subprocess.check_output(
                        ["dpkg-deb", "-f", str(f), "Package"],
                        stderr=subprocess.DEVNULL, text=True, timeout=2
                    ).strip()
                    if p:
                        return p
                except Exception:
                    pass
    return app_base

def find_deb_for_pkg(pkg_name: str) -> Path | None:
    if not DEB_DIR.is_dir():
        return None
    candidates = []
    for f in DEB_DIR.glob("*.deb"):
        try:
            pkg = subprocess.check_output(
                ["dpkg-deb", "-f", str(f), "Package"],
                stderr=subprocess.DEVNULL, text=True, timeout=2
            ).strip()
            if pkg == pkg_name:
                candidates.append((f.stat().st_mtime, f))
        except Exception:
            pass
    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    return None

class DebProvider(BaseProvider):
    name = "deb"
    source_label = "deb"
    priority = 1

    @classmethod
    def is_available(cls) -> bool:
        return IS_LINUX and not IS_ARCH and shutil.which("dpkg") is not None and EGET_CONFIG_PATH.is_file()

    def check_updates(self) -> list[dict[str, Any]]:
        if not EGET_CONFIG_PATH.is_file():
            return []
        try:
            with open(EGET_CONFIG_PATH, "rb") as f:
                cfg = tomllib.load(f)
        except Exception:
            return []

        updates = []
        for repo, opts in cfg.items():
            if repo == "global":
                continue
            target_str = opts.get("target", "")
            if "gh-debs" not in target_str:
                continue

            prerelease = opts.get("prerelease", False)
            pkg_name = resolve_deb_pkg(repo, opts)
            installed_ver = get_dpkg_version(pkg_name)
            if not installed_ver:
                continue

            url = f"https://api.github.com/repos/{repo}/releases?per_page=1" if prerelease else f"https://api.github.com/repos/{repo}/releases/latest"
            headers = {"User-Agent": "updater/3.0", "Accept": "application/vnd.github.v3+json"}
            if TOKEN:
                headers["Authorization"] = f"Bearer {TOKEN}"

            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.load(resp)
                    rel = data[0] if isinstance(data, list) and data else data
                    avail_tag = rel.get("tag_name", "")
                    title = rel.get("name", "")
                    body = rel.get("body", "")
                    html_url = rel.get("html_url", "")
                    published_at = rel.get("published_at", "")[:10]
            except Exception:
                continue

            clean_i = normalize_compare_tag(installed_ver)
            clean_a = normalize_compare_tag(avail_tag)

            if clean_i and clean_a and clean_i != clean_a:
                updates.append({
                    "id": f"deb_{repo.replace('/', '_')}",
                    "source": "deb",
                    "name": pkg_name,
                    "repo": repo,
                    "pkg": pkg_name,
                    "target": str(DEB_DIR),
                    "prerelease": prerelease,
                    "installed": installed_ver,
                    "available": avail_tag,
                    "title": title or avail_tag,
                    "body": body or "No release notes provided.",
                    "url": html_url,
                    "published": published_at
                })
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        repo = item["repo"]
        name = item["name"]
        DEB_DIR.mkdir(parents=True, exist_ok=True)
        before_debs = set(DEB_DIR.iterdir())

        print_info(f"[deb] Downloading package for {name} ({repo})...")
        cmd = ["eget"]
        if item.get("prerelease"):
            cmd.append("--pre-release")
        if item.get("available"):
            cmd.extend(["-t", item["available"]])
        cmd.append(repo)

        res = subprocess.run(cmd, env=env)

        target_deb = None
        new_files = set(DEB_DIR.iterdir()) - before_debs
        for nf in new_files:
            if nf.suffix == ".deb":
                target_deb = nf
                break

        if not target_deb:
            target_deb = find_deb_for_pkg(item.get("pkg") or name)

        if not target_deb or not target_deb.is_file():
            print_error(f"[deb] Could not locate downloaded .deb file for {name}")
            return False

        print_info(f"[deb] Installing {target_deb.name} via dpkg...")
        inst_res = subprocess.run(["sudo", "dpkg", "-i", str(target_deb)], env=env)
        if inst_res.returncode != 0:
            print_warn(f"[deb] Resolving dependencies with 'apt-get install -f'...")
            subprocess.run(["sudo", "apt-get", "install", "-f", "-y"], env=env)

        print_success(f"[deb] {name} installed ({item['available']})")
        return True

    def list_installed(self) -> list[dict[str, Any]]:
        # Staged debs are listed through AptProvider / dpkg status
        return []

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["pkg"]
        print_info(f"[deb] Purging {name}...")
        res = subprocess.run(["sudo", "apt-get", "purge", "-y", name])
        if res.returncode == 0:
            subprocess.run(["sudo", "apt-get", "autoremove", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if item.get("repo"):
                comment_out_eget_entry(item["repo"])
            cached_deb = find_deb_for_pkg(name)
            if cached_deb and cached_deb.is_file():
                try:
                    cached_deb.unlink()
                except Exception:
                    pass
            print_success(f"[deb] {name} purged and configuration updated")
            return True
        print_error(f"[deb] Failed to purge {name}")
        return False
