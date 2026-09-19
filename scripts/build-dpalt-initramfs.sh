#!/usr/bin/env bash
# Build the isolated DP-alt-mode initramfs from the dpalt module root; installs nothing.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
(( EUID == 0 )) || { echo 'Run as root.' >&2; exit 1; }
project=$PWD
release=7.1.13-usb4-gpu-test
module_root=$project/artifacts/dpalt/root
build_tree=$project/artifacts/usb4-backport/build
[[ $(<"$build_tree/include/config/kernel.release") == "$release" ]]
tipd=usb/typec/tipd/tps6598x-core.ko
test -s "$module_root/lib/modules/$release/kernel/drivers/$tipd"
# the dpalt tipd module must differ from the v3 one; everything else must match v3
cmp -s "$module_root/lib/modules/$release/kernel/drivers/$tipd" \
       "$project/artifacts/usb4-dpin-v3/root/lib/modules/$release/kernel/drivers/$tipd" \
  && { echo "tps6598x-core.ko is unchanged from v3; refusing." >&2; exit 1; }
for m in thunderbolt/thunderbolt.ko phy/apple/phy-apple-atc.ko gpu/drm/apple/appledrm.ko; do
  cmp "$module_root/lib/modules/$release/kernel/drivers/$m" \
      "$project/artifacts/usb4-dpin-v3/root/lib/modules/$release/kernel/drivers/$m"
done
mkdir -p artifacts/dpalt/initramfs-tmp reports/dp-altmode
mkinitcpio --nopost -k "$build_tree/arch/arm64/boot/Image" -r "$module_root" \
  -c "$project/config/usb4-dpin-v3-mkinitcpio.conf" \
  -t "$project/artifacts/dpalt/initramfs-tmp" \
  -g "$project/artifacts/dpalt/initramfs-dpalt.img" \
  2>&1 | tee reports/dp-altmode/initramfs-build.log
lsinitcpio -l artifacts/dpalt/initramfs-dpalt.img > reports/dp-altmode/initramfs-contents.txt
for module in appledrm phy-apple-atc tps6598x-core tps6598x thunderbolt thunderbolt_apple btrfs mux-apple-display-crossbar; do
  rg -q "/$module\\.ko$" reports/dp-altmode/initramfs-contents.txt || { echo "missing $module in initramfs" >&2; exit 1; }
done
rg -q 'hooks/asahi$' reports/dp-altmode/initramfs-contents.txt
# the embedded tipd module must match the dpalt root byte for byte
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
path=$(rg "kernel/drivers/$tipd" reports/dp-altmode/initramfs-contents.txt | head -1)
(cd "$tmp" && lsinitcpio -x "$project/artifacts/dpalt/initramfs-dpalt.img" "$path" >/dev/null)
cmp "$tmp/$path" "$module_root/lib/modules/$release/kernel/drivers/$tipd"
echo 'DP-alt initramfs built and verified; not installed.'
