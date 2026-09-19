# SPDX-License-Identifier: MIT
#
# LG-UltraFine-over-Thunderbolt bring-up trace (M1 / t8103, front port = ATC1).
#
# Traces the DP-IN bridge + display crossbar + DP PHY on ATC1 while macOS brings the
# external display up, so we can capture the exact register sequence Linux is missing.
# Pair this with the DCP DPTX EPIC decode:
#     TRACE_DCP=dcpext  ... -m hv/trace_dcp.py -m hv/trace_dpin_bringup.py
#
# Key addresses (from the macOS ADT dump, reports/macos-dump/):
#   atc1-dpin0  @ 0x501e50000  (0x4000)  -- the DPTX_INACTIVE bit at +0x0c is our v3 hack
#   atc1-dpin1  @ 0x501e58000  (0x4000)
#   atc1-dpxbar @ 0x50304c000  (0x4000)  -- crossbar mux + FIFO/pixel-clock enables
#   atc1-dpphy                            -- DP PHY side
#
# SYNC mode traps every access in program order; these are small, low-traffic bring-up
# registers, so full ordering is worth the slowdown. Switch to ASYNC if it is too slow.

from m1n1.hv import TraceMode

DEVICES = ["atc1-dpin0", "atc1-dpin1", "atc1-dpxbar", "atc1-dpphy"]

for _dev in DEVICES:
    if _dev in hv.adt["/arm-io"]:
        trace_device("/arm-io/" + _dev, mode=TraceMode.SYNC)
        print(f"[dpin-bringup] tracing /arm-io/{_dev} (SYNC)")
    else:
        print(f"[dpin-bringup] WARNING: /arm-io/{_dev} not in ADT (wrong port? LG on ATC0?)")

# If the LG is on the other port during the trace, also try ATC0:
for _dev in ["atc0-dpin0", "atc0-dpin1", "atc0-dpxbar", "atc0-dpphy"]:
    if _dev in hv.adt["/arm-io"]:
        trace_device("/arm-io/" + _dev, mode=TraceMode.SYNC)
        print(f"[dpin-bringup] also tracing /arm-io/{_dev} (SYNC)")
