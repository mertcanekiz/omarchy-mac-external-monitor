#!/usr/bin/env bash
# Bring the LG UltraFine (DP over Thunderbolt, DP-IN v4 kernel) back after a link drop:
# cable replug, monitor power cycle, or a fresh boot. Run as your user inside Hyprland
# (uses passwordless sudo for the kernel side and hyprctl for the modeset).
#   1. DCP disconnect + connect (re-does the whole macOS bring-up sequence in the kernel)
#   2. global DPMS off/on so Hyprland issues a real modeset (it keeps stale output state
#      across a reconnect and otherwise never re-sends the mode; DCP modeset takes ~8 s)
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
out=${1:-reports/usb4-dpin-v4/recover-$(date +%Y%m%d-%H%M%S)}
[[ $(uname -r) == 7.1.13-usb4-gpu-test ]] || { echo "not the DP-IN kernel" >&2; exit 1; }
if ! ls /sys/bus/thunderbolt/devices/*/device_name 2>/dev/null | xargs cat 2>/dev/null | grep -q UltraFine; then
  echo "LG not enumerated on Thunderbolt; check the cable/port (left-front) and try again" >&2; exit 1
fi
echo "== 1/3 DCP disconnect"
sudo -n python3 scripts/run-dpin-v3.py disconnect | tail -1
sleep 2
echo "== 2/3 DCP connect ($out)"
sudo -n python3 scripts/run-dpin-v3.py connect "$out" --dpin 0 --wait 15 2>&1 | grep -E 'external connector|activate:|DPRX cap|crossbar up|timed out|fail' | head -5
sudo -n chown -R "$USER" "$out" 2>/dev/null
sleep 2
echo "== 3/3 Hyprland modeset (all displays blank for ~10 s)"
timeout 20 hyprctl dispatch 'hl.dsp.dpms("off")' >/dev/null
sleep 10
timeout 20 hyprctl dispatch 'hl.dsp.dpms("on")' >/dev/null
sleep 15
timeout 15 hyprctl monitors | grep -E '^Monitor|dpms'
for c in /sys/class/drm/card*-DP-*; do echo "$c: $(cat "$c/status") $(cat "$c/enabled")"; done
journalctl -k -b --no-pager --since '-40 sec' | grep -q 'mode_set_gated.*link: 1' && echo "DCP reports the link up with a mode set" || echo "WARNING: no mode_set_gated in the last 40 s; run once more or check journalctl -k"
