# Thunderbolt DP-IN experiment, 2026-09-18

**Superseded by [the v2 boot fix](dpin-v2-bringup.md).** This first candidate
booted but crashed during external PIODMA setup; no display connection was
attempted. The rest of this document retains the original experiment history.

The USB4 kernel boots and discovers an authorized LG UltraFine 4K at 20 Gb/s
(two 10 Gb/s lanes). Display output is **not working or verified yet**.
A compiled, separate DP-IN experiment is verified and activated for the next
attended boot. Select **Omarchy - Thunderbolt DP-IN experiment (manual)**.

## What the live hardware established

Read-only capture: [first-boot-registers.json](first-boot-registers.json).

| Router | Adapters found |
| --- | --- |
| Apple host, `0-0` | PCIe DOWN 3, USB3 DOWN 4, DP IN 5/6, NHI 7 |
| LG, `0-1` | PCIe UP 8, PCIe DOWN 9, DP OUT 10/11; **no USB3 adapter** |

The LG is connected through the front port's `501f00000.nhi`. Its downstream
USB devices cannot demonstrate native USB3 tunneling in this topology. A USB4
peripheral exposing a USB3 UP adapter would be needed for that separate test.
The monitor's USB function in Thunderbolt mode may depend on a PCIe USB
controller; that has not been enumerated or proven here.

Linux attempted `0:5 <-> 1:10 (DP)` and tore it down after the 12-second
DPRX negotiation deadline. Current DP adapter registers show both adapters
disabled, `DPRX_DONE=0`, and cleared remote/common capability registers.
Both host DP-IN and the LG's active DP-OUT advertise HBR3/four-lane capability.
This is a capability advertisement, not an active video link or a bandwidth
guarantee on the 20 Gb/s transport.

The running tree has external DCP disabled and only `eDP-1` exists. The missing
native-device-links warning in `tb_probe()` concerns resume ordering. It is
not evidence of the cause of the display failure. Neither missing USB buses
nor that warning justifies claiming that DWC3 wiring is the display blocker.

## Prototype implemented

[Patch](../../patches/thunderbolt-dpin-experiment.patch) changes five files in
`sources/linux-thunderbolt`, based on commit
`236788cd2602a24c703fe7bdaddaf73ef77d2027`.
The source checkout is now on branch `thunderbolt-dpin-j313`.

- Enable J313's external DCP, its mailbox, and display IOMMUs, including the
  current five-cell DMA-aperture specifiers. Add the loader's `dcpext` alias.
- Add an opt-in `apple,tbt-dpin-test` mode. Set ATC=1/core=1 and crossbar
  output=1/source=0: front-port DPIN0 fed by dispext0.
- Start DCP's DPTX endpoint without a physical DP PHY. Preserve the PHY's
  Thunderbolt configuration and describe the virtual DP input as four lanes.
- Add a root-only `tunnel_hpd` debugfs control to request the connection after
  the Thunderbolt tunnel exists. It validates the firmware destination before
  connecting and logs firmware errors. Reading `1` means **requested**, not
  that the monitor works.
- Correct the completion timeout check (zero means timeout), and initialize
  PHY validation options instead of reading an uninitialized union when no
  PHY fills it.

The manual GRUB entry adds `thunderbolt.dprx_timeout=-1`. This is an existing
upstream diagnostic parameter. It holds the receiver negotiation pending
until the manual DCP request; it does not force DPRX_DONE or fake a connected
monitor. Leaving a pending tunnel causes continued polling during this test.

This is a fixed-route research prototype, not upstream-ready support. It does
not integrate automatic tunnel hotplug, dynamic port selection, suspend,
bandwidth arbitration, or all disconnect/teardown lifetimes. Additional
Apple DP-IN register or firmware setup may still be necessary. Keep the
cable connected during the first test and do not unload the display module.

## Verification

- Module compilation, MODPOST, linking and BTF generation succeeded.
- Module vermagic matches the running `7.2.2-thunderbolt-test+` kernel.
- Build configuration matches `/proc/config.gz`, except Kconfig's
  informational `CONFIG_RUST_IS_AVAILABLE=y` probe.
- Corrected DTB builds without the initial IOMMU-cell warning.
- Separate initramfs generation succeeded; see
  [build log](dpin-initramfs-build.log). Existing firmware/font/autodetect
  warnings remain; no image-generation error occurred.
- [Artifact checksums](dpin-artifacts.json) record the module, DTB, loader
  bundle, initramfs and patch. [Verification](dpin-verification.json) compares
  initramfs files and checks DT routing.
- The manual capture tool refuses the current baseline module by build ID,
  before making any trace or display-control writes.
- No reboot, active module replacement, live register writes, or cable reset
  was performed. After sudo access was restored, activation succeeded. The
  active loader now matches the DP-IN candidate, hash
  `6c22c07bd01d04bb532afe3a62e0aee54abbcd46996ec05b06d6663b15e9fa6e`.

The initramfs comparison found 984 identical entries; only the display module
and runtime `config` differed, with an added `early_cpio` marker and no removed
files. The runtime-config check initially stopped activation: the existing
`apple_hid_modules.conf` conditional now detects `hid_apple` and `hid_magicmouse`
and adds them to early loading. Both modules already existed, byte-identical,
in the baseline image. The verifier now explicitly checks this narrow exception,
preserves all hook ordering, and rejects any other file or module change.
Verification and activation then passed; see [activation log](dpin-activation-verified.log).

## Attended next boot

Activation is complete. The command used (retained for reference) was:

```bash
sudo python3 scripts/stage-dpin-test.py activate
```

Save work, reboot manually with the Thunderbolt cable in the front port, and
select **Omarchy - Thunderbolt DP-IN experiment (manual)**. The GRUB default
is unchanged. This uses the existing kernel and a separate initramfs containing
the experimental display module. The installed root module tree is unchanged.
The m1n1 device tree is shared by every GRUB entry, so changing the menu entry
alone does not restore the previous tree.

After login:

```bash
sudo python3 scripts/run-dpin-test.py --check-only
sudo python3 scripts/run-dpin-test.py reports/thunderbolt/dpin-attempt-1
```

The capture tool verifies the loaded module build ID, correct NHI, enabled
host DP-IN adapter and timeout override. It records registers and DRM state,
enables DPTX tracepoints in a private instance, requests one connection,
records for 20 seconds, and captures the result. It does not reconnect the
cable or claim that a successful firmware call means video works.

Evidence of success must include DPRX_DONE, an active tunnel, an external DRM
connector with usable modes, and an actual visible image. A failed validation
or firmware timeout should guide the next change; do not repeatedly reconnect
without collecting the trace.

Restore the verified USB4 baseline bundle if necessary:

```bash
sudo python3 scripts/stage-dpin-test.py restore
```

Then reboot into **Omarchy - Asahi USB4 bring-up (manual)**. Recovery can copy
`m1n1/boot.bin.before-thunderbolt-dpin` over `m1n1/boot.bin` on the same EFI
partition used earlier. The stock and earlier display-test backups also remain.

## Source evidence

- [Asahi display-controller documentation](https://asahilinux.org/docs/hw/soc/display-controllers/)
  identifies the M1 external DCP's routing to USB-C and USB4 tunneling.
- [m1n1 DCP definitions](https://github.com/AsahiLinux/m1n1/blob/b4654b32941d51afdb77579d63e7cb1aa6c03ecc/proxyclient/m1n1/fw/dcp/dcpav.py)
  name DPPHY=0, DPIN0=1, DPIN1=2. The local trace decoder defines the core,
  ATC and die bitfields. Applying that core selection to this firmware is
  the experiment to validate, not an already-observed successful transaction.
- Local `drivers/mux/apple-display-crossbar.c` implements distinct DPPHY,
  DPIN0 and DPIN1 outputs; this experiment uses the existing DPIN0 path.
- [USB4 v2 cover-letter discussion](https://lists.openwall.net/linux-kernel/2026/09/07/1875)
  explicitly limits supported tunneling to USB3 and XDomain and says DP and
  PCIe need further work. Our imported integration uses the earlier switch
  notification API; the newer device-link changes should be considered when
  rebasing after the first DP experiment.
