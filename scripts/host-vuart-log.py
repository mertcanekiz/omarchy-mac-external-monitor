#!/usr/bin/env python3
"""Log the m1n1 virtual UART (guest serial console) ACM port to a file with host timestamps.
usage: host-vuart-log.py /dev/cu.usbmodemXXXX3 ~/dpin-guest-console.log"""
import sys, time, serial
dev, out = sys.argv[1], sys.argv[2]
with open(out, "ab", buffering=0) as f:
    while True:
        try:
            with serial.Serial(dev, 115200, timeout=0.5) as s:
                f.write(f"# opened {dev} {time.strftime('%H:%M:%S')}\n".encode())
                buf = b""
                while True:
                    data = s.read(4096)
                    if not data:
                        continue
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        f.write(time.strftime("%H:%M:%S ").encode() + line.rstrip(b"\r") + b"\n")
        except (serial.SerialException, OSError) as e:
            f.write(f"# {time.strftime('%H:%M:%S')} port error: {e}; retrying\n".encode())
            time.sleep(1)
