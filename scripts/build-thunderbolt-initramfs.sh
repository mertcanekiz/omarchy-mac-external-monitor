#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Install the custom modules into a workspace root and build a private initramfs.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

project=$PWD
source_tree=$project/sources/linux-thunderbolt
build_tree=$project/artifacts/thunderbolt-kernel/build
module_root=$project/artifacts/thunderbolt-kernel/root
initramfs=$project/artifacts/initramfs-thunderbolt-test.img
config=$project/artifacts/thunderbolt-mkinitcpio.conf
build_tmp=$project/artifacts/thunderbolt-initramfs-tmp
log=$project/reports/thunderbolt/initramfs-build.log

kernel_release=$(make -s -C "$source_tree" O="$build_tree" kernelrelease)
[[ $kernel_release == 7.2.2-thunderbolt-test+ ]] || {
  echo "Unexpected kernel release: $kernel_release" >&2
  exit 1
}
[[ -s $build_tree/arch/arm64/boot/Image ]]
[[ -s $build_tree/drivers/thunderbolt/thunderbolt.ko ]]
[[ -s $build_tree/drivers/thunderbolt/thunderbolt_apple.ko ]]

mkdir -p "$module_root" "$build_tmp" "$(dirname -- "$log")"
make -C "$source_tree" O="$build_tree" \
  INSTALL_MOD_PATH="$module_root" modules_install
depmod -b "$module_root" "$kernel_release"

# Supplying -c disables automatic drop-ins. Concatenate the installed config
# and its drop-ins, then force the bring-up path and root filesystem modules.
cat /etc/mkinitcpio.conf /etc/mkinitcpio.conf.d/*.conf > "$config"
cat >> "$config" <<'CONFIG'

MODULES+=(btrfs appledrm phy_apple_atc tps6598x_core tps6598x thunderbolt thunderbolt_apple)
CONFIG

mkinitcpio --nopost -k "$kernel_release" -r "$module_root" \
  -c "$config" -t "$build_tmp" -g "$initramfs" 2>&1 | tee "$log"
lsinitcpio -l "$initramfs" > "$project/reports/thunderbolt/initramfs-contents.txt"

for module in thunderbolt.ko thunderbolt_apple.ko phy-apple-atc.ko appledrm.ko; do
  grep -q "/$module$" "$project/reports/thunderbolt/initramfs-contents.txt" || {
    echo "Initramfs is missing $module" >&2
    exit 1
  }
done

printf 'Built %s for %s\n' "$initramfs" "$kernel_release"
