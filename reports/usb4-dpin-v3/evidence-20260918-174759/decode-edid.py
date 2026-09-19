#!/usr/bin/env python3
# Usage: python3 decode-edid.py 04-dp1.edid   -> prints header validity, PnP vendor, name, serial.
import sys
d = open(sys.argv[1], 'rb').read()
print("valid header:", d[:8] == bytes([0,255,255,255,255,255,255,0]))
m = (d[8] << 8) | d[9]
print("manufacturer:", ''.join(chr(((m >> (5*i)) & 31) + 64) for i in (2,1,0)))
for off in (54, 72, 90, 108):
    b = d[off:off+18]
    if b[0:3] == b'\x00\x00\x00' and b[3] in (0xFC, 0xFF):
        print({0xFC:'name',0xFF:'serial'}[b[3]] + ":", b[5:18].split(b'\n')[0].decode('ascii','replace'))
