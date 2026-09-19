# Attended first test: existing kernel + patched modules + J313 DTB

**Status update:** staging and the privileged backup are complete. A dedicated manual GRUB entry is now installed. Use [NEXT-STEPS.md](../NEXT-STEPS.md) for current execution instructions instead of repeating the installation/manual-GRUB-edit steps below. The experiment has not been activated or boot tested. The monitor is confirmed as LG 24MD4KL.

## 1. Recheck prerequisites together

- `uname -r` must still be `7.1.13-3-1-ARCH`; `pacman -Q linux-asahi` must still report `7.1.13.asahi3-1`.
- Run `python3 scripts/verify-experiment.py` against the current prepared artifacts. Read the verification report and build logs.
- Read the real `/boot/grub/grub.cfg` with appropriate privileges and confirm the stock entry's `linux` and `initrd` paths. This file was not readable during sandboxed preparation. Confirm that its initrd line is a conventional separate initramfs path and the menu can be edited.
- Identify the paired EFI partition by PARTUUID and the `asahi,efi-system-partition` device-tree property. Confirm how to mount it from macOS/recovery before changing its boot bundle.
- Keep the internal screen available. Do not unload/reload live Type-C drivers: they also control USB roles and power delivery.

## 2. Back up before activation

Make a complete privileged backup of the current boot files, GRUB configuration, module tree, and relevant `/etc` boot configuration. The existing workspace snapshot is partial: the stock initramfs and grub.cfg were unreadable without root.

Additionally preserve current `m1n1/boot.bin` as a distinctly named file on the EFI partition, e.g. `m1n1/boot.bin.before-display-test`. Verify the copy's SHA-256 and keep it reachable from macOS. Refuse to overwrite an existing backup of that name; investigate it instead.

Expected current bundle SHA-256:

```
566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33
```

Do not rely solely on update-m1n1's `.old` file, which later updates can replace.

## 3. Stage the separate initramfs, then activate the bundle

After these checks, copy `artifacts/initramfs-display-test.img` to a new `/boot/initramfs-display-test.img`, verify its checksum against `reports/verification.json`, and keep `/boot/initramfs-linux-asahi.img` intact. Do not replace the stock kernel or install either module under `/usr/lib`.

Copy `artifacts/boot.bin.display-test` to the EFI partition using a new temporary filename beside `m1n1/boot.bin`. Verify its checksum against `reports/boot-bundle-validation.json`, sync the filesystem, then rename it to `m1n1/boot.bin` and sync again. Perform this only in the attended session.

Do **not** run `update-m1n1` afterward: its automatic DTB selection would reconstruct a stock bundle and undo the candidate. This experiment does not add a persistent `/etc/default/update-m1n1` override.

The candidate changes hardware description for every kernel booted through this bundle. It is not isolated by a GRUB menu entry. Firmware initialization can fail before GRUB, so EFI-level recovery is required first.

## 4. Boot once with the test initramfs

1. Connect the LG with its full-featured USB-C cable and a host/input port (not one of the three downstream USB ports). Start with the MacBook's front port nearest the trackpad. Keep the lid open.
2. Reboot when explicitly ready. In GRUB, select the normal stock entry and press `e`. On its initrd line, change **only the initramfs filename** from `initramfs-linux-asahi.img` to `initramfs-display-test.img`, retaining its path prefix and any other initrd arguments. Keep kernel and root arguments unchanged. Boot with Ctrl-X/F10. This edit is for that boot only.
3. `uname -r` remains the stock value. The test modules come from the alternate initramfs and remain resident across switch-root. Do not unload them or mix them with stock modules from the root filesystem.
4. Run `python3 scripts/check-loaded-modules.py` to confirm both resident modules are experimental by build ID. Then run the collector into a new report filename. Check the external DCP probe in the journal and a DP connector under `/sys/class/drm` before attempting compositor configuration.
5. Check the internal screen and Apple GPU acceleration. Then verify external modes and try an advertised mode. Treat 4K60 as a target to test, not an established result.

If there is no DP connector, inspect live external DCP status, firmware initialization, deferred probes, and the Type-C-to-DCP link. If DP exists but is disconnected, inspect HPD, cable, port mapping and monitor input. If connected with modes but black, inspect link training and modesetting logs.

This is a first-boot experiment. Suspend/hotplug and persistent installation are follow-up tests after basic video works.

## 5. Restore the original state

Restore the original m1n1 bundle, then boot the normal GRUB entry with the original initramfs. Root kernel and module files were never changed.

For a pre-GRUB failure, mount the identified EFI partition in macOS/recovery, restore the distinctly named backup as `m1n1/boot.bin`, verify its checksum, then boot Linux normally.

Never use a raw compiled DTB with GRUB's `devicetree` command in place of m1n1's firmware-patched tree. See [Asahi boot-flow/recovery documentation](https://asahilinux.org/docs/sw/u-boot/).

After success, choose between a separately named kernel package or a version-pinned module package with controlled initramfs integration. Do not leave this manually staged experiment silently surviving kernel upgrades.
