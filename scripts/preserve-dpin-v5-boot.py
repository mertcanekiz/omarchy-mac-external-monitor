#!/usr/bin/env python3
"""Preserve verified v5 boot inputs and exercise the packaged m1n1 updater.

Run as root. Does not reboot. Refuses unrelated existing configuration.
The original stock EFI recovery image is never modified.
"""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
LOCAL = Path('/usr/local/share/asahi-dpin-v5')
CONFIG = Path('/etc/default/update-m1n1')
ESP = Path('/boot/efi/m1n1')
STOCK = '566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33'
V5 = '195a5df61a12e226f5b0aa2a332e991c023d9c8af991c363acdfb957ea405d49'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def atomic_write(path, data, mode=0o644):
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    require(os.geteuid() == 0, 'Run as root.')
    subprocess.run(['mountpoint', '-q', '/boot/efi'], check=True)
    partuuid = subprocess.check_output(
        ['findmnt', '-n', '-o', 'PARTUUID', '-T', str(ESP)], text=True).strip()
    require(partuuid == 'bf0b62f5-e52c-4ba5-afa8-e77cd9364cf5', 'Wrong EFI partition.')
    require(digest((ESP / 'boot.bin.before-display-test').read_bytes()) == STOCK,
            'Stock recovery backup does not match.')
    bundle = (ESP / 'boot.bin.usb4-dpin-v5').read_bytes()
    require(digest(bundle) == V5, 'Saved v5 bundle does not match.')
    manifest = json.loads((ROOT / 'reports/usb4-dpin-v5/boot-bundle.json').read_text())
    stage = json.loads((ROOT / 'reports/usb4-dpin-v5/stage-manifest.json').read_text())
    require(manifest['sha256'] == V5 and stage['bundle'] == V5, 'Manifest mismatch.')
    require(digest(Path('/boot/initramfs-usb4-dpin-v5.img').read_bytes()) == stage['initramfs'],
            'Installed v5 initramfs changed.')
    for name, expected in stage['modules'].items():
        p = Path('/usr/lib/modules/7.1.13-usb4-gpu-test/kernel/drivers') / name
        require(digest(p.read_bytes()) == expected, f'Installed module changed: {name}')
    require(not Path('/etc/m1n1.conf').exists(), 'Review existing m1n1 options first.')
    config = (ROOT / 'config/update-m1n1-dpin-v5').read_bytes()
    old_config = CONFIG.read_bytes() if CONFIG.exists() else None
    require(old_config in (None, config), 'Existing updater configuration needs review.')
    inputs = {}
    uboot = None
    for c in manifest['components']:
        data = bundle[c['offset']:c['offset'] + c['bytes']]
        require(digest(data) == c['sha256'], f'Invalid component: {c["name"]}')
        require(Path(c['name']).name == c['name'], 'Invalid component name.')
        if c['kind'] == 'loader':
            inputs[LOCAL / 'm1n1.bin'] = data
        elif c['kind'] in ('installed-dtb', 'custom-dtb'):
            inputs[LOCAL / 'dtbs' / c['name']] = data
        elif c['kind'] == 'uboot':
            uboot = c
    require(uboot is not None, 'Missing U-Boot component.')
    installed_uboot = Path('/usr/lib/asahi-boot/u-boot-nodtb.bin').read_bytes()
    require(gzip.decompress(bundle[uboot['offset']:uboot['offset'] + uboot['bytes']])
            == installed_uboot, 'U-Boot changed: review before activating.')
    checksums = ''.join(f'{digest(data)}  {p}\n' for p, data in sorted(inputs.items()))
    inputs[LOCAL / 'SHA256SUMS'] = checksums.encode()
    for p, data in inputs.items():
        require(not p.exists() or p.read_bytes() == data, f'Local input differs: {p}')
    backup = Path('/var/backups/asahi-dpin-v5') / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True, mode=0o700)
    shutil.copyfile(ESP / 'boot.bin', backup / 'boot.bin.before')
    if old_config is not None:
        (backup / 'update-m1n1.before').write_bytes(old_config)
    for p, data in inputs.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(p, data)

    def verify(path):
        data = path.read_bytes()
        require(data[:uboot['offset']] == bundle[:uboot['offset']],
                f'{path}: loader/device trees differ from known-good v5.')
        require(gzip.decompress(data[uboot['offset']:]) == installed_uboot,
                f'{path}: incorrect U-Boot payload.')
        return digest(data)

    try:
        atomic_write(CONFIG, config)
        candidate = backup / 'boot.bin.candidate'
        subprocess.run(['/usr/bin/update-m1n1', str(candidate)], check=True)
        candidate_hash = verify(candidate)
        print('PASS: packaged updater generated verified v5 loader + device trees + U-Boot.', flush=True)
        # Exercise the exact no-argument invocation used by the pacman hook.
        subprocess.run(['/usr/bin/update-m1n1'], check=True)
        active_hash = verify(ESP / 'boot.bin')
        require(active_hash == candidate_hash, 'Active image differs from verified candidate.')
        os.sync()
    except BaseException:
        atomic_write(ESP / 'boot.bin', (backup / 'boot.bin.before').read_bytes())
        if old_config is None:
            CONFIG.unlink(missing_ok=True)
        else:
            atomic_write(CONFIG, old_config)
        os.sync()
        raise
    result = dict(active_sha256=active_hash, known_good_v5=V5,
                  verified='Identical uncompressed boot components; gzip encoding may differ.',
                  config=str(CONFIG), inputs=str(LOCAL), backup=str(backup), reboot_required=True)
    (backup / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
