# External Monitor Support on Omarchy-on-Mac

Research recorded on 2026-09-17 for later experimentation.

## Current machine

- Model: Apple MacBook Air (M1, 2020)
- Device tree: `apple,j313` / `apple,t8103`
- Architecture: `aarch64`
- Omarchy: `4.0.3rc4-1`
- Kernel package: `linux-asahi 7.1.13.asahi3-1`
- Running kernel: `7.1.13-3-1-ARCH`
- Hyprland: `0.56.2-3`
- Mesa: `26.1.8-1`
- Bootloader: `m1n1 1.6.1-1`

The stock kernel currently exposes only the internal display connector:

```text
/sys/class/drm/card2-eDP-1
```

There is no `DP-*` connector, so this is currently a kernel/driver limitation rather than an Omarchy or Hyprland configuration problem.

## Support status

Asahi's official M1 feature table still marks both Thunderbolt and USB-C DisplayPort Alt Mode as WIP:

- https://asahilinux.org/docs/platform/feature-support/m1/

The experimental `fairydust` branch in the official Asahi kernel repository contains USB-C DisplayPort Alt Mode work:

- https://github.com/AsahiLinux/linux/tree/fairydust

This is DisplayPort Alt Mode support, not complete Thunderbolt/USB4 host support. It is therefore important to distinguish a monitor that can fall back to ordinary USB-C DisplayPort from a Thunderbolt-only monitor.

## LG monitor compatibility

The likely monitor is the LG UltraFine 4K `24MD4KL`. Confirm the exact label on the back before proceeding.

LG documents USB-C video support up to 3840x2160 at 60 Hz for this model, in addition to Thunderbolt 3. That makes it a plausible match for fairydust's DisplayPort Alt Mode support:

- https://www.lg.com/es/monitores3/monitores-4k-uhd/24md4kl-b/
- https://www.lg.com/us/support/product/lg-24MD4KL-B.AUSA

For testing, prefer the monitor's full-featured USB-C cable instead of depending on Thunderbolt transport. Connect it to the display's host/input port.

If the actual monitor is an older or different Thunderbolt-only UltraFine model, fairydust DisplayPort Alt Mode may not be sufficient.

## Experimental behavior reported

Community fairydust testing reports:

- M1 MacBook Air (`J313`) is included and has been tested by users.
- Only one specific USB-C port may provide display output. On the MacBook Air this is generally the front port, closest to the user/trackpad.
- Only one external display should be expected.
- Hot-plug detection can be unreliable; booting with the display connected may work better.
- Suspend/resume, color, and mode detection may still have problems.
- Full Thunderbolt features, PCIe tunneling, and daisy chaining should not be assumed to work.

Community references (unofficial, review before use):

- https://github.com/bharambetejas/asahi-fairydust-display
- https://github.com/rgvxsthi/asahi-linux-hdmi-sleep-fixer

## Packaging caveat

This installation uses Arch Linux ARM/Asahi packages, not Fedora Asahi Remix. The available community build automation has an ALARM path, but its DisplayPort patch was documented as verified against Asahi `7.1.12`. This machine already has `linux-asahi 7.1.13.asahi3-1`.

Do not apply an old patch snapshot blindly. First compare the current `fairydust` branch with the exact source/tag used by the installed ALARM kernel and verify that the DisplayPort changes apply cleanly.

The installed `linux-asahi` package conflicts with `linux-asahi-edge`, and community ALARM scripts may rebuild/replace the same package rather than install a genuinely parallel kernel. Confirm package names, boot entries, DTB paths, initramfs generation, and `m1n1` behavior before installation.

## Safe next-step plan

1. Confirm the LG monitor's exact model number.
2. Record the currently bootable kernel, initramfs, DTBs, GRUB configuration, and m1n1 configuration.
3. Identify the exact source tag/commit used for `linux-asahi 7.1.13.asahi3-1`.
4. Compare that source with the current official `fairydust` branch.
5. Review all fairydust commits and any community build script before running it.
6. Build a separately named package/kernel if the boot tooling supports side-by-side kernels.
7. Preserve the stock kernel and a tested recovery path.
8. Test first with the LG USB-C cable in the MacBook Air's front USB-C port and the display connected before boot.
9. After boot, check for a new connector with:

   ```bash
   ls -l /sys/class/drm
   hyprctl monitors all
   ```

10. Verify GPU acceleration is still active and the renderer is not `llvmpipe`.
11. Only after basic output works, configure placement and scaling in `~/.config/hypr/monitors.lua`.

Omarchy's normal monitor support should take over once the kernel exposes the external connector:

- https://github.com/omacom/omarchy/blob/quattro/manual/33-monitors.md

## Expected outcome

With the experimental fairydust kernel and an LG `24MD4KL` operating in USB-C DisplayPort Alt Mode, 3840x2160 at 60 Hz appears feasible on this M1 MacBook Air. It is not supported by the currently installed stock kernel and should still be treated as experimental.
