# 󰚰 updater

Fast, modular, cross-platform CLI application & package manager for **Linux**, **macOS**, and **Windows**.

`updater` audits your installed tools and applications across diverse package managers and download sources, discovers available upstream updates concurrently, renders clean changelogs and release notes with syntax highlighting, and provides interactive (`fzf`) and unattended (`-all`) upgrade workflows alongside a safe interactive uninstaller (`-rem`).

---

## 󰏖 Supported Package Providers

| Provider | Platform | Detection Method | Update Method | Uninstaller Support |
| :--- | :--- | :--- | :--- | :--- |
| **`[eget]`** | All | `~/.eget.toml` manifest & binary hash/version probes | Concurrent `eget` binary downloads |  Yes (Deletes tracked binary/app) |
| **`[git]`** | All | Automated repo discovery (`~/.config`, `~/.local`, `~/Applications`, `~/Projects`, `~/src`, `~/.agents`) | `git pull --ff-only` with automated `--rebase --autostash` fallback |  Yes (Deletes repository clone) |
| **`[vencord]`** | All | Linux, macOS, & Windows Vencord/Vesktop install directories | Atomic direct GitHub asset download & sha verify |  Yes (Deletes bundle) |
| **`[npm]`** | All | `npm list -g --json` | `npm update -g <pkg>` |  Yes (`npm uninstall -g`) |
| **`[bun]`** | All | `bun pm ls -g --json` | `bun update -g <pkg>` |  Yes (`bun remove -g`) |
| **`[cargo]`** | All | `~/.cargo/.crates2.json` queried via Crates.io API | `cargo install <pkg>` |  Yes (`cargo uninstall`) |
| **`[pipx]`** | All | `pipx list --json` queried via PyPI API | `pipx upgrade <pkg>` |  Yes (`pipx uninstall`) |
| **`[uv]`** | All | `uv tool list` queried via PyPI API | `uv tool upgrade <pkg>` |  Yes (`uv tool uninstall`) |
| **`[gh-ext]`** | All | `gh extension list` queried via GitHub Releases API | `gh extension upgrade <ext>` |  Yes (`gh extension remove`) |
| **`[standalone]`** | All | Discovers untracked apps in `~/.local/opt`, `~/.local/share`, `/opt` | Manual/Upstream |  Yes (Interactive purge with size calculation) |
| **`[apt]`** | Linux | `/var/lib/dpkg/status` reverse-dependency parser & `apt list --upgradable` | `sudo apt-get install --only-upgrade` |  Yes (`sudo apt-get purge`) with reverse dependency safety warning |
| **`[deb]`** | Linux | Staged GitHub `.deb` packages in `~/Downloads/gh-debs` | `sudo dpkg -i <deb>` / `apt-get install` |  Yes (`sudo apt-get purge`) |
| **`[flatpak]`** | Linux | `flatpak remote-ls --updates` | `flatpak update -y <app>` |  Yes (`flatpak uninstall -y`) |
| **`[snap]`** | Linux | `snap refresh --list` | `sudo snap refresh <app>` |  Yes (`sudo snap remove`) |
| **`[brew]`** | macOS | `brew outdated --json=v2` (Formulae + Casks) | `brew upgrade <formula/cask>` |  Yes (`brew uninstall`) |
| **`[mas]`** | macOS | Mac App Store via `mas outdated` | `mas upgrade <id>` | N/A |
| **`[winget]`** | Windows | `winget upgrade` JSON/table parser | `winget upgrade --id <id> --exact` |  Yes (`winget uninstall --id`) |
| **`[scoop]`** | Windows | `scoop status` | `scoop update <app>` |  Yes (`scoop uninstall`) |
| **`[choco]`** | Windows | `choco outdated` | `choco upgrade <pkg> -y` |  Yes (`choco uninstall -y`) |

---

## 🚀 Key Bug Fixes & Reliability Guarantees

1. **Ollama Service `Text file busy` Fix (Linux):**
   - Automatically executes `sudo systemctl stop ollama.service` *prior* to replacing `/usr/local/bin/ollama`.
   - Uses `sudo install -m 755` for atomic binary replacement and executable permission assignment, then restarts `ollama.service`.
2. **AyuGram Non-Interactive Filter:**
   - Respects `asset_filters = ["full.tar.gz"]` in `~/.eget.toml` so `eget` never prompts interactively during unattended updates.
3. **Diverged Git Repo Handling:**
   - Attempts fast-forward pull (`git pull --ff-only`).
   - If local commits have diverged, automatically falls back to `git pull --rebase --autostash`.
   - If merge conflicts occur, cleanly runs `git rebase --abort` and warns the user without corrupting the working tree.
4. **Shell Quote Immunity:**
   - Preview generation uses `updater preview <workdir> {1}` instead of shell parameter interpolation, completely eliminating quoting bugs across Bash, Zsh, Fish, and PowerShell.
5. **Reverse Dependency Safety Gate (Linux `apt` / `deb`):**
   - Fast native parsing of `/var/lib/dpkg/status` checks whether any other installed packages depend on or recommend an application before uninstallation.
   - Distinctly highlights safe packages vs. packages with dependents in the preview window.

---

## 🛠️ Installation

### Standalone Python Tool (`uv` / `pipx`)
You can install and run `updater` directly in an isolated environment without cloning:
```bash
# Using uv (Recommended)
uv tool install git+https://github.com/Kai-Kodes/Updater.git

# Using pipx
pipx install git+https://github.com/Kai-Kodes/Updater.git
```

### From Source (Linux & macOS)
```bash
git clone https://github.com/Kai-Kodes/Updater.git ~/updater
cd ~/updater
./install.sh
```
Add to your `~/.bashrc` or `~/.zshrc`:
```bash
alias ghup='updater'
```

### Windows (PowerShell)
```powershell
git clone https://github.com/Kai-Kodes/Updater.git $HOME\updater
cd $HOME\updater
.\install.ps1
```

---

## 💻 Operating Modes

### 1. Default Interactive Mode (`updater`)
Audits all installed apps concurrently, opens a split-pane `fzf` selector with smooth, syntax-highlighted changelog previews, and applies selected updates:
```bash
updater
```
- **Controls:**
  - `Tab`: Toggle selection
  - `Ctrl-A`: Select all
  - `Ctrl-X`: Deselect all
  - `Shift-Up / Shift-Down` (or `Alt-J / Alt-K`): Scroll changelog preview
  - `Ctrl-D / Ctrl-U`: Half-page scroll preview
  - `Enter`: Confirm and update selected items
  - `Esc`: Abort

### 2. Unattended Full Update Mode (`updater -all` / `--all`)
Skips the interactive picker and immediately upgrades all available items across every detected provider:
```bash
updater -all
```

### 3. Interactive Multi-Source Uninstaller (`updater -rem` / `--rem`)
Audits installed packages, binaries, git repositories, and standalone apps. Shows disk footprint and reverse-dependency warnings in the preview pane, prompts for confirmation with total reclaimed disk space, and safely uninstalls:
```bash
updater -rem
```

### 4. Read-Only Check Mode (`updater -c` / `--check`)
Scans all configured sources and prints a clean, formatted list of available updates without making changes:
```bash
updater -c
```

### 5. Preview Subcommand (`updater preview <workdir> <id>`)
Renders the preview markdown for any item:
```bash
updater preview /tmp/updater-12345 eget_fastfetch
```

---

## ⚙️ Configuration

`updater` automatically discovers tools from your existing environment:
- **GitHub Token:** Reads from `gh auth token` or `GITHUB_TOKEN` environment variable to grant 5,000 requests/hour API rate limit (vs 60/hour anonymous).
- **`~/.eget.toml`:** Automatically monitored for binary tools, custom targets, filters, and GitHub release tracking.
- **Git Repositories:** Automatically discovers git repos in `~/.config`, `~/.local`, `~/Applications`, `~/Projects`, `~/src`, and `~/.agents`.
