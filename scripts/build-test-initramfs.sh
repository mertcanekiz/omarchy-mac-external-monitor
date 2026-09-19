#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Stage a separate boot image using a private copy of the module tree.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project=$PWD
kernel=7.1.13-3-1-ARCH
[[ $(uname -r) == "$kernel" ]] || { echo 'Kernel changed; rebuild and reassess first.' >&2; exit 1; }
[[ $(pacman -Q linux-asahi) == 'linux-asahi 7.1.13.asahi3-1' ]]
mkdir -p artifacts/module-root/lib/modules artifacts/initramfs-tmp
cp -a "/usr/lib/modules/$kernel" artifacts/module-root/lib/modules/
cp artifacts/tipd/tps6598x-core.ko artifacts/tipd/tps6598x.ko \
  "artifacts/module-root/lib/modules/$kernel/kernel/drivers/usb/typec/tipd/"
depmod -b artifacts/module-root "$kernel"

# Passing -c disables mkinitcpio's automatic drop-ins, so include the installed
# configuration and its drop-ins explicitly, then force the matching module pair
# into early boot. All paths written by mkinitcpio point into the workspace.
cat /etc/mkinitcpio.conf /etc/mkinitcpio.conf.d/*.conf > artifacts/test-mkinitcpio.conf
cat >> artifacts/test-mkinitcpio.conf <<'CONFIG'

MODULES+=(tps6598x_core tps6598x)
CONFIG
mkinitcpio --nopost -k "$kernel" -r "$project/artifacts/module-root" \
  -c "$project/artifacts/test-mkinitcpio.conf" \
  -t "$project/artifacts/initramfs-tmp" \
  -g "$project/artifacts/initramfs-display-test.img" 2>&1 | tee reports/initramfs-build.log
lsinitcpio -l artifacts/initramfs-display-test.img > reports/initramfs-contents.txt
echo 'Test initramfs staged only; no live boot files changed.'
