#!/usr/bin/env bash
# Build the isolated DP-IN v3 initramfs from the v3 module root; installs nothing.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
project=$PWD
release=7.1.13-usb4-gpu-test
module_root=$project/artifacts/usb4-dpin-v3/root
build_tree=$project/artifacts/usb4-backport/build
[[ $(<"$build_tree/include/config/kernel.release") == "$release" ]]
for m in thunderbolt/thunderbolt.ko phy/apple/phy-apple-atc.ko gpu/drm/apple/appledrm.ko; do
  test -s "$module_root/lib/modules/$release/kernel/drivers/$m"
done
# the v3 modules must differ from the staged v2/GPU test ones
for m in thunderbolt/thunderbolt.ko phy/apple/phy-apple-atc.ko gpu/drm/apple/appledrm.ko; do
  if cmp -s "$module_root/lib/modules/$release/kernel/drivers/$m" \
            "$project/artifacts/usb4-backport/root/lib/modules/$release/kernel/drivers/$m"; then
    echo "Module $m is unchanged from the baseline; refusing." >&2; exit 1
  fi
done
mkdir -p artifacts/usb4-dpin-v3/initramfs-tmp reports/usb4-dpin-v3
mkinitcpio --nopost -k "$build_tree/arch/arm64/boot/Image" -r "$module_root" \
  -c "$project/config/usb4-dpin-v3-mkinitcpio.conf" \
  -t "$project/artifacts/usb4-dpin-v3/initramfs-tmp" \
  -g "$project/artifacts/usb4-dpin-v3/initramfs-usb4-dpin-v3.img" \
  2>&1 | tee reports/usb4-dpin-v3/initramfs-build.log
lsinitcpio -l artifacts/usb4-dpin-v3/initramfs-usb4-dpin-v3.img > reports/usb4-dpin-v3/initramfs-contents.txt
for module in appledrm phy-apple-atc tps6598x-core tps6598x thunderbolt thunderbolt_apple btrfs mux-apple-display-crossbar; do
  rg -q "/$module\\.ko$" reports/usb4-dpin-v3/initramfs-contents.txt || { echo "missing $module in initramfs" >&2; exit 1; }
done
rg -q 'hooks/asahi$' reports/usb4-dpin-v3/initramfs-contents.txt
# embedded modules must match the v3 root byte for byte
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for m in thunderbolt/thunderbolt.ko phy/apple/phy-apple-atc.ko gpu/drm/apple/appledrm.ko; do
  path=$(rg "kernel/drivers/$m" reports/usb4-dpin-v3/initramfs-contents.txt | head -1)
  lsinitcpio -x artifacts/usb4-dpin-v3/initramfs-usb4-dpin-v3.img "$path" -C "$tmp" >/dev/null 2>&1 || true
  cmp "$tmp/$path" "$module_root/lib/modules/$release/kernel/drivers/$m" || (cd "$tmp" && lsinitcpio -x "$project/artifacts/usb4-dpin-v3/initramfs-usb4-dpin-v3.img" "$path" >/dev/null && cmp "$tmp/$path" "$module_root/lib/modules/$release/kernel/drivers/$m")
done
echo 'DP-IN v3 initramfs built and verified; not installed.'
