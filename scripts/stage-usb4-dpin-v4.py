#!/usr/bin/env python3
"""Install the DP-IN v4 test target (run as root): module tree, initramfs, m1n1 bundle, GRUB entry.

The 7.1.13-usb4-gpu-test module directory was deleted from /usr/lib/modules, so unlike the
v3 stager this one installs the COMPLETE module tree built for v4 (artifacts/usb4-dpin-v4/root),
which is a superset of the v3/GPU-test one (same kernel release, only appledrm and
phy-apple-atc differ). Steps, each verified and backed up:
  1. the v4 initramfs must exist (scripts/build-usb4-dpin-v4-initramfs.sh)
  2. install /usr/lib/modules/7.1.13-usb4-gpu-test from the v4 root (an existing tree is moved
     aside to <release>.before-usb4-dpin-v4), run depmod
  3. copy the initramfs to /boot/initramfs-usb4-dpin-v4.img
  4. copy the v4 loader bundle to the ESP, back up the active one as boot.bin.before-usb4-dpin-v4
  5. append the GRUB menu entry (backup of custom.cfg kept)
  6. activate: copy the v4 bundle over /boot/efi/m1n1/boot.bin
No reboot is performed. `restore` puts the previous loader and GRUB file back; the module tree
and initramfs stay (the GPU+USB4 and v3 entries need the modules too).
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / 'artifacts/usb4-dpin-v4'
REP = ROOT / 'reports/usb4-dpin-v4'
RELEASE = '7.1.13-usb4-gpu-test'
ESP = Path('/boot/efi/m1n1')
CUSTOM = Path('/boot/grub/custom.cfg')
MODULES_DIR = Path('/usr/lib/modules') / RELEASE
STOCK = '566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33'
KEY_MODULES = ('thunderbolt/thunderbolt.ko', 'phy/apple/phy-apple-atc.ko', 'gpu/drm/apple/appledrm.ko')


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

    if action == 'restore':
        m = json.loads(manifest_path.read_text())
        copy(ESP / 'boot.bin.before-usb4-dpin-v4', ESP / 'boot.bin')
        assert digest(ESP / 'boot.bin') == m['previous_loader']
        copy(ART / 'custom.cfg.before-v4', CUSTOM)
        subprocess.run(['grub-script-check', str(CUSTOM)], check=True)
        manifest_path.rename(REP / 'stage-manifest.restored.json')
        print('restored previous loader and GRUB entries (module tree + v4 initramfs left in place)')
        return

    if action != 'install':
        raise SystemExit('usage: stage-usb4-dpin-v4.py [install|restore]')
    if manifest_path.exists():
        raise SystemExit('Already installed (manifest exists). Use restore first to redo.')

    initramfs = ART / 'initramfs-usb4-dpin-v4.img'
    if not initramfs.exists():
        raise SystemExit('Build the initramfs first: sudo bash scripts/build-usb4-dpin-v4-initramfs.sh')
    bundle = ART / 'boot.bin.usb4-dpin-v4'
    report = json.loads((REP / 'boot-bundle.json').read_text())
    assert digest(bundle) == report['sha256'], 'bundle report mismatch'
    entry = (ROOT / 'config/usb4-dpin-v4-grub-entry.cfg').read_text()
    assert 'initramfs-usb4-dpin-v4.img' in entry and 'dprx_timeout=-1' in entry
    src_tree = ART / 'root/lib/modules' / RELEASE
    for name in KEY_MODULES:
        assert (src_tree / 'kernel/drivers' / name).is_file(), name
    assert (src_tree / 'modules.dep').is_file()
    # the v4 appledrm/phy modules must be the ones baked into the initramfs
    for name in ('phy/apple/phy-apple-atc.ko', 'gpu/drm/apple/appledrm.ko'):
        assert digest(src_tree / 'kernel/drivers' / name) != digest(
            ROOT / 'artifacts/usb4-dpin-v3/root/lib/modules' / RELEASE / 'kernel/drivers' / name), \
            f'{name} identical to v3?'

    # 2. module tree
    if MODULES_DIR.exists() or MODULES_DIR.is_symlink():
        aside = Path(str(MODULES_DIR) + '.before-usb4-dpin-v4')
        if aside.exists():
            raise SystemExit(f'{aside} already exists; clean up first')
        MODULES_DIR.rename(aside)
        print('moved existing module tree to', aside)
    subprocess.run(['cp', '-a', str(src_tree), str(MODULES_DIR)], check=True)
    subprocess.run(['depmod', RELEASE], check=True)
    for name in KEY_MODULES:
        assert digest(MODULES_DIR / 'kernel/drivers' / name) == digest(src_tree / 'kernel/drivers' / name)
    n_modules = sum(1 for _ in MODULES_DIR.rglob('*.ko*'))

    # 3. initramfs
    copy(initramfs, Path('/boot/initramfs-usb4-dpin-v4.img'), 0o600)

    # 4. loader bundle
    previous = digest(ESP / 'boot.bin')
    copy(bundle, ESP / 'boot.bin.usb4-dpin-v4')
    if not (ESP / 'boot.bin.before-usb4-dpin-v4').exists():
        copy(ESP / 'boot.bin', ESP / 'boot.bin.before-usb4-dpin-v4')
    (ESP / 'USB4-DPIN-V4-RECOVERY.txt').write_text(
        'DP-IN v4 test loader active. To recover from macOS/Recovery, copy\n'
        'boot.bin.before-usb4-dpin-v4 (previous loader) or\n'
        'boot.bin.before-display-test (original stock loader) over boot.bin\n'
        'in this folder. See USB4-GPU-RECOVERY.txt for the partition details.\n')

    # 5. GRUB entry
    if not (ART / 'custom.cfg.before-v4').exists():
        copy(CUSTOM, ART / 'custom.cfg.before-v4')
    text = CUSTOM.read_text()
    if 'omarchy-usb4-dpin-v4' not in text:
        candidate = ART / 'custom.cfg'
        candidate.write_text(text + entry)
        subprocess.run(['grub-script-check', str(candidate)], check=True)
        copy(candidate, CUSTOM)
    subprocess.run(['grub-script-check', str(CUSTOM)], check=True)

    # 6. activate
    copy(ESP / 'boot.bin.usb4-dpin-v4', ESP / 'boot.bin')
    manifest = dict(release=RELEASE, previous_loader=previous, bundle=report['sha256'],
                    initramfs=digest(initramfs), modules_installed=n_modules,
                    modules={n: digest(src_tree / 'kernel/drivers' / n) for n in KEY_MODULES})
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Installed and activated ({n_modules} modules). Active loader:', digest(ESP / 'boot.bin'))
    print('Reboot and select: Omarchy - Asahi 7.1 USB4 DP-IN v4 (manual)')


if __name__ == '__main__':
    main()
