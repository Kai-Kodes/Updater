"""
Eget GitHub release binary and standalone application provider.
"""

import os
import re
import json
import shutil
import tomllib
import zipfile
import tempfile
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import concurrent.futures
from pathlib import Path
from typing import Any
from updater.config import (
    HOME, EGET_CONFIG_PATH, TOKEN, IS_ARCH,
    clean_version, normalize_compare_tag
)
from updater.providers.base import BaseProvider
from updater.ui import print_info, print_success, print_error

def _is_deb_eget_entry(opts: dict[str, Any]) -> bool:
    """Return True if an eget entry targets a .deb package."""
    target_str = str(opts.get("target", ""))
    if "gh-debs" in target_str or target_str.lower().endswith(".deb"):
        return True
    file_str = str(opts.get("file", ""))
    if file_str.lower().endswith(".deb"):
        return True
    filters = opts.get("asset_filters", [])
    if isinstance(filters, str):
        filters = [filters]
    if isinstance(filters, list):
        for af in filters:
            if isinstance(af, str) and not af.startswith("^") and ".deb" in af.lower():
                return True
    return False

def _is_pacman_owned_entry(opts: dict[str, Any], target: Path, bin_path: Path, display_name: str) -> bool:
    """On Arch/CachyOS, return True if target/binary or its /usr/bin counterpart is owned by pacman."""
    if not IS_ARCH or shutil.which("pacman") is None:
        return False

    ignored_dirs = {
        HOME,
        HOME / ".local",
        HOME / ".local" / "bin",
        HOME / ".local" / "opt",
        HOME / ".local" / "share",
        HOME / "Applications",
    }
    candidates: list[str] = []
    seen: set[str] = set()

    def _add_candidate(p: Path):
        sp = str(p)
        if sp not in seen and p.exists():
            seen.add(sp)
            candidates.append(sp)

    if target not in ignored_dirs:
        _add_candidate(target)
    if bin_path not in ignored_dirs and bin_path.is_file():
        _add_candidate(bin_path)

    cand_names = {
        display_name,
        str(opts.get("file") or ""),
        target.name if not target.is_dir() else "",
        bin_path.name if bin_path.is_file() else "",
    }
    for name in cand_names:
        name = name.strip()
        if name:
            _add_candidate(Path("/usr/bin") / name)

    if not candidates:
        return False

    try:
        res = subprocess.run(
            ["pacman", "-Qo", *candidates],
            capture_output=True,
            text=True,
            timeout=3,
            env={**os.environ, "LC_ALL": "C"},
        )
        return " is owned by " in (res.stdout or "")
    except Exception:
        return False

def _resolve_eget_bin_path(repo: str, target: Path, file_name: str | None, display_name: str) -> Path:
    """Resolve the local binary/app path for an eget manifest entry."""
    if repo == "kovidgoyal/kitty":
        return HOME / ".local" / "kitty.app" / "bin" / "kitty"
    if repo == "zed-industries/zed":
        return HOME / ".local" / "zed.app" / "bin" / "zed"
    if target.is_dir():
        if (target / "resources" / "app.asar").is_file():
            return target
        if (target / "version").exists():
            return target
        if file_name and (target / file_name).exists():
            return target / file_name
        if (target / display_name).exists():
            return target / display_name
    return target


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_gh_hosts_token(hosts_path: Path | None = None) -> str:
    """Extract oauth_token for github.com from ~/.config/gh/hosts.yml if present."""
    hp = hosts_path or (HOME / ".config" / "gh" / "hosts.yml")
    if not hp.is_file():
        return ""
    try:
        in_github = False
        for line in hp.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line[0].isspace():
                in_github = line.strip().startswith("github.com:")
                continue
            if in_github:
                m = re.match(r"^\s*oauth_token:\s*(.+?)\s*$", line)
                if m:
                    tok = m.group(1).strip().strip('"').strip("'")
                    if tok:
                        return tok
    except Exception:
        pass
    return ""


def _resolve_github_token(env: dict[str, str] | None = None) -> str:
    """Resolve GitHub token from env, os.environ, ~/.config/gh/hosts.yml, or `gh auth token`."""
    src_env = env or {}
    tok = (
        src_env.get("EGET_GITHUB_TOKEN")
        or src_env.get("GITHUB_TOKEN")
        or os.environ.get("EGET_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or TOKEN
    )
    if tok:
        return tok.strip()

    tok = _read_gh_hosts_token()
    if tok:
        return tok

    if shutil.which("gh"):
        try:
            tok = subprocess.check_output(
                ["gh", "auth", "token"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            ).strip()
            if tok:
                return tok
        except Exception:
            pass
    return ""


def _build_eget_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Build subprocess environment for `eget` with EGET_CONFIG and GitHub tokens populated."""
    run_env = dict(env) if env is not None else os.environ.copy()
    if EGET_CONFIG_PATH != HOME / ".eget.toml":
        run_env["EGET_CONFIG"] = str(EGET_CONFIG_PATH)

    tok = _resolve_github_token(run_env)
    if tok:
        run_env["EGET_GITHUB_TOKEN"] = tok
        run_env["GITHUB_TOKEN"] = tok
    return run_env


def _fetch_github_release(repo: str, prerelease: bool) -> dict[str, str] | None:
    """Fetch latest GitHub release metadata via API with web-redirect fallback on rate limit."""
    url = (
        f"https://api.github.com/repos/{repo}/releases?per_page=1"
        if prerelease
        else f"https://api.github.com/repos/{repo}/releases/latest"
    )
    base_headers = {"User-Agent": "updater/3.0", "Accept": "application/vnd.github.v3+json"}
    token = _resolve_github_token()

    for use_token in ([True, False] if token else [False]):
        headers = dict(base_headers)
        if use_token and token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.load(resp)
                rel = data[0] if isinstance(data, list) and data else data
                if isinstance(rel, dict) and rel.get("tag_name"):
                    return {
                        "tag_name": rel.get("tag_name", ""),
                        "name": rel.get("name", ""),
                        "body": rel.get("body", ""),
                        "html_url": rel.get("html_url", ""),
                        "published_at": rel.get("published_at", "")[:10],
                    }
        except urllib.error.HTTPError as e:
            if e.code == 401 and use_token:
                continue
            break
        except Exception:
            break

    # Fallback: GitHub web redirect / HTML (not subject to 60/hr API rate limit)
    if not prerelease:
        opener = urllib.request.build_opener(_NoRedirectHandler)
        try:
            req = urllib.request.Request(
                f"https://github.com/{repo}/releases/latest",
                headers={"User-Agent": "updater/3.0"},
            )
            opener.open(req, timeout=5)
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location", "")
            if "/releases/tag/" in loc:
                tag = urllib.parse.unquote(loc.rsplit("/releases/tag/", 1)[-1].split("?")[0].strip("/"))
                if tag:
                    return {
                        "tag_name": tag,
                        "name": tag,
                        "body": f"New release `{tag}` available on GitHub.",
                        "html_url": loc,
                        "published_at": "",
                    }
        except Exception:
            pass
    else:
        try:
            req = urllib.request.Request(
                f"https://github.com/{repo}/releases",
                headers={"User-Agent": "updater/3.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                m = re.search(rf'href="/{re.escape(repo)}/releases/tag/([^"]+)"', html)
                if m:
                    tag = urllib.parse.unquote(m.group(1))
                    return {
                        "tag_name": tag,
                        "name": tag,
                        "body": f"New release `{tag}` available on GitHub.",
                        "html_url": f"https://github.com/{repo}/releases/tag/{tag}",
                        "published_at": "",
                    }
        except Exception:
            pass
    return None

def probe_binary_version(bin_path: Path | str) -> str:
    bp = Path(bin_path)
    if not bp.exists():
        return ""

    if bp.is_dir():
        # 1. Electron app.asar check (e.g. balenaEtcher, youtube-music)
        asar = bp / "resources" / "app.asar"
        if asar.is_file():
            try:
                with open(asar, "rb") as f:
                    all_bytes = f.read()
                    m = re.search(rb'"productName":"balenaEtcher","version":"([^"]+)"', all_bytes)
                    if not m:
                        m = re.search(rb'"name":"balena-etcher".*?"version":"([^"]+)"', all_bytes)
                    if not m:
                        m = re.search(rb'"name":\s*"youtube-music"[^}]{0,250}"version":\s*"([^"]+)"', all_bytes)
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

        # 5. ytm-rs embedded User-Agent version check
        if "ytm-rs" in str(bp).lower():
            ytm_bin = bp / "ytm-rs"
            if ytm_bin.is_file():
                try:
                    m = re.search(rb'ytm-rs/(\d+\.\d+\.\d+)', ytm_bin.read_bytes())
                    if m:
                        return m.group(1).decode("utf-8", errors="ignore").strip()
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

    if "ytm-rs" in str(bp).lower() and bp.is_file():
        try:
            m = re.search(rb'ytm-rs/(\d+\.\d+\.\d+)', bp.read_bytes())
            if m:
                return m.group(1).decode("utf-8", errors="ignore").strip()
        except Exception:
            pass

    if not bp.is_file():
        return ""

    if bp.suffix.lower() == ".jar":
        try:
            with zipfile.ZipFile(bp) as zf:
                for name in zf.namelist():
                    if name.startswith("META-INF/maven/") and name.endswith("/pom.properties"):
                        content = zf.read(name).decode("utf-8", errors="ignore")
                        if bp.stem.lower() in content.lower():
                            m = re.search(r'^version=(.+)$', content, re.M)
                            if m:
                                return m.group(1).strip()
        except Exception:
            pass

    if os.access(bp, os.X_OK):
        for flag in ["--version", "version", "-v", "-V", "-version", "--help"]:
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
        "grapedjuice/ytm-rs": "ytm-rs",
        "th-ch/youtube-music": "youtube-music",
        "lolitemaultes/Gridline": "gridline-app",
        "H-M-H/Weylus": "weylus",
        "storytold/effectcraft": "effectcraft",
        "storytold/figcraft": "figcraft",
        "storytold/filmcraft": "filmcraft",
        "storytold/gridcraft": "gridcraft",
        "storytold/photocraft": "photocraft",
        "storytold/wordcraft": "wordcraft",
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

        candidates: list[tuple[str, str, Path, bool, str]] = []
        for repo, opts in cfg.items():
            if repo == "global" or not isinstance(opts, dict):
                continue
            target_str = opts.get("target", "")
            if IS_ARCH:
                if _is_deb_eget_entry(opts):
                    continue
            elif "gh-debs" in target_str:
                continue # Handled by DebProvider

            target = Path(os.path.expanduser(target_str))
            file_name = opts.get("file")
            prerelease = opts.get("prerelease", False)
            display_name = get_display_name(repo, opts)
            bin_path = _resolve_eget_bin_path(repo, target, file_name, display_name)

            if _is_pacman_owned_entry(opts, target, bin_path, display_name):
                continue

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
            else:
                installed_ver = probe_binary_version(bin_path)

            if installed_ver:
                candidates.append((repo, display_name, target, prerelease, installed_ver))

        def _check_one(entry: tuple[str, str, Path, bool, str]) -> dict[str, Any] | None:
            repo, display_name, target, prerelease, installed_ver = entry
            rel = _fetch_github_release(repo, prerelease)
            if not rel:
                return None
            avail_tag = rel.get("tag_name", "")
            clean_i = normalize_compare_tag(installed_ver)
            clean_a = normalize_compare_tag(avail_tag)
            if clean_i and clean_a and clean_i != clean_a:
                return {
                    "id": f"eget_{repo.replace('/', '_')}",
                    "source": "eget",
                    "name": display_name,
                    "repo": repo,
                    "target": str(target),
                    "prerelease": prerelease,
                    "installed": installed_ver,
                    "available": avail_tag,
                    "title": rel.get("name") or avail_tag,
                    "body": rel.get("body") or "No release notes provided.",
                    "url": rel.get("html_url", ""),
                    "published": rel.get("published_at", ""),
                }
            return None

        updates = []
        if candidates:
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                for res in executor.map(_check_one, candidates):
                    if res:
                        updates.append(res)
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

        run_env = _build_eget_env(env)

        target = Path(item.get("target", ""))
        if target and not target.is_dir() and target.parent.exists() and not os.access(target.parent, os.W_OK):
            with tempfile.TemporaryDirectory(prefix="eget-stage-") as tmpdir:
                staged = Path(tmpdir) / target.name
                stage_cmd = [*cmd[:-1], "--to", str(staged), repo]
                res = subprocess.run(stage_cmd, env=run_env)
                if res.returncode == 0 and staged.is_file():
                    res = subprocess.run(["sudo", "install", "-m", "755", str(staged), str(target)], env=run_env)
        else:
            res = subprocess.run(cmd, env=run_env)

        # Standalone archive unpacking for kitty
        if repo == "kovidgoyal/kitty":
            kitty_dir = HOME / ".local" / "kitty.app"
            if kitty_dir.is_dir():
                for f in kitty_dir.glob("*.txz"):
                    subprocess.run(["tar", "-xJof", str(f), "-C", str(kitty_dir)], env=run_env)
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
            if repo == "global" or not isinstance(opts, dict):
                continue
            target_str = opts.get("target", "")
            if IS_ARCH:
                if _is_deb_eget_entry(opts):
                    continue
            elif "gh-debs" in target_str:
                continue

            target = Path(os.path.expanduser(target_str))
            disp = get_display_name(repo, opts)
            file_name = opts.get("file")
            bin_path = _resolve_eget_bin_path(repo, target, file_name, disp)

            if _is_pacman_owned_entry(opts, target, bin_path, disp):
                continue

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
