#!/usr/bin/env bash
# Build only: never installs files or changes the running kernel.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project=$PWD
source_tree=$project/sources/linux-usb4-backport
build_tree=$project/artifacts/usb4-backport/build
base=94fb23346d522edf53722357c426a3e58030beea
export RUSTUP_HOME=$project/artifacts/usb4-backport-toolchain/rustup
export CARGO_HOME=$project/artifacts/usb4-backport-toolchain/cargo
export RUSTUP_TOOLCHAIN=1.93.1
export PATH="$CARGO_HOME/bin:$project/artifacts/thunderbolt-toolchain/root/usr/bin:$PATH"
export LD_LIBRARY_PATH="$project/artifacts/thunderbolt-toolchain/root/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export KBUILD_BUILD_USER=mert KBUILD_BUILD_HOST=asahi-usb4-backport
export KBUILD_BUILD_TIMESTAMP='Fri Sep 18 00:00:00 UTC 2026'

[[ $(rustc --version) == 'rustc 1.93.1 '* ]]
[[ $(git -C "$source_tree" branch --show-current) == thunderbolt-7.1.13-gpu ]]
[[ -z $(git -C "$source_tree" status --porcelain --untracked-files=no) ]]
git -C "$source_tree" diff --exit-code "$base" -- \
  drivers/gpu/drm/asahi drivers/gpu/drm/apple drivers/iommu rust
mkdir -p "$build_tree" reports/usb4-backport
kmake() { make -C "$source_tree" O="$build_tree" LOCALVERSION= "$@"; }

if [[ ${1:-build} == configure ]]; then
  [[ ! -e $build_tree/.config ]] || { echo 'Config already exists; refusing to replace it.' >&2; exit 1; }
  cp artifacts/headers/usr/lib/modules/7.1.13-3-1-ARCH/build/.config "$build_tree/.config"
  "$source_tree/scripts/config" --file "$build_tree/.config" \
    --set-str LOCALVERSION '-usb4-gpu-test' --disable LOCALVERSION_AUTO \
    --module USB4 --module USB4_APPLE_SOC --enable RESET_APPLE_CIO \
    --module USB4_NET
  kmake rustavailable
  kmake olddefconfig
fi

for option in RUST DRM_ASAHI RUST_APPLE_RTKIT RUST_APPLE_MAILBOX; do
  rg -q "^CONFIG_${option}=y$" "$build_tree/.config" || {
    echo "Required GPU/Rust option lost: $option" >&2; exit 1;
  }
done
for option in DRM_APPLE USB4 USB4_APPLE_SOC; do
  rg -q "^CONFIG_${option}=m$" "$build_tree/.config"
done
[[ $(kmake -s kernelrelease) == 7.1.13-usb4-gpu-test ]]

if [[ ${1:-build} == configure ]]; then
  "$source_tree/scripts/diffconfig" \
    artifacts/headers/usr/lib/modules/7.1.13-3-1-ARCH/build/.config "$build_tree/.config"
  exit 0
fi

if [[ ${1:-build} == modules-install ]]; then
  test -s "$build_tree/arch/arm64/boot/Image"
  kmake INSTALL_MOD_PATH="$project/artifacts/usb4-backport/root" INSTALL_MOD_STRIP=1 modules_install
  depmod -b "$project/artifacts/usb4-backport/root" 7.1.13-usb4-gpu-test
  exit 0
fi
[[ ${1:-build} == build ]]

nice -n 10 make -C "$source_tree" O="$build_tree" LOCALVERSION= -j6 \
  Image modules apple/t8103-j313.dtb 2>&1 | tee reports/usb4-backport/build.log
rg -q 'asahi' "$build_tree/System.map"
test -s "$build_tree/drivers/gpu/drm/asahi/asahi.o"
test -s "$build_tree/drivers/thunderbolt/thunderbolt_apple.ko"
echo 'Build finished. GPU runtime and USB4 transport still require a reboot test.'
