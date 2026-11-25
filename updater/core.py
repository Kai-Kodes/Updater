"""
Core orchestrator for scanning, preview generation, update execution, and uninstallation.
"""

import os
import json
import shutil
import concurrent.futures
from pathlib import Path
from typing import Any
from updater.config import (
    TOKEN, compact_list_version, format_size, sanitize_markdown_preview, confirm_action
)
from updater.providers import get_available_providers
from updater.post_hooks import run_post_update_hooks
from updater.ui import (
    ICON_PKG, ICON_CHANGELOG, ICON_AUDIT, ICON_DOWNLOAD,
    ICON_SUCCESS, ICON_WARN, ICON_DESC, ICON_DEP,
    print_info, print_success, print_error, print_warn, render_preview_file
)

def scan_updates(workdir: Path, git_repos: list[str] | None = None) -> list[dict[str, Any]]:
    """Scan all available providers concurrently for available updates."""
    workdir.mkdir(parents=True, exist_ok=True)
    preview_dir = workdir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    print(f"  {ICON_AUDIT}  Auditing installed apps & querying upstream releases in parallel...")

    providers = get_available_providers(git_repos)
    all_updates: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers) + 5) as executor:
        future_to_provider = {executor.submit(p.check_updates): p for p in providers}
        for fut in concurrent.futures.as_completed(future_to_provider):
            p = future_to_provider[fut]
            try:
                res = fut.result()
                if res:
                    all_updates.extend(res)
            except Exception as e:
                pass

    # Sort updates by provider priority and name
    source_priority_map = {p.source_label: p.priority for p in providers}
    all_updates.sort(key=lambda x: (source_priority_map.get(x.get("source", ""), 99), x.get("name", "").lower()))

    # Write manifest.json
    manifest_path = workdir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(all_updates, f, indent=2)

    # Adaptive column sizing for side-by-side left pane (~45% width)
    term_cols = shutil.get_terminal_size((120, 30)).columns
    avail_left = max(34, int(term_cols * 0.45) - 4)
    target_name_width = avail_left - 10 - 5 - 22
    name_col_width = max(14, min(target_name_width, 24))

    # Write items.tsv and preview markdown files
    items_tsv = workdir / "items.tsv"
    with open(items_tsv, "w", encoding="utf-8") as f_tsv:
        for u in all_updates:
            uid = u["id"]
            src = f"[{u['source']}]"
            name = u["name"]
            curr_v = u["installed"]
            avail_v = u["available"]

            co = compact_list_version(curr_v)
            cn = compact_list_version(avail_v)
            if co == cn:
                co, cn = curr_v, avail_v
            vdiff = f"{co} -> {cn}"

            disp_name = name[:name_col_width - 1] + "…" if len(name) > name_col_width else name
            display = f"{src:<10}  {disp_name:<{name_col_width}}   {vdiff}"
            f_tsv.write(f"{uid}\t{display}\n")

            # Write preview markdown file
            pfile = preview_dir / f"{uid}.md"
            with open(pfile, "w", encoding="utf-8") as pf:
                pf.write(f"# {ICON_PKG} {u['name']}\n\n")
                pf.write(f"- **Source:** `{u['source']}`\n")
                if u.get("repo"):
                    pf.write(f"- **Repository:** `{u['repo']}`\n")
                if u.get("path"):
                    pf.write(f"- **Local Path:** `{u['path']}`\n")
                pf.write(f"- **Version Diff:** `{curr_v}` → `{avail_v}`\n")
                pf.write(f"- **Installed Version:** `{curr_v}`\n")
                pf.write(f"- **Available Version:** `{avail_v}`\n")
                if u.get("published"):
                    pf.write(f"- **Release Date:** {u['published']}\n")
                if u.get("url"):
                    pf.write(f"- **Upstream URL:** {u['url']}\n")
                pf.write("\n---\n\n")
                if u.get("title"):
                    pf.write(f"### {ICON_CHANGELOG} {u['title']}\n\n")
                body = u.get("body", "").strip()
                if not body or body == "No release notes provided.":
                    body = f"An update is available for **{u['name']}** from version `{curr_v}` to `{avail_v}`."
                pf.write(sanitize_markdown_preview(body))
                pf.write("\n")

    return all_updates

def apply_updates(workdir: Path, selected_ids: list[str] | None = None) -> list[tuple[str, str, str]]:
    """Apply selected updates and trigger post-update service hooks."""
    manifest_path = workdir / "manifest.json"
    if not manifest_path.is_file():
        print_warn("No update manifest found.")
        return []

    with open(manifest_path, "r", encoding="utf-8") as f:
        all_items = {item["id"]: item for item in json.load(f)}

    if selected_ids is None:
        selected_ids = list(all_items.keys())

    if not selected_ids:
        print_warn("No items were selected for update.")
        return []

    print(f"\n  {ICON_DOWNLOAD}  Applying {len(selected_ids)} selected update(s)...\n")

    providers = {p.source_label: p for p in get_available_providers()}
    updated_summary: list[tuple[str, str, str]] = []

    env = os.environ.copy()
    if TOKEN:
        env["EGET_GITHUB_TOKEN"] = TOKEN
        env["GITHUB_TOKEN"] = TOKEN

    for uid in selected_ids:
        if uid not in all_items:
            continue
        item = all_items[uid]
        src = item["source"]
        if src in providers:
            try:
                success = providers[src].apply_update(item, env)
                if success:
                    updated_summary.append((item["name"], src, item["available"]))
            except Exception as e:
                print_error(f"[{src}] Unexpected error updating {item['name']}: {e}")
        else:
            print_error(f"No active provider found for source [{src}]")

    # Execute service and application post-update hooks
    run_post_update_hooks(updated_summary)

    # Print clean completion summary
    print()
    print("  " + "═" * 68)
    if updated_summary:
        print(f"  {ICON_SUCCESS}  Update Complete! ({len(updated_summary)} items updated)")
        print("  " + "─" * 68)
        for name, src, ver in updated_summary:
            print(f"     • {name} [{src}] -> {ver}")
    else:
        print(f"  {ICON_SUCCESS}  Update process finished.")
    print("  " + "═" * 68)
    print()

    return updated_summary

def scan_uninstall(workdir: Path, git_repos: list[str] | None = None) -> list[dict[str, Any]]:
    """Scan all providers for installed applications and generate uninstaller manifest."""
    workdir.mkdir(parents=True, exist_ok=True)
    preview_dir = workdir / "previews_uninstall"
    preview_dir.mkdir(parents=True, exist_ok=True)

    print(f"  {ICON_AUDIT}  Auditing installed apps across all available system and package providers...")

    providers = get_available_providers(git_repos)
    all_items: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(providers) + 3) as executor:
        future_to_provider = {executor.submit(p.list_installed): p for p in providers}
        for fut in concurrent.futures.as_completed(future_to_provider):
            try:
                res = fut.result()
                if res:
                    all_items.extend(res)
            except Exception:
                pass

    # Sort items: standalone apps & tracked tools first, then system packages
    source_priority_map = {p.source_label: p.priority for p in providers}
    all_items.sort(key=lambda x: (source_priority_map.get(x.get("source", ""), 99), x.get("name", "").lower()))

    # Write manifest_uninstall.json
    manifest_path = workdir / "manifest_uninstall.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2)

    # Responsive column alignment for side-by-side left pane (~45% width)
    term_cols = shutil.get_terminal_size((120, 30)).columns
    avail_left = max(38, int(term_cols * 0.45) - 4)
    name_col_width = max(14, min(22, avail_left - 10 - 12 - 12))
    ver_col_width = max(10, min(16, avail_left - 10 - name_col_width - 12))

    items_tsv = workdir / "items_uninstall.tsv"
    with open(items_tsv, "w", encoding="utf-8") as f_tsv:
        for item in all_items:
            uid = item["id"]
            src = f"[{item['source']}]"
            name = item["name"]
            ver = compact_list_version(item.get("version", ""))
            sz_str = f"({format_size(item.get('size_bytes', 0))})"

            disp_name = name[:name_col_width - 1] + "…" if len(name) > name_col_width else name
            disp_ver = ver[:ver_col_width - 1] + "…" if len(ver) > ver_col_width else ver

            display = f"{src:<10}  {disp_name:<{name_col_width}}   {disp_ver:<{ver_col_width}}   {sz_str:>10}"
            f_tsv.write(f"{uid}\t{display}\n")

            # Write preview markdown file
            pfile = preview_dir / f"{uid}.md"
            with open(pfile, "w", encoding="utf-8") as pf:
                pf.write(f"# {ICON_PKG} {item['name']}\n\n")
                pf.write(f"- **Source:** `{item['source']}`\n")
                pf.write(f"- **Installed Version:** `{item.get('version', 'installed')}`\n")
                pf.write(f"- **Disk Footprint:** `{format_size(item.get('size_bytes', 0))}`\n")
                if item.get("path"):
                    pf.write(f"- **Installation Path:** `{item['path']}`\n")
                if item.get("repo"):
                    pf.write(f"- **Repository:** `{item['repo']}`\n")
                if item.get("homepage"):
                    pf.write(f"- **Homepage / Upstream:** {item['homepage']}\n")
                pf.write("\n---\n\n")
                pf.write(f"### {ICON_DESC} Description\n\n")
                desc = item.get("desc", "").strip() or "No package description available."
                pf.write(sanitize_markdown_preview(desc))
                pf.write("\n\n---\n\n")
                pf.write(f"### {ICON_DEP} Dependency Analysis\n\n")

                if item["source"] in ("apt", "deb", "pacman"):
                    deps = item.get("depends", [])
                    if deps:
                        sample_deps = deps[:10]
                        more = f" ...and {len(deps)-10} more" if len(deps) > 10 else ""
                        pf.write(f"- **Direct Dependencies:** {', '.join(f'`{d}`' for d in sample_deps)}{more}\n\n")
                    else:
                        pf.write("- **Direct Dependencies:** None\n\n")

                    rdeps = item.get("rdepends", [])
                    if rdeps:
                        pf.write(f"⚠️ **Warning: {len(rdeps)} installed package(s) depend on this package:**\n")
                        for rpkg, rtype in rdeps[:15]:
                            rel_badge = "Depends" if rtype == "depends" else "Recommends"
                            pf.write(f"  • `{rpkg}` ({rel_badge})\n")
                        if len(rdeps) > 15:
                            pf.write(f"  • ...and {len(rdeps)-15} more packages\n")
                    else:
                        pf.write("✅ **None** (Safe to remove: no other installed packages depend on this)\n")
                else:
                    pf.write("- **Direct Dependencies:** None (Self-contained / isolated application)\n\n")
                    pf.write("✅ **None** (Safe to remove: no other installed packages depend on this)\n")

    return all_items

def apply_uninstall(workdir: Path, selected_ids: list[str]) -> list[tuple[str, str, str]]:
    """Prompt confirmation and uninstall selected items across providers."""
    manifest_path = workdir / "manifest_uninstall.json"
    if not manifest_path.is_file():
        print_warn("No uninstaller manifest found.")
        return []

    with open(manifest_path, "r", encoding="utf-8") as f:
        all_items = {item["id"]: item for item in json.load(f)}

    selected_items = [all_items[uid] for uid in selected_ids if uid in all_items]
    if not selected_items:
        print_warn("No items were selected for uninstallation.")
        return []

    total_est_bytes = sum(it.get("size_bytes", 0) for it in selected_items)

    print()
    print("  " + "─" * 68)
    print(f"    Items Selected for Uninstallation ({len(selected_items)} item(s)):")
    print("  " + "─" * 68)
    for it in selected_items:
        sz_disp = format_size(it.get("size_bytes", 0))
        print(f"     • [{it['source']}] {it['name']} ({sz_disp})")
    print("  " + "─" * 68)
    print(f"     Estimated Reclaimed Space: ~{format_size(total_est_bytes)}")
    print()

    # User confirmation prompt
    confirmed = confirm_action(f"  Are you sure you want to remove these {len(selected_items)} selected item(s)? [y/N]: ")
    if not confirmed:
        print("\n    Uninstallation aborted by user. No changes were made.\n")
        return []

    print(f"\n    Uninstalling {len(selected_items)} item(s)...\n")

    providers = {p.source_label: p for p in get_available_providers()}
    removed_summary: list[tuple[str, str, str]] = []
    total_reclaimed_bytes = 0

    for it in selected_items:
        src = it["source"]
        sz = it.get("size_bytes", 0)
        if src in providers:
            try:
                success = providers[src].uninstall(it)
                if success:
                    total_reclaimed_bytes += sz
                    removed_summary.append((it["name"], src, f"Removed ({format_size(sz)})"))
            except Exception as e:
                print_error(f"[{src}] Unexpected error removing {it['name']}: {e}")
        else:
            print_error(f"No active provider found for source [{src}]")

    print()
    print("  " + "═" * 68)
    if removed_summary:
        print(f"  {ICON_SUCCESS}  Uninstallation Complete! ({len(removed_summary)} item(s) removed)")
        print("  " + "─" * 68)
        for name, src, detail in removed_summary:
            print(f"     • [{src}] {name} - {detail}")
        print("  " + "─" * 68)
        print(f"     Total Reclaimed Disk Space: ~{format_size(total_reclaimed_bytes)}")
    else:
        print(f"  {ICON_SUCCESS}  Uninstallation process finished (no items removed).")
    print("  " + "═" * 68)
    print()

    return removed_summary

def preview_item(workdir: Path, item_id: str):
    """Render the preview markdown for a specific item in workdir."""
    p1 = workdir / "previews" / f"{item_id}.md"
    p2 = workdir / "previews_uninstall" / f"{item_id}.md"
    target = p1 if p1.is_file() else p2
    render_preview_file(target)
