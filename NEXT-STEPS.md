> **2026-09-19 — DP alt mode investigation (Paugge USB4 cable):** see
> [reports/dp-altmode/INVESTIGATION.md](reports/dp-altmode/INVESTIGATION.md). Short version: the
> USB4 cable makes the CD321x enter Thunderbolt 3 (firmware decides, Linux cannot override), so DP alt
> mode needs a non-Thunderbolt full-featured USB-C cable with SBU/AUX wiring. The fairydust port is
> prepared and compile-checked in `sources/linux-dpalt` / `patches/dp-altmode/`, not built for boot.

> **Handoff for a fresh session:** see [reports/usb4-dpin-v3/HANDOFF.md](reports/usb4-dpin-v3/HANDOFF.md).

# WORKING: LG UltraFine over Thunderbolt (DP-IN) — 2026-09-18 04:21

The missing piece was Apple's DP-IN bridge block (`atc1-dpin0` at 0x501e50000, `atc1-dpin1` at
0x501e58000, 0x4000 each, "atc-dpin,t8103"; irqs 887/888). macOS's AppleATCDPINAdapterPort clears
"DPTX_INACTIVE" (offset 0x0c, default 1) and polls "DPTX_INACTIVE_ACK" (offset 0x10) before the
DCP activates. With that done from userspace (`artifacts/mmio/mmio-rw w 501e5000c 0`), the v3
connect fully works: DPRX read completes, HBR2 x4 link training, DP-1 connected, 3840x2160@60 in
Hyprland. Evidence: reports/usb4-dpin-v3/attempt6-dpin0-dptx-active, reports/macos-dump/.

Manual procedure on the DP-IN v3 boot entry (until it is baked into the kernel):
```sh
cd /home/mert/Work/omarchy-mac-external-monitor
sudo artifacts/mmio/mmio-rw w 501e5000c 0 && sudo artifacts/mmio/mmio-rw p 501e50010 0 1 500
sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v3/<new-dir> --dpin 0
```
Remaining: put the register write into dcp_dptx_connect (after crossbar select, before
dptxport_connect; set back to 1 on disconnect), add atc-dpin DT nodes, automate on tunnel HPD.

---

# Current work: DP-IN v3 (LG UltraFine over Thunderbolt) — boot-tested 2026-09-18 04:00, no picture

Result: v3 boots cleanly (dcpext up, DP-1 registered, DP tunnel held open, PHY DP clocks enabled and
AUSPLL locked in TBT mode). Every combination still fails identically: firmware calls
get_supports_hpd, get_max_lane_count, activate, then ~7 s later device_not_responding(22) and
device_not_started(24); DPRX_DONE never sets. Tested (reports/usb4-dpin-v3/attempt*):
DP IN 0/1 crossbar route x host adapter 5/6 x PHY clock modes 2 and 3. Conclusion: the AUX path
from the external DCP into the CIO DP IN adapters needs an Apple-specific enable we do not know
(likely ACIO-side; the host router has vendor caps 0x05/vs 0-5 that Linux never touches).

Most useful next step: boot macOS with the LG connected and dump
`ioreg -l -w0 -p IODeviceTree > adt.txt`, `ioreg -l -w0 > ioreg.txt`,
`system_profiler SPThunderboltDataType SPDisplaysDataType`. Needed: /arm-io/atc1-dpin0,
atc1-dpin1, acio1 properties (regs, tunables), and the IOThunderbolt DP adapter / DCP DPTX classes.

## Original v3 plan (kept for reference)

Installed and activated on 2026-09-18 ~03:55. Select **Omarchy - Asahi 7.1 USB4 DP-IN v3 (manual)**
in GRUB (same kernel `7.1.13-usb4-gpu-test`, new initramfs, new m1n1 DTB, cmdline adds
`thunderbolt.dprx_timeout=-1 thunderbolt.dyndbg=+p`). Keep the LG on the front (left-front) port
with the Thunderbolt cable during boot.

## Why v3 (see reports/usb4-backport/boot-*.json and reports/thunderbolt/dpin-v2-*)

- USB4 transport works on the 7.1.13 backport kernel: NHI 501f00000, LG router 0-1 authorized.
  The LG exposes two DP OUT adapters (ports 10/11) and PCIe, no USB3 adapter.
- The thunderbolt core builds DP tunnel 0:5 <-> 1:10 by itself; DPRX_DONE never sets and it is
  torn down after 12 s unless `dprx_timeout=-1`.
- In v2 the tunnel was fully programmed when the DCP-ext connected, and firmware still reported
  device_not_responding/device_not_started: the AUX path DCP -> DP IN adapter is dead.
- The Type-C PHY driver only enables the DP clocks (DPRX/DPTX pixel clocks, AUSPLL) for DP alt
  modes; in USB4/TBT mode nothing feeds the CIO DP IN adapters. Asahi docs confirm dcpext is the
  only M1 controller that reaches USB-C; upstream has no DP tunneling yet.

## What v3 changes (patches/thunderbolt-dpin-v3-experiment.patch, branch thunderbolt-7.1.13-dpin-v3)

- v2 DCP-ext DP-IN route ported to 7.1.13 (j313 DT: dcpext on, dpin crossbar controls 1 and 2,
  `phys = atcphy1 DP`, `apple,tbt-dpin-test`).
- phy-apple-atc: in USB4/TBT mode, `phy_configure(rate)` enables the DP clocks and programs the
  AUSPLL (`dpin_clocks` param 0-3, default 2, writable at runtime).
- appledrm: keeps the PHY in tunnel mode; primes the clocks on firmware `activate`
  (`dpin_prime_rate`, default 5400); debugfs `tunnel_dpin` (0/1) picks DP IN 0/1; `tunnel_hpd`.
- thunderbolt: `dp_in_skip_mask` (writable) to steer the tunnel to host DP IN 5 or 6.

## After boot

```sh
cd /home/mert/Work/omarchy-mac-external-monitor
sudo python3 scripts/run-dpin-v3.py status          # expect 0-0/port5 DP IN adapter_enabled, dprx_done false
sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v3/attempt1-dpin0-clk2
```
Look for: `set_link_rate`/`set_active_lane_count` callbacks in the trace, `DPRX capabilities read
completed` in the journal, `dprx_done: true` on 0-0/port5, and `card*-DP-1: connected`.

Matrix if it fails (disconnect between attempts):
```sh
sudo python3 scripts/run-dpin-v3.py disconnect
sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v3/attempt2-dpin1 --dpin 1
sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v3/attempt3-clk3 --dpin 0 --phy-clocks 3
sudo python3 scripts/run-dpin-v3.py disconnect && sudo python3 scripts/run-dpin-v3.py retunnel --skip-mask 0x20   # tunnel on port 6
sudo python3 scripts/run-dpin-v3.py connect reports/usb4-dpin-v3/attempt4-port6-dpin1 --dpin 1
```

## Restore

`sudo python3 scripts/stage-usb4-dpin-v3.py restore` puts back the previous loader
(`boot.bin.before-usb4-dpin-v3`), the three baseline modules and the GRUB file. The stock loader
`boot.bin.before-display-test` is untouched; `USB4-DPIN-V3-RECOVERY.txt` is on the ESP.

---

# Current work: stock 7.1.13 GPU + USB4 backport

The 7.2 test kernel lacks the Asahi GPU driver and uses llvmpipe, explaining
the loss of hardware acceleration. A new branch, `thunderbolt-7.1.13-gpu`, in
`sources/linux-usb4-backport` backports the newer USB4 transport onto the exact
installed `asahi-7.1.13-3` source. GPU, display, Rust and IOMMU sources are
unchanged from stock. See [backport status](reports/usb4-backport/README.md).

**Built, installed, verified and activated on 2026-09-18; awaiting reboot.**
Select **Omarchy - Asahi 7.1 GPU + USB4 (manual)** in GRUB. The expected release
is `7.1.13-usb4-gpu-test`. No reboot was performed and the default entry was not
changed. The GPU is compiled and linked into this kernel, but hardware
rendering and USB4 enumeration must still be verified together after boot.
The first baseline does not enable the external display controller or promise
a monitor picture.

After boot:

```sh
python3 scripts/verify-usb4-gpu-boot.py
```

The active m1n1 device tree is now the 7.1 USB4 baseline. Do not select an older
DP-IN experiment expecting its former device tree. The original stock loader
and previous DP-IN v2 loader are preserved. From this project, restore stock
with `sudo python3 scripts/stage-usb4-gpu-test.py restore-stock`, then reboot
into the ordinary stock Asahi kernel. See [recovery instructions](config/USB4-GPU-RECOVERY.txt)
for the macOS/Recovery path if Linux cannot boot.

## Previous experiment: v2 boots; DP-IN activation still times out

Updated 2026-09-18 after the USB4 test boot.

The LG UltraFine is authorized and connected at 20 Gb/s. The monitor exposes
DP/PCIe adapters but no native USB3 adapter, so USB3-over-USB4 is not a suitable
milestone for this monitor. The running tree disables external DCP; the first
DP tunnel timed out during receiver negotiation.

A first display-driver/DT experiment crashed during external DCP initialization.
V2 fixes that failure: both DCPs boot and eDP-1/DP-1 register. Its first captured
connection attempt validates ATC1/core1 and selects the DPIN0 crossbar, but
times out before link configuration completes; DPRX_DONE stays clear and DP-1
has no modes. Read [the v2 live result](reports/thunderbolt/dpin-v2-result.md).
Do not repeat the connection command blindly: its requested state remains set.
It routes external DCP to the front port's Thunderbolt DPIN0, provides a manual
firmware trigger, and captures the handshake. Display output remains unverified.

The sections below retain the earlier cable/display experiments as history.
Their next-step instructions are superseded by the DP-IN procedure above.

## USB4 first boot

The 7.2.2 USB4 test target was built, staged, activated, and successfully booted on 2026-09-18 using:

**Omarchy - Asahi USB4 bring-up (manual)**

The ordinary entry remains the default. The selected entry should report `7.2.2-thunderbolt-test+`. For this first milestone, a working picture is not required: success means the Apple NHI registers, a USB4 domain/router appears, and the monitor's USB devices enumerate through a USB3 tunnel.

Immediately after login, collect a new result without overwriting prior evidence:

```bash
cd /home/mert/Work/omarchy-mac-external-monitor
uname -r
python3 scripts/collect-thunderbolt-state.py reports/thunderbolt/first-boot.json
```

Useful direct checks are:

```bash
lsmod | grep -E 'thunderbolt|apple'
find /sys/bus/thunderbolt/devices -maxdepth 2 -type f -print
lsusb -tv
journalctl -k -b --no-pager | grep -Ei 'thunderbolt|usb4|acio|nhi|drom|xhci'
```

If startup fails, restore the immediately previous loader bundle from Linux/macOS Recovery using `boot.bin.before-thunderbolt-test`, as described in `/boot/efi/m1n1/THUNDERBOLT-TEST-RECOVERY.txt`. From a working Linux boot:

```bash
cd /home/mert/Work/omarchy-mac-external-monitor
sudo bash scripts/thunderbolt-bundle.sh restore-previous
```

This milestone targets USB3 tunneling only. The imported Apple host driver does not implement DisplayPort tunneling, so a successful USB4 test establishes the foundation for the subsequent DP tunnel work; it does not by itself make the LG panel light up.

**The test loads and USB-C DisplayPort negotiation now succeeds, but display startup times out.** The LG USB devices enumerate, while `DP-1` still reports `disconnected` with no modes. See the latest boot and expanded trace below. The internal screen remains usable.

## Second cable: Thunderbolt negotiation confirmed

The attended reconnect trace recorded:

```text
cd321x_data_status: DATA_CONNECTION|ACTIVE_CABLE|USB_DATA_ROLE|TBT_CONNECTION|0x400000
```

This confirms **Thunderbolt transport was negotiated with the second cable**. The captured reconnect did not report `DP_CONNECTION` or `HPD_LEVEL`; `DP-1` remained disconnected. The external DCP and patched drivers are running, but this connection does not exercise the DisplayPort Alt Mode path they enable. This does not yet prove that a USB-C DisplayPort cable will produce a working picture.

Next use a known full-featured USB-C video/DisplayPort cable, preferably the LG's separately supplied USB-C cable. Do not substitute a charging-only USB-C cable. No additional kernel change is justified by this trace yet.

Evidence: [negotiation trace](reports/second-cable-typec-trace.txt), [after reconnect](reports/second-cable-after-reconnect.json). The helper `scripts/trace-typec.py` records existing tracepoints for 120 seconds in a private instance, then disables and removes it; it does not reset devices or reload drivers.

## Third cable: USB reported, no display negotiation yet

The user identified the next cable as USB-C. Its attended reconnect reports:

```text
cd321x_data_status: DATA_CONNECTION|USB2_CONNECTION|USB3_CONNECTION|USB3_GEN2|USB_DATA_ROLE
```

No `DP_CONNECTION`, `HPD_LEVEL`, or `TBT_CONNECTION` has appeared in this capture. `DP-1` remains disconnected and no USB device has enumerated. USB flags in a controller status report alone do not prove the cable supports video or that USB enumeration succeeded. The user confirmed a Thunderbolt-marked LG socket; the cable has never been tested for video. Next coordinate one LG mains-power cycle with this USB-C cable connected, to test fresh negotiation. A failed attempt still cannot rule out the cable.

Evidence: [third cable snapshot](reports/third-usbc-after-reconnect.json), [third negotiation trace](reports/third-usbc-typec-trace.txt).

## LG power-cycle result

The user disconnected and restored LG mains power with the third USB-C cable attached. The trace again reported USB data flags but no `DP_CONNECTION`, `HPD_LEVEL`, or `TBT_CONNECTION`. `DP-1` stayed disconnected. This attempt did not fix negotiation.

Evidence: [power-cycle trace](reports/usbc-monitor-power-cycle-trace.txt), [state afterward](reports/usbc-after-monitor-power-cycle.json).

## USB-C preconnected boot: DisplayPort negotiation now confirmed

The reboot with this USB-C cable already attached progressed further. Both patched Type-C drivers loaded. The LG USB hub, audio, and display controls enumerated, and the external DCP started a connection attempt. The external screen remained black and `DP-1` remained disconnected.

An expanded trace of the subsequent reconnect established:

1. `DP_CONNECTION`, pin assignment C.
2. `HPD_LEVEL` asserted by the monitor.
3. DCP connection routed to core 0 / ATC 1 / die 0.
4. Firmware asks `get_supports_hpd`, `get_max_lane_count`, then `activate`.
5. About seven seconds later: `device_busy_timeout` and `device_not_started`.
6. No `set_link_rate` or `set_active_lane_count` callbacks appeared in the capture. Cached external display attributes/timings were all empty.

The earlier statement that this USB-C cable never negotiates DisplayPort is superseded by this boot and trace. The failure is now narrowed to display startup after negotiation. It does not establish whether the physical video/AUX path through the cable works; USB-C control negotiation and USB2 enumeration alone do not settle that. PHY routing, firmware communication, or cable problems remain possibilities.

Evidence: [boot state](reports/usbc-preconnected-boot.json), [kernel log](reports/usbc-preconnected-kernel.log), [expanded trace](reports/usbc-dptx-reconnect-trace.txt). Firmware callback names were checked against the exact installed kernel source's `drivers/gpu/drm/apple/dptxep.h`.

## Do this next

The most useful hardware check is now **a known working video cable**: test this exact USB-C cable and the LG on a computer known to support USB-C video, or substitute a USB-C cable already proven to carry video. No further identical reboot or monitor power-cycle test is needed.

If that cable/monitor path works elsewhere but still fails here, the next Linux experiment should use the prepared diagnostic display module in a new, separate initramfs and manual GRUB entry. Do not unload the live `appledrm` driver; it also drives the internal panel.

### Diagnostic display module prepared, not installed

`artifacts/display-debug/drivers/gpu/drm/apple/appledrm.ko` was built from the exact stock source plus [logging-only patch](patches/display-startup-diagnostics.patch). Compilation, MODPOST, linking, BTF and matching vermagic passed. See [artifact metadata](reports/display-debug-artifact.json) and [build log](reports/display-debug-build.log).

This is **instrumentation, not a fix**. It records return codes currently ignored for connect/request-display/HPD calls, explicitly reports link-configuration completion versus timeout, and logs the PHY lane count and requested link rate. Source review found that the existing timeout check tests `< 0`, although `wait_for_completion_timeout()` returns zero on timeout; this can hide a timeout in the normal log. The patch adds reporting without changing that startup behavior.

For a future boot test: create a fresh private module tree with the existing patched Type-C pair plus this diagnostic `appledrm.ko`; build a separately named initramfs preserving the Asahi hooks; verify its embedded modules; add a separate manual entry; leave the current test and stock images intact. The same experimental m1n1 device tree can be reused. None of those diagnostic boot-installation steps has been performed yet.

## What is finished

- Created and checksum-verified a **337 MB boot/configuration/module backup** in `snapshots/boot-review-ywfOl6EC/`. It includes the original EFI contents and vendor firmware.
- Read and syntax-checked your real GRUB configuration, including its Btrfs `/@/boot/...` paths.
- Compared the stock and test initramfs contents: **982 files identical**. Only the two intended driver modules and build/load configuration changed; the stock image also has an `early_cpio` marker absent from the test image. The Asahi firmware hooks are identical.
- Installed a **separate** test initramfs and a manual GRUB entry. The normal stock entry remains the default.
- Put both the original recovery copy and candidate on the EFI partition, with a plain-text recovery guide beside them.
- Confirmed both currently resident Type-C drivers are experimental by ELF build ID. The off-screen renderer remains **Apple M1 (G13G B1)**, Mesa 26.1.8.
- Confirmed a registered **Macintosh HD** boot target exists. This does not prove it successfully boots.
- Added guarded activation and restoration helpers. No helper reboots automatically.

| Installed file | Purpose |
| --- | --- |
| `/boot/initramfs-display-test.img` | Separate test initramfs with the patched module pair |
| `/boot/grub/custom.cfg` | Manual entry: **Omarchy - external monitor test (manual)** |
| `/boot/efi/m1n1/boot.bin` | Experimental bundle, activated after recovery was confirmed |
| `/boot/efi/m1n1/boot.bin.before-display-test` | Verified original recovery copy |
| `/boot/efi/m1n1/boot.bin.display-test` | Verified experimental source copy |
| `/boot/efi/m1n1/DISPLAY-TEST-RECOVERY.txt` | Recovery instructions accessible outside Linux |

No stock kernel, stock initramfs, root module files, GRUB default, NVRAM boot selection, or Hyprland configuration was changed. The added test menu entry alone does not activate the device-tree changes.

Evidence: [installed state and checksums](reports/installed-test-state.json), [staging checks](reports/staged-boot-check.log), [backup log](reports/privileged-backup.log), [initramfs comparison](reports/initramfs-content-comparison.json), and [boot targets](reports/boot-volumes.txt).

## Recovery check — completed

The following procedure has now been completed; it is retained for reference.

Save your work and do this when you are ready to shut down:

1. Shut down the Mac normally.
2. Press and hold the power/Touch ID button until startup options appear, then release it.
3. Choose **Options**, then **Continue**. Authenticate if asked.
4. Confirm you reach the Recovery utilities and can open **Utilities → Terminal**. Do not reinstall or erase anything.
5. Identify and mount the Linux EFI partition, then confirm its `m1n1` folder contains `boot.bin.before-display-test` and `DISPLAY-TEST-RECOVERY.txt`.
6. Return to Omarchy and tell me whether this worked. Keep the ordinary/default GRUB entry for this check.

These startup steps follow [Apple's Apple-silicon Recovery instructions](https://support.apple.com/en-gb/102518). A working macOS desktop with access to the EFI backup is also a usable recovery route.

The partition to identify is:

| Field | Value |
| --- | --- |
| EFI label | `EFI - OMARC` |
| Partition UUID | `bf0b62f5-e52c-4ba5-afa8-e77cd9364cf5` |
| Linux device | `/dev/nvme0n1p4` |

In macOS/Recovery Terminal, `diskutil list` lists devices; `diskutil info diskXsY` shows an individual partition's identity. Replace `diskXsY` with the actual identifier whose **partition UUID matches** the table. Then `diskutil mount diskXsY` mounts it; use `diskutil info` again to find its actual mount point. Normal macOS may require `sudo`. Do not assume its disk numbering matches Linux.

The recovery check was completed while the stock image was active. Since then the experimental image has been activated; use the restore instructions below if you need to return to the original image.

## Activation — completed; reference commands

Back in Linux, the staged-file check is:

```bash
cd /home/mert/Work/omarchy-mac-external-monitor
sudo bash scripts/boot-bundle.sh check
```

The following activation command has already completed successfully:

```bash
sudo bash scripts/boot-bundle.sh activate --recovery-confirmed
```

This verifies the staged files, kernel version, EFI partition and recovery copy, then replaces only the active m1n1 bundle. **It does not reboot.** The shared device tree will then apply to every GRUB entry; selecting the stock entry alone does not undo it.

Connect the LG 24MD4KL directly using its full-featured **USB-C cable**, in a monitor host/input port. Start with the Mac's front USB-C port nearest the trackpad. Keep the lid open. Reboot when ready and manually select:

**Omarchy - external monitor test (manual)**

The menu currently waits five seconds, so press an arrow key promptly. There is no need to edit a GRUB line by hand. The test entry uses the existing kernel and separate initramfs; it omits the splash/quiet options so boot messages are visible. `uname -r` stays `7.1.13-3-1-ARCH`.

After boot:

```bash
python3 scripts/check-loaded-modules.py
artifacts/check-renderer
python3 scripts/collect-display-state.py reports/after-display-test.json
```

The module checker returns 0 for two experimental drivers, 2 for two stock drivers, and 1 for missing/mixed/unknown drivers. Expect an Apple renderer and a new external DP connector. Working output, 4K60, hotplug and suspend remain unverified. Use a new capture filename for each attempt.

Do not unload/reload the Type-C drivers during this experiment. The initramfs contains the matching patched pair; the root filesystem deliberately retains the stock files.

## Restore the normal boot state

If Linux is usable:

```bash
sudo bash scripts/restore-stock-boot.sh
```

It verifies the original backup and restores the active m1n1 bundle, without rebooting. On your next boot, use the ordinary **Omarchy Linux** entry. The inactive test files can remain until cleanup.

If a future activated test fails before GRUB, use macOS/Recovery to restore the saved bundle following the guide already on the EFI partition. Original bundle SHA-256:

```
566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33
```

The activation helper completed successfully, and the active bundle checksum matches the candidate. The original recovery copy checksum was verified again afterward. Restoration in the previously stock state was tested as a no-op; restoration from the experimental state remains untested. The experimental boot has now completed, but external display output is not working yet.

## Project file tree

`.gitignore` contains only the large `sources/`, `artifacts/`, `snapshots/` directories and Python caches. A local Git repository was initialized so Neo-tree respects those rules; there are no commits or remotes. Reopen Neo-tree if an old view still shows ignored files.
