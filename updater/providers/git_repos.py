"""
Git repository discovery, concurrent remote checking, and autostash-rebase updates.
"""

import os
import re
import shutil
import urllib.request
import json
import subprocess
import concurrent.futures
from pathlib import Path
from typing import Any
from updater.config import (
    HOME, IS_WINDOWS, IS_MACOS, TOKEN,
    confirm_action
)
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error, print_warn

def discover_git_repos() -> list[str]:
    """Auto-discover git repositories across user application and development directories."""
    repos = []
    seen = set()

    search_dirs = [
        (HOME / "Applications", 2),
        (HOME / ".local" / "opt", 2),
        (HOME / "Projects", 2),
        (HOME / "Developer", 2),
        (HOME / "src", 2),
    ]

    if IS_WINDOWS:
        search_dirs.extend([
            (HOME / "source" / "repos", 2),
            (HOME / "Desktop", 2),
        ])

    for sdir, max_d in search_dirs:
        if not sdir.is_dir():
            continue
        base_depth = len(sdir.parts)
        for root, dirs, files in os.walk(str(sdir)):
            cur_p = Path(root)
            depth = len(cur_p.parts) - base_depth
            if depth > max_d:
                dirs.clear()
                continue
            if ".git" in dirs and (cur_p / ".git").is_dir():
                rp = str(cur_p.resolve())
                if rp not in seen:
                    seen.add(rp)
                    repos.append(rp)
                dirs.clear()

    # Scan visible top-level user directories in ~ (depth 1 and 2)
    ignored_home_dirs = {
        "Downloads", "Music", "Pictures", "Videos", "Documents",
        "Templates", "Public", "Desktop", "AppData", "Library", "Local Settings"
    }
    try:
        for entry in HOME.iterdir():
            if entry.name.startswith(".") or entry.name in ignored_home_dirs or not entry.is_dir():
                continue
            if (entry / ".git").is_dir():
                rp = str(entry.resolve())
                if rp not in seen:
                    seen.add(rp)
                    repos.append(rp)
            else:
                try:
                    for sub in entry.iterdir():
                        if sub.name.startswith(".") or not sub.is_dir():
                            continue
                        if (sub / ".git").is_dir():
                            rp = str(sub.resolve())
                            if rp not in seen:
                                seen.add(rp)
                                repos.append(rp)
                except Exception:
                    pass
    except Exception:
        pass

    return sorted(repos)

def check_one_git(rpath: str, headers: dict) -> dict[str, Any] | None:
    p = Path(rpath)
    if not (p / ".git").is_dir():
        return None
    try:
        local_full = subprocess.check_output(
            ["git", "-C", rpath, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, text=True, timeout=3
        ).strip()
        rem_out = subprocess.check_output(
            ["git", "-C", rpath, "ls-remote", "origin", "HEAD"],
            stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip().split()
        if not rem_out:
            return None
        remote_full = rem_out[0].strip()
        if local_full != remote_full:
            local_c = local_full[:7]
            remote_c = remote_full[:7]
            remote_url = subprocess.check_output(
                ["git", "-C", rpath, "config", "--get", "remote.origin.url"],
                stderr=subprocess.DEVNULL, text=True, timeout=2
            ).strip()
            m = re.search(r'github\.com[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(\.git)?$', remote_url)
            gh_repo = m.group(1) if m else None
            name = p.name

            body_lines = []
            if gh_repo:
                try:
                    req = urllib.request.Request(f"https://api.github.com/repos/{gh_repo}/commits?per_page=10", headers=headers)
                    with urllib.request.urlopen(req, timeout=4) as resp:
                        commits = json.load(resp)
                        for c in commits:
                            sha = c["sha"][:7]
                            msg = c["commit"]["message"].splitlines()[0]
                            body_lines.append(f"• `{sha}` - {msg}")
                            if sha == local_c:
                                break
                except Exception:
                    pass
            if not body_lines:
                try:
                    log_out = subprocess.check_output(
                        ["git", "-C", rpath, "log", "--oneline", "--no-merges", "-n", "10", "origin/HEAD"],
                        stderr=subprocess.DEVNULL, text=True, timeout=2
                    )
                    body_lines = [f"• {l}" for l in log_out.splitlines()]
                except Exception:
                    pass

            body = "\n".join(body_lines) if body_lines else "New commits available on origin/HEAD."
            return {
                "id": f"git_{name}",
                "source": "git",
                "name": name,
                "repo": gh_repo,
                "path": rpath,
                "installed": local_c,
                "available": remote_c,
                "title": f"Git Pull ({local_c}..{remote_c})",
                "body": body,
                "url": f"https://github.com/{gh_repo}" if gh_repo else ""
            }
    except Exception:
        pass
    return None

class GitProvider(BaseProvider):
    name = "git"
    source_label = "git"
    priority = 20

    def __init__(self, repos: list[str] | None = None):
        self.repos = repos

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("git") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        target_repos = self.repos if self.repos else discover_git_repos()
        headers = {"User-Agent": "updater/3.0"}
        if TOKEN:
            headers["Authorization"] = f"Bearer {TOKEN}"

        updates = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(check_one_git, rp, headers) for rp in target_repos]
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                if res:
                    updates.append(res)
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        rpath = item["path"]
        name = item["name"]
        print_info(f"[git] Pulling {name} ({rpath})...")

        # 1. First attempt: fast-forward only
        res = subprocess.run(["git", "-C", rpath, "pull", "--ff-only"], env=env)
        if res.returncode == 0:
            print_success(f"[git] {name} updated to {item['available']}")
            return True

        # 2. Second attempt (Part 1 Bugfix 3): Diverged local commits -> rebase with autostash
        print_warn(f"[git] Fast-forward failed for {name}. Attempting 'git pull --rebase --autostash'...")
        rebase_res = subprocess.run(["git", "-C", rpath, "pull", "--rebase", "--autostash"], env=env)
        if rebase_res.returncode == 0:
            print_success(f"[git] {name} rebased cleanly to {item['available']}")
            return True

        # 3. Clean abort on conflicts
        print_error(f"[git] Rebase conflict encountered in {name}. Aborting rebase to preserve local state...")
        subprocess.run(["git", "-C", rpath, "rebase", "--abort"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        target_repos = self.repos if self.repos else discover_git_repos()
        items = []
        for rpath in target_repos:
            p = Path(rpath)
            if not (p / ".git").is_dir():
                continue
            name = p.name
            try:
                commit = subprocess.check_output(
                    ["git", "-C", rpath, "rev-parse", "--short", "HEAD"],
                    stderr=subprocess.DEVNULL, text=True
                ).strip()
                rurl = subprocess.check_output(
                    ["git", "-C", rpath, "config", "--get", "remote.origin.url"],
                    stderr=subprocess.DEVNULL, text=True
                ).strip()
            except Exception:
                commit = "HEAD"
                rurl = ""

            total_sz = sum(
                f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink()
            )

            items.append({
                "id": f"git_{name}",
                "source": "git",
                "name": name,
                "version": commit,
                "size_bytes": total_sz,
                "path": rpath,
                "homepage": rurl,
                "desc": f"Local git repository at {rpath}",
                "depends": [],
                "rdepends": []
            })
        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        name = item["name"]
        rpath = item["path"]
        print_info(f"[git] Checking {name} ({rpath})...")

        dirty = False
        try:
            diff_res = subprocess.run(["git", "-C", rpath, "status", "--porcelain"], capture_output=True, text=True)
            if diff_res.stdout.strip():
                dirty = True
        except Exception:
            pass

        proceed = True
        if dirty:
            proceed = confirm_action(f"     ⚠️  Repository '{name}' has uncommitted changes! Remove anyway? [y/N]: ")

        if proceed:
            try:
                shutil.rmtree(rpath)
                print_success(f"[git] {name} repository removed")
                return True
            except Exception as e:
                print_error(f"[git] Failed to remove {rpath}: {e}")
                return False
        else:
            print_warn(f"[git] Preserved {name} (uncommitted changes)")
            return False
