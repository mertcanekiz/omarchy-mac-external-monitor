# Stock GPU + USB4 backport

Base: `asahi-7.1.13-3`, commit `94fb23346d522edf53722357c426a3e58030beea`.
Worktree: `sources/linux-usb4-backport`, branch `thunderbolt-7.1.13-gpu`.
Planned release: `7.1.13-usb4-gpu-test`.

This is a transport/GPU baseline, not a working external-display release.
The 7.2 DP-IN prototype remains in its original worktree and boot artifacts.

## Imported changes

- `bits/270-thunderbolt` through `d7a0d0e6d082`, including its reset driver
  and common Thunderbolt fixes.
- The preceding mainline NHI/PCI separation and ring interrupt prerequisites.
- Apple Type-C Thunderbolt switch, corrected CD321x cable VDOs, and port
  notifications. Stock 7.1 stores structures in `tps6598x.h`, so the two
  structure edits were moved there when resolving the imported patches.
- ATC PIPE mux refactor and USB4 state. Stock already had the dummy state;
  the duplicate case introduced during import was removed in the next commit.
- M1-only CIO reset and USB4 device-tree nodes, plus existing m1n1 aliases.

The new DART aperture patches were deliberately **not** imported: the M1 USB4
nodes use one-cell IOMMU specifiers, and stock DART already supports the legacy
DMA ranges. This preserves the installed IOMMU implementation.

`drivers/gpu/drm/asahi`, `drivers/gpu/drm/apple`, `drivers/iommu`, and `rust`
are byte-for-byte unchanged from the stock source base. The J313 board-specific
DT is unchanged; only its common M1 includes gain USB4 nodes.

## Build

`scripts/build-usb4-backport.sh` uses a private Rust 1.93.1 toolchain and the
exact installed headers' configuration, with a separate release name, Apple
USB4/reset support and USB4 networking enabled. It asserts `CONFIG_DRM_ASAHI=y`
and `CONFIG_RUST=y`; build success must also include `asahi.o` and linked GPU
symbols. Runtime hardware acceleration still needs verification after reboot.

Current status: **built, installed, verified and activated at 2026-09-18
00:15 UTC; awaiting the user's reboot.** Branch HEAD is
`5f7d34c835af70252a7fcddeb27291b7d1fe50c6` and the worktree is clean.
The manual GRUB entry is **Omarchy - Asahi 7.1 GPU + USB4 (manual)**.
The normal default entry is unchanged; no reboot or live driver reload occurred.

Rust support, the Asahi GPU, Apple display driver, Apple Thunderbolt host
driver and all modules compiled successfully. The final kernel contains
AsahiDriver probe symbols. `depmod -e -F System.map` reported no unresolved
symbols. Extracted initramfs copies of the six relevant display/PHY/Type-C/USB4
modules match the staged modules byte-for-byte; the Asahi early and late firmware
hooks are present. The private module package and installed boot files pass
the full [staging manifest](stage-manifest.json) checks. GPU runtime and USB4
transport are **not yet boot-tested**.

The build helper was edited while its first compilation was running, which
caused a shell parsing error after the kernel build finished. A clean invocation
of the current helper then completed successfully, including its GPU and module
assertions, without changing the kernel image. The initial compilation output
is preserved in `build-first-pass.log`; the successful final invocation is in
`build.log`. Five boot-file safety tests and three existing DP-IN helper tests pass.

The initial bindgen steps reported a missing optional `rustfmt` component and
continued successfully; that component has since been installed in the private
toolchain. No stock Rust source changes were needed.

The initramfs builder retained its platform-generic warnings about optional
xHCI/dockchannel firmware, x86 microcode on ARM64, privacy-screen support and an
unset console font. It completed successfully; the M1's vendor firmware archive
is present on the EFI partition and its Asahi loading hooks are included.

Installed artifacts:

- Kernel: `/boot/vmlinuz-usb4-gpu-test`, SHA-256
  `e2d1796b282d1199b366240bb6d54183022c9348bf5cafcb9df6e37a5436af10`.
- Initramfs: `/boot/initramfs-usb4-gpu-test.img`, SHA-256
  `11765c7447ff32ee52b5f2df1e2dcb0465aab3d8234a8ebff35daa517e571277`.
- Active m1n1 bundle: `/boot/efi/m1n1/boot.bin`, SHA-256
  `c57af648855b9740c5bfbfa76784a6cd9ad221bfb9b2ba48ed3635f15e012a79`.
- Previous DP-IN v2 loader: `/boot/efi/m1n1/boot.bin.before-usb4-gpu-test`.
- Original stock loader: `/boot/efi/m1n1/boot.bin.before-display-test` (untouched).

This experimental USB4 driver deliberately rejects suspend while a USB4/TBT
connection is active. Disconnect that cable before testing suspend. Package
updates may replace the shared loader; check the bundle before subsequent tests.

## First-boot checks

- `uname -r` is `7.1.13-usb4-gpu-test`.
- `/dev/dri/renderD*` exists and EGL reports Apple M1, not llvmpipe.
- The internal display is stable; no GPU/DCP faults in the kernel journal.
- With a Thunderbolt cable, the LG router enumerates and is authorized.
- No DP-IN manual request for this baseline. An external picture is not expected.
- This LG's observed router exposes no native USB3 adapter; successful USB4
  enumeration is not proof of USB3 tunneling, which needs a suitable device.

After booting the matching test entry, run:

```sh
python3 scripts/verify-usb4-gpu-boot.py
```

The checker is read-only and saves an exclusive, per-boot JSON report. It
refuses to call the old running kernel a successful new boot.

The m1n1 device tree is shared by every GRUB entry. Restoring only a kernel
selection does not restore a loader/device tree. Preserve the original stock
bundle and the previous DP-IN v2 bundle before activating this test.
