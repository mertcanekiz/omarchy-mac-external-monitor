#!/usr/bin/env bash
# Build an isolated initramfs; no installed files or boot defaults are changed.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
project=$PWD
release=7.1.13-usb4-gpu-test
module_root=$project/artifacts/usb4-backport/root
build_tree=$project/artifacts/usb4-backport/build
for option in DRM_ASAHI RUST; do
  rg -q "^CONFIG_${option}=y$" "$build_tree/.config"
done
[[ $(<"$build_tree/include/config/kernel.release") == "$release" ]]
test -s "$module_root/lib/modules/$release/kernel/drivers/thunderbolt/thunderbolt_apple.ko"
mkdir -p artifacts/usb4-backport/initramfs-tmp
mkinitcpio --nopost -k "$build_tree/arch/arm64/boot/Image" -r "$module_root" \
  -c "$project/config/usb4-gpu-mkinitcpio.conf" \
  -t "$project/artifacts/usb4-backport/initramfs-tmp" \
  -g "$project/artifacts/usb4-backport/initramfs-usb4-gpu-test.img" \
  2>&1 | tee reports/usb4-backport/initramfs-build.log
lsinitcpio -l artifacts/usb4-backport/initramfs-usb4-gpu-test.img \
  > reports/usb4-backport/initramfs-contents.txt
for module in appledrm phy-apple-atc tps6598x-core tps6598x thunderbolt thunderbolt_apple btrfs; do
  rg -q "/$module\\.ko$" reports/usb4-backport/initramfs-contents.txt
done
rg -q 'hooks/asahi$' reports/usb4-backport/initramfs-contents.txt
echo 'Private initramfs built and required modules checked; not installed.'
