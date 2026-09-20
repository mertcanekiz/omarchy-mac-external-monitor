# 05 — Rewrite plan: rebuild it yourself, one verifiable step at a time

Base: `sources/linux-usb4-backport` branch `thunderbolt-7.1.13-gpu` (`5f7d34c83`). Start a fresh
branch from there; do not cherry-pick the WIP commits. Build/install tooling that already exists and
does not need to be rewritten: `scripts/build-usb4-dpin-v5.sh quick|modules` (point it at your
branch name), `scripts/build-usb4-dpin-v5-initramfs.sh`, `scripts/assemble-thunderbolt-bundle.py
--profile ...`, `scripts/stage-usb4-dpin-v5.py`. Kernel image and full module tree for
`7.1.13-usb4-gpu-test` already exist; you only ever rebuild `appledrm`, `phy-apple-atc`,
`thunderbolt` and the DTB.

Ground rules that saved days: never claim a picture without the webcam (`scripts/webcam-snap.sh`);
keep `thunderbolt.dprx_timeout=-1` on the command line until the DCP side is automatic; read the
DCP firmware syslog lines in `journalctl -k`, they are the most honest signal.

## Step 0 — Understand the tunnel without any DCP change (no kernel change)
Boot the stock GPU+USB4 kernel with the LG plugged in. Confirm in `journalctl -k`: LG router
enumerated, `0:5 <-> 1:1x (DP): activating`, Video/AUX paths, then `DPRX read timeout` forever.
Read the adapter registers with `sudo python3 scripts/run-dpin-v3.py status` (debugfs
`/sys/kernel/debug/thunderbolt/*/port*/regs`, decoder in `scripts/collect-tunnel-registers.py`).
Expected: DP IN 5 `adapter_enabled`, `video_enabled`, `dprx_done: false`. This is the state the DCP
work starts from.

## Step 1 — Enable dcpext on j313 and route it to the DP-IN crossbar (DT only + minimal driver)
DT from A2 minus the hack properties you will design differently. Driver: make `appledrm` accept a
DCP whose "phy" is the ATC PHY in TBT mode and whose crossbar target is dpin0: skip the alt-mode/typec
mux setup, start the DPTX endpoint. **Test:** boot; `dcpext` prints `DCP booted`, `AFK[ep:2a]: new
service AppleDCPDPTXRemotePort` twice, `DP-1` connector appears (disconnected). No LG activity yet.

## Step 2 — Hand-driven DPTX_INACTIVE + connect (prove the AUX path)
Add a debugfs trigger that runs connect (F1) with the *old* order first if you want to see the
failure mode: without clearing `DPTX_INACTIVE` the firmware reports `device_not_responding(22)` /
`device_not_started(24)` after ~7 s and `dprx_done` never sets. Then add E1/E2 (`0x08 = 3`, clear
`0x0c` inside ACTIVATE). **Test:** `DPRX capabilities read completed` in the thunderbolt log within a
second of ACTIVATE; `DP-1` becomes connected with 7 modes; `sudo cat /sys/class/drm/card*-DP-1/edid
| wc -c` = 384. Still no picture is normal at this step.

## Step 3 — PHY pixel clock (B2, B4, B5, B6)
Implement the tunnel PCLK programming in `atc.c` and hook it to `SET_LINK_RATE`. **Test:** the log
line you add should show `TX_DP_CTRL0 = 0xe01d`, `PCLK_STAT` bit 3 set (0xf observed),
`CLKOUT_MASTER = 0x2054`. Dump the PHY registers with `artifacts/mmio/mmio-dump 503002000 0x240` and
`503007000 0x50` and compare with 02-macos-sequence.md.

## Step 4 — Crossbar ordering + HPD ordering (E3, E4, F1, F3)
Move the crossbar select into SET_LINK_RATE after the PLL, answer GET_SUPPORTS_HPD with 1, send HPD
right after ACTIVATE, connectTo unk 0xb0101, no validate, teardown in WILL_CHANGE/DEACTIVATE.
**Test:** Hyprland adds DP-1 and does a modeset (`dcp_poweron() starting`,
`set_digital_out_mode(...3840x2160...)`, `mode_set_gated ... link: 1`) and the webcam shows a picture.
This is the v4 milestone. If dark: compare your journal with
`reports/usb4-dpin-v4/attempt1-macos-seq/journal.txt` line by line; the differences that mattered
historically were all in this step.

If you want to know which of the v4 deltas is actually load-bearing (never isolated): revert them one
at a time from a working state, `disconnect`/`connect` (plus `scripts/dpin-recover.sh` to force the
modeset), webcam each time. Candidates: PLL table (RBR VCO vs HBR2), REFBUFCLK divider, APB command
0x2000, crossbar timing, HPD timing, `unk` 0xb0101, tiled-hints echo.

## Step 5 — Replug without reboot (04-drm-and-hotplug.md)
Unplug/replug with your debugfs trigger: you will see the "swallowed swap" failure. Implement the
forced modeset + `powered` (G). **Test:** `disconnect`, replug, `connect`, picture returns without
any DPMS cycle; the journal shows `forcing a modeset`.

## Step 6 — Automatic hotplug (C2, H)
Thunderbolt notifier + DCP work item. **Test:** boot with the LG attached → picture at the lock
screen; unplug/replug → picture returns; monitor power cycle → picture returns. Evidence to compare:
`reports/usb4-dpin-v5/boot1-auto/kernel-journal.txt`.

## Step 7 — Clean-up towards something reviewable
- One commit per subsystem: DT (with a binding for the dpin block), PHY (tunnel PCLK API), thunderbolt
  (notification), appledrm (DP-IN route), appledrm (hotplug/modeset), plus the two small fixes (D6).
- No module parameters, no `of_iomap` of foreign nodes, no debugfs in the main path.
- Decide who owns the dpin block: crossbar driver (mirrors macOS's `AppleT8103ATCDPXBAR` owning the
  `AppleATCDPINAdapterPort`s) is the most natural.
- Think about dpin1 / DP IN 6 and the back port (atc0) which have the same blocks at `0x381exxxxx`
  / NHI `0x381f00000`; nothing here was tested on them.
- Consider the second DCP-side consumer: dcp0 (the internal panel's controller) can also drive the
  crossbar on some machines; make sure nothing assumes dcpext.

## Things you will want to keep from the tooling
`scripts/run-dpin-v3.py` (status/connect/disconnect/retunnel with evidence capture),
`artifacts/mmio/mmio-rw` and `mmio-dump` (/dev/mem 32-bit access; how DPTX_INACTIVE was found),
`scripts/webcam-snap.sh`, `scripts/dpin-recover.sh`, and on the m1n1 side
`proxyclient/hv/trace_dpin_bringup.py` (fork branch `thunderbolt-dpin-trace`) if you ever need another
trace (e.g. of dcp0 on the crossbar, or of the back port).
