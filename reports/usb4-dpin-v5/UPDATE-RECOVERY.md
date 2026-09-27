# 2026-09-22: package update replaced the DP-IN boot bundle

## Cause and evidence

The `pacman -Syu --needed chatgpt-bin` transaction upgraded `linux-asahi`
from `7.1.13.asahi3-1` to `7.1.13.asahi3-2`. At 00:04:34 +03,
`95-m1n1-install.hook` ran `/usr/bin/update-m1n1`, replacing the shared EFI
`m1n1/boot.bin` with the packaged loader/device trees.

The resulting image's SHA-256 was
`566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33`, exactly
the original stock backup. `boot.bin.old` and `boot.bin.usb4-dpin-v5` both
retained the verified v5 image, SHA-256
`195a5df61a12e226f5b0aa2a332e991c023d9c8af991c363acdfb957ea405d49`.

The working September 21 boot logged external DCP startup, DP tunnel creation,
automatic DP-IN connect and seven monitor modes. Both September 22 boots lacked
Thunderbolt initialization. The running device tree had
`/soc/dcp@271c00000/status = disabled`, no NHI nodes, and DRM had no external DP
connector. The custom kernel remained selected; all three v5 modules and the
installed v5 initramfs matched the installation manifest.

## Repair installed from Linux

`scripts/preserve-dpin-v5-boot.py` verifies the EFI partition, original stock
backup, v5 bundle and its individual components, installed modules and initramfs.
It extracts the tested m1n1 and complete device-tree set to the root-owned
`/usr/local/share/asahi-dpin-v5/`, independent of this workspace and packaged
kernel directories. The source is the verified saved bundle, not a potentially
modified build tree.

`/etc/default/update-m1n1` now contains `config/update-m1n1-dpin-v5`. The packaged
updater explicitly supports sourcing this file. It checks the preserved inputs'
SHA-256 hashes and sets `M1N1` and `DTBS` to those inputs. A failed integrity check
stops the updater before it touches the EFI image. U-Boot continues to come from
its installed package. No packaged hook or executable was modified, and updates
were not disabled.

The installer first generated a candidate with the real packaged updater and
verified that its loader/device-tree bytes exactly matched the tested v5 bundle,
and its decompressed U-Boot matched the known-good payload. It then exercised the
exact no-argument updater invocation used by pacman and verified the active EFI
image against that candidate. Both checks passed.

Active SHA-256 after repair:
`e056ce5806d7c66f101e33c2c0e46e9d9aa4036a3822653e42fa5b0ad35ad664`.
The hash differs from the old bundle because the packaged updater uses a
different gzip encoding; uncompressed boot components are identical.

Backup and installation result:
`/var/backups/asahi-dpin-v5/20260922-171334/`.
The stock recovery image and saved v5 image on the EFI partition are untouched.
Updated recovery instructions are in this report and
`config/USB4-DPIN-V5-RECOVERY.txt`. On retry, the revised text was successfully
copied to `/boot/efi/m1n1/USB4-DPIN-V5-RECOVERY.txt` and verified byte-for-byte
against the project copy. The EFI recovery note includes the updater override.

## Verification after reboot

No reboot was performed during repair. Save work and reboot into the existing
default **Omarchy - Asahi 7.1 USB4 DP-IN v5** entry with the LG attached.

```sh
cat /sys/firmware/devicetree/base/soc/dcp@271c00000/status
ls /sys/bus/thunderbolt/devices
cat /sys/class/drm/card*-DP-*/status
hyprctl monitors all
journalctl -k -b --no-pager | rg 'DP tunnel up|DP-IN auto connect|dcp_hotplug'
```

Expected: external DCP enabled, Thunderbolt devices present, DP connected, LG
listed in Hyprland, and a visible desktop. Image restoration is verified;
post-reboot monitor output remains to be checked.

## Scope and maintenance

This prevents the observed package-hook replacement. It deliberately pins the
experimental m1n1 and device trees as a tested pair; it does not port the DP-IN
patches to future kernels or guarantee compatibility with every future update.
Keep the existing v5 kernel/initramfs/default entry until a replacement is tested.
Future m1n1/device-tree improvements require a deliberate update of these local
inputs and checksums. Normal packages and packaged U-Boot can still update.

## Return to packaged boot components

From a working Linux session, remove the override before invoking the normal
updater; it regenerates the stock bundle from installed packages:

```sh
sudo mv /etc/default/update-m1n1 /etc/default/update-m1n1.dpin-v5-disabled
sudo update-m1n1
```

Then choose the ordinary **Omarchy Linux** entry at the next boot. Do not reboot
until the updater has succeeded. Restoring a stock EFI image alone does not
remove the override: a later package update would re-enable the custom inputs.

If Linux cannot boot, the existing macOS/Recovery procedure still works: copy
`boot.bin.before-display-test` to `boot.bin` on the Linux EFI partition, then
select the ordinary Omarchy entry. Disable the updater override once back in
Linux if staying on stock. The preserved local input directory can remain inert.
