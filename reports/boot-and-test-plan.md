# External display experiment: attended steps

Prepared for Apple MacBook Air M1 / J313, Arch Linux ARM, 2026-09-17.
Nothing in this document has been installed or boot tested.

**Update:** the focused module-pair + J313-DTB experiment has now been built. Follow [attended-module-test.md](attended-module-test.md) first. Full-kernel sections below remain a fallback. The user confirmed LG 24MD4KL and both cable types.

## Why this needs more than a module

The running kernel is `7.1.13-3-1-ARCH`. Its configuration already has
`CONFIG_TYPEC_DP_ALTMODE=m`, `CONFIG_PHY_APPLE_ATC=m`,
`CONFIG_PHY_APPLE_DPTX=m`, and `CONFIG_DRM_APPLE=m`. Nevertheless, the live
device tree marks `/soc/dcp@271c00000` (the external display controller)
`disabled`. DRM exposes only `card2-eDP-1`.

Asahi's experimental fairydust changes wire the second Type-C controller to
the external DCP, enable its supporting hardware, and send display hotplug
events from the CD321x driver. A monitor configuration line cannot supply
these missing hardware connections. Do not unload the live display or USB-C
controller modules to try to apply this while the machine is in use.

## Before any installation

1. The user confirmed LG 24MD4KL; select its full-featured USB-C cable. A Thunderbolt-only
   display is a different problem; fairydust does not provide full Thunderbolt
   host support. Prefer a direct USB-C DisplayPort-capable connection.
2. Keep the laptop lid open. Confirm macOS or recovery boots and that the
   Linux EFI partition can be located there. Record its partition UUID using
   `lsblk -o NAME,FSTYPE,LABEL,PARTLABEL,PARTUUID,MOUNTPOINTS` on Linux.
   Do not guess a macOS disk number from Linux's NVMe partition number.
3. Back up the stock kernel, its complete `/usr/lib/modules/7.1.13-3-1-ARCH`
   directory, `/boot/initramfs-linux-asahi.img`, `/boot/grub/grub.cfg`,
   `/boot/efi/m1n1/boot.bin`, and boot configuration. Root is required to read
   the initramfs and GRUB configuration here. The workspace's m1n1 snapshot
   is verified, but is NOT a complete recovery backup.
4. Copy a known-good `boot.bin` to a distinct file on the EFI partition,
   such as `m1n1/boot.bin.before-display-test`, and record its checksum.
   Also retain a copy reachable from macOS. Do not rely on `boot.bin.old`:
   later update-m1n1 runs can overwrite that rolling backup.

## Build and package design

Use the installed distribution's configuration and exact release source as
the comparison baseline. Pin experimental source to a full commit hash.
Keep the stock `linux-asahi` package installed. Give the experimental package,
kernel release, kernel image, and initramfs distinct names.

Do not run the downloaded community installer. Its ALARM path ultimately
runs `makepkg -si` with the original `linux-asahi` package name; it replaces
the stock package. It also offers unrelated scheduler and native-HDMI
suspend patches. Neither is needed to test this MacBook Air's USB-C output.

Preserve Rust and `CONFIG_DRM_ASAHI=y`; otherwise a build can lose GPU
acceleration. Use the source's pinned Rust toolchain and matching rust-src,
and pass `make rustavailable` before compiling. This machine currently lacks
Rust, rust-bindgen, bc, dtc, and pahole build packages.

## Device trees and the shared boot image

On this installation `/usr/bin/update-m1n1` sources
`/etc/default/update-m1n1` (NOT Fedora's `/etc/sysconfig/update-m1n1`). By
default it chooses DTBs from the highest version matching
`/lib/modules/*-ARCH/dtbs/*.dtb`. It concatenates m1n1, those DTBs, compressed
U-Boot, and configuration into a shared EFI `m1n1/boot.bin`.

Installing files under `usr/lib/modules/*/dtbs/*` triggers the
`95-m1n1-install.hook`. A separately named kernel alone does not isolate
these bootloader changes. Stage experimental DTBs outside that hook's path
and build the candidate boot bundle in the workspace first. Before activation,
explicitly check which DTBs are selected, and preserve the stock bundle.

Do not use GRUB's `devicetree` command to replace the firmware-patched live
tree with a raw compiled DTB. m1n1 applies machine-specific fixups before
passing the tree through U-Boot to GRUB.

Prepare a separate GRUB entry for the experimental image and initramfs;
retain a visible stock entry and verify that stock remains the default.
Check the generated configuration with `grub-script-check`. The actual
root/subvolume arguments and paths must be copied from the real, readable
stock GRUB entry at installation time, rather than guessed here.

## First attended boot

1. Connect the display directly before boot. Begin with the front USB-C port
   (nearest the trackpad), as suggested by existing fairydust testing; verify
   port mapping against the J313 source. Keep the internal panel available.
2. Select the experimental kernel manually in GRUB. Do not set it as default.
3. Capture `python3 scripts/collect-display-state.py reports/after-first-boot.json`.
4. Confirm the expected experimental `uname -r`, a new DP connector in
   `/sys/class/drm`, and modes in `hyprctl monitors all`. Distinguish absent
   connector, disconnected connector, and connected-but-black screen.
5. Check renderer information from an available EGL/Vulkan utility or
   compositor log. It must report the Apple GPU, not a software renderer.
6. Start with an advertised conservative mode, then test the desired mode.
   Only then add a monitor-specific Hyprland rule using its actual connector
   name. Leave internal-screen configuration in place during testing.
7. Test replug and suspend separately after basic output works. The branch
   includes always-on Type-C power-domain hacks, so check battery drain too.

## Recovery

If Linux boots but output fails, return to the stock kernel and restore the
stock m1n1 bundle/configuration as needed. A stock kernel with experimental
DTBs is not the same state as the original installation.

If the failure occurs before GRUB, use macOS/recovery to mount the identified
Linux EFI partition and restore `m1n1/boot.bin.before-display-test` to
`m1n1/boot.bin`. Verify the checksum. This recovery route must be confirmed
before changing the active bundle. A GRUB menu selection cannot repair a
failure that happens before GRUB starts.

## Primary references

- [Asahi M1 support status](https://asahilinux.org/docs/platform/feature-support/m1/)
- [Asahi fairydust source](https://github.com/AsahiLinux/linux/tree/fairydust)
- [Distribution kernel recipe](https://github.com/asahi-alarm/PKGBUILDs/tree/d0035bcff85d877a25e2818590cb4fa5b6c8c321/linux-asahi)
- [Asahi U-Boot boot flow and bundle recovery](https://asahilinux.org/docs/sw/u-boot/)
- [LG 24MD4KL specifications](https://www.lg.com/es/monitores3/monitores-4k-uhd/24md4kl-b/)
