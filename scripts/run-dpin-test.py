#!/usr/bin/env python3
"""After the DP-IN boot, capture a single manual connection attempt."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import time

import importlib.util

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('capture', ROOT / 'scripts/collect-tunnel-registers.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def check(revision='v1'):
    if os.geteuid():
        raise SystemExit('Run with sudo.')
    suffix = '' if revision == 'v1' else '-v2'
    # An oops leaves driver/probe state unreliable, even when this module matches.
    if int(Path('/proc/sys/kernel/tainted').read_text()) & (1 << 7):
        raise SystemExit('This boot has a kernel oops; reboot before a connection attempt.')
    expected = subprocess.check_output(['readelf', '-n', str(ROOT / f'artifacts/thunderbolt-dpin{suffix}/appledrm.ko')], text=True)
    match = re.search(r'Build ID: ([0-9a-f]+)', expected)
    note = Path('/sys/module/appledrm/notes/.note.gnu.build-id').read_bytes()
    namesz, descsz, kind = struct.unpack_from('<III', note)
    start = 12 + ((namesz + 3) & ~3)
    if not match or kind != 3 or note[start:start + descsz].hex() != match.group(1):
        raise SystemExit('Experimental appledrm is not loaded; boot the DP-IN entry first.')
    controls = sorted({p.resolve() for p in Path('/sys/kernel/debug/dri').glob('*/DP-*/tunnel_hpd')})
    if len(controls) != 1:
        raise SystemExit(f'Expected exactly one experimental DP connector, found {len(controls)}.')
    if Path('/sys/module/thunderbolt/parameters/dprx_timeout').read_text().strip() != '-1':
        raise SystemExit('DP receiver timeout override is missing from this boot.')
    routers = Path('/sys/bus/thunderbolt/devices')
    hosts = [p for p in routers.glob('*-0') if '501f00000.nhi' in str(p.resolve())]
    if len(hosts) != 1:
        raise SystemExit('Expected the front-port NHI at 501f00000 to be active.')
    dp = Path('/sys/kernel/debug/thunderbolt') / hosts[0].name / 'port5/regs'
    decoded = capture.decode(dp.read_text())
    if decoded.get('type') != 'DP IN' or not decoded.get('adapter_enabled'):
        raise SystemExit('DP-IN 0 has no enabled pending tunnel. Capture state before retrying.')
    if controls[0].read_text().strip() != '0':
        raise SystemExit('A firmware connection is already requested. Capture/review before retrying.')
    return controls[0]


def request_once(control):
    # Buffered text I/O can retry a failed flush during close. A debugfs write
    # is a hardware command, so never allow a close-time replay after timeout.
    fd = os.open(control, os.O_WRONLY | os.O_CLOEXEC)
    try:
        if os.write(fd, b'1') != 1:
            raise OSError('Short display-control write; not retrying.')
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--revision', choices=['v1', 'v2'], default='v1')
    parser.add_argument('output', type=Path, nargs='?')
    args = parser.parse_args()
    control = check(args.revision)
    if args.check_only:
        print(f'Ready for one connection attempt through {control}')
        return
    if args.output is None:
        parser.error('Specify a new output directory.')
    args.output.mkdir(parents=True, exist_ok=False)
    def snapshot(name):
        subprocess.run(['python3', str(ROOT / 'scripts/collect-tunnel-registers.py'),
                        str(args.output / name)], check=True)
    snapshot('before.json')
    instance = Path('/sys/kernel/tracing/instances') / f'dpin-test-{os.getpid()}'
    instance.mkdir()
    result = {'control': str(control), 'write_succeeded': False,
              'note': 'A successful write only means a firmware request, not display output.'}
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        (instance / 'buffer_size_kb').write_text('1024')
        events = list((instance / 'events/dcp').glob('dptxport_*/enable'))
        if not events:
            raise RuntimeError('No DPTX tracepoints are available.')
        for event in events:
            (event.parent / 'filter').write_text('devname == "271c00000.dcp"')
            event.write_text('1')
        (instance / 'tracing_on').write_text('1')
        print('Recording DCP callbacks; issuing one connection request.', flush=True)
        try:
            request_once(control)
            result['write_succeeded'] = True
        except OSError as exc:
            result['write_error'] = str(exc)
        time.sleep(20)
    finally:
        (instance / 'tracing_on').write_text('0')
        (args.output / 'dptx-trace.txt').write_text((instance / 'trace').read_text())
        for event in (instance / 'events/dcp').glob('dptxport_*/enable'):
            event.write_text('0')
        instance.rmdir()
        (args.output / 'request.json').write_text(json.dumps(result, indent=2) + '\n')
        snapshot('after.json')
    print(f'Capture complete: {args.output}. Inspect DRM modes and DPRX_DONE, then verify the picture.')


if __name__ == '__main__':
    main()
