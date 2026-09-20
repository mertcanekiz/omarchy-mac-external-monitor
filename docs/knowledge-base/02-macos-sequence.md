# 02 — The macOS bring-up, register by register

Source: `reports/usb4-dpin-v3/hv-attempt8-macos13.5-trm0-lg-attached.log` (m1n1 hypervisor,
macOS 13.5 kernel as guest, LG on the front port, run 8). Line numbers below refer to that file.
Guest console with host timestamps: `reports/usb4-dpin-v3/hv-attempt3-8-guest-console.log`.
The write-up the kernel work was derived from: `reports/usb4-dpin-v3/HV-TRACE-FINDINGS.md`.
How the trace was taken: `reports/usb4-dpin-v3/M1N1-TRACE-CHECKLIST.md` (tethered boot, proxy-mode
m1n1, `trace_dcp.py` + `trace_atc.py` + `trace_dpin_bringup.py`).

Two cycles were captured (LG attached at boot, lines 1780–2953; hot re-plug, lines 3774–4302).
They are byte-identical in the parts that matter.

## Phase 0 — Thunderbolt side (lines 1780–1826, console 17:44:52–54)

`AppleThunderboltNHI` turns the PHY on; `AppleTypeCPhy` puts all four lanes into USB4
(`ACIOPHY_LANE_MODE 0x249 → 0x0`, `ACIOPHY_CROSSBAR 0x2a → 0x20`, `CIO3PLL_CLK_CTRL = 0x2022`,
`ATCPHY_POWER_CTRL 0xb → 0x1b`). This is the TBT-mode PHY init that Linux's `phy-apple-atc` already
does via the tipd Thunderbolt switch; not part of the DP-IN work. The macOS connection manager then
enumerates the LG (`IOThunderboltSwitch(1@1)`), builds tunnels (`activating Video path
SRC [1:0x0:0x5] DST [1:0x1:0xb] req_bandwidth = 259 → 159`, `AUX Tx`, `AUX Rx`) and reports
`finished DPRX polling on DPIn port [1:0x0:0x5]` right after the DCP's ACTIVATE (below). On Linux
the thunderbolt core does all of this by itself (`0:5 <-> 1:11 (DP): activating`, Video/AUX paths)
and polls DPRX with `thunderbolt.dprx_timeout=-1` so the tunnel is held while we wait.

## Phase 1 — DP-IN bridge enable (lines 1829–1841), before any DCP command

```
dpin0+0x08:  R 0x0  -> W 0x3
dpin0+0x04:  R 0x1
dpin0+0x00:  R 0x5
dpin0+0x04:  R 0x1  -> W 0x1      (written back unchanged)
dpin0+0x00:  R 0x5  -> W 0x5      (written back unchanged)
```
Interpretation (unproven but consistent with every observation): 0x08 is an enable/interrupt-enable
register (bits 0,1), 0x00 and 0x04 are status registers that the driver acknowledges by writing back
what it read. On Linux the pristine block reads `00=5 04=1 08=0 0c=1 10=1`; after our enable it reads
`00=4 04=0 08=3`, i.e. the write-back cleared status bits. Every Thunderbolt link drop resets the
whole block to the pristine values (observed after each replug and monitor power cycle).

## Phase 2 — DCP connect and ACTIVATE (lines 1846–1918)

AP → DCP commands, in order, with payloads:

```
connectTo         (0,11)  unk=0x000b0101  target=0x8011  (CORE=1 ATC=1 DIE=0 CONNECTED=1)
requestDisplay    (0,6)   16 zero bytes   (m1n1 tracer name: "setPowerState")
```
Between those two (the reply to requestDisplay arrives only after them) the firmware issues AP calls
that macOS answers:

| AP call | macOS reply payload (offset 0x10 of the call data) |
|---|---|
| GET_SUPPORTS_HPD (18) | supported = **1** |
| GET_MAX_LANE_COUNT (10) | 4 |
| ACTIVATE (0) | echo; **inside the call**: `dpxbar+0x60: R 0 -> W 0` twice (the mux select, dispext0,0 → dpin0), `dpin0+0x0c: R 0x1 -> W 0x0` (DPTX_INACTIVE cleared), `dpin0+0x10: R 0x0` (ack) |

Then, right after the requestDisplay reply:
```
hotPlugDetectChangeOccurred (8,8)  16 zero bytes + u32 1     ("HPD asserted")
```
Console: `IOPortTransportState: [Port-USB-C@2: DisplayPort@0]`, `powering nub`, `finished DPRX polling`.

## Phase 3 — link configuration (lines 1999–2356), driven by the firmware after HPD

| AP call | macOS reply / AP-side work |
|---|---|
| SET_TILED_DISPLAY_HINTS (21) | request echoed **untouched** (its first word is 1 and stays 1) |
| GET_MAX_LINK_RATE (7) ×2 | 0x1e (HBR3) |
| GET_SUPPORTS_DOWN_SPREAD (13) | 0 |
| SET_DOWN_SPREAD (15) | echo |
| WILL_CHANGE_LINK_CONFIG (5) | nothing (first time) |
| SET_ACTIVE_LANE_COUNT (12) | 0 (first time) |
| SET_LINK_RATE (9) arg 0x14 (HBR2) | **PHY PCLK sequence + crossbar bring-up, see below**; reply 0x14 |
| DID_CHANGE_LINK_CONFIG (6) | nothing |
| GET_SUPPORTS_DOWN_SPREAD, SET_ACTIVE_LANE_COUNT → 4, GET_MAX_DRIVE_SETTINGS → 3,3, "group 1 cmd 3" (drive settings, firmware-internal link training) | |

Console: `AppleT8103TypeCPhy::configureDPTunnelMode: Configuring PCLK(1) at link rate: 20`,
`AppleTypeCPhyInterface::setLinkRate: AppleATCDPINAdapterPort(atc1-dpin0) type 3: link rate 0x14
pclk 1`, then `IOMFB: IOAVVideoInterface published`, `display HPD asserted`. In the kernel-only guest
nothing ever set a mode, so the panel stayed dark there; that is expected.

### SET_LINK_RATE, PHY part (lines 2171–2276), `atc-phy1` core registers

```
ACIOPHY_CFG0 / ACIOPHY_SLEEP_CTRL       read/rewritten unchanged (0x11833fef / 0x15570cff)
ACIOPHY_LANE_DP_CFG_BLK_TX_DP_CTRL0 (0x7000)
        0xe001 -> 0xe005   set DPTXPHY_PMA_LANE_RESET_N     (bit 2)
        0xe005 -> 0xe00d   set DPTXPHY_PMA_LANE_RESET_N_OV  (bit 3)
        0xe00d -> 0xe01d   DPTX_PCLK1_SELECT = 1            (bits 6:4)
        (bits 13,14,15 = the three PCLK enables were already set; bit 0 DP_PMA_BYTECLK_RESET stays 1;
         DPTX_PCLK2_SELECT and DPRX_PCLK_SELECT stay 0)
AUSPLL_FREQ_CFG (0x2224)                0x20086001 -> 0x20086000  (REFCLK field cleared)
AUSPLL_FREQ_DESC_A (0x2080)             0x2a160190 -> 0x2a16021c -> 0x2a0e021c -> 0x1e0e021c
AUSPLL_FREQ_DESC_B (0x2084)             0x0
AUSPLL_FREQ_DESC_C (0x2088)             0x460800 -> 0x460a00 -> 0x464a00 -> 0x454a00 -> 0x654a00
AUSPLL_CLKOUT_DIV (0x2208)              0x180001 -> 0x10001       (PLLA_REFBUFCLK_DI 24 -> 1)
AUSPLL_CLKOUT_DTC_VREG (0x2220)         0x11090a2 unchanged      (VREG_BYPASS bit 7 = 1)
AUSPLL_BGR (0x2214)                     0x1e0 -> 0x1e1            (CTRL_AVAIL)
AUSPLL_CLKOUT_MASTER (0x2200)           0x2000 -> 0x2004 -> 0x2014 -> 0x2054
                                        (PCLK_DRVR_EN bit2, PCLK2_DRVR_EN bit4, REFBUFCLK_DRVR_EN bit6)
AUSPLL_APB_CMD_OVERRIDE (0x2000)        0x2 -> 0x10000003 (cmd 0 + REQ + bit28) -> ack -> 0x10000002
ACIOPHY_DP_PCLK_STAT (0x7044)           R 0x0, R 0x8              (poll for AUSPLL_LOCK bit 3)
AUSPLL_APB_CMD_OVERRIDE                 0x10000000 -> 0x10010001 (cmd 0x2000 + REQ) -> ack -> 0x10010002
```
Decoded with the field layout in `atc.c`:

| FREQ_DESC_A 0x1e0e021c | count_target 0x21c, fbdivn_half 0, rev_divn 0, ki_man 8, ki_exp 3, kp_man 8, kp_exp 7, scale 0 |
|---|---|
| FREQ_DESC_C 0x654a00 | ssc_step 0, ssc_en 0, **pclk_div_sel 5**, lfsdm_div 1, lfclk_ctrl 5, **vclk_op_divn 2**, vclk_pre_divn 1 |

Compare the DP alt-mode tables in `atc.c` (`dp_lr_config[]`): HBR2 uses count 0x1c2 with a
fraction, pclk_div_sel 4, vclk_op_divn 0; RBR uses count 0x21c, no fraction, pclk_div_sel 0x13,
vclk_op_divn 2. The tunnel config is the RBR VCO with a different pixel divider. A divider model that
fits all four alt-mode tables (VCO = count × 12 MHz; link = VCO / (op_divn ? 2 : 1) [/2 with
txa_div2]; pclk = VCO / (2 × (pclk_div_sel + 1))) gives pclk = 6.48 GHz / 12 = **540 MHz**, the HBR2
symbol clock, for the tunnel config, and the same 540 MHz for the alt-mode HBR2 table (5.4 GHz / 10).
So the pixel-clock frequency is identical; the VCO rate, the REFBUFCLK divider (1 vs 7) and the post-lock
APB command (0x2000 vs 0x2800) differ. Which of those three is functionally required was never isolated
(v4 replicates all three and works; v3 used the alt-mode HBR2 table and did not light the panel, but v3
differed in many other ways too).

### SET_LINK_RATE, crossbar part (lines 2292–2350), `atc1-dpxbar`

Names from `drivers/mux/apple-display-crossbar.c`:
```
+0xc00 UNK_TUNABLE          W 0
+0x04  FIFO_WR_N_CLK_EN     0x1ff -> 0x1fe   clear bit 0 (dispext0,0)
+0x28  FIFO_RD_N_CLK_EN     0x1ff -> 0x1fe
+0x48  OUT_N_CLK_EN         0x111 -> 0x110   clear bit 0 (ATC_DPIN0)
+0x804 +0x828 +0x848        status readback (0x1fe, 0x1fe, 0x110)
+0x08  FIFO_WR_UNK_EN       0 -> 1
+0x2c  FIFO_RD_UNK_EN       0 -> 1
+0x4c  OUT_UNK_EN           0 -> 1
+0x00  FIFO_WR_DPTX_CLK_EN  0 -> 1
+0x20  FIFO_RD_PCLK1_EN     0 -> 1
+0x40  OUT_PCLK1_EN         0 -> 1
+0x70  CROSSBAR_ATC_EN      0 -> 1
+0x50  CROSSBAR_DISPEXT_EN  0 -> 1
+0x20  FIFO_RD_PCLK1_EN     1 -> 0 -> 1      (pulse)
```
This is exactly what Linux's `apple_dpxbar_set()` writes for `mux_control_select(dpin0, state 0)`,
including the pulse "HW quirk" comment in the driver. The only difference is *when*: Linux v3 called
it before the DCP was told to connect; macOS does it inside SET_LINK_RATE after the PLL is up.

## Teardown on unplug (lines 2653–2953)

```
(dpin IRQ handler)  dpin0+0x04 R 1, +0x00 R 2, +0x04 W 1, +0x00 W 2
AP -> DCP: hotPlugDetectChangeOccurred(false)
AP call SET_TILED_DISPLAY_HINTS, then WILL_CHANGE_LINK_CONFIG, inside it:
    dpin0+0x0c: 0 -> 1                        DPTX_INACTIVE
    dpxbar +0x50,+0x00,+0x20,+0x40: 1 -> 0 ;  +0x800/+0x820/+0x840 readback
    dpxbar +0x08,+0x2c,+0x4c: 1 -> 0 ;  +0x04: 0x1fe->0x1ff ; +0x28: 0x1fe->0x1ff ; +0x48: 0x110->0x111
    dpin0+0x0c: 1 -> 0 ; dpin0+0x10 R 1 ; dpin0+0x00 R 0
AP call SET_ACTIVE_LANE_COUNT (0), SET_LINK_RATE (0), inside it (unconfigureDPTunnelMode):
    AUSPLL_CLKOUT_MASTER 0x2054 -> 0x2050 -> 0x2040 -> 0x2000   (drop pclk, pclk2, refbufclk drivers)
    AUSPLL_APB_CMD_OVERRIDE 0x10010000 -> 0x10000019 (cmd 3 + REQ) -> ack -> 0x1000001a
AP call DID_CHANGE_LINK_CONFIG, INACTIVE_SINK_DETECTED, then DEACTIVATE, inside it:
    dpin0+0x08: 3 -> 0
```
Note the crossbar teardown in Linux's `apple_dpxbar_set(MUX_IDLE_DISCONNECT)` clears the same bits in
a different order; the end state is the same and it works.

## What macOS did NOT do (and Linux v3 did)

- no `validateConnection` (0,12)
- `connectTo` unk field 0xb0101, not 0
- no PHY programming at ACTIVATE (v3 "primed" the PLL at 5400 there)
- no `phy_set_mode(DP)` on the TBT-mode PHY at ACTIVATE, no `phy_set_mode(INVALID)` at DEACTIVATE
- no DPRX_PCLK_SELECT / DPTX_PCLK2_SELECT, no clearing of DP_PMA_BYTECLK_RESET
- crossbar enables not before the DCP connect
