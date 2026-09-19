# Adversarial review packet — DP-over-Thunderbolt on M1 Air (rev 2, post-review)

Purpose: give a skeptical reviewer everything to **confirm or refute** the claims, with reproducible
commands and captured evidence. Written to be attacked.

**This is rev 2.** An external adversarial review found real technical errors in rev 1. They are
**accepted and corrected here** (see "Corrections adopted"). Where rev 1 overclaimed, rev 2 states
the weaker, defensible claim. If any claim below is not backed by evidence you can re-run, treat it
as unproven.

Evidence bundle: `reports/usb4-dpin-v3/evidence-20260918-174759/` (live capture, DP-IN v3 boot).
Self-contained decoders included: `decode-edid.py`, `decode-dp-cap.py` (the latter corrected in
rev 2). Companion: `HANDOFF.md`, memory `dpin-failure-analysis.md`.

## Corrections adopted from the adversarial review (rev 1 → rev 2)

1. **`DPRX_DONE=1` does NOT prove main-link lock.** DPCD capability reads happen over the **AUX
   channel**, not the main video lanes. `DP_COMMON_CAP.DPRX_DONE` (and `tb_dp_wait_dprx()`) mean
   only "receiver capability read completed," i.e. the tunneled AUX reached the sink and it answered
   capability reads. It says nothing about clock-recovery / channel-EQ / symbol-lock on the lanes.
   Rev 1's "main link is locked at the monitor's receiver" is **retracted**.
2. **DP-OUT register 6 was mis-decoded.** Offset 6 is ambiguous: `DP_STATUS` on a DP-IN adapter
   (allocated_bw[31:24]) vs `DP_STATUS_CTRL` on a DP-OUT adapter (`CMHS`=bit25, `UF`=bit26; see
   `tb_regs.h:434-440`). The LG DP-OUT value `0x04000204` has **bit26 (UF) set**, not
   "allocated_bw=4". `decode-dp-cap.py` now prints both interpretations.
3. **The "consumed bandwidth 0" line was mis-explained twice.** Format is
   `"consumed bandwidth %d/%d Mb/s", up_bw, down_bw` (`tunnel.c:2627`). `0/17280` = **up=0
   (expected for a downstream tunnel), down=17280** (the value `tb_dp_bandwidth()` derives from the
   negotiated HBR2×4 caps — NOT a pixel-throughput measurement). Rev 1's "stale pre-DPRX" excuse is
   also wrong: the captured log prints it AFTER "DPRX ... completed".
4. **EDID has 2 extension blocks, not 1** (byte 126 = 2; 128 base + 256 = 384). And matching the
   Hyprland-reported serial is internal consistency (same EDID via DRM), **not** an independent
   second hardware read.
5. **Main-link training status is not observable from the host here.** There is no `/dev/drm_dp_aux*`
   and `appledrm` exposes no DPCD/AUX path; the DCP firmware owns the tunneled AUX. So the DPCD
   `0x202-0x207` link-status read that would actually prove training **cannot currently be done from
   Linux** on this setup. This limits both sides: neither this packet nor a reviewer can positively
   confirm main-link lock from the host.

## Claims under review (rev 2)

**CLAIMED (evidence below):**
- **A.** Thunderbolt/USB4 transport up; the LG UltraFine router is enumerated and **authorized**,
  link 20 Gb/s.
- **B.** A DP tunnel is **configured** through Thunderbolt: the connection manager activated the
  AUX and Video paths `0:5 <-> 1:10`; both DP adapters report Video-Enable, the sink asserts HPD.
- **C.** The **tunneled AUX reaches the real monitor**: the DP-IN adapter completed a receiver
  capability read (`DPRX_DONE=1`) and the host read the monitor's genuine **EDID** (valid, LG
  UltraFine, serial `010NTAB3E384`); DRM `DP-1` is `connected` with the monitor's modes.
- **D.** The adapters report a negotiated **HBR2 ×4** DP capability.

**NOT CLAIMED / unproven:**
- DP **main-link training** (CR/EQ/symbol-lock) at the LG receiver — not observable from host.
- Any **pixel** reaching the LCD.
- That **missing USB** is the cause of the dark panel (hypothesis, no causal experiment).
- Any DP bandwidth-allocation defect (retracted).

Defensible one-liner (the reviewer's, adopted):
> The captures support Thunderbolt router enumeration, DP tunnel configuration, DP AUX/capability
> discovery reaching the real monitor, a valid LG EDID, and adapter-reported HBR2×4 status. They do
> **not** establish DP main-link lock at the LG's receiver, pixel delivery, or that missing USB
> causes the dark screen. PCIe/USB enumeration is a separately observed failure.

## Proof, claim by claim

### A — TB transport up, LG router authorized  (`02-thunderbolt-devices.txt`)
```
0-0  device_name=iOS  vendor_name=Apple Inc.  authorized=1  generation=4          (host NHI)
0-1  device_name=UltraFine 4K  vendor_name=LG Electronics  authorized=1  gen=3
     rx_speed=10.0 Gb/s tx_speed=10.0 Gb/s rx_lanes=2 tx_lanes=2                    (20 Gb/s link)
```
`authorized=1` + negotiated 20 Gb/s on a router that identifies as LG is the OS TB stack having
enumerated the live remote router over the wire. Solid.

### B — DP tunnel configured (TB layer)  (`05-journal-tunnel.txt`, `05b-video-path-activation.txt`)
```
activating AUX TX path from 0:5 to 1:10   / AUX TX path activation complete
activating AUX RX path from 1:10 to 0:5   / AUX RX path activation complete
activating Video path from 0:5 to 1:10    / Video path activation complete
0:5 <-> 1:10 (DP): DPRX capabilities read completed
```
Caveat: "Video path activation complete" is the connection manager **writing the path hops**
(tunnel configuration), not a measurement that pixels traverse it. Adapter regs (`decode-dp-cap.py`):
host DP-IN `ADP_DP_CS_0=0xc0090400` → VE=1; LG DP-OUT `0xc009044f` → VE=1; DP-OUT `ADP_DP_CS_2` HPD=1.

### C — tunneled AUX reaches the real monitor; genuine EDID
```
host DP-IN DP_COMMON_CAP = 0xaa402214 → DPRX_DONE(capread)=1     (AUX cap read completed)
EDID (04-dp1.edid, 384 B): header valid; all 3 block checksums 0 mod 256; ext-count byte=2
  manufacturer(PnP)=GSM (LG)  name="LG UltraFine"  serial="010NTAB3E384"
DRM: card2-DP-1 status=connected; modes include 3840x2160
```
`DPRX_DONE=1` proves the DP-IN adapter read the sink's DPCD **over the tunneled AUX** — so the AUX
path reaches this specific monitor and its DPRX answers. The EDID is genuine (valid checksums,
real model+serial). It does **not** prove a trained main link or a live picture. Reproduce:
`python3 evidence-*/decode-edid.py evidence-*/04-dp1.edid`.

### D — negotiated HBR2 ×4
`DP_COMMON_CAP=0xaa402214` → rate=HBR2, lanes=4 (min of LOCAL/REMOTE, an actual exchange). Note the
captured host `DP_LOCAL_CAP=0x26402214` shows an **HBR2** encoding in this snapshot (rev 1 wrongly
called it "HBR3-capable"); the sink's `DP_REMOTE_CAP` likewise HBR2. This is the negotiated
capability, not proof pixels run at that rate.

## The wall (why "no picture" — and why the cause is still a hypothesis)
`06-pcie-usb-negative.txt`: only 3 built-in PCI devices, **no tunneled PCI**; **no USB devices**;
`PCIe Down path activation failed: -107` → `PCIe tunnel activation failed, aborting`. There is no
host tunneled-PCIe root complex in the DT (`/proc/device-tree/soc/cio@501ac0000/` = `nhi`,`iommu`,
`ports/port@1` only). macOS ioreg (`reports/macos-dump/`, in the repo, NOT in this evidence bundle)
names the monitor's USB devices "LG UltraFine Display Controls"/"Display Audio"/hubs.

**Honest limits of the USB hypothesis:** we have no measurement that the monitor's scaler is
unpowered, no observed brightness=0, and no controlled experiment where restoring one USB command
produces a picture with DP unchanged. "No USB + no picture" does not by itself prove "USB gates the
picture." Treat "USB-gated backlight/scaler" as the leading hypothesis, not a finding.

## What a reviewer should re-run
On the DP-IN v3 boot (`uname -r`=`7.1.13-usb4-gpu-test`), LG on the front port:
```sh
cd /home/mert/Work/omarchy-mac-external-monitor
sudo python3 scripts/run-dpin-v3.py disconnect
sudo artifacts/mmio/mmio-rw w 501e5000c 0 && sudo artifacts/mmio/mmio-rw p 501e50010 0 1 500
sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v3/review-recheck --dpin 0
sudo cat /sys/kernel/debug/thunderbolt/0-0/port5/regs  | python3 reports/usb4-dpin-v3/evidence-*/decode-dp-cap.py
sudo cat /sys/kernel/debug/thunderbolt/0-1/port10/regs | python3 reports/usb4-dpin-v3/evidence-*/decode-dp-cap.py
sudo cat /sys/class/drm/card2-DP-1/edid | wc -c        # 384, serial 010NTAB3E384
bash scripts/webcam-snap.sh                            # Read jpg: expect DARK (claim of "no picture")
```

## The two tests that would actually settle it (per the review)
1. **Main-link training status:** read the sink's DPCD `0x202-0x207` and evaluate CR/EQ/symbol-lock
   per lane + interlane align (`drm_dp_clock_recovery_ok`/`drm_dp_channel_eq_ok`). **Blocked on
   Linux today** — no host AUX/DPCD access to this firmware-owned tunneled link. Needs DCP-firmware
   instrumentation or an m1n1 MMIO trace of macOS. (DPCD `0x204` ≠ the TB reg value `0x00000204`.)
2. **Causal USB test:** a captured LG USB control transaction whose omission reliably prevents the
   picture and whose replay restores it (with DP config unchanged). Until then, "USB-gated" is a
   hypothesis. A weaker first step: set a working picture + nonzero brightness in macOS, keep the
   monitor mains-powered, retest Linux; a positive result implicates retained monitor state, a
   negative result is inconclusive.

## Known weaknesses (stated up front)
- The result depends on a manual `/dev/mem` write (`501e5000c`), a bring-up hack, not a driver.
  Reproducible and non-persistent (reboot clears it).
- No main-link-training or pixel evidence exists, and cannot be gathered from the host as-is.
- macOS references are a static ioreg/ADT dump, not a live trace, and live in the repo, not this
  bundle.
