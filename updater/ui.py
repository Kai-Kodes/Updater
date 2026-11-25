"""
UI components, terminal formatting, Nerd Font icons, and cross-platform fzf runner.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from updater.config import IS_WINDOWS

# Nerd Font Glyphs
ICON_PKG = "󰏖"
ICON_CHANGELOG = "󰜘"
ICON_UPDATE = "󰚰"
ICON_SUCCESS = ""
ICON_ERROR = ""
ICON_WARN = ""
ICON_DOWNLOAD = ""
ICON_SYNC = ""
ICON_GEAR = ""
ICON_GITHUB = ""
ICON_TRASH = ""
ICON_AUDIT = "󰁯"
ICON_DESC = "󰋽"
ICON_DEP = "󱠇"

# Enable VT100 colors on Windows if possible
if IS_WINDOWS:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

def print_header(title: str):
    print(f"\n  \033[1;36m{ICON_UPDATE}  {title}\033[0m\n")

def print_success(msg: str):
    print(f"     \033[32m{ICON_SUCCESS}\033[0m  {msg}")

def print_error(msg: str):
    print(f"     \033[31m{ICON_ERROR}\033[0m  {msg}")

def print_warn(msg: str):
    print(f"     \033[33m{ICON_WARN}\033[0m  {msg}")

def print_info(msg: str):
    print(f"     \033[34m{ICON_SYNC}\033[0m  {msg}")

def render_preview_file(pfile: str | Path):
    """Render preview markdown file with bat if present, or stdout."""
    p = Path(pfile)
    if not p.exists():
        print(f"\033[33m{ICON_WARN} No preview available for this item.\033[0m")
        return

    cols = shutil.get_terminal_size((80, 24)).columns
    bat_bin = shutil.which("bat") or shutil.which("batcat")
    if bat_bin:
        try:
            subprocess.run([
                bat_bin,
                "--language=markdown",
                "--style=plain",
                "--color=always",
                "--wrap=character",
                f"--terminal-width={cols}",
                str(p)
            ])
            return
        except Exception:
            pass

    # Fallback to direct output
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            print(f.read())
    except Exception as e:
        print(f"Error reading preview: {e}")

def run_fzf_interactive(items_tsv: Path, preview_cmd: str, prompt: str, marker: str, header: str) -> list[str]:
    """Launch fzf multi-select and return list of selected item IDs."""
    fzf_bin = shutil.which("fzf")
    if not fzf_bin:
        return []

    fzf_args = [
        fzf_bin,
        "--multi",
        "--with-nth=2..",
        "--delimiter=\t",
        f"--preview={preview_cmd}",
        "--preview-window=right:55%:wrap:border-rounded",
        "--scroll-off=3",
        f"--header={header}",
        "--header-first",
        f"--prompt={prompt}",
        "--pointer=❯",
        f"--marker={marker}",
        "--bind=tab:toggle+down,shift-tab:toggle+up,ctrl-a:select-all,ctrl-x:deselect-all,shift-up:preview-up,shift-down:preview-down,ctrl-u:preview-half-page-up,ctrl-d:preview-half-page-down,alt-k:preview-up,alt-j:preview-down"
    ]

    try:
        with open(items_tsv, "r", encoding="utf-8") as stdin_f:
            res = subprocess.run(fzf_args, stdin=stdin_f, stdout=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout.strip():
                selected_ids = []
                for line in res.stdout.splitlines():
                    parts = line.strip().split("\t")
                    if parts and parts[0]:
                        selected_ids.append(parts[0])
                return selected_ids
    except Exception as e:
        sys.stderr.write(f"fzf error: {e}\n")

    return []
