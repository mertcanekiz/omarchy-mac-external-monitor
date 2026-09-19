#!/usr/bin/env bash
# Build diagnostic module only. No installation, loading, or boot changes.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
project=$PWD
kernel=7.1.13-3-1-ARCH
base=94fb23346d522edf53722357c426a3e58030beea
headers="$project/artifacts/headers/usr/lib/modules/$kernel/build"
stage="$project/artifacts/display-debug"
[[ ! -e "$stage" ]] || { echo 'Build directory already exists; preserve it and choose a fresh build.' >&2; exit 1; }
[[ -d "$headers" ]]
mkdir -p "$stage"
git -C sources/linux archive "$base" drivers/gpu/drm/apple | tar -x -C "$stage"
patch --batch --fuzz=0 -d "$stage" -p1 < patches/display-startup-diagnostics.patch
export LD_LIBRARY_PATH="$project/artifacts/build-tools/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
module_dir="$stage/drivers/gpu/drm/apple"
make -C "$headers" M="$module_dir" PAHOLE="$project/artifacts/build-tools/usr/bin/pahole" -j4 modules
[[ $(modinfo -F vermagic "$module_dir/appledrm.ko") == "$kernel SMP preempt mod_unload aarch64" ]]
sha256sum "$module_dir/appledrm.ko"
echo 'Diagnostic module built only; running drivers and boot files unchanged.'
