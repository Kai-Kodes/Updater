"""
CLI entry point for updater — unified cross-platform package & application manager.
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path

# Ensure updater root is on sys.path
UPDATER_ROOT = Path(__file__).resolve().parent.parent
if str(UPDATER_ROOT) not in sys.path:
    sys.path.insert(0, str(UPDATER_ROOT))

# Ensure child processes inherit this PYTHONPATH
os.environ["PYTHONPATH"] = f"{UPDATER_ROOT}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"

from updater.config import TOKEN, IS_WINDOWS, IS_MACOS, IS_LINUX
from updater.core import (
    scan_updates, apply_updates, scan_uninstall, apply_uninstall, preview_item
)
from updater.ui import (
    ICON_UPDATE, ICON_SUCCESS, ICON_ERROR, ICON_WARN, ICON_SYNC,
    ICON_PKG, ICON_CHANGELOG, ICON_TRASH, ICON_AUDIT,
    print_header, print_success, print_error, print_warn, print_info,
    run_fzf_interactive
)

HELP_TEXT = f"""
  \033[1;36m{ICON_UPDATE}  updater — Fast, Modular, Cross-Platform Application & Package Manager\033[0m

  \033[1mUsage:\033[0m
    \033[32mupdater\033[0m                      Interactive update picker with live changelog previews (Default)
    \033[32mupdater -all, --all, -y\033[0m      Unattended update all available packages and applications
    \033[32mupdater -rem, --rem, -r\033[0m      Interactive multi-source uninstaller
    \033[32mupdater -c, --check\033[0m          Check for available updates without applying
    \033[32mupdater preview <dir> <id>\033[0m   Render changelog/dependency preview for an item
    \033[32mupdater -h, --help\033[0m           Show this help message

  \033[1mSupported Providers:\033[0m
    • \033[35mAll Platforms:\033[0m   eget, git repos, vencord, npm, bun, cargo, pipx, uv, gh extensions, standalone apps
    • \033[34mLinux:\033[0m           pacman/paru (CachyOS/Arch), apt (dpkg rdepends), deb, flatpak, snap, systemd service & browser hooks
    • \033[33mmacOS:\033[0m           Homebrew (formulae + casks), Mac App Store (mas)
    • \033[36mWindows:\033[0m         winget, scoop, chocolatey

  \033[1mAliases:\033[0m
    \033[33mghup\033[0m                         Drop-in alias for 'updater'
"""

def print_help():
    print(HELP_TEXT)

def run_check_mode(git_repos: list[str] | None = None):
    """Scan and list all available updates in tabular format without installing."""
    with tempfile.TemporaryDirectory(prefix="updater-check-") as tmpdir:
        workdir = Path(tmpdir)
        updates = scan_updates(workdir, git_repos)
        if not updates:
            print("\n  ────────────────────────────────────────────────────────────────────")
            print(f"  \033[32m{ICON_SUCCESS}\033[0m  All applications, repositories, and packages are up-to-date!")
            print("  ────────────────────────────────────────────────────────────────────\n")
            return 0

        print(f"\n  \033[1;36m{ICON_UPDATE}\033[0m  {len(updates)} update(s) available across audited sources:\n")
        items_tsv = workdir / "items.tsv"
        if items_tsv.is_file():
            with open(items_tsv, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) >= 2:
                        print(f"     {parts[1]}")
            print()
        return 0

def run_unattended_mode(git_repos: list[str] | None = None):
    """Scan and apply all available updates non-interactively."""
    with tempfile.TemporaryDirectory(prefix="updater-all-") as tmpdir:
        workdir = Path(tmpdir)
        updates = scan_updates(workdir, git_repos)
        if not updates:
            print("\n  ────────────────────────────────────────────────────────────────────")
            print(f"  \033[32m{ICON_SUCCESS}\033[0m  All applications, repositories, and packages are up-to-date!")
            print("  ────────────────────────────────────────────────────────────────────\n")
            return 0

        print(f"  \033[1;36m{ICON_UPDATE}\033[0m  Unattended mode (-all): Applying all {len(updates)} available update(s)...")
        apply_updates(workdir, None)
        return 0

def run_interactive_update_mode(git_repos: list[str] | None = None):
    """Scan updates, open fzf picker with live bat changelogs, apply selection."""
    with tempfile.TemporaryDirectory(prefix="updater-") as tmpdir:
        workdir = Path(tmpdir)
        updates = scan_updates(workdir, git_repos)
        if not updates:
            print("\n  ────────────────────────────────────────────────────────────────────")
            print(f"  \033[32m{ICON_SUCCESS}\033[0m  All applications, repositories, and packages are up-to-date!")
            print("  ────────────────────────────────────────────────────────────────────\n")
            return 0

        items_tsv = workdir / "items.tsv"
        count = len(updates)

        if not shutil.which("fzf"):
            print_warn(f"fzf is not installed. Applying all {count} available updates...")
            apply_updates(workdir, None)
            return 0

        print(f"  \033[1;36m{ICON_UPDATE}\033[0m  Launching interactive updater ({count} update(s) available)...")

        preview_cmd = f'"{sys.executable}" -m updater.cli preview "{workdir}" {{1}}'
        header = "Tab: Toggle | Ctrl-A: Select all | Shift/Alt-J/K: Scroll preview | Enter: Apply | Esc: Abort"
        prompt = f"{ICON_UPDATE} Select updates > "
        marker = f"{ICON_SUCCESS} "

        selected_ids = run_fzf_interactive(items_tsv, preview_cmd, prompt, marker, header)

        if not selected_ids:
            print(f"\n  \033[33m{ICON_WARN}\033[0m  Update cancelled. No changes were made.\n")
            return 0

        apply_updates(workdir, selected_ids)
        return 0

def run_uninstaller_mode(git_repos: list[str] | None = None):
    """Scan installed apps across all providers, open fzf picker, confirm and remove."""
    with tempfile.TemporaryDirectory(prefix="updater-uninstall-") as tmpdir:
        workdir = Path(tmpdir)
        items = scan_uninstall(workdir, git_repos)
        if not items:
            print("\n  ────────────────────────────────────────────────────────────────────")
            print(f"  \033[33m{ICON_WARN}\033[0m  No installed packages or applications found to uninstall.")
            print("  ────────────────────────────────────────────────────────────────────\n")
            return 0

        items_tsv = workdir / "items_uninstall.tsv"
        count = len(items)

        if not shutil.which("fzf"):
            print_error("fzf is required for interactive uninstaller. Please install fzf.")
            return 1

        print(f"  \033[1;31m{ICON_TRASH}\033[0m  Launching interactive uninstaller ({count} installed item(s))...")

        preview_cmd = f'"{sys.executable}" -m updater.cli preview "{workdir}" {{1}}'
        header = "Tab: Toggle | Ctrl-A: Select all | Shift/Alt-J/K: Scroll preview | Enter: Remove selected | Esc: Abort"
        prompt = f"{ICON_TRASH} Select to remove > "
        marker = f"{ICON_ERROR} "

        selected_ids = run_fzf_interactive(items_tsv, preview_cmd, prompt, marker, header)

        if not selected_ids:
            print(f"\n  \033[33m{ICON_WARN}\033[0m  Uninstallation cancelled. No changes were made.\n")
            return 0

        apply_uninstall(workdir, selected_ids)
        return 0

def handle_preview_subcommand(args: list[str]):
    """Handle 'preview <workdir> <item_id>' invoked by fzf preview."""
    if len(args) < 2:
        return
    workdir = Path(args[0])
    item_id = args[1].strip("'\"")
    preview_item(workdir, item_id)

def main():
    args = sys.argv[1:]

    # Parse optional --git-repos arg
    git_repos = None
    if "--git-repos" in args:
        idx = args.index("--git-repos")
        git_repos = args[idx + 1:]
        args = args[:idx]

    if not args:
        # Default mode: interactive updater
        sys.exit(run_interactive_update_mode(git_repos))

    cmd = args[0].lower()

    if cmd in ("-h", "--help", "help"):
        print_help()
        sys.exit(0)

    elif cmd in ("-c", "--check", "check"):
        # If second arg is a workdir (legacy wrapper compatibility)
        if len(args) >= 2 and Path(args[1]).is_dir():
            workdir = Path(args[1])
            updates = scan_updates(workdir, git_repos)
            if not updates:
                print(f"\n  \033[32m{ICON_SUCCESS}\033[0m  All applications and repositories are up-to-date!\n")
            else:
                print(f"\n  \033[1;36m{ICON_UPDATE}\033[0m  {len(updates)} update(s) available across audited sources.\n")
                tsv = workdir / "items.tsv"
                if tsv.is_file():
                    with open(tsv, "r", encoding="utf-8") as f:
                        for l in f:
                            p = l.strip().split("\t")
                            if len(p) >= 2:
                                print(f"     {p[1]}")
                    print()
            sys.exit(0)
        else:
            sys.exit(run_check_mode(git_repos))

    elif cmd in ("-all", "--all", "-y"):
        sys.exit(run_unattended_mode(git_repos))

    elif cmd in ("-rem", "--rem", "-r", "--remove", "uninstall"):
        sys.exit(run_uninstaller_mode(git_repos))

    elif cmd == "preview":
        handle_preview_subcommand(args[1:])
        sys.exit(0)

    # Legacy subcommands compatibility for existing wrappers
    elif cmd == "scan" and len(args) >= 2:
        workdir = Path(args[1])
        updates = scan_updates(workdir, git_repos)
        sys.exit(0 if len(updates) > 0 else 2)

    elif cmd == "apply" and len(args) >= 2:
        workdir = Path(args[1])
        selected_file = workdir / "selected.tsv"
        selected_ids = None
        if selected_file.is_file():
            with open(selected_file, "r", encoding="utf-8") as f:
                selected_ids = [line.strip().split("\t")[0] for line in f if line.strip()]
        apply_updates(workdir, selected_ids)
        sys.exit(0)

    elif cmd == "scan-uninstall" and len(args) >= 2:
        workdir = Path(args[1])
        items = scan_uninstall(workdir, git_repos)
        sys.exit(0 if len(items) > 0 else 2)

    elif cmd == "apply-uninstall" and len(args) >= 2:
        workdir = Path(args[1])
        selected_file = workdir / "selected_uninstall.tsv"
        selected_ids = []
        if selected_file.is_file():
            with open(selected_file, "r", encoding="utf-8") as f:
                selected_ids = [line.strip().split("\t")[0] for line in f if line.strip()]
        apply_uninstall(workdir, selected_ids)
        sys.exit(0)

    else:
        print_error(f"Unknown argument or command: '{args[0]}'")
        print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
