#!/usr/bin/env python3
"""DP-IN v3 experiment driver: select DP IN route, connect the external DCP, capture evidence.

Subcommands (all need root):
  status                      print tunnel/adapter/DRM state
  connect OUTDIR [--dpin N] [--phy-clocks N] [--prime-rate N] [--wait S]
  disconnect
  retunnel [--skip-mask MASK] rebind the front-port NHI so the thunderbolt core
                              rebuilds the DP tunnel (optionally skipping DP IN adapters)
"""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('capture', ROOT / 'scripts/collect-tunnel-registers.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)

NHI = '501f00000.nhi'
DCP = '271c00000.dcp'
RELEASE = '7.1.13-usb4-gpu-test'
PARAMS = {
    'phy_clocks': Path('/sys/module/phy_apple_atc/parameters/dpin_clocks'),
    'prime_rate': Path('/sys/module/appledrm/parameters/dpin_prime_rate'),
    'skip_mask': Path('/sys/module/thunderbolt/parameters/dp_in_skip_mask'),
    'dprx_timeout': Path('/sys/module/thunderbolt/parameters/dprx_timeout'),
}


def read(p):
    try:
        return Path(p).read_text().strip()
    except OSError as exc:
        return f'<{exc}>'


def write_once(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CLOEXEC)
    try:
        data = text.encode()
        if os.write(fd, data) != len(data):
            raise OSError(f'short write to {path}')
    finally:
        os.close(fd)


def controls():
    files = sorted({p.resolve() for p in Path('/sys/kernel/debug/dri').glob('*/DP-*/tunnel_hpd')})
    if len(files) != 1:
        raise SystemExit(f'Expected one DP-IN connector control, found {len(files)}')
    return files[0].parent


def host_router():
    for p in Path('/sys/bus/thunderbolt/devices').glob('*-0'):
        if NHI in str(p.resolve()):
            return p.name
    return None


def adapters():
    host = host_router()
    out = {}
    if not host:
        return out
    dbg = Path('/sys/kernel/debug/thunderbolt')
    for router in sorted(dbg.iterdir()):
        if not router.is_dir():
            continue
        for port in sorted(router.glob('port*')):
            regs = port / 'regs'
            if regs.is_file():
                d = capture.decode(read(regs))
                if d.get('type') in ('DP IN', 'DP OUT'):
                    out[f'{router.name}/{port.name}'] = {k: v for k, v in d.items() if k != 'registers'}
    return out


def drm():
    res = {}
    for c in Path('/sys/class/drm').glob('card*-*'):
        res[c.name] = (read(c / 'status'), len([m for m in read(c / 'modes').splitlines() if m]))
    return res


def status_dict():
    con = controls()
    return {
        'time': datetime.datetime.now().isoformat(),
        'kernel': read('/proc/sys/kernel/osrelease'),
        'tainted': read('/proc/sys/kernel/tainted'),
        'params': {k: read(v) for k, v in PARAMS.items()},
        'tunnel_hpd': read(con / 'tunnel_hpd'),
        'tunnel_dpin': read(con / 'tunnel_dpin'),
        'tb_devices': sorted(p.name for p in Path('/sys/bus/thunderbolt/devices').iterdir()),
        'adapters': adapters(),
        'drm': drm(),
    }


def show(d):
    print(json.dumps(d, indent=2))


def journal_since(ts):
    return subprocess.run(['journalctl', '-k', '-b', '--no-pager', '--since', ts],
                          capture_output=True, text=True).stdout


def cmd_status(args):
    show(status_dict())


def cmd_disconnect(args):
    con = controls()
    write_once(con / 'tunnel_hpd', '0')
    time.sleep(2)
    print('disconnected; tunnel_hpd =', read(con / 'tunnel_hpd'))


def cmd_retunnel(args):
    if args.skip_mask is not None:
        PARAMS['skip_mask'].write_text(str(args.skip_mask))
    con = controls()
    if read(con / 'tunnel_hpd') != '0':
        raise SystemExit('Disconnect the DCP first (tunnel_hpd must be 0).')
    drv = Path('/sys/bus/platform/drivers/thunderbolt-apple-nhi')
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print('unbinding NHI'); (drv / 'unbind').write_text(NHI); time.sleep(4)
    print('rebinding NHI'); (drv / 'bind').write_text(NHI)
    for _ in range(30):
        time.sleep(1)
        a = adapters()
        if any(v.get('type') == 'DP IN' and v.get('adapter_enabled') for v in a.values()):
            break
    show({'adapters': adapters(), 'tb_devices': sorted(p.name for p in Path('/sys/bus/thunderbolt/devices').iterdir())})
    print(journal_since(ts)[-4000:])


def cmd_connect(args):
    if read('/proc/sys/kernel/osrelease') != RELEASE:
        raise SystemExit('Wrong kernel')
    if int(read('/proc/sys/kernel/tainted')) & (1 << 7):
        raise SystemExit('Kernel oops in this boot; reboot first.')
    con = controls()
    if read(con / 'tunnel_hpd') != '0':
        raise SystemExit('Already requested; run disconnect first.')
    if args.phy_clocks is not None:
        PARAMS['phy_clocks'].write_text(str(args.phy_clocks))
    if args.prime_rate is not None:
        PARAMS['prime_rate'].write_text(str(args.prime_rate))
    if args.dpin is not None:
        write_once(con / 'tunnel_dpin', str(args.dpin))
    a = adapters()
    if not any(v.get('type') == 'DP IN' and v.get('adapter_enabled') for v in a.values()):
        print('WARNING: no enabled DP IN adapter (no pending tunnel).')
    args.output.mkdir(parents=True, exist_ok=False)
    before = status_dict()
    (args.output / 'before.json').write_text(json.dumps(before, indent=2))
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    instance = Path('/sys/kernel/tracing/instances') / f'dpin-v3-{os.getpid()}'
    instance.mkdir()
    result = {'write_succeeded': False, 'settings': before['params'], 'dpin': before['tunnel_dpin']}
    try:
        (instance / 'buffer_size_kb').write_text('1024')
        events = list((instance / 'events/dcp').glob('dptxport_*/enable'))
        for event in events:
            (event.parent / 'filter').write_text(f'devname == "{DCP}"')
            event.write_text('1')
        (instance / 'tracing_on').write_text('1')
        print(f'connecting (dpin={before["tunnel_dpin"]}, params={before["params"]})', flush=True)
        try:
            write_once(con / 'tunnel_hpd', '1')
            result['write_succeeded'] = True
        except OSError as exc:
            result['write_error'] = str(exc)
        for i in range(args.wait):
            time.sleep(1)
            d = drm()
            ext = {k: v for k, v in d.items() if '-DP-' in k}
            if any(v[0] == 'connected' for v in ext.values()):
                print(f'[{i+1}s] external connector: {ext}')
                break
    finally:
        (instance / 'tracing_on').write_text('0')
        (args.output / 'dptx-trace.txt').write_text(read(instance / 'trace'))
        for event in (instance / 'events/dcp').glob('dptxport_*/enable'):
            event.write_text('0')
        instance.rmdir()
        (args.output / 'journal.txt').write_text(journal_since(ts))
        after = status_dict()
        (args.output / 'after.json').write_text(json.dumps(after, indent=2))
        (args.output / 'result.json').write_text(json.dumps(result, indent=2))
    print('--- trace ---')
    print(read(args.output / 'dptx-trace.txt'))
    print('--- journal (filtered) ---')
    for line in read(args.output / 'journal.txt').splitlines():
        if any(k in line for k in ('dcp', 'atc', 'thunderbolt', 'crossbar', 'DP', 'dpin', 'phy')):
            if 'syslog message' in line and 'DPTX' not in line and 'dp' not in line.lower():
                continue
            print(line)
    print('--- adapters after ---')
    show(after['adapters'])
    print('--- drm ---')
    show(after['drm'])


def main():
    if os.geteuid():
        raise SystemExit('Run with sudo.')
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status').set_defaults(fn=cmd_status)
    sub.add_parser('disconnect').set_defaults(fn=cmd_disconnect)
    r = sub.add_parser('retunnel'); r.add_argument('--skip-mask', type=lambda s: int(s, 0)); r.set_defaults(fn=cmd_retunnel)
    c = sub.add_parser('connect')
    c.add_argument('output', type=Path)
    c.add_argument('--dpin', type=int, choices=(0, 1))
    c.add_argument('--phy-clocks', type=int, choices=(0, 1, 2, 3))
    c.add_argument('--prime-rate', type=int)
    c.add_argument('--wait', type=int, default=25)
    c.set_defaults(fn=cmd_connect)
    args = p.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
