#!/bin/bash
# HOST-side helper for reports/usb4-dpin-v3/M1N1-TRACE-CHECKLIST.md (steps A3 + B4).
#   ./scripts/host-m1n1-trace.sh extract [kernelcache]   -> ~/kernelcache.macho
#   ./scripts/host-m1n1-trace.sh trace   [macho] [log]   -> runs run_guest.py with the tracers
#   ./scripts/host-m1n1-trace.sh check                   -> prerequisites + serial device
#   ./scripts/host-m1n1-trace.sh vuart                   -> log the guest serial console (2nd ACM port)
set -euo pipefail
export PATH="$HOME/Library/Python/3.9/bin:$PATH"
M1N1="${M1N1:-$HOME/m1n1}"
MACHO="${2:-$HOME/kernelcache-13.5.macho}"

find_kc() {
    for f in "${1:-}" ~/Downloads/kernelcache* ~/Desktop/kernelcache* ~/kernelcache; do
        [ -n "$f" ] && [ -f "$f" ] && [ "$f" != "$HOME/kernelcache.macho" ] && { echo "$f"; return; }
    done
    echo "no kernelcache found in ~/Downloads, ~/Desktop or ~ (AirDrop it from the TARGET, step A1)" >&2
    exit 1
}

case "${1:-check}" in
check)
    python3 -c 'import serial, construct, pyimg4; print("python deps ok")'
    [ -f "$M1N1/proxyclient/hv/trace_dpin_bringup.py" ] && echo "m1n1 fork ok: $M1N1"
    [ -f "$MACHO" ] && ls -la "$MACHO" || echo "no $MACHO yet (run: $0 extract)"
    ls /dev/cu.usbmodem* 2>/dev/null || echo "no /dev/cu.usbmodem* yet (TARGET not in proxy mode / cable)"
    ;;
extract)
    KC=$(find_kc "${2:-}")
    echo "extracting $KC -> $HOME/kernelcache.macho"
    # The Preboot kernelcache is a full IMG4 (IMG4 > IM4P > LZFSE krnl); unwrap, then decompress.
    if head -c 32 "$KC" | grep -q IMG4; then
        pyimg4 img4 extract -i "$KC" -p "$HOME/kernelcache.im4p"
        KC="$HOME/kernelcache.im4p"
    fi
    pyimg4 im4p extract -i "$KC" -o "$HOME/kernelcache.macho"
    ls -la "$HOME/kernelcache.macho"
    file "$HOME/kernelcache.macho" || true
    ;;
trace)
    LOG="${3:-$HOME/dpin-trace.log}"
    [ -f "$MACHO" ] || { echo "missing $MACHO (run: $0 extract)" >&2; exit 1; }
    DEV=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1) || true
    [ -n "${DEV:-}" ] || { echo "no /dev/cu.usbmodem* device; TARGET must be in m1n1 proxy mode (B3)" >&2; exit 1; }
    export M1N1DEVICE="${M1N1DEVICE:-$DEV}"
    export TRACE_DCP="${TRACE_DCP:-dcpext}"
    echo "device=$M1N1DEVICE  TRACE_DCP=$TRACE_DCP  log=$LOG"
    cd "$M1N1/proxyclient"
    # boot-uuid patch: the stub's chosen node points xnu at the Asahi stub volume, which panics
    # ("rootvp not authenticated"). A nonexistent UUID makes xnu wait 60 s for root instead
    # (all drivers up, LG hot-pluggable), then it reboots into macOS Recovery (compiled-in xnu
    # behaviour: IOSetRecoveryBoot). trm_enabled=0 turns off Thunderbolt Restricted Mode, which
    # otherwise refuses to identify the LG with no user logged in. Kernel must be the 13.5 one
    # (kernelcache.release.mac13g from the 13.5 IPSW) to match the stub's 13.5 firmware.
    exec python3 tools/run_guest.py \
        -m hv/trace_dcp.py -m hv/trace_atc.py -m hv/trace_dpin_bringup.py \
        -c 'hv.adt["/chosen"].boot_uuid = "DEADBEEF-DEAD-BEEF-DEAD-BEEFDEADBEEF"; hv.adt["/chosen"].apfs_preboot_uuid = "DEADBEEF-DEAD-BEEF-DEAD-BEEFDEADBEEF"' \
        -l "$LOG" "$MACHO" \
        -- "-v debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam wdt=-1 clpc=0 trm_enabled=0"
    ;;
vuart)
    DEV=$(ls /dev/cu.usbmodem*3 2>/dev/null | head -1) || true
    [ -n "${DEV:-}" ] || { echo "no vuart port (/dev/cu.usbmodem*3)" >&2; exit 1; }
    exec python3 "$(dirname "$0")/host-vuart-log.py" "$DEV" "${2:-$HOME/dpin-guest-console.log}"
    ;;
*) echo "usage: $0 {check|extract [kernelcache]|trace [macho] [log]}" >&2; exit 2 ;;
esac
