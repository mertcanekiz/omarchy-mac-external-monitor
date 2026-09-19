#!/usr/bin/env python3
"""Assemble a reviewable m1n1 bundle for the Apple USB4 bring-up test."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INSTALLED_KERNEL = "7.1.13-3-1-ARCH"
MODEL_DTB = "t8103-j313.dtb"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def filtered_config(path: Path) -> bytes:
    if not path.exists():
        return b""

    accepted = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("chosen.", "display=", "mitigations=")) and "=" in line:
            accepted.append(line)
            continue
        raise SystemExit(f"Refusing unknown m1n1 option: {line}")
    return ("\n".join(accepted) + ("\n" if accepted else "")).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('thunderbolt-test', 'usb4-gpu', 'usb4-dpin-v3', 'dpalt'),
                        default='thunderbolt-test')
    args = parser.parse_args()
    m1n1_path = ROOT / "sources/m1n1-thunderbolt/build/m1n1.bin"
    custom_dtb_path = (
        ROOT
        / "artifacts/thunderbolt-kernel/build/arch/arm64/boot/dts/apple"
        / MODEL_DTB
    )
    installed_dtbs = Path(f"/usr/lib/modules/{INSTALLED_KERNEL}/dtbs")
    uboot_path = Path("/usr/lib/asahi-boot/u-boot-nodtb.bin")
    output = ROOT / "artifacts/boot.bin.thunderbolt-test"
    report_path = ROOT / "reports/thunderbolt/boot-bundle.json"
    kernel_commit = "236788cd2602a24c703fe7bdaddaf73ef77d2027"
    kernel_release = "7.2.2-thunderbolt-test+"
    if args.profile == 'usb4-gpu':
        custom_dtb_path = ROOT / 'artifacts/usb4-backport/build/arch/arm64/boot/dts/apple' / MODEL_DTB
        output = ROOT / 'artifacts/usb4-backport/boot.bin.usb4-gpu-test'
        report_path = ROOT / 'reports/usb4-backport/boot-bundle.json'
        kernel_commit = subprocess.check_output(
            ['git', '-C', str(ROOT / 'sources/linux-usb4-backport'), 'rev-parse', 'HEAD'],
            text=True).strip()
        kernel_release = '7.1.13-usb4-gpu-test'
    elif args.profile == 'usb4-dpin-v3':
        custom_dtb_path = ROOT / 'artifacts/usb4-backport/build/arch/arm64/boot/dts/apple' / MODEL_DTB
        output = ROOT / 'artifacts/usb4-dpin-v3/boot.bin.usb4-dpin-v3'
        report_path = ROOT / 'reports/usb4-dpin-v3/boot-bundle.json'
        kernel_commit = subprocess.check_output(
            ['git', '-C', str(ROOT / 'sources/linux-usb4-backport'), 'rev-parse', 'HEAD'],
            text=True).strip()
        kernel_release = '7.1.13-usb4-gpu-test'
        if b'apple,tbt-dpin-test' not in custom_dtb_path.read_bytes():
            raise SystemExit('J313 DTB lacks the DP-IN v3 marker')
    elif args.profile == 'dpalt':
        # DP alt mode variant: same kernel/modules as v3 except tipd, fairydust DTB wiring.
        custom_dtb_path = ROOT / 'artifacts/dpalt/out' / MODEL_DTB
        output = ROOT / 'artifacts/dpalt/boot.bin.dpalt'
        report_path = ROOT / 'reports/dp-altmode/boot-bundle.json'
        kernel_commit = subprocess.check_output(
            ['git', '-C', str(ROOT / 'sources/linux-dpalt'), 'rev-parse', 'HEAD'],
            text=True).strip()
        kernel_release = '7.1.13-usb4-gpu-test'
        dtb = custom_dtb_path.read_bytes()
        if b'apple,tbt-dpin-test' in dtb or b'displayport' not in dtb:
            raise SystemExit('J313 DTB is not the DP-alt variant')

    for path in (m1n1_path, custom_dtb_path, installed_dtbs, uboot_path):
        if not path.exists():
            raise SystemExit(f"Required input is missing: {path}")

    m1n1 = m1n1_path.read_bytes()
    custom_dtb = custom_dtb_path.read_bytes()
    uboot = uboot_path.read_bytes()
    config = filtered_config(Path("/etc/m1n1.conf"))

    required_dtb_markers = (
        b"apple,t8103-usb4-acio",
        b"apple,t8103-usb4-nhi",
        b"apple,thunderbolt-drom",
        b"usb4-0-acio",
        b"usb4-1-acio",
    )
    missing = [marker.decode() for marker in required_dtb_markers if marker not in custom_dtb]
    if missing:
        raise SystemExit(f"Custom J313 DTB lacks USB4 markers: {', '.join(missing)}")
    if b"thunderbolt-drom" not in m1n1:
        raise SystemExit("Built m1n1 lacks Thunderbolt DROM support")

    dtb_paths = sorted(installed_dtbs.glob("*.dtb"))
    if not dtb_paths:
        raise SystemExit(f"No installed DTBs found in {installed_dtbs}")
    if sum(path.name == MODEL_DTB for path in dtb_paths) != 1:
        raise SystemExit(f"Expected exactly one installed {MODEL_DTB}")

    components: list[dict[str, object]] = []
    chunks: list[bytes] = []
    offset = 0

    def append(name: str, kind: str, data: bytes, source: str) -> None:
        nonlocal offset
        components.append(
            {
                "name": name,
                "kind": kind,
                "source": source,
                "offset": offset,
                "bytes": len(data),
                "sha256": sha256(data),
            }
        )
        chunks.append(data)
        offset += len(data)

    append("m1n1.bin", "loader", m1n1, str(m1n1_path))
    for path in dtb_paths:
        if path.name == MODEL_DTB:
            append(path.name, "custom-dtb", custom_dtb, str(custom_dtb_path))
        else:
            data = path.read_bytes()
            append(path.name, "installed-dtb", data, str(path))

    # update-m1n1 appends a gzip stream containing U-Boot. A zero timestamp
    # makes our workspace artifact byte-reproducible.
    compressed_uboot = gzip.compress(uboot, compresslevel=9, mtime=0)
    append("u-boot-nodtb.bin.gz", "uboot", compressed_uboot, str(uboot_path))
    if config:
        append("m1n1.conf", "config", config, "/etc/m1n1.conf")

    result = b"".join(chunks)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)

    report = {
        "output": str(output),
        "sha256": sha256(result),
        "bytes": len(result),
        "m1n1_source_commit": "b4654b32941d51afdb77579d63e7cb1aa6c03ecc",
        "kernel_source_commit": kernel_commit,
        "kernel_release": kernel_release,
        "model_dtb": MODEL_DTB,
        "components": components,
        "installed": False,
        "boot_tested": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
