"""
Debian / Ubuntu APT system package update and uninstallation provider.
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from updater.config import IS_LINUX, IS_ARCH
from updater.providers.base import BaseProvider
from updater.providers.deb import KNOWN_DEB_PACKAGES
from updater.ui import print_info, print_success, print_error

class AptProvider(BaseProvider):
    name = "apt"
    source_label = "apt"
    priority = 30

    @classmethod
    def is_available(cls) -> bool:
        return IS_LINUX and not IS_ARCH and shutil.which("apt") is not None

    def check_updates(self) -> list[dict[str, Any]]:
        updates = []
        try:
            res = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=10)
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("Listing"):
                    continue
                m = re.match(r'^([^/]+)/\S+\s+(\S+)\s+\S+\s+\[upgradable from:\s+(\S+)\]', line)
                if m:
                    pkg, new_v, old_v = m.group(1), m.group(2), m.group(3)
                    desc_lines = []
                    section, homepage, maintainer = "", "", ""
                    try:
                        sres = subprocess.run(["apt", "show", pkg], capture_output=True, text=True, timeout=1.5)
                        grab_desc = False
                        for l in sres.stdout.splitlines():
                            if l.startswith("Section:"):
                                section = l.replace("Section:", "").strip()
                            elif l.startswith("Homepage:"):
                                homepage = l.replace("Homepage:", "").strip()
                            elif l.startswith("Maintainer:"):
                                maintainer = l.replace("Maintainer:", "").strip()
                            elif l.startswith("Description:") or l.startswith("Description-en:"):
                                grab_desc = True
                                first = l.split(":", 1)[1].strip()
                                if first:
                                    desc_lines.append(first)
                            elif grab_desc and l.startswith(" "):
                                desc_lines.append(l.strip())
                            elif grab_desc and not l.startswith(" "):
                                grab_desc = False
                    except Exception:
                        pass

                    body_parts = []
                    if desc_lines:
                        body_parts.append("\n".join(desc_lines))
                    else:
                        body_parts.append(f"Standard Debian system package update for `{pkg}`.")

                    meta_info = []
                    if homepage:
                        meta_info.append(f"- **Homepage:** {homepage}")
                    if section:
                        meta_info.append(f"- **Section:** `{section}`")
                    if maintainer:
                        meta_info.append(f"- **Maintainer:** {maintainer}")
                    if meta_info:
                        body_parts.append("\n" + "\n".join(meta_info))

                    updates.append({
                        "id": f"apt_{pkg}",
                        "source": "apt",
                        "name": pkg,
                        "installed": old_v,
                        "available": new_v,
                        "title": f"Debian APT Package: {pkg}",
                        "body": "\n\n".join(body_parts)
                    })
        except Exception:
            pass
        return updates

    def apply_update(self, item: dict[str, Any], env: dict[str, str]) -> bool:
        pkg = item["name"]
        print_info(f"[apt] Upgrading {pkg}...")
        res = subprocess.run(["sudo", "apt-get", "--only-upgrade", "install", "-y", pkg], env=env)
        if res.returncode == 0:
            print_success(f"[apt] {pkg} upgraded to {item['available']}")
            return True
        print_error(f"[apt] Failed to upgrade {pkg}")
        return False

    def list_installed(self) -> list[dict[str, Any]]:
        status_path = Path("/var/lib/dpkg/status")
        if not status_path.is_file():
            return []

        pkg_db: dict[str, dict[str, Any]] = {}
        try:
            with open(status_path, "r", encoding="utf-8", errors="ignore") as f:
                cur_pkg = None
                cur_data = None
                in_desc = False
                for line in f:
                    if line.startswith("Package: "):
                        cur_pkg = line.split(":", 1)[1].strip()
                        cur_data = {
                            "name": cur_pkg,
                            "status": "",
                            "priority": "",
                            "essential": False,
                            "protected": False,
                            "depends": [],
                            "recommends": [],
                            "desc": [],
                            "section": "",
                            "version": "",
                            "size_kb": 0,
                            "homepage": ""
                        }
                        pkg_db[cur_pkg] = cur_data
                        in_desc = False
                    elif cur_data:
                        if line.startswith("Status: "):
                            cur_data["status"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Priority: "):
                            cur_data["priority"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Essential: yes"):
                            cur_data["essential"] = True
                        elif line.startswith("Protected: yes"):
                            cur_data["protected"] = True
                        elif line.startswith("Depends: ") or line.startswith("Pre-Depends: "):
                            for item in line.split(":", 1)[1].split(","):
                                for a in item.split("|"):
                                    clean = re.sub(r'\(.*?\)', '', a).strip()
                                    if clean:
                                        cur_data["depends"].append(clean)
                        elif line.startswith("Recommends: "):
                            for item in line.split(":", 1)[1].split(","):
                                for a in item.split("|"):
                                    clean = re.sub(r'\(.*?\)', '', a).strip()
                                    if clean:
                                        cur_data["recommends"].append(clean)
                        elif line.startswith("Section: "):
                            cur_data["section"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Version: "):
                            cur_data["version"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Installed-Size: "):
                            try:
                                cur_data["size_kb"] = int(line.split(":", 1)[1].strip())
                            except Exception:
                                pass
                        elif line.startswith("Homepage: "):
                            cur_data["homepage"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Description: "):
                            in_desc = True
                            cur_data["desc"].append(line.split(":", 1)[1].strip())
                        elif in_desc and line.startswith(" "):
                            cur_data["desc"].append(line.strip())
                        elif line.strip() == "":
                            in_desc = False
        except Exception:
            return []

        # Build reverse dependency mappings
        rdepends_map: dict[str, set[tuple[str, str]]] = {}
        for p_name, p_data in pkg_db.items():
            if "installed" in p_data.get("status", ""):
                for dep in p_data["depends"]:
                    rdepends_map.setdefault(dep, set()).add((p_name, "depends"))
                for dep in p_data["recommends"]:
                    rdepends_map.setdefault(dep, set()).add((p_name, "recommends"))

        items = []
        deb_known_pkgs = set(KNOWN_DEB_PACKAGES.values())

        # Include deb items first
        for repo, pkg in KNOWN_DEB_PACKAGES.items():
            if pkg in pkg_db and "installed" in pkg_db[pkg].get("status", ""):
                pdata = pkg_db[pkg]
                items.append({
                    "id": f"deb_{pkg}",
                    "source": "deb",
                    "name": pkg,
                    "repo": repo,
                    "pkg": pkg,
                    "version": pdata["version"],
                    "size_bytes": pdata["size_kb"] * 1024,
                    "path": shutil.which(pkg) or f"/usr/bin/{pkg}",
                    "homepage": pdata["homepage"] or f"https://github.com/{repo}",
                    "desc": "\n".join(pdata["desc"]) if pdata["desc"] else f"GitHub deb package from {repo}",
                    "depends": pdata["depends"],
                    "rdepends": sorted(list(rdepends_map.get(pkg, set())))
                })

        # Filtered manual system packages
        try:
            manual = set(subprocess.check_output(['apt-mark', 'showmanual'], text=True).splitlines())
            for pkg in manual:
                if pkg in deb_known_pkgs:
                    continue
                if pkg not in pkg_db:
                    continue
                pdata = pkg_db[pkg]
                if "installed" not in pdata.get("status", ""):
                    continue
                if pdata.get("essential") or pdata.get("protected"):
                    continue
                if pdata.get("priority") in ("required", "important"):
                    continue
                sec = pdata.get("section", "")
                if sec.startswith("libs") or sec.startswith("oldlibs") or sec.startswith("introspection"):
                    continue
                if pkg.startswith("lib") and not pkg.startswith("libreoffice"):
                    continue

                items.append({
                    "id": f"apt_{pkg}",
                    "source": "apt",
                    "name": pkg,
                    "pkg": pkg,
                    "version": pdata["version"],
                    "size_bytes": pdata["size_kb"] * 1024,
                    "path": shutil.which(pkg) or f"/usr/bin/{pkg}",
                    "homepage": pdata.get("homepage", ""),
                    "desc": "\n".join(pdata["desc"]) if pdata["desc"] else f"Debian system package {pkg}",
                    "depends": pdata["depends"],
                    "rdepends": sorted(list(rdepends_map.get(pkg, set())))
                })
        except Exception:
            pass

        return items

    def uninstall(self, item: dict[str, Any]) -> bool:
        pkg = item.get("pkg") or item["name"]
        print_info(f"[apt] Purging {pkg}...")
        res = subprocess.run(["sudo", "apt-get", "purge", "-y", pkg])
        if res.returncode == 0:
            subprocess.run(["sudo", "apt-get", "autoremove", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print_success(f"[apt] {pkg} purged successfully")
            return True
        print_error(f"[apt] Failed to purge {pkg}")
        return False
