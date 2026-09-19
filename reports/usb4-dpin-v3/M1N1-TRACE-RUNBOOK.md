# Runbook: m1n1 hypervisor trace of macOS lighting the LG UltraFine

Goal: capture the exact register + firmware sequence macOS uses to bring the LG 24MD4KL up over
Thunderbolt, so we can (a) learn whether the panel lights from DisplayPort alone or only after USB,
and (b) get the concrete recipe for whatever step Linux is missing. This is the Asahi
reverse-engineering gold standard and it removes the guessing the review flagged.

## Hardware / logistics

- **Target:** this M1 MacBook Air (t8103 / j313), with the LG on the front (left-front) USB-C port.
- **Host:** a SECOND Mac (confirmed available) with a **USB-C cable** to the target, Python 3, and a
  git checkout of this repo's `sources/m1n1-thunderbolt` (or just its `proxyclient/`). The Mac
  cannot trace itself; the hypervisor runs on the target and is driven from the host over USB serial.
- A working macOS install on the target (we have one; the LG works there with nonzero backlight).

## One-time host setup (on the second Mac)

1. Install deps: `python3 -m pip install pyserial construct` (and `pip install` anything
   `run_guest.py` complains about on first run).
2. Get the m1n1 proxyclient: use `sources/m1n1-thunderbolt/proxyclient/` from this repo (it already
   contains our trace module `hv/trace_dpin_bringup.py`). Copy that tree to the host Mac, or clone
   the repo there.
3. Build m1n1 with the hypervisor (`m1n1.macho`) per the upstream Asahi "m1n1 Hypervisor" guide
   (asahilinux.org docs, For Developers → m1n1 Hypervisor / Tethered Boot). The base tethered-boot
   and macho-build steps are exactly the upstream ones; nothing here changes them.

## Getting the target into the hypervisor with macOS as guest

Follow the upstream m1n1 hypervisor tethered-boot flow. In outline (defer to the upstream guide for
exact current commands, they version-drift):
1. On the target, boot into m1n1 **proxy** mode (the tethered stage-2 m1n1 over USB), so the host's
   `run_guest.py` can talk to it on the USB serial device (e.g. `/dev/tty.usbmodemP*` on a Mac host,
   set `M1N1DEVICE=/dev/tty.usbmodemXXX`).
2. From the host, boot macOS as the guest under the hypervisor **with our traces loaded**:

```sh
cd sources/m1n1-thunderbolt/proxyclient
export M1N1DEVICE=/dev/tty.usbmodemXXXX      # the target's USB serial (find with ls /dev/tty.usbmodem*)
export TRACE_DCP=dcpext                       # trace the EXTERNAL DCP (the LG), not the internal panel
python3 tools/run_guest.py \
    -m hv/trace_dcp.py \                       # DCP DPTX EPIC calls (get_max_lane_count, activate, set_link_rate, ...)
    -m hv/trace_atc.py \                       # ATC PHY + dwc3 (DP clocks / pipehandler)
    -m hv/trace_dpin_bringup.py \              # OUR module: atc1-dpin0/dpin1/dpxbar/dpphy MMIO (the crossbar + DP-IN bridge)
    -l dpin-trace.log \                        # capture everything to a file
    <macos-boot-payload> [boot_args...]
```
The `<macos-boot-payload>` is the macOS boot object per the upstream guide (kernelcache / boot.bin
prepared for the hypervisor). If macOS is too heavy to fully boot under the hypervisor on first try,
the upstream guide covers `--strip-node` and CPU limiting; our traces do not require a full desktop,
only that the external-display bring-up path runs.

## During the trace

1. Let macOS boot to the point where it drives displays.
2. With the LG connected on the front port, make macOS (re)enumerate it: if it is already up, unplug
   and replug the LG (or sleep/wake the display) so the whole bring-up sequence is captured live.
3. Watch `dpin-trace.log` fill. Stop once you see the DCP DPTX `activate` / `set_link_rate` calls
   followed by crossbar writes and (if any) the USB/HID backlight traffic.

## What to extract from the log (the two questions)

1. **Does the panel light from DisplayPort alone, or only after USB?**
   - Look at the ordering: do the `atc1-dpin0` / `atc1-dpxbar` writes + DCP `activate`/`set_link_rate`
     complete and the panel come on BEFORE any USB/HID activity? If yes, the video path is the whole
     story and Linux is missing DP-side register writes (compare against what our v3 does).
   - If the panel only lights after USB "Display Controls" HID traffic, the backlight is genuinely
     USB-gated and the PCIe/USB path is mandatory.

2. **The exact DP-IN / crossbar bring-up sequence.** Diff the macOS `atc1-dpin0` (0x501e50000) and
   `atc1-dpxbar` (0x50304c000) writes against the Linux v3 flow (`patches/thunderbolt-dpin-v3-experiment.patch`
   + the `/dev/mem` `501e5000c` hack). We already know macOS does `makeDPINAdapterPortActive`
   (DPTX_INACTIVE=0) and `bringConnectionUp` (pclk_sel=1); the trace gives the actual register writes
   for `bringConnectionUp` and anything else after modeset. Fold those into the kernel driver.

## Known caveats

- `trace_dcp.py` defaults to `dcp0`; we override with `TRACE_DCP=dcpext` for the external controller.
  If the external DCP has a different alias in the ADT on this exact build, check `/arm-io/aliases`
  (`dcpext` was present in the macOS ADT) and set `TRACE_DCP` to match.
- The LG's USB rides a PCIe tunnel; tracing that tunneled xHCI is harder than the DP path (it is not
  the built-in `usb-drd1`). The first trace should nail the DP question; a follow-up trace can add
  the ACIO/PCIe ranges (`/arm-io/acio1`, `/arm-io/apciec1*`) if question 1 shows USB is required.
- Our trace module `hv/trace_dpin_bringup.py` uses SYNC mode (full ordering). If macOS is unusably
  slow, edit it to `TraceMode.ASYNC`.

## After the trace

Copy `dpin-trace.log` back into this repo under `reports/usb4-dpin-v3/` and a fresh session can turn
the captured `bringConnectionUp` / USB sequence into driver changes. Update `HANDOFF.md` with the
answer to question 1 — it decides whether the next work is DP-side (small) or PCIe/USB (large).

## Tracked copy of the trace module

`sources/` is git-ignored, so the trace module is also kept at `config/m1n1-hv/trace_dpin_bringup.py`.
Copy it into `proxyclient/hv/` of whichever m1n1 checkout you run the hypervisor from.
