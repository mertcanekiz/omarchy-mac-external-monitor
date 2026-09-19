#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Run interactively with sudo. Backup/review only; never installs or reboots.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project=$PWD
if (( EUID != 0 )); then
  echo 'Run in your terminal: sudo bash scripts/prepare-boot-review.sh' >&2
  exit 1
fi
[[ $(uname -r) == 7.1.13-3-1-ARCH ]]
[[ $(pacman -Q linux-asahi) == 'linux-asahi 7.1.13.asahi3-1' ]]
printf '%s  %s\n' \
  566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33 /boot/efi/m1n1/boot.bin \
  e339c992eef9bb879680513efee54aec68b39f14cba78f96b6db3a5c1d68533c /boot/vmlinuz-linux-asahi | sha256sum -c -
grub-script-check /boot/grub/grub.cfg
mkdir -p snapshots
backup=$(mktemp -d "$project/snapshots/boot-review-XXXXXXXX")
chmod 700 "$backup"
# Archive all of /boot, including the EFI partition and vendor firmware.
# No --one-file-system: /boot/efi is a separate filesystem on this machine.
tar --acls --xattrs --numeric-owner -cpf "$backup/boot-and-config.tar" -C / \
  boot etc/default/grub etc/grub.d etc/mkinitcpio.conf etc/mkinitcpio.conf.d \
  etc/mkinitcpio.d usr/lib/modules/7.1.13-3-1-ARCH
cp /boot/grub/grub.cfg "$backup/grub.cfg"
cp /boot/efi/m1n1/boot.bin "$backup/boot.bin.original"
lsinitcpio -l /boot/initramfs-linux-asahi.img > "$backup/stock-initramfs-contents.txt"
lsblk -o NAME,FSTYPE,LABEL,PARTLABEL,PARTUUID,MOUNTPOINTS > "$backup/partition-map.txt"
(
  cd "$backup"
  sha256sum boot-and-config.tar grub.cfg boot.bin.original > SHA256SUMS
  sha256sum -c SHA256SUMS
  tar -tf boot-and-config.tar > archive-contents.txt
)
# Files we just created should be inspectable by the invoking desktop user.
if [[ ${SUDO_UID:-} =~ ^[0-9]+$ && ${SUDO_GID:-} =~ ^[0-9]+$ ]]; then
  chown -R -- "$SUDO_UID:$SUDO_GID" "$backup"
fi
printf '\nBackup and review files: %s\n' "$backup"
echo 'No active boot files, installed modules, or GRUB entries changed.'
echo 'Next: review grub.cfg and confirm EFI recovery before staging the experiment.'
