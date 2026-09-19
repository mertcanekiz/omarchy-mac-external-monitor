#!/usr/bin/env python3
"""Prepare, stage, activate or restore the separate 7.1 GPU+USB4 boot target."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / 'artifacts/usb4-backport'
REPORT = ROOT / 'reports/usb4-backport/stage-manifest.json'
RELEASE = '7.1.13-usb4-gpu-test'
ESP = Path('/boot/efi/m1n1')
CUSTOM = Path('/boot/grub/custom.cfg')
STOCK = '566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33'
PREVIOUS = '5c504019c46807826ac91c9e67c0739e972e358eca22dc3076a37e81e0387e89'
OLD_CUSTOM = '45b4a44c814f47d69dfa60a375e18e455c1b3c13014367e014b48a4979e6ca22'
ENTRY = """
# Stock Asahi GPU plus Apple USB4 backport; requires the matching m1n1 bundle.
menuentry 'Omarchy - Asahi 7.1 GPU + USB4 (manual)' --id 'omarchy-usb4-gpu-test' {
    load_video
    set gfxpayload=keep
    insmod gzio
    insmod part_gpt
    insmod btrfs
    search --no-floppy --fs-uuid --set=root 725346d2-f127-47bc-b464-9dd46155e8d6
    linux /@/boot/vmlinuz-usb4-gpu-test root=UUID=725346d2-f127-47bc-b464-9dd46155e8d6 rw rootflags=subvol=@ loglevel=7
    initrd /@/boot/initramfs-usb4-gpu-test.img
}
"""

def run(*args):
    return subprocess.check_output(args, text=True).strip()

def digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f'Not a regular file: {path}')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def require(path, expected):
    if digest(path) != expected:
        raise RuntimeError(f'Hash mismatch: {path}')

def copy_file(source, target, expected, replace=False, mode=0o644):
    source, target = Path(source), Path(target)
    require(source, expected)
    if target.exists() or target.is_symlink():
        if target.is_symlink():
            raise RuntimeError(f'Refusing symlink: {target}')
        if digest(target) == expected:
            return
        if not replace:
            raise RuntimeError(f'Refusing to overwrite {target}')
    tmp = target.with_name(target.name + '.usb4-gpu-staging')
    with tmp.open('xb') as out, source.open('rb') as src:
        shutil.copyfileobj(src, out)
        out.flush()
        os.fsync(out.fileno())
    tmp.chmod(mode)
    require(tmp, expected)
    tmp.replace(target)
    os.sync()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'stage', 'activate', 'check',
                                          'restore-stock', 'restore-previous'))
    action = parser.parse_args().action
    if os.geteuid() != 0:
        raise SystemExit('Run as root (initramfs and boot verification need access).')
    subprocess.run(['mountpoint', '-q', '/boot/efi'], check=True)
    esp_device = run('findmnt', '-nro', 'SOURCE', '/boot/efi')
    if run('blkid', '-s', 'PARTUUID', '-o', 'value', esp_device) != 'bf0b62f5-e52c-4ba5-afa8-e77cd9364cf5':
        raise RuntimeError('Unexpected EFI partition')
    require(ESP / 'boot.bin.before-display-test', STOCK)

    if action == 'prepare':
        if REPORT.exists():
            raise RuntimeError('Manifest already exists; refusing to replace it')
        require(CUSTOM, OLD_CUSTOM)
        require(ESP / 'boot.bin', PREVIOUS)
        source = ROOT / 'sources/linux-usb4-backport'
        if run('git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'):
            raise RuntimeError('Kernel source is dirty')
        subprocess.run(['git', '-C', str(source), 'diff', '--exit-code',
                        '94fb23346d522edf53722357c426a3e58030beea', '--',
                        'drivers/gpu/drm/asahi', 'drivers/gpu/drm/apple', 'drivers/iommu', 'rust'], check=True)
        config = (ART / 'build/.config').read_text().splitlines()
        for line in ('CONFIG_DRM_ASAHI=y', 'CONFIG_RUST=y', 'CONFIG_USB4_APPLE_SOC=m'):
            if line not in config:
                raise RuntimeError(f'Missing {line}')
        if (ART / 'build/include/config/kernel.release').read_text().strip() != RELEASE:
            raise RuntimeError('Wrong kernel release')
        if not (ART / 'build/drivers/gpu/drm/asahi/asahi.o').is_file():
            raise RuntimeError('No built GPU object')
        if 'asahi' not in (ART / 'build/System.map').read_text():
            raise RuntimeError('No linked GPU symbols')
        custom = ART / 'custom.cfg'
        custom.write_text(CUSTOM.read_text() + ENTRY)
        subprocess.run(['grub-script-check', str(custom)], check=True)
        files = [
            (ART / 'build/arch/arm64/boot/Image', Path('/boot/vmlinuz-usb4-gpu-test'), 0o644),
            (ART / 'initramfs-usb4-gpu-test.img', Path('/boot/initramfs-usb4-gpu-test.img'), 0o600),
            (ART / 'boot.bin.usb4-gpu-test', ESP / 'boot.bin.usb4-gpu-test', 0o644),
            (ROOT / 'config/USB4-GPU-RECOVERY.txt', ESP / 'USB4-GPU-RECOVERY.txt', 0o644),
        ]
        module_source = ART / 'root/lib/modules' / RELEASE
        modules = {str(p.relative_to(module_source)): digest(p)
                   for p in sorted(module_source.rglob('*')) if p.is_file() and not p.is_symlink()}
        for name in ('thunderbolt', 'thunderbolt_apple'):
            p = module_source / f'kernel/drivers/thunderbolt/{name}.ko'
            if not run('modinfo', '-F', 'vermagic', str(p)).startswith(RELEASE + ' '):
                raise RuntimeError(f'Wrong module release: {p}')
        bundle = json.loads((ROOT / 'reports/usb4-backport/boot-bundle.json').read_text())
        require(ART / 'boot.bin.usb4-gpu-test', bundle['sha256'])
        manifest = dict(release=RELEASE, source_commit=run('git', '-C', str(source), 'rev-parse', 'HEAD'),
                        custom_hash=digest(custom), bundle_hash=bundle['sha256'], modules=modules,
                        files=[dict(source=str(s), target=str(t), sha256=digest(s), mode=m) for s, t, m in files])
        REPORT.write_text(json.dumps(manifest, indent=2) + '\n')
        print('Prepared verified staging manifest; no system boot changes.')
        return

    manifest = json.loads(REPORT.read_text())
    active = digest(ESP / 'boot.bin')
    if active not in (PREVIOUS, STOCK, manifest['bundle_hash']):
        raise RuntimeError('Unrecognized active m1n1 bundle; refusing to overwrite')
    if action.startswith('restore-'):
        name, expected = ('boot.bin.before-display-test', STOCK) if action == 'restore-stock' else ('boot.bin.before-usb4-gpu-test', PREVIOUS)
        copy_file(ESP / name, ESP / 'boot.bin', expected, replace=True)
        print(f'{action}: loader restored. Select its matching kernel on reboot. No reboot performed.')
        return

    if action == 'stage':
        if digest(CUSTOM) not in (OLD_CUSTOM, manifest['custom_hash']):
            raise RuntimeError('GRUB custom entries changed; refusing to replace')
        copy_file(ESP / 'boot.bin.thunderbolt-dpin-v2', ESP / 'boot.bin.before-usb4-gpu-test', PREVIOUS)
        backup = ART / 'custom.cfg.before-stage'
        if backup.exists():
            require(backup, OLD_CUSTOM)
        else:
            copy_file(CUSTOM, backup, OLD_CUSTOM)
        src = ART / 'root/lib/modules' / RELEASE
        target = Path('/usr/lib/modules') / RELEASE
        if target.is_symlink():
            raise RuntimeError(f'Refusing symlink: {target}')
        for name, expected in manifest['modules'].items():
            require(src / name, expected)
        if not target.exists():
            tmp = target.with_name('.' + RELEASE + '.usb4-gpu-staging')
            if tmp.exists() or tmp.is_symlink():
                raise RuntimeError(f'Staging directory exists: {tmp}')
            shutil.copytree(src, tmp, symlinks=True)
            for name, expected in manifest['modules'].items():
                require(tmp / name, expected)
            tmp.rename(target)
        for name, expected in manifest['modules'].items():
            require(target / name, expected)
        for file in manifest['files']:
            copy_file(file['source'], file['target'], file['sha256'], mode=file['mode'])
        copy_file(ART / 'custom.cfg', CUSTOM, manifest['custom_hash'], replace=True)

    require(CUSTOM, manifest['custom_hash'])
    subprocess.run(['grub-script-check', str(CUSTOM)], check=True)
    subprocess.run(['grub-script-check', '/boot/grub/grub.cfg'], check=True)
    for file in manifest['files']:
        require(file['target'], file['sha256'])
    for name, expected in manifest['modules'].items():
        require(Path('/usr/lib/modules') / RELEASE / name, expected)
    require(ESP / 'boot.bin.before-usb4-gpu-test', PREVIOUS)
    if action == 'activate':
        copy_file(ESP / 'boot.bin.usb4-gpu-test', ESP / 'boot.bin', manifest['bundle_hash'], replace=True)
    print(f'{action}: verified. Active loader: {digest(ESP / "boot.bin")}')
    print('No reboot or GRUB default change. Select: Omarchy - Asahi 7.1 GPU + USB4 (manual)')

if __name__ == '__main__':
    main()
