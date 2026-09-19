#!/usr/bin/env python3
"""Stage, activate, or restore the DP-IN test. Never reboot automatically."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
ESP = Path('/boot/efi/m1n1')
BASE = '9602d026b2960bf308e3cc7a9d14019abeed4b7ccaa387125241073660b7c297'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def install(path, data, mode=0o644, previous=None):
    if path.is_symlink():
        raise SystemExit(f'Refusing symlink {path}')
    if path.exists():
        existing = path.read_bytes()
        if existing == data:
            return
        if previous is None or sha(existing) != previous:
            raise SystemExit(f'Unexpected existing file: {path}')
    temp = path.with_name(path.name + '.dpin-staging')
    with temp.open('xb') as output:
        os.chmod(temp, mode)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp, path)
    os.sync()
    if path.read_bytes() != data:
        raise SystemExit(f'Installed file verification failed: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'activate', 'restore'])
    parser.add_argument('--revision', choices=['v1', 'v2'], default='v1')
    args = parser.parse_args()
    suffix = '' if args.revision == 'v1' else '-v2'
    name = 'thunderbolt-dpin' + suffix
    if os.geteuid():
        raise SystemExit('Run with sudo.')
    subprocess.run(['mountpoint', '-q', '/boot/efi'], check=True)
    source = subprocess.check_output(['findmnt', '-nro', 'SOURCE', '/boot/efi'], text=True).strip()
    uuid = subprocess.check_output(['blkid', '-s', 'PARTUUID', '-o', 'value', source], text=True).strip()
    if uuid != 'bf0b62f5-e52c-4ba5-afa8-e77cd9364cf5':
        raise SystemExit('Unexpected EFI partition.')
    manifest = json.loads((ROOT / f'reports/thunderbolt/dpin{suffix}-artifacts.json').read_text())
    candidate_path = ROOT / f'artifacts/{name}/boot.bin.{name}'
    candidate_hash = manifest['files'][str(candidate_path.relative_to(ROOT))]
    active = ESP / 'boot.bin'
    current_hash = sha(active.read_bytes())
    allowed = {BASE, candidate_hash}
    if args.revision == 'v2':
        # The first candidate is preserved; permit upgrading that exact bundle.
        allowed.add('6c22c07bd01d04bb532afe3a62e0aee54abbcd46996ec05b06d6663b15e9fa6e')
    if current_hash not in allowed:
        raise SystemExit('Active bundle changed outside this experiment.')
    backup = ESP / 'boot.bin.before-thunderbolt-dpin'
    if args.action == 'restore':
        saved = backup.read_bytes()
        if sha(saved) != BASE:
            raise SystemExit('Invalid recovery bundle.')
        install(active, saved, previous=current_hash)
        print('Restored USB4 baseline bundle. No reboot performed.')
        return
    if args.action == 'activate':
        subprocess.run(['python3', str(ROOT / 'scripts/verify-dpin-test.py'),
                        '--revision', args.revision], check=True)
    for relative, expected in manifest['files'].items():
        if sha((ROOT / relative).read_bytes()) != expected:
            raise SystemExit(f'Artifact checksum changed: {relative}')
    if sha(Path('/boot/vmlinuz-thunderbolt-test').read_bytes()) != manifest['kernel_sha256']:
        raise SystemExit('Kernel checksum changed.')
    original = ROOT / 'artifacts/boot.bin.thunderbolt-test'
    if sha(original.read_bytes()) != BASE:
        raise SystemExit('Baseline recovery source changed.')
    install(backup, original.read_bytes())
    install(ESP / f'boot.bin.{name}', candidate_path.read_bytes())
    image = ROOT / f'artifacts/{name}/initramfs-{name}.img'
    install(Path(f'/boot/initramfs-{name}.img'), image.read_bytes(), 0o600)

    custom = Path('/boot/grub/custom.cfg')
    baseline = (ROOT / 'config/thunderbolt-custom.cfg').read_bytes()
    if args.revision == 'v2':
        baseline += (ROOT / 'config/thunderbolt-dpin-grub-entry.cfg').read_bytes()
    entry_path = ROOT / f'config/{name}-grub-entry.cfg'
    entry = entry_path.read_bytes()
    subprocess.run(['grub-script-check', str(entry_path)], check=True)
    if custom.read_bytes() not in (baseline, baseline + entry):
        raise SystemExit('GRUB custom entries changed; preserve and review before adding this entry.')
    install(Path(f'/boot/grub/custom.cfg.before-{name}'), baseline)
    install(custom, baseline + entry, previous=sha(baseline))
    subprocess.run(['grub-script-check', str(custom)], check=True)
    if args.action == 'activate':
        install(active, candidate_path.read_bytes(), previous=current_hash)
        print(f'DP-IN {args.revision} bundle activated for the next boot. Choose its matching experiment entry.')
    else:
        print('DP-IN target staged. Active loader bundle is unchanged.')
    print('No reboot performed. The module override exists only in the new initramfs.')


if __name__ == '__main__':
    main()
