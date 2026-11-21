#!/usr/bin/env bash
# install.sh — Installer for updater on Linux and macOS
set -euo pipefail

ICON_UPDATE="󰚰"
ICON_SUCCESS=""
ICON_WARN=""
ICON_ERROR=""
ICON_PKG="󰏖"

printf "\n  \033[1;36m%s  Installing updater (Cross-Platform Application & Package Manager)\033[0m\n\n" "$ICON_UPDATE"

# 1. Check Python version
if ! command -v python3 >/dev/null 2>&1; then
    printf "  \033[31m%s\033[0m  Python 3 is required but not installed.\n" "$ICON_ERROR"
    exit 1
fi

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)

if (( PYTHON_MAJOR < 3 || (PYTHON_MAJOR == 3 && PYTHON_MINOR < 11) )); then
    printf "  \033[33m%s\033[0m  Warning: Python >= 3.11 is recommended (found Python %s).\n" "$ICON_WARN" "$PYTHON_VER"
else
    printf "  \033[32m%s\033[0m  Found Python %s\n" "$ICON_SUCCESS" "$PYTHON_VER"
fi

# 2. Check dependencies
if command -v fzf >/dev/null 2>&1; then
    printf "  \033[32m%s\033[0m  fzf detected (interactive TUI enabled)\n" "$ICON_SUCCESS"
else
    printf "  \033[33m%s\033[0m  fzf not found (recommended: install fzf for interactive updates)\n" "$ICON_WARN"
fi

if command -v bat >/dev/null 2>&1 || command -v batcat >/dev/null 2>&1; then
    printf "  \033[32m%s\033[0m  bat detected (syntax-highlighted preview rendering enabled)\n" "$ICON_SUCCESS"
else
    printf "  \033[33m%s\033[0m  bat not found (recommended: install bat for enhanced preview rendering)\n" "$ICON_WARN"
fi

if command -v gh >/dev/null 2>&1; then
    printf "  \033[32m%s\033[0m  gh detected (authenticated GitHub API rate limiting enabled)\n" "$ICON_SUCCESS"
else
    printf "  \033[33m%s\033[0m  gh not found (consider setting GITHUB_TOKEN to avoid 60/hr rate limit)\n" "$ICON_WARN"
fi

# 3. Installation Directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"

LAUNCHER="${BIN_DIR}/updater"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# Launcher for updater modular CLI
export PYTHONPATH="${SCRIPT_DIR}:\${PYTHONPATH:-}"
exec python3 -m updater.cli "\$@"
EOF

chmod +x "$LAUNCHER"
printf "\n  \033[32m%s\033[0m  Created launcher: \033[1m%s\033[0m\n" "$ICON_SUCCESS" "$LAUNCHER"

# 4. Check PATH
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        printf "  \033[33m%s\033[0m  Notice: %s is not in your \$PATH. Add it to ~/.bashrc or ~/.zshrc:\n" "$ICON_WARN" "$BIN_DIR"
        printf "     export PATH=\"%s:\$PATH\"\n" "$BIN_DIR"
        ;;
esac

# 5. Shell alias reminder
printf "  \033[32m%s\033[0m  Installation complete! You can run '\033[32mupdater\033[0m' or '\033[32mupdater -all\033[0m'.\n" "$ICON_SUCCESS"
printf "     (Optional) Add alias to ~/.bashrc: \033[36malias ghup='updater'\033[0m\n\n"
