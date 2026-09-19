#!/usr/bin/env python3
"""Record existing Type-C tracepoints for two minutes, without device resets."""
import os
import argparse
from pathlib import Path
import select
import signal
import time


def interrupted(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--display', action='store_true', help='Include external DCP link events and cached connector metadata sizes')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Root is needed to access kernel tracepoints.")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    instance = Path('/sys/kernel/tracing/instances') / f'display-test-{os.getpid()}'
    instance.mkdir()
    fd = None
    enabled = []
    try:
        events = [instance / 'events/tps6598x/enable']
        if args.display:
            events.extend(sorted((instance / 'events/dcp').glob('dptxport_*/enable')))
            if len(events) == 1:
                raise RuntimeError('DCP tracepoints are unavailable')
            for event in events[1:]:
                (event.parent / 'filter').write_text('devname == "271c00000.dcp"')
            for path in sorted(Path('/sys/kernel/debug/dri').glob('*/DP-1/*')):
                if path.name in {'ColorElements', 'TimingElements', 'DisplayAttributes', 'Transport'}:
                    print(f'CACHED: {path}: {len(path.read_bytes())} bytes', flush=True)
        for event in events:
            event.write_text('1')
            enabled.append(event)
        (instance / 'tracing_on').write_text('1')
        fd = os.open(instance / 'trace_pipe', os.O_RDONLY | os.O_NONBLOCK)
        print('READY: Type-C trace enabled for 120 seconds. Reconnect the monitor cable once now.', flush=True)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], min(1, max(0, deadline - time.monotonic())))
            if readable:
                try:
                    data = os.read(fd, 65536)
                except BlockingIOError:
                    continue
                print(data.decode(errors='replace'), end='', flush=True)
    except KeyboardInterrupt:
        print('\nTrace interrupted.', flush=True)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            (instance / 'tracing_on').write_text('0')
            for event in reversed(enabled):
                event.write_text('0')
        finally:
            instance.rmdir()
        print('Trace disabled; private tracing instance removed.', flush=True)


if __name__ == '__main__':
    main()
