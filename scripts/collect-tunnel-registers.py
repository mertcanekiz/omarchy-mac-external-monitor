#!/usr/bin/env python3
"""Read Thunderbolt adapter registers and display state; never write registers."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess

TYPES = {1: "lane", 2: "NHI", 0x0e0101: "DP IN", 0x0e0102: "DP OUT",
         0x100101: "PCIe DOWN", 0x100102: "PCIe UP",
         0x200101: "USB3 DOWN", 0x200102: "USB3 UP"}


def read(path):
    try:
        return path.read_text().strip()
    except OSError as exc:
        return {"error": str(exc)}


def decode(raw):
    if not isinstance(raw, str):
        return {}
    rows = [line.split() for line in raw.splitlines() if line.startswith("0x")]
    regs = {int(row[0], 16): int(row[4], 16) for row in rows if len(row) == 5}
    kind = regs.get(2, 0) & 0xffffff
    result = {"type": TYPES.get(kind, hex(kind)), "registers": regs}
    if kind in (0x0e0101, 0x0e0102):
        caps = {int(row[1]): int(row[4], 16) for row in rows
                if len(row) == 5 and int(row[2], 16) == 4}
        if 0 in caps:
            result["adapter_enabled"] = bool(caps[0] & (1 << 30))
            result["video_enabled"] = bool(caps[0] & (1 << 31))
        if 7 in caps:
            result["dprx_done"] = bool(caps[7] & (1 << 31))
        for offset, label in ((4, "local"), (5, "remote"), (7, "common")):
            if offset in caps:
                value = caps[offset]
                result[label] = {"raw": hex(value),
                                 "rate_code": (value >> 8) & 15,
                                 "lane_code": (value >> 12) & 7}
    return result


def attributes(root, names):
    return {entry.name: {name: read(entry / name) for name in names
                         if (entry / name).is_file()}
            for entry in sorted(root.iterdir())} if root.exists() else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path("/sys/kernel/debug/thunderbolt")
    ports = {}
    # Require access rather than silently treating a permission failure as no devices.
    list(root.iterdir())
    for path in sorted(root.glob("*/port*/regs")):
        raw = read(path)
        ports[str(path.relative_to(root).parent)] = {
            "raw": raw, "decoded": decode(raw), "path": read(path.with_name("path"))}
    result = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "boot_id": read(Path("/proc/sys/kernel/random/boot_id")),
        "cmdline": read(Path("/proc/cmdline")), "adapters": ports,
        "routers": attributes(Path("/sys/bus/thunderbolt/devices"),
            ("vendor_name", "device_name", "authorized", "generation", "rx_speed",
             "rx_lanes", "tx_speed", "tx_lanes", "security", "usb4_version")),
        "drm": attributes(Path("/sys/class/drm"), ("status", "enabled", "modes")),
        "usb": attributes(Path("/sys/bus/usb/devices"), ("idVendor", "idProduct", "product", "speed")),
        "role": attributes(Path("/sys/class/usb_role"), ("role",)),
        "kernel_log": subprocess.run(["journalctl", "-k", "-b", "--no-pager"],
            capture_output=True, text=True, timeout=30).stdout,
    }
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(f"Saved {len(ports)} adapters to {args.output}")
    for name, port in ports.items():
        print(name, {k: v for k, v in port["decoded"].items() if k != "registers"})


if __name__ == "__main__":
    main()
