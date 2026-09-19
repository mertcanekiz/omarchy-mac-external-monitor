# DP-IN v2: external-controller boot fixes

**Boot-tested:** the initialization fix works, but the first manual connection
still times out. See [the live result](dpin-v2-result.md). Instructions below
describe the original test procedure, not a request to repeat it now.

## First experiment result

Boot `f2d45f52-913f-435c-b448-904bf493bb30` loaded the intended experimental
module, but failed before DRM connector registration. Only the simpledrm
`card0-Unknown-1` connector survived. No manual HPD request was issued.
The Thunderbolt device directory was also empty at inspection; that alone
does not establish whether the cable was connected or why enumeration was absent.

The [saved kernel journal](dpin-v1-boot-kernel.log) establishes this sequence:

1. External DCP attempts to create its PIODMA child device.
2. Apple DART rejects its DMA window: `Invalid DMA window for ias=32`.
3. The display driver prints a zero-valued error and reports the component bound.
4. `dcp_start()` reaches `apple_rtkit_start_ep()` with a NULL RTKit pointer,
   faulting at virtual address `0x98`.

Source inspection explains the failure. The inherited external PIODMA DT
specifier requests length `0xffff00000` starting at zero, spanning almost
64 GiB. This cannot fit a 32-bit DART input address space. In addition,
`iommu_get_domain_for_dev()` can return NULL, but the driver checked only
`IS_ERR()`. Its caller then returned `dev_err_probe(..., 0, ...)`, falsely
reporting success without initializing RTKit.

## Changes in v2

- Change external PIODMA to the same `0..0xfbffffff` window used by internal
  PIODMA and the external display/RTKit clients on this SoC.
- Reject NULL IOMMU domains with `-ENODEV`, destroy the failed child device,
  clear its pointer, and propagate the actual failure to component binding.
- Keep v1 artifacts and add separately named v2 module, DTB, initramfs, loader
  bundle, patch, and manual GRUB entry.
- Strengthen DT verification to check the external PIODMA aperture exactly.
- Refuse manual display tests on any boot tainted by a kernel oops.

These changes address the observed initialization faults. They do **not** prove
that external DCP will finish booting, or that Thunderbolt video will work.
The unchanged fixed-route prototype still lacks production hotplug/suspend
and teardown support.

## Verification and next boot

Module compilation, MODPOST, BTF, DT compilation, Python syntax checks, and
source whitespace checks passed. Packaging retains the existing kernel image
and root module files. [Checksums](dpin-v2-artifacts.json),
[initramfs/DT verification](dpin-v2-verification.json), and
[activation log](dpin-v2-activation.log) record the final state.

Activation completed successfully. The active loader SHA-256 is
`5c504019c46807826ac91c9e67c0739e972e358eca22dc3076a37e81e0387e89`;
the installed v2 initramfs and baseline backup were independently checksum
verified afterward. The subsequent boot and connection result are recorded
separately in the live-result report linked above.

Save your work, leave the Thunderbolt cable connected to the **front USB-C
port, nearest the trackpad**, and reboot manually. Select:

**Omarchy - Thunderbolt DP-IN v2 (manual)**

First inspect the new kernel journal and DRM connectors. Do not unload/reload
appledrm in the damaged v1 boot. Once the new boot is healthy:

```bash
sudo python3 scripts/run-dpin-test.py --revision v2 --check-only
```

Only after checking initialization and the pending tunnel, capture one manual
connection using a fresh output directory:

```bash
sudo python3 scripts/run-dpin-test.py --revision v2 reports/thunderbolt/dpin-v2-attempt1
```

Success still requires a working picture, not just successful firmware calls.

## Recovery

The loader's device tree is shared across GRUB entries. Selecting a stock
entry alone does not restore it. To return to the known USB4 baseline:

```bash
sudo python3 scripts/stage-dpin-test.py restore --revision v2
```

Then reboot and select **Omarchy - Asahi USB4 bring-up (manual)**. From Recovery,
restore `boot.bin.before-thunderbolt-dpin` over `boot.bin` on the verified Linux
EFI partition. That baseline backup has SHA-256
`9602d026b2960bf308e3cc7a9d14019abeed4b7ccaa387125241073660b7c297`.
Stock recovery and all prior test bundles remain intact. No automatic reboot
or runtime display-driver replacement is performed by these helpers.
