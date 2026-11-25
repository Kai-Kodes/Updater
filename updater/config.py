"""
Configuration, OS detection, and shared helper utilities for updater.
"""

import os
import re
import sys
import shutil
import platform
import subprocess
from pathlib import Path

# Operating System Detection
PLATFORM_SYSTEM = platform.system()
IS_LINUX = PLATFORM_SYSTEM == "Linux"
IS_MACOS = PLATFORM_SYSTEM == "Darwin"
IS_WINDOWS = PLATFORM_SYSTEM == "Windows"

def read_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a key-value dictionary on Linux."""
    data: dict[str, str] = {}
    if not IS_LINUX:
        return data
    for candidate in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
        if candidate.is_file():
            try:
                for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    data[key.strip()] = val.strip().strip('"').strip("'")
                break
            except Exception:
                pass
    return data

OS_RELEASE = read_os_release()
DISTRO_ID = OS_RELEASE.get("ID", "").lower()
DISTRO_ID_LIKE = OS_RELEASE.get("ID_LIKE", "").lower().split()
IS_CACHYOS = IS_LINUX and DISTRO_ID == "cachyos"
IS_ARCH = IS_LINUX and (DISTRO_ID in ("arch", "cachyos") or "arch" in DISTRO_ID_LIKE)
IS_DEBIAN = IS_LINUX and (DISTRO_ID in ("debian", "ubuntu") or "debian" in DISTRO_ID_LIKE)

# Standard Base Directories
HOME = Path.home()

if IS_WINDOWS:
    APPDATA = Path(os.environ.get("APPDATA", str(HOME / "AppData" / "Roaming")))
    LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local")))
    CONFIG_DIR = APPDATA / "updater"
    CACHE_DIR = LOCALAPPDATA / "updater" / "cache"
elif IS_MACOS:
    CONFIG_DIR = HOME / ".config" / "updater"
    CACHE_DIR = HOME / "Library" / "Caches" / "updater"
else: # Linux / BSD
    CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(HOME / ".config"))) / "updater"
    CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", str(HOME / ".cache"))) / "updater"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Eget & Downloads Paths
def resolve_eget_config_path() -> Path:
    """Resolve the eget manifest path, preferring Arch/CachyOS-specific manifests when present."""
    env_cfg = os.environ.get("EGET_CONFIG")
    if env_cfg:
        p = Path(os.path.expanduser(env_cfg))
        if p.is_file():
            return p
    if IS_ARCH:
        for candidate in (
            HOME / ".eget.cachyos.toml",
            HOME / ".eget.arch.toml",
            CONFIG_DIR / "eget.toml",
        ):
            if candidate.is_file():
                return candidate
    return HOME / ".eget.toml"

EGET_CONFIG_PATH = resolve_eget_config_path()
DEB_DIR = HOME / "Downloads" / "gh-debs"

# Vencord / Vesktop Candidates
def get_vencord_search_dirs() -> list[Path]:
    if IS_WINDOWS:
        appdata = Path(os.environ.get("APPDATA", str(HOME / "AppData" / "Roaming")))
        return [
            appdata / "vesktop" / "sessionData" / "vencordFiles",
            appdata / "Vencord" / "dist",
            appdata / "Vencord",
        ]
    elif IS_MACOS:
        app_support = HOME / "Library" / "Application Support"
        return [
            app_support / "vesktop" / "sessionData" / "vencordFiles",
            app_support / "Vencord" / "dist",
            app_support / "Vencord",
        ]
    else: # Linux
        return [
            HOME / ".config" / "vesktop" / "sessionData" / "vencordFiles",
            HOME / ".config" / "Vencord" / "dist",
            HOME / ".config" / "Vencord",
        ]

def get_gh_token() -> str:
    """Retrieve GitHub token to avoid 60/hr API rate limiting."""
    t = os.environ.get("EGET_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not t:
        try:
            t = subprocess.check_output(["gh", "auth", "token"], stderr=subprocess.DEVNULL, text=True).strip()
        except Exception:
            pass
    return t or ""

TOKEN = get_gh_token()
if TOKEN:
    os.environ["EGET_GITHUB_TOKEN"] = TOKEN
    os.environ["GITHUB_TOKEN"] = TOKEN

# Version Parsing and Formatting Helpers
def clean_version(raw: str) -> str:
    """Extract clean semver or date version from command output."""
    if not raw:
        return ""
    low = raw.lower()
    if any(k in low for k in ["unknown flag", "unknown shorthand", "unknown command", "unknown option", "usage:", "invalid option"]):
        return ""
    m = re.search(r'\b(v?\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?)\b', raw)
    if m:
        return m.group(1)
    m = re.search(r'\b(\d{4}\.\d{1,2}\.\d{1,2})\b', raw)
    if m:
        return m.group(1)
    return raw.strip()

def clean_tag_for_github(ver: str) -> str:
    """Strip packaging epochs, revisions, and distro suffixes."""
    if not ver or ver.startswith("hash:") or ver.startswith("mtime:"):
        return ""
    t = re.sub(r'^[0-9]+:', '', ver)
    t = re.sub(r'[-+][a-zA-Z0-9.+%~_-]+$', '', t)
    return t.strip()

def normalize_compare_tag(tag: str) -> str:
    """Normalize version string for comparison (strip leading v, etc.)."""
    t = clean_tag_for_github(tag)
    if t.startswith("v") or t.startswith("V"):
        t = t[1:]
    return t

def parse_ver_tuple(v: str) -> tuple:
    nums = re.findall(r'\d+', v)
    return tuple(int(x) for x in nums) if nums else (0,)

def compact_list_version(v: str) -> str:
    """Compact verbose Debian/distro packaging suffixes for the left-pane list view."""
    if not v:
        return ""
    cv = re.sub(r'~debian\.[0-9]+(~[a-zA-Z0-9]+)?', '', v)
    cv = re.sub(r'([~+]deb[0-9]+u[0-9]+|\+b[0-9]+|~build[0-9]+)', '', cv)
    cv = cv.rstrip("-")
    return cv if cv else v

def format_size(num: int | float) -> str:
    """Format bytes into clean, human-readable units."""
    if not num or num <= 0:
        return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0 or unit == 'TB':
            return f"{num:.1f} {unit}" if unit in ['MB', 'GB', 'TB'] else f"{int(num)} {unit}"
        num /= 1024.0
    return f"{num:.1f} GB"

def sanitize_markdown_preview(text: str) -> str:
    """Clean plain-text/markdown links and remove excessive blank lines."""
    if not text:
        return ""
    # Replace [url](url) with just url
    text = re.sub(r'\[(https?://[^\]\s]+)\]\(\1\)', r'\1', text)
    # Replace [text](url) where text matches url
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)\s]+)\)', lambda m: m.group(2) if m.group(1).strip() == m.group(2).strip() else f"{m.group(1)} ({m.group(2)})", text)
    # Remove excessive blank lines (>2 newlines -> 2 newlines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Strip trailing whitespace on each line to avoid wrap markers
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()

def confirm_action(prompt_text: str) -> bool:
    """Prompt user for confirmation via tty if available, falling back to input()."""
    if not sys.stdin.isatty():
        try:
            line = sys.stdin.readline()
            if line:
                return line.strip().lower() in ("y", "yes")
        except Exception:
            pass
    if not IS_WINDOWS:
        try:
            with open("/dev/tty", "r") as tty_in, open("/dev/tty", "w") as tty_out:
                tty_out.write(prompt_text)
                tty_out.flush()
                ans = tty_in.readline().strip().lower()
                return ans in ("y", "yes")
        except Exception:
            pass
    try:
        ans = input(prompt_text).strip().lower()
        return ans in ("y", "yes")
    except Exception:
        return False
