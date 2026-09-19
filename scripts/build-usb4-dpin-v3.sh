#!/usr/bin/env bash
# Build only (DP-IN v3 modules + J313 DTB); never installs files.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project=$PWD
source_tree=$project/sources/linux-usb4-backport
build_tree=$project/artifacts/usb4-backport/build
export RUSTUP_HOME=$project/artifacts/usb4-backport-toolchain/rustup
export CARGO_HOME=$project/artifacts/usb4-backport-toolchain/cargo
export RUSTUP_TOOLCHAIN=1.93.1
export PATH="$CARGO_HOME/bin:$project/artifacts/thunderbolt-toolchain/root/usr/bin:$PATH"
export LD_LIBRARY_PATH="$project/artifacts/thunderbolt-toolchain/root/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export KBUILD_BUILD_USER=mert KBUILD_BUILD_HOST=asahi-usb4-backport
export KBUILD_BUILD_TIMESTAMP='Fri Sep 18 00:00:00 UTC 2026'
[[ $(git -C "$source_tree" branch --show-current) == thunderbolt-7.1.13-dpin-v3 ]]
[[ $(<"$build_tree/include/config/kernel.release") == 7.1.13-usb4-gpu-test ]]
mkdir -p reports/usb4-dpin-v3 artifacts/usb4-dpin-v3
kmake() { make -C "$source_tree" O="$build_tree" LOCALVERSION= "$@"; }
image_before=$(sha256sum "$build_tree/arch/arm64/boot/Image" | cut -d' ' -f1)
case ${1:-quick} in
  quick)
    nice -n 10 make -C "$source_tree" O="$build_tree" LOCALVERSION= -j8 drivers/thunderbolt/ drivers/phy/apple/ drivers/gpu/drm/apple/ \
      apple/t8103-j313.dtb 2>&1 | tee reports/usb4-dpin-v3/build-quick.log ;;
  modules)
    nice -n 10 make -C "$source_tree" O="$build_tree" LOCALVERSION= -j8 modules apple/t8103-j313.dtb 2>&1 | tee reports/usb4-dpin-v3/build-modules.log
    rm -rf artifacts/usb4-dpin-v3/root
    kmake INSTALL_MOD_PATH="$project/artifacts/usb4-dpin-v3/root" INSTALL_MOD_STRIP=1 modules_install \
      2>&1 | tail -3
    depmod -b "$project/artifacts/usb4-dpin-v3/root" 7.1.13-usb4-gpu-test ;;
  *) echo "usage: $0 [quick|modules]" >&2; exit 2 ;;
esac
image_after=$(sha256sum "$build_tree/arch/arm64/boot/Image" | cut -d' ' -f1)
[[ $image_before == "$image_after" ]] || { echo "Kernel image changed unexpectedly" >&2; exit 1; }
echo "Build ok; Image unchanged ($image_after)"
