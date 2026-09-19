#!/usr/bin/env python3
"""Package the fixed-route DP-IN experiment, without activating or rebooting."""
import gzip
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "artifacts/thunderbolt-dpin"
BUILD = ROOT / "artifacts/thunderbolt-kernel/build"
RELEASE = "7.2.2-thunderbolt-test+"
BASE_HASH = "9602d026b2960bf308e3cc7a9d14019abeed4b7ccaa387125241073660b7c297"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args, **kwargs):
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=['v1', 'v2'], default='v1')
    args = parser.parse_args()
    suffix = '' if args.revision == 'v1' else '-v2'
    name = 'thunderbolt-dpin' + suffix
    report_prefix = 'dpin' + suffix
    OUT = ROOT / ('artifacts/' + name)
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo for mkinitcpio firmware access.")
    OUT.mkdir(exist_ok=True)
    module = OUT / "module/appledrm.ko"
    dtb = BUILD / "arch/arm64/boot/dts/apple/t8103-j313.dtb"
    if b"tunnel_hpd" not in module.read_bytes() or b"apple,tbt-dpin-test" not in dtb.read_bytes():
        raise SystemExit("Build the experimental module and DTB first.")
    # Kconfig's tool-availability probe can add this informational symbol.
    def normalized(text):
        return [line for line in text.splitlines() if line != "CONFIG_RUST_IS_AVAILABLE=y"]
    if normalized(gzip.decompress(Path('/proc/config.gz').read_bytes()).decode()) != normalized((BUILD / '.config').read_text()):
        raise SystemExit("Build configuration differs from the running test kernel.")
    if digest(BUILD / "arch/arm64/boot/Image") != digest(Path('/boot/vmlinuz-thunderbolt-test')):
        raise SystemExit("Existing kernel image changed; module-only packaging is invalid.")

    private = OUT / "root"
    if private.exists():
        raise SystemExit(f"Refusing to overwrite existing private module tree: {private}")
    run("cp", "-a", "--reflink=auto", ROOT / "artifacts/thunderbolt-kernel/root", private)
    destination = private / f"lib/modules/{RELEASE}/kernel/drivers/gpu/drm/apple/appledrm.ko"
    shutil.copy2(module, destination)
    run("depmod", "-b", private, RELEASE)
    image = OUT / f"initramfs-{name}.img"
    with (ROOT / f"reports/thunderbolt/{report_prefix}-initramfs-build.log").open("x") as log:
        run("mkinitcpio", "--nopost", "-k", RELEASE, "-r", private,
            "-c", ROOT / "artifacts/thunderbolt-mkinitcpio.conf", "-g", image,
            stdout=log, stderr=subprocess.STDOUT)
    contents = subprocess.check_output(["lsinitcpio", "-l", str(image)], text=True)
    for required in ("appledrm.ko", "thunderbolt.ko", "thunderbolt_apple.ko", "hooks/asahi"):
        if required not in contents:
            raise SystemExit(f"Initramfs missing {required}")
    (ROOT / f"reports/thunderbolt/{report_prefix}-initramfs-contents.txt").write_text(contents)

    original = ROOT / "artifacts/boot.bin.thunderbolt-test"
    if digest(original) != BASE_HASH:
        raise SystemExit("Original USB4 bundle hash changed.")
    metadata = json.loads((ROOT / "reports/thunderbolt/boot-bundle.json").read_text())
    matches = [c for c in metadata['components'] if c['name'] == 't8103-j313.dtb']
    if len(matches) != 1:
        raise SystemExit("Ambiguous model DTB in original manifest.")
    component = matches[0]
    data = original.read_bytes()
    start, length = component['offset'], component['bytes']
    if hashlib.sha256(data[start:start + length]).hexdigest() != component['sha256']:
        raise SystemExit("DTB offset/hash in original manifest is invalid.")
    bundle = OUT / f"boot.bin.{name}"
    bundle.write_bytes(data[:start] + dtb.read_bytes() + data[start + length:])
    shutil.copy2(module, OUT / "appledrm.ko")
    shutil.copy2(dtb, OUT / dtb.name)
    patch = subprocess.check_output(["git", "-C", str(ROOT / "sources/linux-thunderbolt"), "diff", "--binary"])
    patch_path = ROOT / f"patches/{name}-experiment.patch"
    patch_path.write_bytes(patch)
    report = {
        'release': RELEASE, 'baseline_bundle_sha256': BASE_HASH,
        'kernel_sha256': digest(Path('/boot/vmlinuz-thunderbolt-test')),
        'files': {str(path.relative_to(ROOT)): digest(path) for path in
                  (image, bundle, OUT / 'appledrm.ko', OUT / dtb.name,
                   patch_path)},
        'boot_tested': False, 'display_working': False,
        'scope': 'J313, front port, DPIN0; manual connection; no hotplug/suspend support',
    }
    (ROOT / f'reports/thunderbolt/{report_prefix}-artifacts.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
