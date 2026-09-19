#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Check, activate, or restore the shared m1n1 bundle. Never reboots.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

action=${1:-check}
case "$action" in
  check|restore-previous|restore-stock) [[ $# -eq 1 ]] ;;
  activate)
    [[ $# -eq 2 && $2 == --recovery-confirmed ]] || {
      echo 'Activation requires: activate --recovery-confirmed' >&2
      exit 1
    }
    ;;
  *)
    echo 'Usage: thunderbolt-bundle.sh check | activate --recovery-confirmed | restore-previous | restore-stock' >&2
    exit 1
    ;;
esac
(( EUID == 0 )) || { echo 'Run this script as root.' >&2; exit 1; }

stock=566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33
previous=af4c29967c23f23a571080f3f90b511f2263f5d42e6e06ea14e53cb2be582201
usb4=9602d026b2960bf308e3cc7a9d14019abeed4b7ccaa387125241073660b7c297
hash() { sha256sum "$1" | cut -d' ' -f1; }
verify() { [[ -f $2 && ! -L $2 && $(hash "$2") == "$1" ]]; }

mountpoint -q /boot/efi
esp_source=$(findmnt -nro SOURCE /boot/efi)
[[ $(blkid -s PARTUUID -o value "$esp_source") == bf0b62f5-e52c-4ba5-afa8-e77cd9364cf5 ]]

active=/boot/efi/m1n1/boot.bin
previous_file=/boot/efi/m1n1/boot.bin.before-thunderbolt-test
stock_file=/boot/efi/m1n1/boot.bin.before-display-test
candidate=/boot/efi/m1n1/boot.bin.thunderbolt-test
verify "$previous" "$previous_file"
verify "$stock" "$stock_file"
verify "$usb4" "$candidate"
verify fde2572e039cba1fb360ac6c72773a5df6abb73d025b4030a57e4aa89a290f29 /boot/vmlinuz-thunderbolt-test
verify 24b04c9775f4a4d2be535f554ab2accc30be477f12722c44d0629af4282674f0 /boot/initramfs-thunderbolt-test.img
verify 8af4f7ab56aac8c24d5c637b73858f31e02f8640f35c6e1e87c434a3bd1249b1 /boot/grub/custom.cfg
grub-script-check /boot/grub/custom.cfg

current=$(hash "$active")
[[ $current == "$stock" || $current == "$previous" || $current == "$usb4" ]] || {
  echo 'Active bundle is not a recognized saved state; refusing to overwrite it.' >&2
  exit 1
}

if [[ $action == check ]]; then
  printf 'Active m1n1 SHA-256: %s\n' "$current"
  echo 'Kernel, initramfs, GRUB entry, candidate, and recovery images verified. No changes made.'
  exit 0
elif [[ $action == activate ]]; then
  source_file=$candidate expected=$usb4
elif [[ $action == restore-previous ]]; then
  source_file=$previous_file expected=$previous
else
  source_file=$stock_file expected=$stock
fi

if [[ $current == "$expected" ]]; then
  echo "Already in requested $action state; no changes made."
  exit 0
fi

temporary=$active.usb4-switch
[[ ! -e $temporary && ! -L $temporary ]]
cp -- "$source_file" "$temporary"
verify "$expected" "$temporary"
sync -f "$temporary"
mv -T -- "$temporary" "$active"
sync -f "$active"
verify "$expected" "$active"
echo "m1n1 bundle action completed: $action. No reboot performed."
if [[ $action == activate ]]; then
  echo 'At the next boot, manually select: Omarchy - Asahi USB4 bring-up (manual)'
  echo 'The USB4 device tree is shared by all GRUB entries until restored.'
fi
