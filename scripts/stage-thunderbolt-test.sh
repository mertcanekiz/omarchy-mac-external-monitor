#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Install a parallel kernel target and stage (but do not activate) its m1n1 bundle.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
(( EUID == 0 )) || { echo 'Run this script as root.' >&2; exit 1; }

release=7.2.2-thunderbolt-test+
esp_partuuid=bf0b62f5-e52c-4ba5-afa8-e77cd9364cf5
stock_bundle=566227f96ea94bafac65ee6c997da0ba98be6f20479c3619ba1b8b739d156f33
display_bundle=af4c29967c23f23a571080f3f90b511f2263f5d42e6e06ea14e53cb2be582201
usb4_bundle=9602d026b2960bf308e3cc7a9d14019abeed4b7ccaa387125241073660b7c297

hash() { sha256sum "$1" | cut -d' ' -f1; }
require_hash() {
  local expected=$1 path=$2
  [[ -f $path && ! -L $path && $(hash "$path") == "$expected" ]] || {
    echo "Hash check failed: $path" >&2
    exit 1
  }
}

mountpoint -q /boot/efi
esp_source=$(findmnt -nro SOURCE /boot/efi)
[[ $(blkid -s PARTUUID -o value "$esp_source") == "$esp_partuuid" ]]
require_hash "$display_bundle" /boot/efi/m1n1/boot.bin
require_hash "$stock_bundle" /boot/efi/m1n1/boot.bin.before-display-test
current_custom=$(hash /boot/grub/custom.cfg)
[[ $current_custom == 4e7282d85a64d3a0aa21e2eb1903d3e6c38df490e5e6bf1edcb82159c7177624 ||
   $current_custom == 8af4f7ab56aac8c24d5c637b73858f31e02f8640f35c6e1e87c434a3bd1249b1 ]] || {
  echo 'Installed custom.cfg is not a recognized state.' >&2
  exit 1
}

require_hash fde2572e039cba1fb360ac6c72773a5df6abb73d025b4030a57e4aa89a290f29 \
  artifacts/thunderbolt-kernel/build/arch/arm64/boot/Image
require_hash 24b04c9775f4a4d2be535f554ab2accc30be477f12722c44d0629af4282674f0 \
  artifacts/initramfs-thunderbolt-test.img
require_hash "$usb4_bundle" artifacts/boot.bin.thunderbolt-test
require_hash 8af4f7ab56aac8c24d5c637b73858f31e02f8640f35c6e1e87c434a3bd1249b1 \
  config/thunderbolt-custom.cfg
require_hash 06bec4164bd16565322a9eeaf7b8041d9493f8c090d57c4c9a17bfa0f295e799 \
  config/THUNDERBOLT-TEST-RECOVERY.txt
grub-script-check config/thunderbolt-custom.cfg
grub-script-check /boot/grub/grub.cfg

module_source="artifacts/thunderbolt-kernel/root/lib/modules/$release"
[[ -d $module_source ]]
require_hash 77f5795312cf034de8a19b6565ff35095437c75b9d2b34b68fbf34c5ca04e70e \
  "$module_source/kernel/drivers/thunderbolt/thunderbolt.ko"
require_hash dc4fb57f9bbe7fb51a78a55de6413b4d751c6ae706660d167aab2992ccf8a5fe \
  "$module_source/kernel/drivers/thunderbolt/thunderbolt_apple.ko"

install_file() {
  local mode=$1 source=$2 target=$3 expected=$4 temporary="$3.staging"
  [[ ! -L $target && ! -e $temporary && ! -L $temporary ]]
  if [[ -e $target ]]; then
    require_hash "$expected" "$target"
    return
  fi
  install -m "$mode" "$source" "$temporary"
  require_hash "$expected" "$temporary"
  mv -T -- "$temporary" "$target"
}

replace_file() {
  local mode=$1 source=$2 target=$3 expected=$4 temporary="$3.staging"
  [[ ! -L $target && ! -e $temporary && ! -L $temporary ]]
  if [[ -e $target && $(hash "$target") == "$expected" ]]; then
    return
  fi
  install -m "$mode" "$source" "$temporary"
  require_hash "$expected" "$temporary"
  mv -T -- "$temporary" "$target"
}

module_target="/usr/lib/modules/$release"
module_temporary="/usr/lib/modules/.$release.staging"
[[ ! -L $module_target && ! -e $module_temporary && ! -L $module_temporary ]]
if [[ -e $module_target ]]; then
  require_hash 77f5795312cf034de8a19b6565ff35095437c75b9d2b34b68fbf34c5ca04e70e \
    "$module_target/kernel/drivers/thunderbolt/thunderbolt.ko"
  require_hash dc4fb57f9bbe7fb51a78a55de6413b4d751c6ae706660d167aab2992ccf8a5fe \
    "$module_target/kernel/drivers/thunderbolt/thunderbolt_apple.ko"
else
  cp -a -- "$module_source" "$module_temporary"
  require_hash 77f5795312cf034de8a19b6565ff35095437c75b9d2b34b68fbf34c5ca04e70e \
    "$module_temporary/kernel/drivers/thunderbolt/thunderbolt.ko"
  mv -T -- "$module_temporary" "$module_target"
fi

install_file 644 artifacts/thunderbolt-kernel/build/arch/arm64/boot/Image \
  /boot/vmlinuz-thunderbolt-test fde2572e039cba1fb360ac6c72773a5df6abb73d025b4030a57e4aa89a290f29
install_file 600 artifacts/initramfs-thunderbolt-test.img \
  /boot/initramfs-thunderbolt-test.img 24b04c9775f4a4d2be535f554ab2accc30be477f12722c44d0629af4282674f0
replace_file 644 config/thunderbolt-custom.cfg /boot/grub/custom.cfg \
  8af4f7ab56aac8c24d5c637b73858f31e02f8640f35c6e1e87c434a3bd1249b1
install_file 644 artifacts/boot.bin.thunderbolt-test \
  /boot/efi/m1n1/boot.bin.thunderbolt-test "$usb4_bundle"
install_file 644 config/THUNDERBOLT-TEST-RECOVERY.txt \
  /boot/efi/m1n1/THUNDERBOLT-TEST-RECOVERY.txt \
  06bec4164bd16565322a9eeaf7b8041d9493f8c090d57c4c9a17bfa0f295e799
install_file 644 /boot/efi/m1n1/boot.bin \
  /boot/efi/m1n1/boot.bin.before-thunderbolt-test "$display_bundle"

sync
grub-script-check /boot/grub/custom.cfg
echo 'USB4 kernel target staged. Active m1n1 bundle, GRUB default, and NVRAM selection are unchanged.'
