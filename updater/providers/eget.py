"""
Eget GitHub release binary and standalone application provider.
"""

import os
import re
import shutil
import tomllib
import subprocess
import urllib.request
from pathlib import Path
from typing import Any
from updater.config import (
    HOME, EGET_CONFIG_PATH, TOKEN,
    clean_version, normalize_compare_tag
)
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

def probe_binary_version(bin_path: Path | str) -> str:
    bp = Path(bin_path)
    if not bp.exists():
        return ""

    if bp.is_dir():
        # 1. Electron app.asar check (e.g. balenaEtcher)
        asar = bp / "resources" / "app.asar"
        if asar.is_file():
            try:
                with open(asar, "rb") as f:
                    all_bytes = f.read()
                    m = re.search(rb'"productName":"balenaEtcher","version":"([^"]+)"', all_bytes)
                    if not m:
                        m = re.search(rb'"name":"balena-etcher".*?"version":"([^"]+)"', all_bytes)
                    if not m:
                        m = re.search(rb'"version":\s*"([0-9]+\.[0-9]+[^\"]*)"', all_bytes)
                    if m:
                        return m.group(1).decode("utf-8", errors="ignore").strip()
            except Exception:
                pass

        # 2. Dedicated version file
        vfile = bp / "version"
        if vfile.is_file():
            try:
                v = vfile.read_text().strip()
                if not re.match(r'^4[0-9]\.', v):
                    return v
            except Exception:
                pass

        # 3. Java / jpackage check
        jpack = bp / "lib" / "app" / ".jpackage.xml"
        if jpack.is_file():
            try:
                m = re.search(r'<app-version>(.*?)</app-version>', jpack.read_text())
                if m:
                    return m.group(1)
            except Exception:
                pass

        # 4. AyuGram log check
        if "ayugram" in str(bp).lower():
            log_file = HOME / ".local" / "share" / "AyuGramDesktop" / "log.txt"
            if log_file.is_file():
                try:
                    with open(log_file, "r", errors="ignore") as f:
                        for line in f:
                            m = re.search(r'Launched version:\s*(\d+)', line)
                            if m:
                                num = int(m.group(1))
                                return f"v{num // 1000000}.{(num % 1000000) // 1000}.{num % 1000}"
                except Exception:
                    pass

        sub_bin = bp / bp.name
        if sub_bin.is_file():
            bp = sub_bin
        else:
            return ""

    if "ayugram" in str(bp).lower():
        log_file = HOME / ".local" / "share" / "AyuGramDesktop" / "log.txt"
        if log_file.is_file():
            try:
                with open(log_file, "r", errors="ignore") as f:
                    for line in f:
                        m = re.search(r'Launched version:\s*(\d+)', line)
                        if m:
                            num = int(m.group(1))
                            return f"v{num // 1000000}.{(num % 1000000) // 1000}.{num % 1000}"
            except Exception:
                pass

    if not bp.is_file():
        return ""

    if os.access(bp, os.X_OK):
        for flag in ["--version", "version", "-v", "-V", "-version"]:
            try:
                res = subprocess.run([str(bp), flag], capture_output=True, text=True, timeout=1.2)
                out = (res.stdout or res.stderr).strip().splitlines()
                if out:
                    candidate = clean_version(out[0].strip())
                    if candidate:
                        return candidate
            except Exception:
                pass
    return ""

def get_display_name(repo: str, opts: dict[str, Any]) -> str:
    name_map = {
        "cli/cli": "gh",
        "zen-browser/desktop": "zen-browser",
        "kovidgoyal/kitty": "kitty",
        "zed-industries/zed": "zed",
        "amir1376/ab-download-manager": "ab-download-manager",
        "yorukot/superfile": "superfile",
        "duxlabs-dev/dux-calendar": "dcal",
        "duxlabs-dev/dux-files": "dfiles",
        "duxlabs-dev/dux-search": "dsearch",
        "duxlabs-dev/dux-shell": "dms",
        "AvengeMedia/dgop": "dgop",
        "Vencord/Vesktop": "vesktop",
        "AyuGram/AyuGramDesktop": "ayugram",
    }
    if repo in name_map:
        return name_map[repo]
    if opts.get("file"):
        return opts["file"]
    return repo.split("/")[-1]

def cleanup_desktop_and_symlinks(target_path: Path | str, name_hints: list[str] | None = None) -> list[str]:
    removed_items = []
    if not target_path:
        return removed_items
    target_abs = str(Path(target_path).resolve())

    bin_dir = HOME / ".local" / "bin"
    if bin_dir.is_dir():
        for item in bin_dir.iterdir():
            if item.is_symlink():
                try:
                    dest = str(item.resolve())
                    if dest == target_abs or dest.startswith(target_abs + os.sep):
                        item.unlink()
                        removed_items.append(f"Symlink: {item}")
                except Exception:
                    pass

    app_dir = HOME / ".local" / "share" / "applications"
    if app_dir.is_dir():
        for item in app_dir.glob("*.desktop"):
            try:
                content = item.read_text(errors="ignore")
                if target_abs in content:
                    item.unlink()
                    removed_items.append(f"Desktop launcher: {item}")
            except Exception:
                pass
    return removed_items

def comment_out_eget_entry(repo: str) -> bool:
    if not EGET_CONFIG_PATH.is_file():
        return False
    try:
        content = EGET_CONFIG_PATH.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        out = []
        in_target_section = False
        target_headers = {f'["{repo}"]', f"['{repo}']", f"[{repo}]"}

        modified = False
        for line in lines:
            sline = line.strip()
            if sline.startswith("[") and sline.endswith("]"):
                if sline in target_headers:
                    in_target_section = True
                    modified = True
                    out.append(f"# {line}")
                    continue
                else:
                    in_target_section = False

            if in_target_section:
                if sline == "":
                    in_target_section = False
                    out.append(line)
                else:
                    out.append(f"# {line}" if not line.startswith("#") else line)
            else:
                out.append(line)

        if modified:
            EGET_CONFIG_PATH.write_text("".join(out), encoding="utf-8")
            return True
    except Exception:
        pass
    return False

class EgetProvider(BaseProvider):
    name = "eget"
    source_label = "eget"
    priority = 2

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("eget") is not None and EGET_CONFIG_PATH.is_file()

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
            if "gh-debs" in target_str:
                continue # Handled by DebProvider

            target = Path(os.path.expanduser(target_str))
            file_name = opts.get("file")
            prerelease = opts.get("prerelease", False)
            display_name = get_display_name(repo, opts)

            installed_ver = ""
            if repo == "zen-browser/desktop":
                ini_path = HOME / ".local" / "share" / "zen" / "application.ini"
                if ini_path.is_file():
                    try:
                        m = re.search(r'^Version=(.*?)$', ini_path.read_text(), re.M)
                        if m:
                            installed_ver = m.group(1).strip()
                    except Exception:
                        pass
            elif repo == "kovidgoyal/kitty":
                installed_ver = probe_binary_version(HOME / ".local" / "kitty.app" / "bin" / "kitty")
            elif repo == "zed-industries/zed":
                installed_ver = probe_binary_version(HOME / ".local" / "zed.app" / "bin" / "zed")
            else:
                bin_path = target
                if target.is_dir():
                    if file_name and (target / file_name).exists():
                        bin_path = target / file_name
                    elif (target / "version").exists():
                        bin_path = target
                    elif (target / display_name).exists():
                        bin_path = target / display_name
                installed_ver = probe_binary_version(bin_path)

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
                    "id": f"eget_{repo.replace('/', '_')}",
                    "source": "eget",
                    "name": display_name,
                    "repo": repo,
                    "target": str(target),
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
        print_info(f"[eget] Updating {name} ({repo})...")
        cmd = ["eget"]
        if item.get("prerelease"):
            cmd.append("--pre-release")
        if item.get("available"):
            cmd.extend(["-t", item["available"]])
        cmd.append(repo)

        res = subprocess.run(cmd, env=env)

        # Standalone archive unpacking for kitty
        if repo == "kovidgoyal/kitty":
            kitty_dir = HOME / ".local" / "kitty.app"
            if kitty_dir.is_dir():
                for f in kitty_dir.glob("*.txz"):
                    subprocess.run(["tar", "-xJof", str(f), "-C", str(kitty_dir)], env=env)
                    try:
                        f.unlink()
                    except Exception:
                        pass

        if res.returncode == 0:
            print_success(f"[eget] {name} updated to {item['available']}")
            return True
        print_error(f"[eget] Failed to update {name}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        if not EGET_CONFIG_PATH.is_file():
            return []
        try:
            with open(EGET_CONFIG_PATH, "rb") as f:
                cfg = tomllib.load(f)
        except Exception:
            return []

        items = []
        for repo, opts in cfg.items():
            if repo == "global":
                continue
            target_str = opts.get("target", "")
            if "gh-debs" in target_str:
                continue

            target = Path(os.path.expanduser(target_str))
            disp = get_display_name(repo, opts)
            file_name = opts.get("file")
            bin_path = target
            if target.is_dir():
                if file_name and (target / file_name).exists():
                    bin_path = target / file_name
                elif (target / "version").exists():
                    bin_path = target
                elif (target / disp).exists():
                    bin_path = target / disp

            if target.exists() or bin_path.exists():
                ver = probe_binary_version(bin_path)
                if target.is_dir():
                    total_sz = sum(
                        f.stat().st_size for f in target.rglob("*") if f.is_file() and not f.is_symlink()
                    )
                else:
                    total_sz = target.stat().st_size if target.is_file() else 0

                items.append({
                    "id": f"eget_{repo.replace('/', '_')}",
                    "source": "eget",
                    "name": disp,
                    "repo": repo,
                    "version": ver or "installed",
                    "size_bytes": total_sz,
                    "path": str(target),
                    "homepage": f"https://github.com/{repo}",
                    "desc": f"Standalone application/binary managed by eget ({repo})",
                    "depends": [],
                    "rdepends": []
                })
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        target = Path(item["path"])
        repo = item.get("repo")
        print_info(f"[eget] Removing {name} ({target})...")

        deleted = False
        try:
            if target.is_dir():
                shutil.rmtree(target)
                deleted = True
            elif target.is_file() or target.is_symlink():
                target.unlink()
                deleted = True
        except Exception as e:
            print_error(f"[eget] Failed to delete target {target}: {e}")

        cleanup_desktop_and_symlinks(target, [name, repo] if repo else [name])
        if repo:
            comment_out_eget_entry(repo)

        if deleted or not target.exists():
            print_success(f"[eget] {name} removed and configuration updated")
            return True
        return False
