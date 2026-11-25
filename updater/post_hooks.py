"""
Post-update service and bootstrap hooks for system services and browsers.
"""

import os
import shutil
import subprocess
from pathlib import Path
from updater.config import HOME, IS_LINUX, IS_ARCH
from updater.ui import print_info, print_success, print_error, print_warn

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

    # 1. Ollama Service Hook
    if "ollama" in updated_names:
        ollama_bin = HOME / ".local" / "bin" / "ollama"
        if not IS_ARCH and ollama_bin.is_file():
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
        elif shutil.which("systemctl"):
            is_active = subprocess.run(
                ["systemctl", "is-active", "--quiet", "ollama.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ).returncode == 0
            if is_active:
                print_info("Restarting ollama.service...")
                res = subprocess.run(["sudo", "systemctl", "restart", "ollama.service"])
                if res.returncode == 0:
                    print_success("ollama.service restarted")
                else:
                    print_error("Failed to restart ollama.service")
            else:
                print_info("ollama updated (ollama.service is inactive; skipping restart)")

    # 2. Sunshine Service Hook
    if any("sunshine" in n for n in updated_names) and shutil.which("systemctl"):
        is_active = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "sunshine.service"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode == 0
        if is_active:
            print_info("Restarting sunshine.service (user)...")
            res = subprocess.run(["systemctl", "--user", "restart", "sunshine.service"])
            if res.returncode == 0:
                print_success("sunshine.service restarted")
            else:
                print_warn("Failed to restart sunshine.service")
        else:
            print_info("sunshine updated (sunshine.service is inactive; skipping restart)")

    # 3. Zen Browser Bootstrap Hook (Preserves Vimium C & Auto Tab Discard)
    zen_bootstrap_dir = HOME / ".config" / "zen-bootstrap"
    zen_target_dirs = [
        HOME / "Downloads" / "zen.linux-x86_64" / "zen",
        HOME / ".local" / "share" / "zen"
    ]
    if zen_bootstrap_dir.is_dir():
        print_info("Applying Zen Browser bootstrap configs (Vimium C & Auto Tab Discard protection)...")
        for zdir in zen_target_dirs:
            if zdir.is_dir():
                subprocess.run(f"cp -rf \"{zen_bootstrap_dir}/.\" \"{zdir}/\" 2>/dev/null || true", shell=True)
                print_success(f"Applied bootstrap configs to {zdir}")
