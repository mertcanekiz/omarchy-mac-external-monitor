# DP-over-Thunderbolt bring-up — handoff for the next agent

Last updated 2026-09-19 (early hours). Written so a fresh session can continue with no prior context.

For an adversarial review packet (claims + reproducible proof + threats to validity), see
`reports/usb4-dpin-v3/REVIEW.md` and the `evidence-*/` bundle it cites.

Next planned step: an m1n1 hypervisor trace of macOS lighting the LG. See
`reports/usb4-dpin-v3/M1N1-TRACE-RUNBOOK.md` and the trace module
`sources/m1n1-thunderbolt/proxyclient/hv/trace_dpin_bringup.py`.

## Goal

Make the **LG 24MD4KL UltraFine** (Thunderbolt 3 monitor) show a picture on an **M1 MacBook Air
(j313 / t8103)** running Asahi/Omarchy Linux. The monitor exposes DisplayPort only through a
Thunderbolt DP tunnel; there is no plain DP-alt path to it on this hardware.

## TL;DR status

**The DisplayPort-over-Thunderbolt tunnel NEGOTIATES: the tunnel is established host-side, and the
host reads a valid EDID (7 modes) from the monitor over the tunneled AUX channel. But a working
PICTURE is NOT demonstrated — the panel looks dead (no faint LCD image even under a raking light,
per the user), which means the LCD is not being driven at all, not merely unlit.** Live register
reads show the DP tunnel is CONFIGURED and the tunneled AUX reaches the monitor: host DP-IN
`DP_COMMON_CAP` `DPRX_DONE=1` (receiver capability read done over AUX — NOT proof of main-link
training; see REVIEW.md corrections), negotiated HBR2 x4, LG DP-OUT HPD=1/VE=1. **Main-link training
status is NOT observable from the host** (no DPCD/AUX access; DCP firmware owns the tunneled AUX),
so we do not claim link-lock or pixel delivery. What drives the LCD (the monitor's internal
scaler/TCON) and the backlight are, on the UltraFine, powered/managed over the monitor's **USB**
link — and there is no USB on Linux, because the LG's USB rides a **PCIe tunnel** (the router has
no native USB3 adapter) and PCIe tunneling is not wired on M1 Asahi (no host apciec PCIe controller
in the device tree; tunnel activation fails with -107). So the remaining work is a **separate,
larger subsystem** (PCIe tunnel + host apciec + xHCI + LG USB hub + "Display Controls" HID +
backlight/scaler bring-up), not more DP work.

Two earlier overclaims to NOT repeat: (1) "consumed bandwidth 0 / DP bandwidth bring-up is the
blocker" — wrong, stale log line before DPRX finished. (2) "video reaches the panel, only the
backlight is off" — NOT established; EDID+AUX only prove the receiver answers, and the dead-looking
panel is evidence the LCD is not being driven. Do not claim a working picture without a webcam
frame that actually shows one.

What works now (all reproducible on the DP-IN v3 boot):
- Thunderbolt/USB4 transport: Apple NHI at `501f00000`, LG router `0-1` authorized, retimer seen.
- The thunderbolt core builds the DP tunnel `0:5 <-> 1:10` and holds it (`dprx_timeout=-1`).
- The external display controller (`dcpext`, `271c00000.dcp`) boots, and after the fix below the
  TB connection manager configures the DP tunnel (AUX+Video paths activated), both adapters set
  Video-Enable, the sink asserts HPD, and the DP-IN adapter completes a **receiver capability read**
  over the tunneled AUX (`DP_COMMON_CAP DPRX_DONE=1`, negotiated **HBR2 x4**). The controller sets
  **3840x2160@60**, submits+completes frames, DP-1 shows 7 modes with real EDID. (DPRX_DONE is an
  AUX capability-read bit; it is NOT proof of main-link training — see REVIEW.md.)

What does NOT work (the wall):
- **No picture.** The panel looks dead (no faint LCD image under a raking light). The tunneled AUX
  reaches the monitor (EDID + capability read), but **DP main-link training at the sink is not
  verifiable from the host**, and no pixels are shown to reach the LCD. The leading (unproven)
  hypothesis is the monitor's **internal scaler/TCON + backlight** are USB-managed and not driven. On the
  UltraFine that scaler board and the backlight are powered/configured over the monitor's **USB**
  link, and there is no USB on Linux (see the PCIe-tunnel blocker below). Always confirm any claimed
  picture with an actual webcam frame (`scripts/webcam-snap.sh`).

## Source trees on GitHub (the `sources/` dir is gitignored here)

- Kernel: **https://github.com/mertcanekiz/linux** (fork of AsahiLinux/linux). Branches
  `thunderbolt-7.1.13-dpin-v3` (active), `thunderbolt-7.1.13-gpu` (baseline), `thunderbolt-7.1.13-dpalt`.
- m1n1: **https://github.com/mertcanekiz/m1n1** (fork of AsahiLinux/m1n1). Branch `thunderbolt-dpin-trace`
  (adds `proxyclient/hv/trace_dpin_bringup.py`).

To recreate `sources/` from scratch:
```sh
git clone -b thunderbolt-7.1.13-dpin-v3 https://github.com/mertcanekiz/linux sources/linux-usb4-backport
git clone -b thunderbolt-dpin-trace   https://github.com/mertcanekiz/m1n1  sources/m1n1-thunderbolt
```

## The environment

- Running kernel on the test boot: `7.1.13-usb4-gpu-test` (aarch64). `uname -r` must show this.
- GRUB entry: **Omarchy - Asahi 7.1 USB4 DP-IN v3 (manual)**. cmdline adds
  `thunderbolt.dprx_timeout=-1 thunderbolt.dyndbg=+p`.
- Kernel source worktree: `sources/linux-usb4-backport`, branch `thunderbolt-7.1.13-dpin-v3`
  (WIP commit on top of `5f7d34c835af`). Build the base first, then the v3 driver changes.
- Keep the LG on the **front (left-front) USB-C port** with the Thunderbolt cable during boot.

## Reproduce the current best result (gets the link trained, still no picture)

```sh
cd /home/mert/Work/omarchy-mac-external-monitor
uname -r                                   # must be 7.1.13-usb4-gpu-test
sudo python3 scripts/run-dpin-v3.py status # expect 0-0/port5 DP IN adapter_enabled, dprx_done false

# The macOS "makeDPINAdapterPortActive" step, done by hand via /dev/mem:
sudo artifacts/mmio/mmio-rw w 501e5000c 0            # clear DPTX_INACTIVE on atc1-dpin0
sudo artifacts/mmio/mmio-rw p 501e50010 0 1 500      # wait DPTX_INACTIVE_ACK -> 0

sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v3/<new-dir> --dpin 0
# -> DPRX capabilities read completed, HBR2 x4, DP-1 connected 7 modes, DCP modeset 3840x2160@60
```

If the Thunderbolt link ever drops (a physical replug, or the `04:44` unplug we saw), the bridge
bit resets and Hyprland still thinks DP-1 is active. Full recovery:
```sh
sudo python3 scripts/run-dpin-v3.py disconnect
sudo artifacts/mmio/mmio-rw w 501e5000c 0 && sudo artifacts/mmio/mmio-rw p 501e50010 0 1 500
sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v3/<new-dir> --dpin 0
# then in Hyprland force a fresh modeset (DPMS off/on DP-1), see "Hyprland notes" below
```

## Remaining blocker: leading hypothesis is USB-managed scaler/backlight (see REVIEW.md rev 2)

Decoded the live TB adapter registers against `drivers/thunderbolt/tb_regs.h` (corrected decoder in
`evidence-*/decode-dp-cap.py`):
- Host DP-IN `0-0/port5` `ADP_DP_CS_0 = 0xc0090400` → `VE`(bit31)=1, `AE`(bit30)=1, video hopid 9.
  `DP_COMMON_CAP = 0xaa402214` → HBR2 / 4 lanes, `DPRX_DONE=1` (AUX capability read done — NOT
  main-link training).
- LG DP-OUT `0-1/port10` `ADP_DP_CS_0 = 0xc009044f` → `VE`=1; reg6 `0x04000204` = `DP_STATUS_CTRL`
  with `UF`(bit26)=1 — **not** "allocated_bw=4" (that was a rev-1 mis-decode).
- `sudo cat /sys/class/drm/card2-DP-1/edid | wc -c` = **384** (base + 2 ext; EDID read over AUX).

We do NOT claim video reaches the LCD. The tunneled AUX reaches the monitor (EDID + capability
read), but main-link training/pixel delivery are not observable from the host. The **leading
hypothesis** (not proven — no causal experiment) is the panel is dark because the monitor's
scaler/backlight are host-controlled over USB. macOS ioreg (`reports/macos-dump/ioreg.txt`) shows
the LG exposes USB devices **"LG UltraFine Display Controls"** (HID) and **"LG UltraFine Display
Audio"**, behind **"USB3.1 Hub"/"USB2.1 Hub"**. The m1n1 trace (see runbook) is meant to confirm or
refute this before committing to the large PCIe/USB build.

Why USB never comes up on Linux:
- The LG router has **no native USB3 adapter** — only DP and PCIe. So its USB (an xHCI) sits behind
  its internal PCIe, reachable only via a **PCIe tunnel**.
- The host router (`0-0`) has a PCIe-DOWN adapter (port 3). `tb_tunnel_pci` runs and writes the
  path hops, but activation fails: `PCIe Down path activation failed: -107` (ENOTCONN) →
  `1:8: PCIe tunnel activation failed, aborting`.
- Structurally: **there is no host PCIe controller for tunneled devices in the Linux device tree.**
  `/proc/device-tree/soc/cio@501ac0000/` has only `nhi`, `iommu`, `ports/port@1` — no apciec/pcie
  child. macOS's ACIO is itself an `ApplePCIEHostBridge` (acio1 ADT has `IOPCITunnelControllerID`,
  `function-pcie_port_control`, `portmap`, `link-speed/width-default`, `apple,tunable-pcie-adapter`).
  The USB4 backport DT/m1n1 only exposed the NHI+IOMMU, not the tunneled-PCIe root complex.

So to get a picture, the path is: **m1n1/DT expose the ACIO apciec PCIe root complex (with its
tunables from the macOS ADT) → a pcie-apple driver that binds it and accepts the tunneled bus → fix
the TB PCIe tunnel activation (-107) → xHCI enumerates the LG hub → bind "LG UltraFine Display
Controls" HID → send the brightness/backlight-on command.** This is substantial new work
(essentially PCIe-tunneling bring-up on M1, which Asahi has not done) and is NOT a tonight task.

Cheap things worth trying first (low confidence): power-cycle the LG at the wall with the DP tunnel
already up, in case its firmware self-lights the backlight on stable DP; or check whether any
`ddcutil`/DPCD brightness path exists (the UltraFine is widely reported NOT to support DDC/CI, and
Linux has no raw AUX access to this firmware-owned tunneled link, so expect this to fail).

## (Superseded) earlier bandwidth theory, with evidence

The Apple DP-IN adapter (a Thunderbolt adapter inside the host ACIO router, port 5) never gets its
**requested/allocated bandwidth** programmed, so the tunnel carries no video.

- Host DP-IN `0-0/port5` DP capability, cap_id 4 relative regs (read via debugfs):
  `rel6 (DP_STATUS) = 0x00000000` → allocated bandwidth 0.
- LG DP-OUT `0-1/port10` `rel6 = 0x04000000`.
- Kernel: `0:5 <-> 1:10 (DP): consumed bandwidth 0/17280 Mb/s`.
- macOS doing the same connection (see `reports/macos-dump/kernel-log.txt`):
  `Thunderbolt DP - activating Video path - SRC [1:0x0:0x5] DST [1:0x1:0xa] - req_bandwidth = 259`
  then `= 159`. So macOS programs ~159 units of video bandwidth; Linux programs 0.

The macOS driver stack that does this: `AppleThunderboltDPInAdapter` +
`AppleATCDPINAdapterPort` (in the `AppleDisplayCrossbar` kext) +
`AppleThunderboltDPAdapterFamily`. The relevant macOS op sequence, from the log, after the DCP
`DisplayRequest`:
1. `AppleT8103ATCDPXBAR::validateConnection: dispext0,0 -> atc1,1 (atc1-dpin0)`
2. `AppleATCDPINAdapterPort::makeDPINAdapterPortActive: set DPTX_INACTIVE=0, poll DPTX_INACTIVE_ACK=0`
   **(this is the /dev/mem write we replicated — it is what made the link train)**
3. `activate` → firmware AP calls (get_supports_hpd, get_max_lane_count, activate)
4. `willChangeLinkConfiguration` → `setActiveLaneCount(0)` → `setLinkRate(HBR2, PHY pclk1)`
5. `AppleT8103ATCDPXBAR::bringConnectionUp: dispext0,0 -> atc1,1; ufpBit=0x1 dfpBit=0x1 pclk=PCLK1 (pclk_sel=1)`
6. `setActiveLaneCount(4)` → `setDriveSettings` → video path carries pixels → panel lights.

On Linux the firmware AP-call sequence (steps 3-6, minus the crossbar bring-up specifics) now runs
correctly — the trace shows `set_link_rate 0x14`, `set_active_lane_count`, `did_change_link_config`
etc. But the **tunnel bandwidth stays 0**, so the working theory is that either:
- (H1) the DP-IN adapter's `ADP_DP_CS_8 REQUESTED_BW` / `DP_STATUS` in Thunderbolt config space
  must be written by the host (mirroring `AppleThunderboltDPInAdapter`), and the DCP firmware does
  not do it for us; or
- (H2) the crossbar `bringConnectionUp` (step 5) does an extra MMIO write beyond what Linux's
  `apple_dpxbar_set` does, so the pixel FIFO from `dispext0` into the DP-IN adapter is never fully
  clocked, and the adapter therefore reports 0 consumed.

Both need register-level evidence. The macOS text log gives the op names and a few parameters
(`req_bandwidth=159`, `pclk_sel=1`, `ufpBit/dfpBit=1`) but **not raw register writes**. To get
those, the gold-standard is an **m1n1 hypervisor MMIO trace of macOS** bringing this monitor up
(trace the `atc1-dpin0` block `0x501e50000`, the `atc1-dpxbar` block `0x50304c000`, and the ACIO
router), or disassembly of the `AppleDisplayCrossbar` / `AppleThunderboltDPAdapterFamily` kexts.

## Decode the DP adapter registers precisely (do this next)

`sources/linux-usb4-backport/drivers/thunderbolt/tb_regs.h` has the bit definitions
(`ADP_DP_CS_0/2/8`, `DP_LOCAL_CAP`, `DP_REMOTE_CAP`, `DP_STATUS`, `DP_COMMON_CAP*`). The debugfs
dump columns are: `offset  relative_offset  cap_id  vs_cap_id  value`. For port5, cap_id 4 is the
DP adapter capability; relative_offset 0..8 map onto those `ADP_DP_CS_*` / `DP_*_CAP` / `DP_STATUS`
registers. Read `tb_dp_consumed_bandwidth()` and `tb_dp_read_cap()` in
`drivers/thunderbolt/tunnel.c` to see exactly which fields the core reads and why it computes 0.
The current port5 cap-4 values captured while "video active":
```
rel0=0xc0090400 rel1=0x00004008 rel2=0x00000040 rel3=0x00000000
rel4=0x05402334 rel5=0x0840a234 rel6=0x00000000 rel7=0x08402234 rel8=0x41000552
```
(rel6 DP_STATUS = 0 is the smoking gun; rel4/5 are LOCAL/REMOTE cap, rel7 is COMMON cap.)

## Key files

Code / patches (in `sources/linux-usb4-backport`, branch `thunderbolt-7.1.13-dpin-v3`):
- `drivers/gpu/drm/apple/dcp.c`, `dcp-internal.h`, `dcp.h`, `connector.c`, `dptxep.c` — the DP-IN
  route (crossbar select, `apple,tbt-dpin-test`, `tunnel_hpd`/`tunnel_dpin` debugfs, DP-IN 0/1
  runtime switch, prime PHY clocks on activate).
- `drivers/phy/apple/atc.c` — `dpin_clocks` module param: enable DP pixel clocks + AUSPLL in
  USB4/TBT mode (default 2). This makes `PCLK_STAT` lock (0xf).
- `drivers/thunderbolt/tb.c` — `dp_in_skip_mask` module param to steer the tunnel to host DP IN 5
  or 6.
- `arch/arm64/boot/dts/apple/t8103-j313.dts` — dcpext on, DP-IN crossbar controls, `phys=atcphy1`.
- Exported patch: `patches/thunderbolt-dpin-v3-experiment.patch`.

Scripts / tools:
- `scripts/run-dpin-v3.py` — `status` / `connect OUTDIR [--dpin N] [--phy-clocks N] [--prime-rate N]
  [--wait S]` / `disconnect` / `retunnel [--skip-mask MASK]`. The main harness.
- `artifacts/mmio/mmio-rw` — `/dev/mem` 32-bit `r <addr>` / `w <addr> <val>` / `p <addr> <val>
  <mask> <ms>` (poll). Built from `artifacts/mmio/mmio-rw.c`. **This is how we found the fix.**
- `artifacts/mmio/mmio-dump <phys> <len>` — hex dump a register block.
- `scripts/webcam-snap.sh [out.jpg]` — grab one frame from the FaceTime camera (`/dev/video1`).
  Point the laptop at the LG, run it, and Read the jpg to check for a picture without asking the
  user. **This is the objective picture check.** (A fullscreen white `foot` window on workspace 2
  makes a lit panel obvious.)
- `scripts/stage-usb4-dpin-v3.py install|restore` — installs/reverts the whole v3 boot target.
- `scripts/build-usb4-dpin-v3.sh quick|modules`, `scripts/build-usb4-dpin-v3-initramfs.sh`.

Evidence:
- `reports/macos-dump/` — the macOS 14.3 dump WITH the LG working: `adt.txt` (IODeviceTree),
  `ioreg.txt`, `kernel-log.txt` (the DP bring-up op sequence), `atc1-dpin0.txt`, `atc1-dpxbar.txt`,
  `acio1.txt` (ACIO tunables + `thunderbolt-drom`), `tbports.txt`, `tbswitch.txt`, `tb.txt`.
  **This is the primary RE source.** Re-dump script lives on the EFI at `/boot/efi/dump-macos.sh`.
- `reports/usb4-dpin-v3/attempt*/` — each connect attempt's trace/journal/before-after.
- `reports/usb4-dpin-v3/dpin0-regs-*.txt` — the atc1-dpin0 MMIO block in pending/active states.

Memory (persistent, load first): `dpin-failure-analysis.md` in the session memory dir has the
condensed history and every dead end already ruled out.

## Hardware facts (don't re-derive)

- Host DP-IN adapters: TB port **5** (→ crossbar `dpin0`) and **6** (→ `dpin1`). LG DP-OUT: TB
  ports **10** and **11**. LG has PCIe up/down but **no USB3 adapter** (so USB3-tunnel milestones
  are meaningless for this monitor).
- Apple ADT DP-IN bridge blocks: `atc1-dpin0 @ 0x501e50000` (irq 887), `atc1-dpin1 @ 0x501e58000`
  (irq 888), 0x4000 each, `compatible = "atc-dpin,t8103"`. Crossbar `atc1-dpxbar @ 0x50304c000`.
  The dpin block offsets we know: `0x0c = DPTX_INACTIVE` (default 1, clear to activate),
  `0x10 = DPTX_INACTIVE_ACK`. The rest of the block did not change across pending/active, so the
  bandwidth bring-up is NOT in this block — look at TB config space and the crossbar.
- The LG "powers on automatically when connected to a powered-on device"; it has no "no signal"
  OSD. So a dark panel = no valid stream, full stop.

## Anything needed from macOS

The text dump is captured. The high-value thing still missing is a **register-level trace** of
macOS lighting this exact monitor, via the m1n1 hypervisor (`m1n1` is in
`sources/m1n1-thunderbolt`; `proxyclient/hv` has `trace_dcp.py` which already decodes the DCP DPTX
EPIC calls). That requires a tethered m1n1 hypervisor boot of macOS with the monitor attached and
MMIO tracing on the `atc1-dpin0` / `atc1-dpxbar` / ACIO ranges. If pursuing H1/H2 from the static
dump stalls, that trace is the way to get ground truth. Ask the user to set up the tethered
hypervisor session if needed.

## Safety / restore

- `sudo python3 scripts/stage-usb4-dpin-v3.py restore` reverts loader + modules + GRUB to the
  plain `7.1.13-usb4-gpu-test` state. Stock loader backup `boot.bin.before-display-test` is
  untouched on the EFI. Recovery text: `/boot/efi/USB4-DPIN-V3-RECOVERY.txt`.
- All register writes so far are reads or single-word writes to the `atc1-dpin0` block via
  `/dev/mem`; nothing persistent. A reboot clears any poke.
