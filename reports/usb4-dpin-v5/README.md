# DP-IN v5 — automatic hotplug — **WORKS (2026-09-21): picture at the lock screen, replug recovers by itself**

**2026-09-22 update recovery:** a package hook overwrote the shared boot bundle
with stock components. Restored verified v5 boot components and installed a
supported `update-m1n1` override to preserve them across updates. Reboot validation
is pending. See [cause, repair, maintenance and rollback](UPDATE-RECOVERY.md).

v4 lights the LG but needs `scripts/dpin-recover.sh` (or `run-dpin-v3.py connect` + a DPMS cycle)
after every boot, replug or monitor power cycle. v5 makes both automatic. Kernel branch
`thunderbolt-7.1.13-dpin-v5` (commit `69349e941`, one commit on top of v4 `9a7b5dbca`), same
kernel release `7.1.13-usb4-gpu-test`; changed modules: `thunderbolt.ko`, `phy-apple-atc.ko`
(rebuilt, unchanged source), `appledrm.ko`, plus the J313 DTB (`apple,tbt-nhi = <&usb4_1_nhi>`).

## Result (first boot, 2026-09-21)

Booted the v5 entry with the LG attached: picture as soon as the lock screen appeared. Unplugged and
replugged the cable: picture came back by itself. Evidence in `boot1-auto/` (kernel log, DRM and
Hyprland state). Both mechanisms fired:

```
boot:   DP tunnel up on host DP IN 5 -> DP-IN auto connect: 0 -> dcp_hotplug() connected:1 nr_modes:7
        -> dcp_poweron() -> mode_set_gated 3840x2160@60 link: 1
replug: DP tunnel down -> DP-IN auto disconnect: 0
        DP tunnel up -> DP-IN auto connect: 0 -> dcp_hotplug() connected:1
        -> crtc_atomic_check: forcing a modeset (no valid mode)   <- Hyprland kept its stale output state
        -> dcp_poweron() -> mode_set_gated 3840x2160@60 link: 1
```
So on a replug Hyprland does *not* disable/enable the CRTC; the forced modeset in atomic_check plus
the `dcp->powered` re-poweron is what makes the reconnect work. `scripts/dpin-recover.sh` is now
only a fallback.

## What v5 adds

1. **Thunderbolt core → display driver notifier.** `tb_dp_tunnel_notifier_register()` in the
   thunderbolt module reports `TB_DP_TUNNEL_UP` when the connection manager activates a DP tunnel
   from a host router DP IN adapter (`tb_tunnel_one_dp`) and `TB_DP_TUNNEL_DOWN` when it tears one
   down (`tb_deactivate_and_free_tunnel`: unplug, monitor power cycle). Tunnels already up are
   replayed to late subscribers, so it does not matter whether the tunnel or the DCP comes up first
   at boot.
2. **appledrm subscribes** (when routed into a DP IN adapter; `apple,tbt-nhi` picks the front-port
   host interface, DP IN 5 → dpin0, 6 → dpin1). A work item runs the existing
   `dcp_dptx_connect_oob` / `dcp_dptx_disconnect_oob`, retrying every 0.5 s for 30 s until the DCP
   endpoints are ready. `appledrm.dpin_auto=0` turns this off (the `tunnel_hpd` debugfs trigger
   still works either way).
3. **Forced modeset on reconnect.** The v4 experiments showed that after a reconnect Hyprland keeps
   its output state, never re-sends the mode, the firmware swallows every swap
   (`fControllerPowerState is 0`) and then drops the link. `dcp_crtc_atomic_check` now sets
   `mode_changed` when the mode is invalid (the amdgpu pattern), and `apple_crtc_atomic_enable`
   powers the DCP back on when the firmware pipeline was powered down by HPD removal
   (`dcp->powered`). With the automatic disconnect the compositor should also see a real
   disconnect → connect cycle and do this by itself; the forced modeset is the safety net.

## Expected behaviour on the v5 entry

- Boot with the LG attached: within a few seconds of the tunnel activating,
  `DP tunnel up on host DP IN 5`, `DP-IN auto connect (tunnel up on host DP IN 5): 0`, the usual
  v4 sequence, `dcp_hotplug() connected:1`, Hyprland adds DP-1, `dcp_poweron()`,
  `set_digital_out_mode(... 3840x2160 ...)`, `mode_set_gated ... link: 1`. Picture, no script.
- Unplug / monitor power cycle: `DP tunnel down`, `DP-IN auto disconnect (tunnel down): 0`,
  Hyprland removes DP-1 (`dcp_poweroff`). Replug: as at boot.
- If the picture does not come back by itself: `scripts/dpin-recover.sh` still works, and
  `journalctl -k -b | grep -E 'DP tunnel|DP-IN|forcing a modeset|dcp_power'` shows which step
  did not happen.

## Restore

If the September 22 updater override is installed, disable it as documented in
[UPDATE-RECOVERY.md](UPDATE-RECOVERY.md#return-to-packaged-boot-components) before
returning to stock; otherwise a package update will reactivate the v5 inputs.

`sudo python3 scripts/stage-usb4-dpin-v5.py restore` puts the v4 modules, the v4 loader
(`boot.bin.before-usb4-dpin-v5`) and the GRUB file back. The v4 GRUB entry stays as a fallback
while v5 is active (its initramfs carries the v4 modules; the DTB comes from the active loader
and only adds a property v4 ignores).
