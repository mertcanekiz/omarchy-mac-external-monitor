# m1n1 hypervisor trace of macOS bringing the LG UltraFine up — findings (2026-09-20)

Eight runs on the HOST Mac driving the M1 Air (TARGET) as an m1n1 hypervisor guest. Runs 1–7 were
setup failures that each taught one thing (below). **Run 8 captured the complete kernel-side DP-IN
bring-up twice**: once with the LG attached at boot, once on a hot re-plug. Raw evidence:

| file | what |
|---|---|
| `hv-attempt8-macos13.5-trm0-lg-attached.log` | run 8 hypervisor trace: atc1-dpin0 / atc1-dpxbar (SYNC), atc-phy1 + usb-drd1 (ASYNC), dcpext EPIC decode |
| `hv-attempt3-8-guest-console.log` | guest xnu serial console (timestamped on the HOST) for runs 3–8 |
| `hv-attempt1…7-*.log` | earlier runs, kept for the failure modes |

The panel **did not light** in any run. That is expected for this setup, see "What is still missing".

## The recipe (run 8, first cycle, trace lines 1780–2660)

Trace line numbers refer to `hv-attempt8-macos13.5-trm0-lg-attached.log`. The AP-side driver is
`AppleTypeCPhy` / `AppleATCDPINAdapterPort(atc1-dpin0)`; the DCP side is `dcpext`'s `dcpdptx-port-epic0`
EPIC service. Phases are ordered exactly as macOS did them. Register bases: `atc1-dpin0` =
0x501e50000, `atc1-dpxbar` = 0x50304c000, `atc-phy1` = 0x503000000.

### Phase 0 — Type-C PHY switches the port to USB4/TBT with DP mode (lines 1780–1826)
`AppleTCController` sees the LG, negotiates TBT alt mode; `AppleThunderboltNHI` turns the PHY on.
```
ACIOPHY_SLEEP_CTRL   0x15540033 -> 0x155400f3 -> 0x155500f3 -> 0x155500ff -> 0x155700ff -> 0x15570cff
ACIOPHY_CFG0         0x10000cef -> 0x10003cef -> 0x10803cef -> 0x10803fef -> 0x11803fef -> 0x11833fef
CIO3PLL_CLK_CTRL     0x2022 (PCLK_EN=1, REFCLK_EN=1)
ACIOPHY_LANE_MODE    0x249 -> 0x248 -> 0x240 -> 0x200 -> 0x0   (all four lanes USB4)
ACIOPHY_CROSSBAR     0x2a -> 0x20                              (PROTOCOL=USB4, DPMODE=1)
ATCPHY_MISC          0x1 (RESET_N=1)
ATCPHY_POWER_CTRL    0xb -> 0x1b (PHY_RESET_N=1)
```
Thunderbolt then enumerates the LG router (`IOThunderboltSwitch(1@1)`), creates tunnels
(`IOThunderboltTunnelDriver 1:1:8/9/a/b`), and `finished DPRX polling on DPIn port [1:0x0:0x5]`.

### Phase 1 — DP-IN adapter enable, before talking to the DCP (lines 1829–1841)
```
dpin0+0x08:  R 0x0  -> W 0x3
dpin0+0x04:  R 0x1  -> W 0x1      (rewritten unchanged)
dpin0+0x00:  R 0x5  -> W 0x5      (rewritten unchanged)
```

### Phase 2 — DCP `connectTo` + `ACTIVATE` (lines 1846–1918)
```
dcpdptx-port-epic0 > connectTo(target=0x8011: CORE=1, ATC=1, DIE=0, CONNECTED=1, unk1=0xb0101)
dcpdptx-port-epic0 > setPowerState
DCP -> AP  DPTX_APCALL_GET_SUPPORTS_HPD
DCP -> AP  DPTX_APCALL_GET_MAX_LANE_COUNT       AP replies 4
DCP -> AP  DPTX_APCALL_ACTIVATE                 AP does, inside the call:
    dpxbar+0x60:  R 0x0 -> W 0x0   (twice)
    dpin0+0x0c:   R 0x1 -> W 0x0   <- the DPTX_INACTIVE bit; this is what our v3 hack pokes
    dpin0+0x10:   R 0x0
dcpdptx-port-epic0 > hotPlugDetectChangeOccurred(True)
```

### Phase 3 — link configuration (lines 1999–2356)
```
DCP -> AP  DPTX_APCALL_SET_TILED_DISPLAY_HINTS
DCP -> AP  DPTX_APCALL_GET_MAX_LINK_RATE        AP replies 0x1e (HBR3)   [asked twice]
DCP -> AP  DPTX_APCALL_GET_SUPPORTS_DOWN_SPREAD
DCP -> AP  DPTX_APCALL_SET_DOWN_SPREAD
DCP -> AP  DPTX_APCALL_WILL_CHANGE_LINK_CONFIG
DCP -> AP  DPTX_APCALL_SET_ACTIVE_LANE_COUNT
DCP -> AP  DPTX_APCALL_SET_LINK_RATE  arg 0x14 (HBR2)   AP does, inside the call
           (console: "AppleT8103TypeCPhy::configureDPTunnelMode: Configuring PCLK(1) at link rate: 20"):
    ACIOPHY_CFG0 / ACIOPHY_SLEEP_CTRL rewritten unchanged (0x11833fef / 0x15570cff)
    ACIOPHY_LANE_DP_CFG_BLK_TX_DP_CTRL0   0xe001 -> 0xe005 -> 0xe00d -> 0xe01d
        (PMA_LANE_RESET_N=1, then RESET_N_OV=1, then the next bit up)
    0x503002224 = 0x20086000                 (unnamed PLL reg)
    AUSPLL_TOP_FREQ_DESC_0A  0x2a160190 -> 0x2a16021c -> 0x2a0e021c -> 0x1e0e021c
    AUSPLL_TOP_FREQ_DESC_0B  0x0
    AUSPLL_TOP_FREQ_DESC_0C  0x460800 -> 0x460a00 -> 0x464a00 -> 0x454a00 -> 0x654a00
    0x503002208 = 0x10001
    AUSPLL_CLKOUT_DTC_VREG   0x11090a2 (DTC_VREG_ADJUST=2)
    0x503002214 = 0x1e1
    0x503002200 = 0x2004 -> 0x2014 -> 0x2054
    AUSPLL_CMD_OVERRIDE      0x2 -> 0x10000003 -> 0x10000002 -> 0x10010001 -> 0x10010002
    -- then the crossbar (lines 2292–2350):
    dpxbar+0xc00: W 0x0
    dpxbar+0x04:  R 0x1ff -> W 0x1fe
    dpxbar+0x28:  R 0x1ff -> W 0x1fe
    dpxbar+0x48:  R 0x111 -> W 0x110
    dpxbar+0x804 R 0x1fe, +0x828 R 0x1fe, +0x848 R 0x110      (status readback)
    dpxbar+0x08:  0 -> 1
    dpxbar+0x2c:  0 -> 1
    dpxbar+0x4c:  0 -> 1
    dpxbar+0x00:  0 -> 1
    dpxbar+0x20:  0 -> 1
    dpxbar+0x40:  0 -> 1
    dpxbar+0x70:  0 -> 1
    dpxbar+0x50:  0 -> 1
    dpxbar+0x20:  1 -> 0 -> 1                                (pulse)
DCP -> AP  DPTX_APCALL_DID_CHANGE_LINK_CONFIG
DCP -> AP  GET_SUPPORTS_DOWN_SPREAD, SET_ACTIVE_LANE_COUNT, GET_MAX_DRIVE_SETTINGS, "unknown group 1; command 3" ...
           (DCP firmware link training; no further AP register writes)
```
Console at this point: `IOMFB: IOAVVideoInterface published`, `display HPD asserted`, then
**`hotPlug_notify_gated: AP dispext0 HPD notification not registered yet`** — the DCP is waiting for
an AP framebuffer client to ask for a mode. None exists in this kernel-only guest.

### Teardown on unplug (lines 2653–2953) — the exact inverse
```
dpin0+0x00:  W 0x2 (was read 0x2)         setLinkRate 0x00 / unconfigureDPTunnelMode
dpin0+0x0c:  0 -> 1                       DPTX_INACTIVE
dpxbar+0x50, +0x00, +0x20, +0x40: 1 -> 0
dpxbar+0x800 R 0x1fc, +0x820 R 0x1fc, +0x840 R 0x0
dpxbar+0x08, +0x2c, +0x4c: 1 -> 0
dpxbar+0x04: 0x1fe -> 0x1ff ; +0x28: 0x1fe -> 0x1ff ; +0x48: 0x110 -> 0x111
dpin0+0x0c:  1 -> 0 ; dpin0+0x10 R 0x1 ; dpin0+0x00 R 0x0
dpin0+0x08:  0x3 -> 0x0
```
The second cycle (re-plug at 17:45:09, lines 3774–4302) repeats phases 1–3 byte for byte.

## Answers to the two questions in the checklist

1. **Does the panel light before any USB / "Display Controls" traffic?** Not answerable from a
   kernel-only guest: nothing ever requested a mode, so the panel never lit. What *is* established:
   the DP link (HBR2, HPD asserted, `IOAVVideoInterface published`) was fully configured at 17:44:55,
   and the LG's USB hub, "Display Audio" and "Display Controls" devices only enumerated at 17:44:57–58,
   over the USB3 tunnel. So the DP path does not wait for USB, at least up to HPD. Whether the
   backlight/scaler needs the HID path is still open and needs a userland guest (see below).
2. **The atc1-dpin0 / atc1-dpxbar write sequence around activate / set_link_rate.** Captured in
   full above. Key deltas versus what Linux does today: macOS (a) sets `dpin0+0x08 = 3` first,
   (b) clears `dpin0+0x0c` (DPTX_INACTIVE) *inside* DPTX_APCALL_ACTIVATE after two writes of 0 to
   `dpxbar+0x60`, (c) programs the ATC PHY's DP lane block and AUSPLL for the link rate *before*
   touching the crossbar, (d) then flips nine crossbar enable bits in a fixed order and pulses
   `+0x20`. The `+0x04/+0x28/+0x48` masks drop one bit (0x1ff→0x1fe, 0x111→0x110) to route DP-IN 0.

## What it took to get here (each item cost one reboot cycle; the checklist is updated)

- The Preboot kernelcache is a full IMG4, not a bare IM4P: unwrap with `pyimg4 img4 extract -p`, then `im4p extract`.
- m1n1's ports show up as `/dev/cu.usbmodem<AirSerial>1` (proxy) and `…3` (guest serial console). **Log port 3**; every panic went there and was invisible until run 3.
- The Air's 14.3 kernel cannot run on the stub's 13.5 firmware: `panic: "Unexpected SIO Protocol version 9 - 10"`. Use the 13.5 kernel (`kernelcache.release.mac13g` from the 13.5 IPSW, fetched with `remotezip`, ~25 MB instead of 12 GB).
- The stub's `chosen/boot-uuid` points xnu at the Asahi stub volume → `panic: rootvp not authenticated after mounting`. Patching boot-uuid to a bogus UUID (`run_guest -c`) makes xnu wait for root instead. `rd=` is ignored on arm64 macOS.
- That wait is exactly 60 s (`ROOTDEVICETIMEOUT`, compiled in), after which xnu writes `boot-command=recover-system` to NVRAM and reboots into **macOS Recovery**. Every run ends there; hold power → Omarchy to get back.
- With no user logged in, Thunderbolt Restricted Mode refuses to identify the LG (`IOThunderboltTRMPolicyRoot: identification restricted`), so nothing past the HPD packets happens. Boot-arg `trm_enabled=0` (on the stub's allowed list) fixes it.
- `trace_dcp.py` needs `dart-dispext0` (not `dart-dispext`) and `trace_dpin_bringup.py` must skip `atc1-dpphy` (no `reg`). Both patched locally in `~/m1n1` on the HOST, uncommitted.

## What is still missing, and the options

The mode set that lights the panel is requested by WindowServer through IOMobileFramebuffer; a
kernel-only guest never gets there. To see the panel light under the trace (and to answer question 1
properly, including the "Display Controls" HID question) the guest needs userland:

- **Upstream's way (recommended):** a second macOS volume whose version matches the stub firmware
  (13.5), `diskutil apfs addVolume` + install macOS 13.5 (InstallAssistant / IPSW, ~12 GB, ~40 GB disk).
  Then boot-uuid = that volume's UUID, no 60 s limit, panel should light exactly as on real macOS.
- **Cheaper gamble:** point boot-uuid/root-snapshot-name at the existing 14.3 volume and also swap the
  13.5 static trust cache for the 14.3 one from the 14.3 boot objects. 13.5 kernel + 14.3 userland
  may or may not boot; one reboot cycle to find out.

For the Linux driver work, the recipe above is already the concrete deliverable: replay phases 1–3 in
`run-dpin-v3.py` (or the kernel driver) in that order, and compare each register readback with the
values macOS saw.
