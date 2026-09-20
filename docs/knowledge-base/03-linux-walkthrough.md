# 03 — Walkthrough of the Linux changes (cumulative diff, `dpin-cumulative-v3-v5.diff`)

Verdict legend: **KEEP** = needed and reasonably shaped; **RESHAPE** = needed but do it properly;
**HACK** = experiment scaffolding, drop or replace; **UNKNOWN** = works, not understood.

The three patches map onto the diff like this: v3 (`01-v3-experiment.patch`) = DT route, DCP
`dp_tunnel` mode, debugfs triggers, PHY "dpin clocks", `dp_in_skip_mask`; v4
(`02-v4-macos-sequence.patch`) = the macOS-faithful handshake, dpin bridge writes, tunnel PLL
sequence, crossbar ordering; v5 (`03-v5-auto-hotplug.patch`) = tunnel notifier, auto connect,
forced modeset, `powered`.

---

## A. Device tree (`t8103.dtsi`, `t8103-j313.dts`)

### A1. `t8103.dtsi`: `atc1_dpin0` / `atc1_dpin1` nodes — RESHAPE
```
atc1_dpin0: dpin@501e50000 { compatible = "apple,t8103-atc-dpin"; reg = <0x5 0x01e50000 0x0 0x4000>; power-domains = <&ps_atc1_usb>; };
atc1_dpin1: dpin@501e58000 { ... 0x01e58000 ... };
```
Addresses from the macOS ADT (`reports/macos-dump/atc1-dpin0.txt`: `reg = <0000e501 05000000 00400000
00000000>` → 0x5_01e50000, size 0x4000; IRQ 887; properties `dp-switch-dfp-port=1`, `port-number=2`,
`transport-type=5`, `transport-tunneled=1`, `dpxbar-parent`, `acio-parent`, `atc-phy`). The power
domain is a guess (the crossbar's); the block was always accessible while the port was in TBT mode.
For a rewrite: write a DT binding, give it a tiny driver (or fold it into the crossbar driver, which
is where macOS's `AppleT8103ATCDPXBAR` keeps the DP-IN ports), expose "activate/deactivate" to the DCP
through a proper API instead of `of_iomap` from the DCP driver. The interrupt (887) is unused; macOS
services it (status ack pattern in phase 1), Linux got away without it.

### A2. `t8103-j313.dts`: enable dcpext and route it — RESHAPE
- `&display { iommus = <&disp0_dart 0>, <&dispext0_dart 0>; }`, `dispext0_dart`, `dcpext_dart`,
  `dcpext_mbox` status okay — plain enabling of the external DCP, same as other Asahi machines that
  have dcpext on (KEEP).
- `&dcpext`: `apple,connector-type = "DP"`; `apple,dptx-phy = <1>` (ATC1), `apple,dptx-core = <1>`
  (DPIN0 in the DCP firmware's numbering: DPPHY=0, DPIN0=1, DPIN1=2 from m1n1 `dcpav.py`);
  `phys = <&atcphy1 PHY_TYPE_DP>` (KEEP: the DCP needs the PHY handle to drive PCLK);
  `mux-controls = <&atcphy1_xbar 1>, <&atcphy1_xbar 2>` = crossbar controls dpin0 and dpin1
  (KEEP); `mux-index = <0>` = dispext0,0 (KEEP).
- `apple,tbt-dpin-test;` — HACK marker that switches the driver into DP-IN mode. A clean version
  would derive "this DCP is tunneled" from the presence of a DP-IN phandle, or better from an
  `apple,dptx-core` value that names a DP-IN core.
- `apple,tbt-dpin = <&atc1_dpin0>, <&atc1_dpin1>;` — RESHAPE into whatever API the dpin driver gets.
- `apple,tbt-nhi = <&usb4_1_nhi>;` — RESHAPE: identifies which host interface's tunnels belong to
  this DCP. Alternatively derive it from `apple,dptx-phy` (ATC1 ↔ usb4_1) in code.
- `aliases { dcpext = &dcpext; }` — KEEP (the DCP driver uses the alias for its index).

The DTB is loaded by m1n1 from the bundle, not by the kernel package; that is why every kernel
change here needed a new `boot.bin` (`scripts/assemble-thunderbolt-bundle.py`).

---

## B. Type-C PHY (`drivers/phy/apple/atc.c`)

### B1. `dpin_mode` module parameter — HACK
Runtime switch between the v4 sequence (1), the v3 sequence (2) and nothing (0). Drop it; keep one
path.

### B2. `atcphy_mode_is_tunnel()` — KEEP
`mode == USB4 || mode == TBT`. The PHY is put into TBT mode by the tipd Thunderbolt switch long
before the DCP asks for a pixel clock; the DP configure path has to know it must not touch the lanes.

### B3. `atcphy_dpin_enable_clocks_legacy()` — HACK (v3)
DP alt-mode style: all three PCLK selects = 1, `ACIOPHY_PLL_COMMON_CTRL WAIT_FOR_CMN_READY`. Not what
macOS does. Delete.

### B4. `dp_tunnel_pclk_config` + `atcphy_dp_tunnel_enable_pclk()` — KEEP (values are ground truth)
The table is the decode of `FREQ_DESC_A/B/C` from the trace (02-macos-sequence.md): count 0x21c, no
fraction, pclk_div_sel 5, lfclk_ctrl 5, vclk_op_divn 2, vreg bypass. The existing generic field-write
code in `atcphy_dp_configure()` reproduces macOS's final register values exactly from this table
(including lfsdm_div 1 and vclk_pre_divn 1 which the generic code always sets). The enable function
sets the three PCLK enables (macOS already had them set before its sequence; where they get set on
macOS was not traced — possibly the TBT PHY init), then `PMA_LANE_RESET_N`, `_OV`, and
`DPTX_PCLK1_SELECT = 1`, in that order, matching trace lines 2209–2216.

### B5. `atcphy_dp_configure()` tunnel branch — RESHAPE
In tunnel mode: always re-run (no `dp_link_rate == lr` short-circuit, so a replug re-programs), use
the tunnel table, and three deltas vs alt mode, each from the trace:
- `AUSPLL_CLKOUT_DIV PLLA_REFBUFCLK_DI = 1` (alt mode 7)
- post-lock `atcphy_auspll_apb_command(0x2000)` (alt mode 0x2800)
- skip the lane configuration (`mode_cfg->dp_lane` is already false for TBT) and skip clearing
  `DP_PMA_BYTECLK_RESET` / `DP_MAC_DIV20_CLK_SEL` (macOS leaves the byte clock in reset; no DP lanes)
The `ACIOPHY_CMN_SHM_STS_REG0 CMD_READY` poll before programming is not in the macOS trace but is
harmless and passes. The generic sequence's `AUSPLL_FREQ_CFG` refclk clear, DTC_VREG bypass, BGR
ctrl-avail, CLKOUT_MASTER three drivers, APB cmd 0, PCLK_STAT lock poll all match the trace 1:1.
For a rewrite: add a proper PHY API for "DP tunnel pixel clock" instead of overloading
`phy_configure(PHY_MODE_DP)` on a PHY that is in TBT mode — e.g. a new `phy_configure_opts` flag or a
dedicated `phy_set_mode_ext(PHY_MODE_DP, submode=TUNNEL)`.

### B6. `atcphy_dp_tunnel_disable_pclk()` — KEEP
`unconfigureDPTunnelMode`: clear CLKOUT_MASTER bits 2, 4, 6 in that order, APB command 3. Reached
through `phy_configure` with link rate 0 (`case 0` in `atcphy_dpphy_configure`).

### B7. `atcphy_dpphy_validate()` returns 4 lanes in TBT/USB4 mode — KEEP-ish
`dptxport_call_get_max_lane_count` would otherwise ask the PHY and get 0 lanes. v4 short-circuits
that call anyway for `dp_tunnel` (reply 4, as macOS does), so this is belt and braces.

---

## C. Thunderbolt core (`drivers/thunderbolt/tb.c`, `include/linux/thunderbolt.h`)

### C1. `dp_in_skip_mask` — HACK (v3)
Lets you steer the tunnel to DP IN 6 instead of 5 for experiments. Delete.

### C2. DP tunnel notifier — RESHAPE
`tb_dp_tunnel_notify()` at the two hook points, a replay list, `tb_dp_tunnel_notifier_register/
unregister` exported. It is Apple-specific glue living in generic code. Options for a cleaner shape:
(a) a generic "DP tunnel established/torn down" notification in the thunderbolt core with the host
adapter's `struct device` (there is precedent for USB4 port devices, `usb4_usb3_port_match`), (b) let
the Apple NHI driver (`drivers/thunderbolt/apple.c`) own it and expose it through its platform device,
(c) model the DP IN adapter as a device the DCP can bind to. Whatever the shape, the *semantics* that
proved right: notify after activation (before DPRX completes, because DPRX only completes after the
DCP's ACTIVATE), notify on every teardown path (both go through `tb_deactivate_and_free_tunnel`),
replay current state to late subscribers.

---

## D. DCP driver, structure (`dcp-internal.h`, `dcp.h`, probe)

### D1. New `struct apple_dcp` fields — RESHAPE
`dp_tunnel`, `tunnel_mux_selected`, `dptx_core`, `tunnel_mux_index`, `xbar_dpin[2]`, `tunnel_dpin`,
`dpin_regs[2]`, `dpin_lock`, `dpin_active`, `dpin_activate_completion`, `tb_dp_nb`,
`tb_dp_nb_registered`, `tb_nhi_node`, `dpin_hotplug_work`, `dpin_tunnel_up`, `dpin_tunnel_in_port`,
`dpin_hotplug_retries`, `powered`. Most of this belongs in a small `struct dcp_dpin` sub-object (or a
separate file `dpin.c`) rather than sprinkled into the main struct.

### D2. probe (`dcp_platform_probe`) — RESHAPE
Reads `apple,dptx-core` (1 or 2), `mux-index`, gets both crossbar controls (`dp-xbar`,
`dp-xbar-dpin1`), maps the dpin blocks, inits the lock/completion/work, parses `apple,tbt-nhi`,
registers the notifier. The existing DP-alt-mode setup (`if (dcp->phy)` block: DP2HDMI GPIOs, typec
mux, `mux_control_select` at probe) is skipped for the tunnel route (`if (dcp->phy &&
!dcp->dp_tunnel)`) — that skip is essential: the alt-mode path selects the crossbar at probe and
registers a Type-C mux that would fight the tipd Thunderbolt switch. `dcp_start()` starts the DPTX
endpoint when `dcp->phy || dcp->dp_tunnel` (was `dcp->phy` only).

### D3. debugfs `tunnel_hpd` / `tunnel_dpin` (`connector.c`) — HACK, but keep something like it
Manual trigger for connect/disconnect and DP IN 0/1 selection under `/sys/kernel/debug/dri/*/DP-1/`.
Invaluable for bring-up; a rewrite can keep it behind `CONFIG_DRM_APPLE_DEBUG`.

### D4. `dcp_dptx_tunnel_select_dpin()` / `_get_dpin()` — HACK
Runtime switch between dpin0 and dpin1 (only allowed while disconnected). In practice port 5/dpin0 is
always what the core picks first; v5's auto path selects by the notified DP IN number. Keep the
mapping (DP IN 5 → dpin0 → dptx core 1; 6 → dpin1 → core 2), drop the debugfs knob if you like.

### D5. Module parameters `dpin_validate`, `dpin_connect_unk`, `dpin_hpd_after_activate`,
`dpin_auto` (dcp.c), `dpin_prime_rate` (dptxep.c) — HACK
A/B switches for each delta between v3 and the macOS sequence. The defaults are the macOS behaviour
and the only tested-working combination. Hard-code: no validate, unk 0xb0101, HPD after ACTIVATE,
auto on, no priming.

### D6. Two unrelated fixes that rode along (`dcp_create_piodma_iommu_dev`) — KEEP/separate
`IS_ERR_OR_NULL` on the iommu domain and `dcp->piodma = NULL` on the error path, plus the newline in
the probe error string. Real bugs found while dcpext was first enabled on this machine; they belong
in their own commit.

---

## E. DCP driver, the DP-IN bridge helpers (`dcp.c`)

Register map used (offsets in the 0x4000 block): `0x00`, `0x04` status-ish, `0x08` enable
(value 3), `0x0c DPTX_INACTIVE`, `0x10 DPTX_INACTIVE_ACK`. All other words in the block read 0 and
were never written by macOS.

### E1. `dcp_dpin_enable()` — KEEP (phase 1)
`0x08 = 3`, read 0x04, read 0x00, read 0x04, write back 0x04 and 0x00. Called at the start of
`dcp_dptx_connect()` for the tunnel route, before `connectTo`.

### E2. `dcp_dpin_activate()` — KEEP (inside ACTIVATE)
`0x0c = 0`, poll `0x10` bit 0 clear (macOS reads once; the poll is defensive), `complete()` the
activate completion (used by the HPD-after-activate wait). This single write is what turned v2's
"AUX dead, DPRX never completes" into a working link, discovered by hand with `/dev/mem` before the
trace confirmed macOS does it inside ACTIVATE.

### E3. `dcp_dpin_xbar_up()` — KEEP (inside SET_LINK_RATE, after `phy_configure`)
`mux_control_select(dcp->xbar, mux_index)` guarded by `tunnel_mux_selected`. The mux driver's write
sequence already equals macOS's `bringConnectionUp`.

### E4. `dcp_dpin_xbar_down()` — KEEP (inside WILL_CHANGE_LINK_CONFIG, and on disconnect)
`0x0c = 1`, `mux_control_deselect`, `0x0c = 0`, no-op if the crossbar is not up (so the initial
WILL_CHANGE before the first SET_LINK_RATE does nothing, as on macOS).

### E5. `dcp_dpin_deactivate()` — KEEP (inside DEACTIVATE, and on disconnect)
`0x08 = 0`; if the crossbar is unexpectedly still up, tear it down first.

Locking: `dpin_lock` serializes the helpers; they must **not** take `hpd_mutex`, because they run in
the AFK receive context while `dcp_dptx_connect()` holds `hpd_mutex` waiting for a command reply
(the firmware sends AP calls *during* the `requestDisplay` command).

---

## F. DCP driver, the handshake (`dcp_dptx_connect` / `_disconnect`, `dptxep.c`)

### F1. `dcp_dptx_connect()` tunnel order — KEEP
`dcp_dpin_enable` → (no validate) → `dptxport_connect(core=1, atc=1, die=0, unk=0xb0101)` →
`dptxport_request_display` → unlock → wait for the ACTIVATE completion (2 s) →
`dptxport_set_hpd(true)` → wait for `linkcfg_completion` (2 s; completed by `SET_ACTIVE_LANE_COUNT`
with a non-zero count) → `av_service_connect`. The generic (alt-mode) order was validate → connect
→ requestDisplay → wait linkcfg → HPD; on the tunnel route the firmware answered our
`GET_SUPPORTS_HPD = 1` and waits for HPD before link config, so HPD must come first. Also note the
error handling: the original code ignored the return values of connect/request_display; v3 checks them.

### F2. `dcp_dptx_disconnect()` — KEEP
`releaseDisplay` under the mutex, then (outside it) `dcp_dpin_xbar_down` + `dcp_dpin_deactivate` as
a fallback in case the firmware did not run its teardown AP calls. `dcp_dptx_disconnect_oob()` (the
external entry point) additionally sends HPD(false) first, emits the DRM disconnect, and clears
`dcp->powered` for the tunnel route.

### F3. `dptxep.c` AP-call handlers, tunnel behaviour — KEEP
- `GET_SUPPORTS_HPD` → 1 (macOS). 
- `GET_MAX_LANE_COUNT` → 4 without asking the PHY.
- `ACTIVATE` → no `phy_set_mode_ext(DP)` (the PHY is in TBT mode and would return -EINVAL), call
  `dcp_dpin_activate()`; the `dpin_prime_rate` block is v3 residue (HACK, delete).
- `SET_LINK_RATE` → after `phy_configure` (which runs B5), `dcp_dpin_xbar_up()` if the rate is
  non-zero. Rate 0 reaches B6 through `phy_configure` with `link_rate = 0`.
- `WILL_CHANGE_LINK_CONFIG` → `dcp_dpin_xbar_down()`.
- `DEACTIVATE` → `dcp_dpin_deactivate()` instead of `phy_set_mode_ext(INVALID)` (which would try to
  power the TBT PHY down).
- `SET_TILED_DISPLAY_HINTS` → echo the request untouched (macOS keeps the first word 1; the generic
  fallback zeroes it). UNKNOWN whether it matters; replicated because it was cheap.
- `dptxport_connect()` gained a `unk_field` parameter; `dptxport_validate_connection` untouched.
`INACTIVE_SINK_DETECTED` (20) still hits the "acking unhandled call" fallback; fine.

---

## G. DRM glue (`dcp.c` atomic check, `apple_drv.c`) — see 04-drm-and-hotplug.md

`dcp_crtc_atomic_check()` forced modeset (RESHAPE, see the caveat), `dcp_needs_poweron()` +
`apple_crtc_atomic_enable()` (KEEP), `dcp->powered` bookkeeping in `dcp_poweron/off` (KEEP).

---

## H. Auto hotplug (`dcp.c`) — see 04-drm-and-hotplug.md

`dcp_tb_dp_notifier()`, `dcp_dpin_hotplug_work()`, `dcp_dpin_auto_stop()` and the
`platform_remove/shutdown` hooks. RESHAPE together with C2.

---

## What was never needed (dead ends, so you do not re-add them)

- Programming the DP adapters' Thunderbolt config space (bandwidth allocation mode, `DP_STATUS`):
  the LG is TBT3 without BW-alloc mode; the core's tunnel is complete as built.
- Any PCIe/USB tunnel work.
- `phy_set_mode(PHY_MODE_DP)` on the ATC PHY: it is in TBT mode; only PCLK1 is needed.
- Forcing a DPTX_INACTIVE 1→0 edge before connect (attempt 3): not the cause of the replug failure;
  the missing modeset was.
- The `DPRX_DONE`/"consumed bandwidth 0" theories from the v2/v3 era.
