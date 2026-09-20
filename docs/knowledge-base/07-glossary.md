# 07 — Glossary

- **ACIO / CIO**: Apple's name for the USB4/Thunderbolt host router IP ("Converged I/O"). `acio1`
  in the ADT = the front port's router; NHI = its host interface (DMA rings).
- **ADT**: Apple Device Tree, dumped from macOS (`ioreg -p IODeviceTree`); source of all addresses.
- **AFK / EPIC**: the RTKit endpoint framing (AFK ring buffers) and the RPC layer (EPIC services,
  commands/replies/notifies) used by the DCP firmware. `afk.c`, `dptxep.c`.
- **AP call**: an EPIC "notify" from the DCP firmware to the AP (Linux) that must be answered;
  `DPTX_APCALL_*`.
- **ATC / atcphy**: Apple Type-C PHY (`phy-apple-atc`), per port; contains the AUSPLL and the DP
  lane/pixel clock machinery. Modes: USB2/USB3/USB3_DP/DP/TBT/USB4.
- **AUSPLL**: the PLL inside the Type-C PHY that generates DP link and pixel clocks
  (`AUSPLL_*` registers at core+0x2000…).
- **atc-dpin bridge**: Apple block (`atc1-dpin0/1`) between the display crossbar and the CIO DP IN
  adapter. Registers used: 0x08 enable, 0x0c DPTX_INACTIVE, 0x10 DPTX_INACTIVE_ACK.
- **CD321x / tipd**: the Type-C port controller (TI TPS6598x family variant), driver `tps6598x`.
  Decides USB/DP-alt/TBT mode; exposes DATA_STATUS (TBT_CONNECTION, DP_CONNECTION bits).
- **DCP / dcpext**: Display CoProcessor; `dcp0` drives the internal panel, `dcpext` the external
  outputs. Runs Apple firmware; Linux driver `appledrm`.
- **dispext0**: the pixel pipeline of dcpext; crossbar input "dispext0,0".
- **DP IN / DP OUT adapter**: USB4 router adapters that packetize a DP stream into a tunnel
  (host side, ports 5/6) and unpack it (LG side, ports 10/11).
- **DPRX done**: bit in the DP IN adapter's `DP_COMMON_CAP` set when the receiver capability read
  over tunneled AUX completed. Needs the DCP's AUX to reach the adapter, i.e. DPTX_INACTIVE cleared.
- **dpxbar / display crossbar**: mux routing dispext outputs to dpphy/dpin0/dpin1 on a port;
  driver `mux-apple-display-crossbar`.
- **HBR2**: DP link rate 5.4 Gb/s per lane (code 0x14); symbol clock 540 MHz.
- **m1n1 hypervisor**: Asahi's bootloader running macOS as a guest with MMIO tracing; the tool
  that produced the ground truth.
- **NHI**: Native Host Interface, the host-side DMA engine of the router; `thunderbolt_apple` driver.
- **PCLK1**: the pixel clock output of the ATC PHY selected for the crossbar's dpin0 path
  (`DPTX_PCLK1_SELECT`, `FIFO_RD_PCLK1_EN`).
- **RTKit**: Apple's coprocessor runtime/mailbox protocol.
- **TBT3 / USB4 mode**: the port's lanes carry Thunderbolt; the ATC PHY is in `MODE_TBT`; DP is
  tunneled, not on the lanes.
- **valid_mode / powered**: `appledrm` state: a mode has been set on the firmware / the firmware
  pipeline is powered (set_power_state). Both false after a tunnel reconnect.
