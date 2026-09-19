#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Explicit, checksum-guarded activation/restoration. Never reboots.
set -euo pipefail
action=${1:-check}
case "$action" in
  check|restore) [[ $# -le 1 ]] ;;
  activate)
    [[ $# -eq 2 && $2 == --recovery-confirmed ]] || {
      echo 'Activation requires: activate --recovery-confirmed' >&2
      echo 'First verify macOS/Recovery can access the EFI backup.' >&2
      exit 1
    }
    ;;
  *) echo 'Usage: boot-bundle.sh check | restore | activate --recovery-confirmed' >&2; exit 1 ;;
esac
(( EUID == 0 )) || { echo 'Run this script with sudo.' >&2; exit 1; }
mountpoint -q /boot/efi
esp_source=$(findmnt -nro SOURCE /boot/efi)
[[ $(blkid -s PARTUUID -o value "$esp_source") == bf0b62f5-e52c-4ba5-afa8-e77cd9364cf5 ]]
original=566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33
experimental=af4c29967c23f23a571080f3f90b511f2263f5d42e6e06ea14e53cb2be582201
active=/boot/efi/m1n1/boot.bin
backup=/boot/efi/m1n1/boot.bin.before-display-test
candidate=/boot/efi/m1n1/boot.bin.display-test
hash() { sha256sum "$1" | cut -d' ' -f1; }
[[ ! -L "$active" && ! -L "$backup" && ! -L "$candidate" ]]
[[ $(hash "$backup") == "$original" ]]
current=$(hash "$active")
[[ "$current" == "$original" || "$current" == "$experimental" ]] || {
  echo 'Active bundle is neither the saved stock image nor this experiment. Refusing to overwrite it.' >&2
  exit 1
}
if [[ $action != restore ]]; then
  [[ $(hash "$candidate") == "$experimental" ]]
  [[ $(uname -r) == 7.1.13-3-1-ARCH ]]
  [[ $(pacman -Q linux-asahi) == 'linux-asahi 7.1.13.asahi3-1' ]]
  printf '%s  %s\n' \
    e339c992eef9bb879680513efee54aec68b39f14cba78f96b6db3a5c1d68533c /boot/vmlinuz-linux-asahi \
    07e921128b0c4a2d22eed52eeff73e102bdaf6d0b2294a9e13899e1c889424d4 /boot/initramfs-linux-asahi.img \
    85b41f507744b1e1861ec3ac06eeb8e6b32b73154f7007ed780761977edeca50 /boot/initramfs-display-test.img \
    4e7282d85a64d3a0aa21e2eb1903d3e6c38df490e5e6bf1edcb82159c7177624 /boot/grub/custom.cfg \
    f98179847d4da91bb8c96b9f820ef654e05b1c2f5a3acaeb11eb98a636f9dd3f /boot/grub/grub.cfg | sha256sum -c -
  grub-script-check /boot/grub/custom.cfg
  grub-script-check /boot/grub/grub.cfg
fi
if [[ $action == check ]]; then
  printf 'Active m1n1 SHA-256: %s\n' "$current"
  echo 'Staged files and recovery copy verified. No changes made.'
  exit 0
fi
if [[ $action == activate ]]; then
  source_file=$candidate
  expected=$experimental
else
  source_file=$backup
  expected=$original
fi
if [[ "$current" == "$expected" ]]; then
  echo "Already in requested $action state; no changes made."
  exit 0
fi
temporary="$active.display-switch"
[[ ! -e "$temporary" && ! -L "$temporary" ]]
cp -- "$source_file" "$temporary"
[[ $(hash "$temporary") == "$expected" ]]
sync -f "$temporary"
mv -T -- "$temporary" "$active"
sync -f "$active"
[[ $(hash "$active") == "$expected" ]]
echo "Boot bundle action completed: $action. No reboot performed."
if [[ $action == activate ]]; then
  echo 'On the next boot, manually choose: Omarchy - external monitor test (manual)'
  echo 'The shared experimental device tree applies even if another GRUB entry is selected.'
fi
