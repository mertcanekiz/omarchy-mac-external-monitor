#!/usr/bin/env python3
"""Install the DP-IN v5 test target (run as root) on top of the v4 install.

Same kernel release; v5 changes thunderbolt.ko, phy-apple-atc.ko, appledrm.ko and the J313 DTB.
  1. back up and replace those three modules in /usr/lib/modules/<release>, depmod
  2. copy the v5 initramfs to /boot/initramfs-usb4-dpin-v5.img
  3. copy the v5 loader bundle to the ESP, back up the active one as boot.bin.before-usb4-dpin-v5
  4. append the GRUB entry (the v4 entry stays as a fallback: its initramfs carries the v4 modules)
  5. activate: copy the v5 bundle over /boot/efi/m1n1/boot.bin
`restore` reverts the modules, loader and GRUB file.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / 'artifacts/usb4-dpin-v5'
REP = ROOT / 'reports/usb4-dpin-v5'
RELEASE = '7.1.13-usb4-gpu-test'
ESP = Path('/boot/efi/m1n1')
CUSTOM = Path('/boot/grub/custom.cfg')
MODULES = ('thunderbolt/thunderbolt.ko', 'phy/apple/phy-apple-atc.ko', 'gpu/drm/apple/appledrm.ko')
STOCK = '566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33'


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def copy(src, dst, mode=0o644):
    tmp = Path(str(dst) + '.tmp')
    shutil.copyfile(src, tmp)
    os.chmod(tmp, mode)
    os.replace(tmp, dst)
    assert digest(src) == digest(dst), f'copy mismatch {dst}'


def main():
    if os.geteuid():
        raise SystemExit('Run as root.')
    action = sys.argv[1] if len(sys.argv) > 1 else 'install'
    subprocess.run(['mountpoint', '-q', '/boot/efi'], check=True)
    assert digest(ESP / 'boot.bin.before-display-test') == STOCK, 'stock loader backup missing'
    manifest_path = REP / 'stage-manifest.json'
    modroot = ART / 'root/lib/modules' / RELEASE / 'kernel/drivers'
    target = Path('/usr/lib/modules') / RELEASE / 'kernel/drivers'
    backup = ART / 'module-backup'

    if action == 'restore':
        m = json.loads(manifest_path.read_text())
        copy(ESP / 'boot.bin.before-usb4-dpin-v5', ESP / 'boot.bin')
        assert digest(ESP / 'boot.bin') == m['previous_loader']
        for name in MODULES:
            copy(backup / name, target / name)
        subprocess.run(['depmod', RELEASE], check=True)
        copy(ART / 'custom.cfg.before-v5', CUSTOM)
        subprocess.run(['grub-script-check', str(CUSTOM)], check=True)
        manifest_path.rename(REP / 'stage-manifest.restored.json')
        print('restored v4 loader, modules and GRUB entries (v5 initramfs left in /boot)')
        return
    if action != 'install':
        raise SystemExit('usage: stage-usb4-dpin-v5.py [install|restore]')
    if manifest_path.exists():
        raise SystemExit('Already installed (manifest exists). Use restore first to redo.')

    initramfs = ART / 'initramfs-usb4-dpin-v5.img'
    if not initramfs.exists():
        raise SystemExit('Build the initramfs first: sudo bash scripts/build-usb4-dpin-v5-initramfs.sh')
    bundle = ART / 'boot.bin.usb4-dpin-v5'
    report = json.loads((REP / 'boot-bundle.json').read_text())
    assert digest(bundle) == report['sha256'], 'bundle report mismatch'
    entry = (ROOT / 'config/usb4-dpin-v5-grub-entry.cfg').read_text()
    assert 'initramfs-usb4-dpin-v5.img' in entry and 'dprx_timeout=-1' in entry

    # 1. modules
    backup.mkdir(parents=True, exist_ok=True)
    for name in MODULES:
        src, dst = modroot / name, target / name
        assert src.is_file() and dst.is_file(), name
        (backup / name).parent.mkdir(parents=True, exist_ok=True)
        if not (backup / name).exists():
            copy(dst, backup / name)
    for name in MODULES:
        if digest(modroot / name) == digest(target / name):
            print('unchanged module, kept:', name)
            continue
        copy(modroot / name, target / name)
    subprocess.run(['depmod', RELEASE], check=True)

    # 2. initramfs
    copy(initramfs, Path('/boot/initramfs-usb4-dpin-v5.img'), 0o600)

    # 3. loader bundle
    previous = digest(ESP / 'boot.bin')
    copy(bundle, ESP / 'boot.bin.usb4-dpin-v5')
    if not (ESP / 'boot.bin.before-usb4-dpin-v5').exists():
        copy(ESP / 'boot.bin', ESP / 'boot.bin.before-usb4-dpin-v5')

    # 4. GRUB entry
    if not (ART / 'custom.cfg.before-v5').exists():
        copy(CUSTOM, ART / 'custom.cfg.before-v5')
    text = CUSTOM.read_text()
    if 'omarchy-usb4-dpin-v5' not in text:
        candidate = ART / 'custom.cfg'
        candidate.write_text(text + entry)
        subprocess.run(['grub-script-check', str(candidate)], check=True)
        copy(candidate, CUSTOM)
    subprocess.run(['grub-script-check', str(CUSTOM)], check=True)

    # 5. activate
    copy(ESP / 'boot.bin.usb4-dpin-v5', ESP / 'boot.bin')
    manifest = dict(release=RELEASE, previous_loader=previous, bundle=report['sha256'],
                    initramfs=digest(initramfs),
                    modules={n: digest(modroot / n) for n in MODULES},
                    module_backups={n: digest(backup / n) for n in MODULES})
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print('Installed and activated. Active loader:', digest(ESP / 'boot.bin'))
    print('Reboot and select: Omarchy - Asahi 7.1 USB4 DP-IN v5 (manual)')


if __name__ == '__main__':
    main()
