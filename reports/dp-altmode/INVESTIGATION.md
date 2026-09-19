# DP alt mode (fairydust) for the LG 24MD4KL: investigation, 2026-09-19

Question: with the new Paugge USB4 cable (USB4 Gen3, 40 Gbps, DP alt mode), can the LG be driven
over plain USB-C DisplayPort alt mode instead of Thunderbolt, using Asahi's `fairydust` work, and
what does it take to build that into the running `7.1.13-usb4-gpu-test` kernel?

## Live state with the Paugge cable (front port, 18:54 local)

- The CD321x PD controller negotiated **Thunderbolt 3**, not DP alt mode: `/sys/bus/thunderbolt/devices/0-1`
  is "LG Electronics UltraFine 4K", generation 3, 2 lanes x 20 Gb/s. The port's `typec` partner shows
  PD support and `usb2 usb3` modes; no DP alt mode partner object exists (the tipd driver does not
  register partner alt modes).
- The thunderbolt core built the DP tunnel `0:5 <-> 1:11` and holds it (`dprx_timeout=-1`); DPRX read
  timeouts spam the log because nothing has run the manual v3 connect (`run-dpin-v3.py connect`).
- New with this cable: the **PCIe tunnel paths activated** ("PCIe Down/Up path activation complete",
  "xHCI connected") where previous cables failed with -107. Nothing enumerates because there is no host
  PCIe root complex driver for tunneled devices; this does not change the DP-IN conclusions.
- `card2-DP-1` reports "connected" only because Hyprland's stale state from yesterday's DP-IN session.

So the monitor is alive on the link, but this cable puts it in exactly the mode that was already
explored (DP-IN over Thunderbolt), not in DP alt mode.

## Why the cable cannot select DP alt mode

The Apple CD321x firmware alone decides which mode is entered; Linux learns the outcome afterwards.
Sven Peter (Asahi USB3/USB4 series): "Unlike the original chips we however get no control over which
mode is negotiated or are even able to see the PDOs or VDOs. We only get to know once the mode has been
negotiated and have to act accordingly. I even went as far as dumping the firmware from the chip to
confirm this." The driver confirms it: the only 4CC commands used are role swaps, SSPS and patching;
the TPS "Intel VID config" (0x52) / "DP SID config" (0x51) registers that gate alt modes on stock
TPS6598x parts are never touched, and there is no evidence they work on the Apple firmware.

With a Thunderbolt 3 sink (the LG) and a Thunderbolt-capable cable, the firmware always prefers
TBT3. macOS behaves identically (the macOS dump shows `TransportsActive = ("CC","CIO")`). The
fairydust tracker (Sapporo issue #46) states the same for docks: "Docks speaking USB4 protocol fall
back to USB2; pure DP-alt adapters required."

Consequence: to get DP alt mode with this monitor you need a cable that carries DP alt mode but is
**not** Thunderbolt/USB4-capable: a full-featured USB 3.2 Gen 1 (5 Gbps) USB-C cable with SBU wires
(AUX) and 4 SuperSpeed pairs, typically not e-marked. The Paugge USB4 cable will always land in TBT3.

## What happened on the earlier DP alt mode attempt (2026-09-17)

With the plain USB-C cable and the stock 7.1.13 kernel plus the fairydust tipd modules and DTB
(booted with the monitor attached), DP alt mode DID negotiate:
`DATA_CONNECTION|USB2_CONNECTION|DP_CONNECTION|HPD_LEVEL, DP pinout C`, the LG hub, audio and
"Display Controls" HID enumerated over USB 2.0, and dcpext ran `get_supports_hpd`,
`get_max_lane_count`, `activate`, then `device_busy_timeout`/`device_not_started` ~7 s later
(reports/usbc-dptx-reconnect-trace.txt). That is the same signature the DP-IN path showed when its
AUX path was dead. Pin assignment C uses all four SS pairs for DP and needs the SBU pair for AUX; a
"charging/data" cable can negotiate DP over CC yet have no SBU wiring, which fits this trace. The
monitor itself is proven DP-alt-capable by that negotiation (and by LG's spec).

## What fairydust actually is

`fairydust` = tag `asahi-7.1.13-1` + 12 commits. The DP alt mode substance:

| Commit | Content |
| --- | --- |
| 296c91ac1 | tipd: track `data_status` changes for CD321x (debounced HPD bit) |
| 9c1679215 | tipd HACK: fire `drm_connector_oob_hotplug_event()` on the connector referenced by a `displayport` phandle |
| 7eb562930 | t8103 DTS: enable dcpext + dispext0/dcpext DARTs + mailbox, `phys = <&atcphy1 PHY_TYPE_DP>`, `mux-controls = <&atcphy1_xbar 0>`, dpaudio1, `displayport = <&dcpext>` on typec1 |
| 7003fe04c | HACK: `ps_atc1_common` always-on (suspend/resume) |

Everything else (atcphy DP modes, display crossbar, dcp dptx code, `apple_connector_oob_hotplug`
in apple_drv.c) is already in the stock 7.1.13 tree and therefore in the running kernel.

## What the running kernel lacks, and the prepared port

The running branch `thunderbolt-7.1.13-dpin-v3` is a sibling of fairydust on the same base. It lacks
the two tipd commits, and its j313 DTS configures dcpext for the DP-IN route
(`apple,tbt-dpin-test`, crossbar controls 1 and 2), which the dcp driver treats as mutually
exclusive with the DP alt mode setup (`if (dcp->phy && !dcp->dp_tunnel)`). So DP alt mode needs
its own DTB variant.

Prepared in worktree `sources/linux-dpalt`, branch `thunderbolt-7.1.13-dpalt` (3 commits on top of
dpin-v3), exported to `patches/dp-altmode/`:

1. `0001` tipd: track data_status changes (clean cherry-pick).
2. `0002` tipd: oob hotplug hack (one trivial conflict with the thunderbolt-switch code, both kept).
3. `0003` j313 DTS: replace the DP-IN block with the fairydust wiring (route 0 to the PHY,
   `displayport = <&dcpext>`, dpaudio1 on, `ps_atc1_common` always-on).

Compile-checked in a separate output dir (`artifacts/dpalt/build`, config copied from the v3 build):
tipd objects build without warnings; the DTB decompiles with dcpext `status = "okay"`, no
`apple,tbt-dpin-test`, `mux-controls = <&atcphy1_xbar 0>`, and the connector's `displayport`
phandle pointing at dcpext. The kernel Image is unchanged; only `tps6598x-core.ko` and the DTB differ.

## To boot it (not done; needs a suitable cable first)

1. Build modules + DTB for the dpalt branch (adapt `scripts/build-usb4-dpin-v3.sh`: source tree
   `sources/linux-dpalt`, output dir `artifacts/dpalt/build`, then `modules` + `modules_install`).
2. Assemble a loader bundle: add a `dpalt` profile to `scripts/assemble-thunderbolt-bundle.py`
   (it currently refuses a DTB without the `apple,tbt-dpin-test` marker for the v3 profile).
3. New initramfs containing the patched `tps6598x-core.ko` (as `build-usb4-dpin-v3-initramfs.sh`
   does), new GRUB entry (same kernel image, `dprx_timeout` no longer needed), stage/restore script
   like `stage-usb4-dpin-v3.py` with its own loader backup name.
4. Boot with the monitor already connected to the **front** port through a non-Thunderbolt DP cable;
   expect `cd321x_data_status: ...DP_CONNECTION|HPD_LEVEL, DP pinout C`, then `DP-1` connected with
   modes; verify with `scripts/webcam-snap.sh`.

If the same `device_busy_timeout` reappears with a known-good DP cable, the cable hypothesis is
wrong and the next step is instrumenting the atcphy DP AUX path (atc.c `atcphy_enable_dp_aux`) or
an m1n1 trace of macOS in DP alt mode.

## Sources

- https://lwn.net/Articles/1034692/ (CD321x: no control over negotiated mode)
- https://ratatoskr.run/asahi/2026/08/17409224/t (tipd Thunderbolt VDO fix)
- https://ratatoskr.run/asahi/2026/09/17521478/t (USB4 series v2: DP and PCIe tunnels "will come later")
- https://github.com/stevederico/Sapporo/issues/46 (fairydust DP-alt baseline; USB4 docks fall back)
- https://www.ti.com/lit/pdf/slvubh2 (TPS65987D host interface: 0x51 DP SID config, 0x52 Intel VID config)

## Update 20:38: Apple USB-C cable (probably an iPhone/iPad charge cable)

Plugged into the front port with the LG: **no Thunderbolt router appeared; the CD321x entered DP alt
mode.** Read live from the controller over I2C (`i2ctransfer -f 0 w1@0x3f 0x5f r12`, register
0x5f Data Status = `0x00008513`): DATA_CONNECTION | UPSIDE_DOWN | USB2_CONNECTION | DP_CONNECTION
(pin assignment C) | HPD_LEVEL. The LG "USB2.1 Hub", "UltraFine Display Audio" and "UltraFine
Display Controls" HID enumerated over USB 2.0 through the front port's own xHCI. The v3 kernel logged
`WARN_ON_ONCE(atcphy->pipehandler_up)` in atcphy_mux_set while switching the PHY from the previous
Thunderbolt mode to DP mode (v3's USB4 pipehandler path leaves the flag set; harmless here). Nothing
reached the display controller because the running DTB has no `displayport` reference and dcpext is
on the DP-IN route.

Cable identity: register 0x49 (Received Identity SOP', the cable e-marker) is all zeros, so the cable
has **no e-marker**. Apple's 60 W USB-C charge cables (iPhone 15 / iPad / MacBook box cables) are
USB 2.0-only and unmarked, so this is most likely one of those: it negotiates DP over CC but has no
SuperSpeed pairs and no SBU pair, i.e. no DP lanes and no AUX. Expect the same `activate` timeout as
on 2026-09-17 if booted. The negotiation itself, however, confirms the LG and the port do DP alt mode
whenever the cable is not Thunderbolt-capable.

Prepared (not installed): `artifacts/dpalt/{root,initramfs-dpalt.img,boot.bin.dpalt,out/}`,
`config/dpalt-grub-entry.cfg`, `scripts/stage-dpalt.py install|restore`,
`scripts/build-dpalt-initramfs.sh`, bundle profile `assemble-thunderbolt-bundle.py --profile dpalt`.
The tipd module was linked in `artifacts/dpalt/build` (config + Module.symvers copied from the v3
build; BTF skipped because that output dir has no vmlinux). Vermagic matches the running kernel.
