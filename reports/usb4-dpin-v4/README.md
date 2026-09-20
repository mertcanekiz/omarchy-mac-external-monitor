# DP-IN v4 — replay the macOS DP-IN bring-up on Linux (built + installed 2026-09-20, NOT yet booted)

v4 turns the m1n1 hypervisor trace of macOS 13.5 lighting the LG UltraFine
(`reports/usb4-dpin-v3/HV-TRACE-FINDINGS.md`, run 8) into kernel code. Same kernel image and
release as v3 (`7.1.13-usb4-gpu-test`, `/boot/vmlinuz-usb4-gpu-test`); only `appledrm`,
`phy-apple-atc` and the J313 DTB changed. Kernel branch `thunderbolt-7.1.13-dpin-v4` in
`sources/linux-usb4-backport` (commit `9a7b5dbca`, one commit on top of v3 `51095b678`); the same
diff is `patches/thunderbolt-dpin-v4-macos-sequence.patch`.

The `/usr/lib/modules/7.1.13-usb4-gpu-test` tree had been deleted; `scripts/stage-usb4-dpin-v4.py`
reinstalled the complete tree from the v4 module build (1865 modules), so the older
"GPU + USB4" and "DP-IN v3" GRUB entries work again too (with v4's appledrm/phy modules).

## What differs from v3, and where each item comes from in the trace

| step | macOS (run 8) | v3 | v4 |
|---|---|---|---|
| dpin block `0x08` | `W 3` before connectTo (line 1829), `W 0` at DEACTIVATE | never written (Linux dump: 0) | `dcp_dpin_enable()` / `dcp_dpin_deactivate()` |
| dpin `0x04`/`0x00` | read, written back unchanged | untouched | same, in `dcp_dpin_enable()` |
| `DPTX_INACTIVE` (`0x0c`) | cleared inside `DPTX_APCALL_ACTIVATE` after `dpxbar+0x60 = 0` | manual `/dev/mem` poke before connect | `dcp_dpin_activate()` inside ACTIVATE, polls `0x10` |
| validateConnection | not sent | sent (unk 0x100) | skipped (`appledrm.dpin_validate=0`) |
| connectTo unk | `0xb0101` | `0` | `0xb0101` (`appledrm.dpin_connect_unk`) |
| requestDisplay | sent (tracer name "setPowerState", group 0 cmd 6) | sent | sent |
| GET_SUPPORTS_HPD reply | 1 | 0 | 1 in tunnel mode |
| hotPlugDetectChangeOccurred(true) | right after ACTIVATE, before link config | after link config (2 s wait) | after ACTIVATE (`appledrm.dpin_hpd_after_activate=1`) |
| PHY prime on ACTIVATE | none | PLL programmed at 5400 | none (`appledrm.dpin_prime_rate=0`) |
| SET_LINK_RATE PHY | `configureDPTunnelMode` sequence (lines 2171–2276) | DP alt-mode HBR2 table + DPRX/PCLK2 clocks | `phy_apple_atc.dpin_mode=1`: RBR VCO (count 0x21c, no fraction), pclk_div_sel 5, vclk_op_divn 2, refbufclk div 1 (v3: 7), APB cmd 0x2000 (v3: 0x2800), only PCLK1 select, byte clock left in reset |
| crossbar enables | inside SET_LINK_RATE after the PLL (lines 2292–2350) | at connect, before the DCP is even told to connect | `dcp_dpin_xbar_up()` after `phy_configure` in SET_LINK_RATE (same nine writes + pulse via the mux driver) |
| SET_TILED_DISPLAY_HINTS reply | request echoed untouched (first word 1) | first word zeroed | echoed untouched |
| unplug: WILL_CHANGE_LINK_CONFIG | `DPTX_INACTIVE` 1, crossbar teardown, `DPTX_INACTIVE` 0 | nothing | `dcp_dpin_xbar_down()` |
| unplug: SET_LINK_RATE 0 | `unconfigureDPTunnelMode`: drop CLKOUT_MASTER drivers, APB cmd 3 | nothing | `atcphy_dp_tunnel_disable_pclk()` |
| DEACTIVATE | dpin `0x08 = 0` | `phy_set_mode(INVALID)` on the TBT PHY | dpin `0x08 = 0`, PHY untouched |

Everything else already matched: GET_MAX_LINK_RATE → 0x1e, GET_MAX_LANE_COUNT → 4,
GET_MAX_DRIVE_SETTINGS → 3/3, down-spread unsupported, the crossbar write order, and the
Thunderbolt DP tunnel (paths + VE/AE) which the thunderbolt core builds by itself.

The PCLK frequency is the same in both PLL configurations under the divider model that fits all
four DP alt-mode tables (VCO = count × 12 MHz, pclk = VCO / (2 × (pclk_div_sel + 1)) → 540 MHz);
what differs is the VCO rate, the refbufclk divider and the post-lock APB command. Those are the
only PHY-side unknowns left, hence replicated byte for byte.

## Test procedure (one reboot)

1. LG on the **left-front** port with the Thunderbolt cable, then reboot and pick
   **Omarchy - Asahi 7.1 USB4 DP-IN v4 (manual)**.
2. ```sh
   cd /home/mert/Work/omarchy-mac-external-monitor
   uname -r                                    # 7.1.13-usb4-gpu-test
   sudo python3 scripts/run-dpin-v3.py status  # DP IN 0-0/port5 adapter_enabled, dprx_done false
   sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v4/attempt1-macos-seq --dpin 0
   scripts/webcam-snap.sh reports/usb4-dpin-v4/attempt1-macos-seq/panel.jpg   # the only picture proof
   journalctl -k -b --no-pager | grep -E 'DP-IN|dpin|crossbar|DPTX|dptx' > reports/usb4-dpin-v4/attempt1-macos-seq/dpin-journal.txt
   ```
   No `/dev/mem` pokes any more: the kernel does the `0x08`/`0x0c` writes itself. Expected new
   log lines, in order: `DP-IN dpin0 before enable` / `after enable` (08 should read 3),
   `DP-IN dpin0 activate: DPTX_INACTIVE cleared, ack=0x0 (0)`, `DPTX HPD assert (after activate): 0`,
   `DP-IN configure: ... dpin_mode=1`, `DP-IN PCLK on: TX_DP_CTRL0=0x0000e01d PCLK_STAT=0x...8 CLKOUT_MASTER=0x00002054`,
   `DP-IN crossbar up (dpin0 <- dispext0): 0`, then the usual `DPRX capabilities read completed`,
   `DP-1` connected with 7 modes.
3. If still dark, A/B the deltas without rebooting (`disconnect` between attempts):
   ```sh
   sudo python3 scripts/run-dpin-v3.py disconnect
   sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v4/attempt2-legacy-pll --dpin 0 --dpin-mode 2
   echo 0 | sudo tee /sys/module/appledrm/parameters/dpin_hpd_after_activate   # HPD after link config (v3 order)
   echo 1 | sudo tee /sys/module/appledrm/parameters/dpin_validate             # v3's validateConnection
   echo 0 | sudo tee /sys/module/appledrm/parameters/dpin_connect_unk          # v3's connectTo
   ```
   Also worth one try each: power-cycle the LG at the wall after `DP-1` is up; DPMS off/on DP-1 in
   Hyprland to force a fresh modeset.
4. If the tunnel drops (replug), `disconnect` then `connect` again; the kernel redoes the whole
   sequence including DPTX_INACTIVE.

## Restore

`sudo python3 scripts/stage-usb4-dpin-v4.py restore` puts the previous loader (the stock one,
`boot.bin.before-usb4-dpin-v4` = `boot.bin.before-display-test`) and the previous GRUB file back.
The module tree and the v4 initramfs stay. From macOS/Recovery: `USB4-DPIN-V4-RECOVERY.txt` on the ESP.

## Files

- `scripts/build-usb4-dpin-v4.sh quick|modules`, `scripts/build-usb4-dpin-v4-initramfs.sh`,
  `scripts/assemble-thunderbolt-bundle.py --profile usb4-dpin-v4`, `scripts/stage-usb4-dpin-v4.py install|restore`
- `config/usb4-dpin-v4-grub-entry.cfg`; artifacts in `artifacts/usb4-dpin-v4/` (module root, initramfs, bundle)
- `scripts/run-dpin-v3.py` now takes `--dpin-mode` instead of `--phy-clocks` and records the dpin
  register blocks in `status`/`before.json`/`after.json`.
- `boot-bundle.json`, `stage-manifest.json`, `build-*.log`, `initramfs-contents.txt` in this directory.

## GRUB cleanup (2026-09-20)

`/boot/grub/custom.cfg` now holds only the v4 entry; the generated default "Omarchy Linux" entry
comes from `grub.cfg`. The old experiment entries (display-test, USB4 bring-up, DP-IN v1/v2,
GPU+USB4, DP-IN v3) are kept in `config/grub-custom-all-experiments.cfg.bak`; their kernels,
initramfs images and loader bundles were not deleted. `stage-usb4-dpin-v4.py restore` now leaves
an empty custom.cfg (default entry only).

## Purge of the old experiments (2026-09-20)

Deleted from `/boot`: `vmlinuz-thunderbolt-test` and the display-test, thunderbolt-test, DP-IN
v1/v2, GPU+USB4 and DP-IN v3 initramfs images. Deleted from the ESP: every experiment loader
bundle and `before-*` backup except the stock loader (`boot.bin.before-display-test`, also
`boot.bin.before-usb4-dpin-v4`), the v4 bundle and `boot.bin.hvproxy`; the old recovery notes went
with them and `USB4-DPIN-V4-RECOVERY.txt` is now self-contained (copy in `config/`). Copies of all
deleted bundles/initramfs images still exist under `artifacts/` (gitignored) if ever needed.
