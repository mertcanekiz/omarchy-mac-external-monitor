# 01 — Architecture: how pixels get from the M1 to the LG UltraFine

## The chain

```
 dcpext (DCP firmware, 0x271c00000)      "external display controller" coprocessor + its own
   │  dispext0 pixel pipeline               display pipe. Linux talks to it through RTKit/AFK/EPIC.
   ▼
 atc1-dpxbar (0x50304c000)               "display crossbar": routes a dispext output to one of
   │  mux: dpphy / dpin0 / dpin1            three sinks on the front Type-C port: the DP PHY lanes
   │                                        (DP alt mode) or the two DP-IN bridges.
   ▼
 atc1-dpin0 (0x501e50000) / dpin1 (0x501e58000)
   │  "atc-dpin" bridge, 0x4000 each       Apple block between the crossbar and the CIO router's
   │                                        DP IN adapter. ADT: compatible "atc-dpin,t8103",
   │                                        transport-tunneled=1, transport-type=5, port-number=2.
   ▼
 CIO / ACIO router 0 (host, NHI 0x501f00000)
   │  DP IN adapter 5 (dpin0) / 6 (dpin1)   Thunderbolt/USB4 host router. The connection manager
   │  PCIe adapter 3, USB3 adapter 4          (Linux thunderbolt core) builds a DP tunnel from a
   │  lane adapters 1, 2                      DP IN adapter to a DP OUT adapter on the remote router.
   ▼  (USB4 link over the Type-C port, 2 lanes x 10 Gb/s on this LG)
 LG UltraFine router (Intel Titan Ridge 8086:15ef, route 1)
   │  DP OUT adapters 10 and 11 (either is used), PCIe up/down 8/9, NO USB3 adapter
   ▼
 the LG's internal DP sink (scaler/TCON) → panel
```

Two clocks matter on the host side:

- The **Type-C PHY (atc-phy1, 0x503000000)** contains the AUSPLL. In DP alt mode it drives the DP
  lanes. In tunnel mode the lanes carry USB4, but the same PLL still has to produce the **pixel
  clock PCLK1** that clocks pixels out of the crossbar FIFO into the DP-IN bridge. macOS calls
  this `AppleT8103TypeCPhy::configureDPTunnelMode` ("Configuring PCLK(1) at link rate: 20").
- The DP link itself (HBR2 x4, symbol rate 540 MHz) is virtual: the DP IN adapter packetizes the
  stream into the tunnel; there are no physical DP lanes. The DCP firmware still does full DP
  link training (DPCD reads, drive settings) over the **tunneled AUX** channel.

## Who does what

| layer | Linux component | role in the bring-up |
|---|---|---|
| Type-C controller | `tps6598x` (CD321x) | decides the port mode. With any Thunderbolt-capable cable and the LG it picks **TBT3**. Linux has no say (firmware policy). |
| Type-C PHY | `phy-apple-atc` (`drivers/phy/apple/atc.c`) | put into `APPLE_ATCPHY_MODE_TBT` by the tipd Thunderbolt switch; must additionally bring up PCLK1 for DP-IN |
| USB4/TB host | `thunderbolt` + `thunderbolt_apple` | enumerates the LG router, builds the DP tunnel (paths, hop IDs, Video Enable / AUX Enable bits), polls DPRX done |
| crossbar | `mux-apple-display-crossbar` | `mux_control_select()` writes the enable bits that connect dispext0 to dpin0 |
| DP-IN bridge | (none; `appledrm` maps it directly in this work) | `DPTX_INACTIVE` gate + enable/irq registers |
| display controller | `appledrm` (`drivers/gpu/drm/apple/`) | `dcp.c` (probe, connect/disconnect), `dptxep.c` (the firmware's "AP calls" during link config), `iomfb*.c` (modeset, swaps, hotplug callbacks) |
| compositor | Hyprland | must issue a modeset once the connector reports a valid EDID |

## The firmware protocol you are driving

`dcpext` runs Apple's DCP firmware (13.5 in the Asahi stub). Linux talks to it through RTKit
mailbox endpoints; the ones involved here:

- **IOMFB endpoint** (`iomfb*.c`): modeset (`set_digital_out_mode`), swaps, `cb_hotplug` callback
  from firmware → DRM hotplug.
- **DPTX endpoint 0x2a** (`dptxep.c`, AFK/EPIC service `AppleDCPDPTXRemotePort`, tracer name
  `dcpdptx-port-epic0`): the DP transmitter side. The AP (Linux) sends *commands* to it and the
  firmware sends *AP calls* (EPIC "notify") that the AP must answer. Commands (group, index):
  `connectTo` (0,11), `validateConnection` (0,12), `requestDisplay` (0,6; the m1n1 tracer calls it
  `setPowerState`), `releaseDisplay` (0,7), `hotPlugDetectChangeOccurred` (8,8). AP calls are
  `DPTX_APCALL_*` in `dptxep.h`: GET_SUPPORTS_HPD, GET_MAX_LANE_COUNT, ACTIVATE,
  SET_TILED_DISPLAY_HINTS, GET_MAX_LINK_RATE, GET/SET_DOWN_SPREAD, WILL/DID_CHANGE_LINK_CONFIG,
  SET_ACTIVE_LANE_COUNT, SET_LINK_RATE, GET_MAX_DRIVE_SETTINGS, SET_DRIVE_SETTINGS, DEACTIVATE,
  INACTIVE_SINK_DETECTED.
- The AP call handlers are where the platform work happens: on macOS, `AppleATCDPINAdapterPort`
  and `AppleT8103TypeCPhy` do their register writes *inside* ACTIVATE / SET_LINK_RATE /
  WILL_CHANGE_LINK_CONFIG / DEACTIVATE. That is the key structural fact: the firmware sequences the
  bring-up and the AP fills in the platform-specific register writes at the points the firmware
  asks.

## Why not DP alt mode

The LG 24MD4KL is a Thunderbolt 3 display. Its Type-C port advertises Thunderbolt; the CD321x
firmware enters TBT3 with any TB-capable cable (also on macOS). With a non-TB USB-C cable it enters
DP alt mode pin assignment C but the LG's DP sink is only reachable behind its Titan Ridge router,
i.e. only through a DP tunnel. So the tunnel path is the only path. (A prepared DP-alt-mode kernel
exists in `sources/linux-dpalt` for other monitors; irrelevant here.)

## Why the LG's USB did not matter

An early hypothesis was that the LG's scaler/backlight are managed over its USB (which rides a PCIe
tunnel to an xHCI inside the monitor) and that without USB the panel would stay dark. False: the
panel lights with only the DP tunnel active; the PCIe tunnel is irrelevant to video. The USB path
(webcam, audio, "Display Controls" brightness HID) is separate future work.

## Address and number cheat sheet

| thing | value |
|---|---|
| dcpext | `0x271c00000`, DT `dcpext`, `apple,dptx-phy = <1>` (ATC1), `apple,dptx-core = <1>` (dpin0; m1n1 dcpav.py: DPPHY=0, DPIN0=1, DPIN1=2) |
| atc1-dpxbar | `0x50304c000`, DT `atcphy1_xbar`, mux indices dpphy=0 dpin0=1 dpin1=2, state 0 = dispext0,0 |
| atc1-dpin0 / dpin1 | `0x501e50000` / `0x501e58000`, 0x4000 each, IRQs 887/888 (unused by Linux) |
| atc-phy1 | `0x503000000` (core regs), DT `atcphy1` |
| host NHI front / back | `0x501f00000` (atc1, domain with the LG) / `0x381f00000` (atc0) |
| host DP IN adapters | port 5 (→ dpin0), port 6 (→ dpin1) |
| LG DP OUT adapters | port 10 or 11 (the core picks; both worked) |
| DP link | HBR2 (0x14) x4, EDID 384 bytes, 7 modes, 3840x2160@60 pixel clock 533.28 MHz |
