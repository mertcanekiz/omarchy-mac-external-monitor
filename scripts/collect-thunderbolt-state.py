#!/usr/bin/env python3
"""Collect read-only evidence for Apple Silicon USB4 bring-up."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import subprocess
import sys


def read(path: Path) -> str | dict[str, str]:
    try:
        return path.read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError as exc:
        return {"error": str(exc)}


def command(*args: str) -> dict[str, object]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def sysfs_tree(root: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[str(path)] = {"target": str(path.resolve())}
        elif path.is_file() and path.stat().st_size <= 65536:
            result[str(path)] = read(path)
    return result


def main() -> None:
    dt = Path("/sys/firmware/devicetree/base")
    dt_usb4: dict[str, object] = {}
    if dt.exists():
        for path in sorted(dt.rglob("*")):
            rendered = str(path.relative_to(dt))
            if any(term in rendered for term in ("cio@", "nhi@", "thunderbolt", "usb4")):
                if path.is_file() and path.stat().st_size <= 65536:
                    dt_usb4[rendered] = read(path)

    result = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "uname": command("uname", "-a"),
        "cmdline": read(Path("/proc/cmdline")),
        "boot_id": read(Path("/proc/sys/kernel/random/boot_id")),
        "modules": command("lsmod"),
        "module_info": {
            name: command("modinfo", name)
            for name in ("thunderbolt", "thunderbolt_apple", "phy_apple_atc")
        },
        "thunderbolt_sysfs": sysfs_tree(Path("/sys/bus/thunderbolt/devices")),
        "typec_sysfs": sysfs_tree(Path("/sys/class/typec")),
        "usb_tree": command("lsusb", "-tv"),
        "pci_tree": command("lspci", "-nnk"),
        "boltctl": command("boltctl", "list", "--all"),
        "device_tree_usb4": dt_usb4,
        "kernel_log": command(
            "journalctl",
            "-k",
            "-b",
            "--no-pager",
            "--grep",
            "thunderbolt|usb4|apple-cio|acio|nhi|drom|tps6598|typec|xhci",
        ),
    }
    output = json.dumps(result, indent=2) + "\n"
    if len(sys.argv) == 2:
        with open(sys.argv[1], "x") as destination:
            destination.write(output)
    elif len(sys.argv) == 1:
        print(output, end="")
    else:
        raise SystemExit(f"Usage: {sys.argv[0]} [new-output.json]")


if __name__ == "__main__":
    main()
