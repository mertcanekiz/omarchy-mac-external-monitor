#!/usr/bin/env python3
"""Identify resident Type-C modules by build ID, not the files on disk.

Exit 0: both experimental; 2: both stock; 1: missing, mixed or unknown.
"""
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent
KERNEL = "7.1.13-3-1-ARCH"


def file_id(path):
    output = subprocess.check_output(["readelf", "-n", str(path)], text=True)
    match = re.search(r"Build ID: ([0-9a-f]+)", output)
    if not match:
        raise ValueError(f"No build ID in {path}")
    return match[1]


def resident_id(name):
    data = Path(f"/sys/module/{name}/notes/.note.gnu.build-id").read_bytes()
    namesize, size, kind = struct.unpack_from("<III", data)
    start = 12 + ((namesize + 3) & ~3)
    if kind != 3 or data[12:12 + namesize] != b"GNU\0" or start + size > len(data):
        raise ValueError("Unexpected GNU build-ID note")
    return data[start:start + size].hex()


def main():
    result = {}
    for module in ("tps6598x-core", "tps6598x"):
        try:
            loaded = resident_id(module.replace("-", "_"))
            experimental = file_id(ROOT / f"artifacts/tipd/{module}.ko")
            stock = file_id(Path(f"/usr/lib/modules/{KERNEL}/kernel/drivers/usb/typec/tipd/{module}.ko"))
            state = "experimental" if loaded == experimental else "stock" if loaded == stock else "unknown"
            result[module] = {"state": state, "loaded": loaded, "experimental": experimental, "stock": stock}
        except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as exc:
            result[module] = {"state": "unknown", "error": str(exc)}
    print(json.dumps(result, indent=2))
    states = {item["state"] for item in result.values()}
    return 0 if states == {"experimental"} else 2 if states == {"stock"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
