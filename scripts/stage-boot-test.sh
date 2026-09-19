#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Root preparation only: never replaces active boot.bin or selects a next boot.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
(( EUID == 0 )) || { echo 'Run with sudo.' >&2; exit 1; }
[[ $(uname -r) == 7.1.13-3-1-ARCH ]]
[[ $(pacman -Q linux-asahi) == 'linux-asahi 7.1.13.asahi3-1' ]]
mountpoint -q /boot/efi
esp_source=$(findmnt -nro SOURCE /boot/efi)
[[ $(blkid -s PARTUUID -o value "$esp_source") == bf0b62f5-e52c-4ba5-afa8-e77cd9364cf5 ]]
printf '%s  %s\n' \
  566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33 /boot/efi/m1n1/boot.bin \
  f98179847d4da91bb8c96b9f820ef654e05b1c2f5a3acaeb11eb98a636f9dd3f /boot/grub/grub.cfg \
  07e921128b0c4a2d22eed52eeff73e102bdaf6d0b2294a9e13899e1c889424d4 /boot/initramfs-linux-asahi.img \
  e339c992eef9bb879680513efee54aec68b39f14cba78f96b6db3a5c1d68533c /boot/vmlinuz-linux-asahi | sha256sum -c -
sha256sum -c reports/artifact-sha256.txt
(cd snapshots/boot-review-ywfOl6EC && sha256sum -c SHA256SUMS)
grub-script-check artifacts/display-test-custom.cfg
grub-script-check /boot/grub/grub.cfg

sources=(
  artifacts/initramfs-display-test.img
  artifacts/display-test-custom.cfg
  snapshots/m1n1-boot.bin
  artifacts/boot.bin.display-test
  artifacts/DISPLAY-TEST-RECOVERY.txt
)
destinations=(
  /boot/initramfs-display-test.img
  /boot/grub/custom.cfg
  /boot/efi/m1n1/boot.bin.before-display-test
  /boot/efi/m1n1/boot.bin.display-test
  /boot/efi/m1n1/DISPLAY-TEST-RECOVERY.txt
)
# Check every destination before writing any of them; never replace unrelated files.
for i in "${!sources[@]}"; do
  target=${destinations[$i]}
  [[ ! -L "$target" ]]
  if [[ -e "$target" ]]; then
    cmp "${sources[$i]}" "$target"
  fi
  [[ ! -e "$target.staging" && ! -L "$target.staging" ]]
done
for i in "${!sources[@]}"; do
  target=${destinations[$i]}
  if [[ ! -e "$target" ]]; then
    install -m 644 "${sources[$i]}" "$target.staging"
    cmp "${sources[$i]}" "$target.staging"
    mv -T -- "$target.staging" "$target"
  fi
done
sync
sha256sum /boot/efi/m1n1/boot.bin /boot/efi/m1n1/boot.bin.before-display-test \
  /boot/efi/m1n1/boot.bin.display-test /boot/initramfs-display-test.img /boot/grub/custom.cfg
echo 'Staged only. Active m1n1, stock initramfs, kernel, GRUB default and NVRAM selection unchanged.'
