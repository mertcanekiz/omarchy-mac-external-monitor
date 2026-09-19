#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Build only: writes under this workspace; never installs or loads modules.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project=$PWD
kernel=7.1.13-3-1-ARCH
source_commit=ce9f2eba72c061a50b2d790450e90af3439d8c24
base_commit=94fb23346d522edf53722357c426a3e58030beea
headers="$project/artifacts/headers/usr/lib/modules/$kernel/build"
tools_dir="$project/artifacts/build-tools"

[[ $(git -C sources/linux rev-parse HEAD) == "$source_commit" ]]
[[ $(git -C sources/linux rev-parse 'asahi-7.1.13-3^{commit}') == "$base_commit" ]]
[[ -z $(git -C sources/linux status --porcelain --untracked-files=no) ]]
printf '%s  %s\n' \
  360813cd9777c4c0c4e82dd48527cd5937a6e7e332ec982e5f9b2b1744d05764 artifacts/linux-asahi-headers-7.1.13.asahi3-1-aarch64.pkg.tar.xz \
  76552e6f3d18daa27d643e1eb5bb55cd6024684998aa9774983475b08402fd75 artifacts/pahole-1.32-1-aarch64.pkg.tar.xz | sha256sum -c -

mkdir -p artifacts/headers artifacts/build-tools artifacts/tipd artifacts/dtb reports
tar -xJf artifacts/linux-asahi-headers-7.1.13.asahi3-1-aarch64.pkg.tar.xz -C artifacts/headers
tar -xJf artifacts/pahole-1.32-1-aarch64.pkg.tar.xz -C artifacts/build-tools
cp sources/linux/drivers/usb/typec/tipd/* artifacts/tipd/
export LD_LIBRARY_PATH="$tools_dir/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
make -C "$headers" M="$project/artifacts/tipd" PAHOLE="$tools_dir/usr/bin/pahole" -j4 modules 2>&1 | tee reports/module-build.log

# Both modules must be rebuilt: the patch changes a structure allocated by i2c.c.
for module in tps6598x-core tps6598x; do
  [[ $(modinfo -F vermagic "artifacts/tipd/$module.ko") == "$kernel SMP preempt mod_unload aarch64" ]]
done

# Preserve the distro's display, PHY, crossbar and GPU code. Only the Type-C
# patch and J313 shared DTS are needed for this experiment.
git -C sources/linux diff --exit-code "$base_commit" "$source_commit" -- drivers/gpu/drm/apple drivers/phy/apple drivers/mux
gcc -E -nostdinc -I sources/linux/scripts/dtc/include-prefixes -undef -D__DTS__ \
  -x assembler-with-cpp -o artifacts/dtb/t8103-j313.preprocessed.dts \
  sources/linux/arch/arm64/boot/dts/apple/t8103-j313.dts
"$headers/scripts/dtc/dtc" -I dts -O dtb -b 0 \
  -Wno-unique_unit_address -Wno-unit_address_vs_reg -Wno-avoid_unnecessary_addr_size \
  -Wno-alias_paths -Wno-interrupt_map -Wno-simple_bus_reg \
  -o artifacts/dtb/t8103-j313.dtb artifacts/dtb/t8103-j313.preprocessed.dts \
  2> reports/dtb-build.log

# Independently reproduce the installed stock DTB using the same compiler.
mkdir -p artifacts/stock-dts
git -C sources/linux archive "$base_commit" arch/arm64/boot/dts/apple include/dt-bindings scripts/dtc/include-prefixes | tar -x -C artifacts/stock-dts
gcc -E -nostdinc -I artifacts/stock-dts/scripts/dtc/include-prefixes -undef -D__DTS__ \
  -x assembler-with-cpp -o artifacts/dtb/stock-j313.preprocessed.dts \
  artifacts/stock-dts/arch/arm64/boot/dts/apple/t8103-j313.dts
"$headers/scripts/dtc/dtc" -I dts -O dtb -b 0 \
  -Wno-unique_unit_address -Wno-unit_address_vs_reg -Wno-avoid_unnecessary_addr_size \
  -Wno-alias_paths -Wno-interrupt_map -Wno-simple_bus_reg \
  -o artifacts/dtb/stock-j313-rebuilt.dtb artifacts/dtb/stock-j313.preprocessed.dts \
  2> reports/stock-dtb-build.log
cmp artifacts/dtb/stock-j313-rebuilt.dtb "/usr/lib/modules/$kernel/dtbs/t8103-j313.dtb"

python3 scripts/stage-boot-bundle.py
sha256sum artifacts/tipd/tps6598x-core.ko artifacts/tipd/tps6598x.ko \
  artifacts/dtb/t8103-j313.dtb artifacts/boot.bin.display-test > reports/artifact-sha256.txt
echo 'Built and staged only. No modules loaded, no boot files changed.'
