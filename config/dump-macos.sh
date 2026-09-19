#!/bin/sh
# Run in macOS Terminal with the LG connected over Thunderbolt and showing a picture:
#   diskutil mount "EFI - OMARC"
#   sh "/Volumes/EFI - OMARC/dump-macos.sh"
set -u
out="/Volumes/EFI - OMARC/macos-dump"
mkdir -p "$out" || { echo "EFI volume not mounted"; exit 1; }
echo "writing to $out"
ioreg -l -w0 -p IODeviceTree > "$out/adt.txt" 2>&1
ioreg -l -w0 > "$out/ioreg.txt" 2>&1
ioreg -l -w0 -r -c IOThunderboltPort > "$out/tbports.txt" 2>&1
ioreg -l -w0 -r -c IOThunderboltSwitch > "$out/tbswitch.txt" 2>&1
ioreg -l -w0 -r -n atc1-dpin0 -p IODeviceTree > "$out/atc1-dpin0.txt" 2>&1
ioreg -l -w0 -r -n atc1-dpin1 -p IODeviceTree > "$out/atc1-dpin1.txt" 2>&1
ioreg -l -w0 -r -n atc1-dpxbar -p IODeviceTree > "$out/atc1-dpxbar.txt" 2>&1
ioreg -l -w0 -r -n acio1 -p IODeviceTree > "$out/acio1.txt" 2>&1
ioreg -l -w0 -r -n dcpext -p IODeviceTree > "$out/dcpext.txt" 2>&1
ioreg -l -w0 -r -c IOThunderboltDPInAdapter > "$out/dpin-adapters.txt" 2>&1
ioreg -l -w0 -r -c IOThunderboltDPOutAdapter > "$out/dpout-adapters.txt" 2>&1
system_profiler SPThunderboltDataType SPDisplaysDataType > "$out/tb.txt" 2>&1
log show --last 10m --predicate 'process == "kernel" AND (eventMessage CONTAINS "Thunderbolt" OR eventMessage CONTAINS "DCP" OR eventMessage CONTAINS "DPTX" OR eventMessage CONTAINS "dpin")' > "$out/kernel-log.txt" 2>&1
sw_vers > "$out/sw_vers.txt" 2>&1
ls -la "$out"
echo "done. Now: diskutil unmount \"EFI - OMARC\" and reboot into Linux."
