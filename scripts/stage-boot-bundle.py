#!/usr/bin/env python3
"""Replace only the matching J313 DTB in a COPY of the active m1n1 bundle."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent.parent
KERNEL = "7.1.13-3-1-ARCH"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def properties(data):
    if len(data) < 40:
        raise ValueError("Truncated FDT header")
    magic, size, structure, strings, _, version, _, _, strings_size, structure_size = struct.unpack_from(">10I", data)
    if magic != 0xD00DFEED or size != len(data) or version < 17:
        raise ValueError("Invalid or unsupported FDT header")
    if strings + strings_size > size or structure + structure_size > size:
        raise ValueError("FDT sections exceed size")
    names = data[strings:strings + strings_size]
    pos, stack, result = structure, [], {}
    while pos < structure + structure_size:
        token, = struct.unpack_from(">I", data, pos)
        pos += 4
        if token == 1:
            end = data.index(b"\0", pos)
            stack.append(data[pos:end].decode())
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from(">II", data, pos)
            pos += 8
            name = names[nameoff:names.index(b"\0", nameoff)].decode()
            path = "/".join(stack) or "/"
            result[(path, name)] = data[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            if stack:
                raise ValueError("Unbalanced FDT nodes")
            return result
        else:
            raise ValueError(f"Unknown FDT token {token}")
    raise ValueError("Missing FDT end token")


def main():
    stock = Path(f"/usr/lib/modules/{KERNEL}/dtbs/t8103-j313.dtb").read_bytes()
    active = Path("/boot/efi/m1n1/boot.bin").read_bytes()
    saved = (ROOT / "snapshots/m1n1-boot.bin").read_bytes()
    candidate = (ROOT / "artifacts/dtb/t8103-j313.dtb").read_bytes()
    if active != saved:
        raise SystemExit("Active boot bundle changed since baseline; take and review a new snapshot first")
    if active.count(stock) != 1:
        raise SystemExit("Expected exactly one byte-identical stock J313 DTB in the active bundle")
    old, new = properties(stock), properties(candidate)
    dcp = "/soc/dcp@271c00000"
    connector = "/soc/i2c@235010000/usb-pd@3f/connector"
    assert b"apple,j313\0" in new[("/", "compatible")]
    assert old[(dcp, "status")] == b"disabled\0"
    assert new[(dcp, "status")] == b"okay\0"
    assert new[(dcp, "apple,connector-type")] == b"DP\0"
    assert new[("/aliases", "dcpext")] == dcp.encode() + b"\0"
    assert new[(connector, "displayport")] == new[(dcp, "phandle")]
    offset = active.index(stock)
    result = active[:offset] + candidate + active[offset + len(stock):]
    # Preserve m1n1, all other DTBs, U-Boot and trailing configuration exactly.
    assert result[:offset] == active[:offset]
    assert result[offset + len(candidate):] == active[offset + len(stock):]
    (ROOT / "artifacts/boot.bin.display-test").write_bytes(result)
    report = {
        "kernel": KERNEL, "stock_bundle_sha256": digest(active),
        "candidate_bundle_sha256": digest(result), "dtb_offset": offset,
        "stock_dtb_sha256": digest(stock), "candidate_dtb_sha256": digest(candidate),
        "stock_dtb_bytes": len(stock), "candidate_dtb_bytes": len(candidate),
        "verified": ["J313 model", "external DCP enabled", "DP connector type", "dcpext alias", "Type-C port 1 linked to external DCP", "all bytes outside J313 DTB preserved"],
        "installed": False, "boot_tested": False,
    }
    (ROOT / "reports/boot-bundle-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
