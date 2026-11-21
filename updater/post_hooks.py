"""
Post-update service and bootstrap hooks for system services and browsers.
"""

import os
import shutil
import subprocess
from pathlib import Path
from updater.config import HOME, IS_LINUX
from updater.ui import print_info, print_success, print_error

def run_post_update_hooks(updated_items: list[tuple[str, str, str]]):
    """
    Execute platform and application specific hooks after updates are applied.
    updated_items: list of (name, source, version) tuples.
    """
    if not updated_items:
        return

    updated_names = {name.lower() for name, _, _ in updated_items}

    # Only Linux has systemd service management and desktop bootstrap hooks
    if not IS_LINUX:
        return

    print()
    print("  " + "─" * 68)
    print("    Executing Post-Update Service Hooks:")
    print("  " + "─" * 68)

    # 1. Ollama Service Hook (Part 1 Bugfix 1)
    if "ollama" in updated_names:
        ollama_bin = HOME / ".local" / "bin" / "ollama"
        if ollama_bin.is_file():
            print_info("Stopping ollama.service and syncing binary via 'install -m 755'...")
            # Stop service first to prevent 'Text file busy' error
            subprocess.run(["sudo", "systemctl", "stop", "ollama.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Use atomic install to ensure binary is replaced cleanly with executable permissions
            install_res = subprocess.run(["sudo", "install", "-m", "755", str(ollama_bin), "/usr/local/bin/ollama"])
            if install_res.returncode == 0:
                subprocess.run(["sudo", "systemctl", "start", "ollama.service"])
                print_success("ollama binary installed to /usr/local/bin and ollama.service restarted")
            else:
                print_error("Failed to install ollama binary to /usr/local/bin")

    # 2. Sunshine Service Hook
    if any("sunshine" in n for n in updated_names):
        print_info("Restarting sunshine.service (user)...")
        subprocess.run(["systemctl", "--user", "restart", "sunshine.service"])
        print_success("sunshine.service restarted")

    # 3. Zen Browser Bootstrap Hook (Preserves Vimium C & Auto Tab Discard)
    zen_bootstrap_dir = HOME / ".config" / "zen-bootstrap"
    zen_target_dirs = [
        HOME / "Downloads" / "zen.linux-x86_64" / "zen",
        HOME / ".local" / "share" / "zen"
    ]
    zen_updated = any("zen" in n for n in updated_names)
    if zen_updated or zen_bootstrap_dir.is_dir():
        print_info("Applying Zen Browser bootstrap configs (Vimium C & Auto Tab Discard protection)...")
        for zdir in zen_target_dirs:
            if zdir.is_dir():
                subprocess.run(f"cp -rf \"{zen_bootstrap_dir}/.\" \"{zdir}/\" 2>/dev/null || true", shell=True)
                print_success(f"Applied bootstrap configs to {zdir}")
