#!/usr/bin/env python3
"""Read-only GPU/USB4 baseline check after booting the 7.1 backport."""
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
RELEASE = '7.1.13-usb4-gpu-test'

def read(path):
    try:
        return path.read_text().strip()
    except OSError as error:
        return {'error': str(error)}

def command(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'error': str(error)}

def main():
    kernel = command('uname', '-r')
    boot_id = read(Path('/proc/sys/kernel/random/boot_id'))
    if kernel.get('stdout', '').strip() != RELEASE:
        print(f'Not running {RELEASE}; no successful boot can be claimed.')
        print(kernel.get('stdout', kernel))
        return 1
    renderer = command(str(ROOT / 'artifacts/check-renderer'))
    render_nodes = [str(p) for p in Path('/dev/dri').glob('renderD*')]
    devices = {}
    thunderbolt = Path('/sys/bus/thunderbolt/devices')
    if thunderbolt.exists():
        for device in sorted(thunderbolt.iterdir()):
            devices[device.name] = {
                key: read(device / key)
                for key in ('device_name', 'vendor_name', 'authorized', 'unique_id',
                            'rx_speed', 'tx_speed', 'generation', 'security')
                if (device / key).is_file()
            }
    checks = {
        'expected_kernel': True,
        'gpu_render_node': bool(render_nodes),
        'hardware_renderer': renderer.get('returncode') == 0 and 'Apple' in renderer.get('stdout', ''),
        'usb4_domain': any(name.startswith('domain') for name in devices),
        'authorized_thunderbolt_device': any(
            re.fullmatch(r'\d+-[0-9a-f]+', name) and name.split('-', 1)[1] != '0'
            and d.get('authorized') == '1' for name, d in devices.items()),
    }
    result = dict(
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        boot_id=boot_id, kernel=kernel, cmdline=read(Path('/proc/cmdline')),
        checks=checks, renderer=renderer, render_nodes=render_nodes, thunderbolt=devices,
        usb_tree=command('lsusb', '-tv'),
        kernel_log=command('journalctl', '-k', '-b', '--no-pager', '--grep',
                           'asahi|drm|dcp|gpu|thunderbolt|usb4|acio|nhi|SError|Oops|panic'),
        note='Authorization/enumeration does not verify USB3 tunneling or external DisplayPort output.',
    )
    output = Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT / f'reports/usb4-backport/boot-{boot_id}.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(checks, indent=2))
    print(f'Evidence saved to {output}')
    return 0 if all(checks.values()) else 1

if __name__ == '__main__':
    if len(sys.argv) > 2:
        raise SystemExit('Usage: verify-usb4-gpu-boot.py [new-output.json]')
    raise SystemExit(main())
