#!/usr/bin/env python3
"""Read-only before/after evidence for the M1 external-display experiment."""
import datetime
import json
from pathlib import Path
import subprocess
import sys


def read(path, binary=False):
    try:
        data = Path(path).read_bytes()
        return data.hex() if binary else data.replace(b"\0", b" ").decode(errors="replace").strip()
    except OSError as exc:
        return {"error": str(exc)}


def command(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def attributes(root, names):
    return {
        str(p): {name: read(p / name) for name in names if (p / name).is_file()}
        for p in sorted(Path(root).glob("*")) if p.is_dir()
    }


def main():
    tree = Path("/sys/firmware/devicetree/base")
    nodes = {}
    for p in tree.glob("soc/**/*"):
        if p.name in {"status", "compatible", "apple,connector-type", "phy-names", "mux-control-names"} and any(
            word in str(p) for word in ("dcp@", "display-subsystem", "phy@", "mux@")
        ):
            nodes[str(p.relative_to(tree))] = read(p)
    result = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kernel": command("uname", "-a"),
        "boot_id": read("/proc/sys/kernel/random/boot_id"),
        "cmdline": read("/proc/cmdline"),
        "loaded_display_modules": command(sys.executable, str(Path(__file__).with_name("check-loaded-modules.py"))),
        "model": read(tree / "model"), "compatible": read(tree / "compatible"),
        "drm": attributes("/sys/class/drm", ("status", "enabled", "modes")),
        "typec": attributes("/sys/class/typec", ("data_role", "power_role", "port_type", "power_operation_mode", "orientation", "supports_usb_power_delivery", "number_of_alternate_modes", "identity/id_header", "identity/cert_stat", "identity/product")),
        "typec_paths": {p.name: str(p.resolve()) for p in sorted(Path("/sys/class/typec").glob("*"))},
        "typec_power": attributes("/sys/class/power_supply", ("online", "usb_type")),
        "usb": attributes("/sys/bus/usb/devices", ("product", "manufacturer", "idVendor", "idProduct", "speed")),
        "device_tree": nodes,
        "hyprland": command("hyprctl", "monitors", "all", "-j"),
        "modules": command("lsmod"),
        "packages": command("pacman", "-Q", "linux-asahi", "m1n1", "uboot-asahi", "mesa", "hyprland"),
    }
    journal = command("journalctl", "-k", "-b", "--no-pager", "--grep", "dcp|drm|typec|tps659|atc|dptx|display-crossbar")
    result["display_kernel_log"] = journal
    output = json.dumps(result, indent=2) + "\n"
    if len(sys.argv) == 2:
        # Exclusive creation protects an earlier baseline from accidental overwrite.
        with open(sys.argv[1], "x") as dest:
            dest.write(output)
    elif len(sys.argv) == 1:
        print(output, end="")
    else:
        sys.exit(f"Usage: {sys.argv[0]} [new-output.json]")


if __name__ == "__main__":
    main()
