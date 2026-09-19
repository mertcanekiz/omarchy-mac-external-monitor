#!/usr/bin/env python3
# Decode a Thunderbolt DP adapter capability (cap id 4). Feed the debugfs regs on stdin:
#   sudo cat .../portN/regs | python3 decode-dp-cap.py
# NOTE ON MEANING (corrected after review):
#  - DP_COMMON/LOCAL/REMOTE_CAP rate/lanes come from CAPABILITY negotiation over the (tunneled) AUX.
#  - DP_COMMON_CAP.DPRX_DONE(bit31) = "receiver DPCD capability read completed over AUX".
#    It does NOT prove DP main-link training (clock-recovery/EQ/symbol-lock). That lives in the
#    sink's DPCD 0x202-0x207, which is NOT exposed on Linux for this firmware-owned tunneled AUX.
#  - Register offset 6 is AMBIGUOUS: DP_STATUS (DP-IN, allocated_bw[31:24]) vs DP_STATUS_CTRL
#    (DP-OUT: CMHS=bit25, UF=bit26). We print BOTH interpretations; pick by adapter type.
import sys
rate = {0:'RBR',1:'HBR',2:'HBR2',3:'HBR3'}
lanes = {0:1,1:2,2:4}
regs = {}
for line in sys.stdin:
    p = line.split()
    if len(p) == 5 and p[2] == '0x04':
        regs[int(p[1])] = int(p[4], 16)
def cap(v): return f"rate={rate.get((v>>8)&0xf,'?')} lanes={lanes.get((v>>12)&7,'?')} DPRX_DONE(capread)={(v>>31)&1}"
if 0 in regs: print(f"ADP_DP_CS_0   = {regs[0]:#010x}  VE={(regs[0]>>31)&1} AE={(regs[0]>>30)&1} video_hopid={(regs[0]>>16)&0x7ff}")
if 2 in regs: print(f"ADP_DP_CS_2   = {regs[2]:#010x}  HPD={(regs[2]>>6)&1}")
if 4 in regs: print(f"DP_LOCAL_CAP  = {regs[4]:#010x}  {cap(regs[4])}")
if 5 in regs: print(f"DP_REMOTE_CAP = {regs[5]:#010x}  {cap(regs[5])}")
if 6 in regs:
    v=regs[6]
    print(f"reg6          = {v:#010x}  [DP-IN read: allocated_bw={(v>>24)&0xff}] "
          f"[DP-OUT read: CMHS={(v>>25)&1} UF={(v>>26)&1}]")
if 7 in regs: print(f"DP_COMMON_CAP = {regs[7]:#010x}  {cap(regs[7])}")
if 8 in regs: print(f"ADP_DP_CS_8   = {regs[8]:#010x}  requested_bw={regs[8]&0xff} DPME={(regs[8]>>30)&1} DR={(regs[8]>>31)&1}")
