# 04 — DRM, the compositor, and hotplug

## The state machine the DCP driver exposes to DRM

- `dcp->connector->connected` is what `apple_connector_detect()` reports. It is set by the firmware's
  `cb_hotplug` callback (`iomfb_template.c`) when the DP link is up and an EDID was read, and cleared by
  `disconnected_hpd_event()` / the firmware on HPD removal. Each change schedules `dcp_hotplug()`
  (`iomfb.c`), which frees the EDID on disconnect and sends the DRM hotplug uevent.
- `dcp->valid_mode` is true only after a successful `set_digital_out_mode` (the modeset, ~8 s on this
  firmware). `cb_hotplug` clears it on every connect/disconnect. `dcp_hotplug()` additionally sets the
  DRM `link-status` property to BAD when connected without a valid mode, which is the standard way to
  tell userspace "please re-modeset". Hyprland ignores it.
- The modeset happens in `apple_crtc_atomic_enable()` → `dcp_crtc_atomic_modeset()`, which the DRM
  helpers call only when `drm_atomic_crtc_needs_modeset()` is true for the commit. `dcp_poweron()` is
  called there only when `active_changed` (CRTC off → on). `dcp_flush()` (page flips) submits swaps;
  the firmware "swallows" swaps if its controller is not powered / no timing set.

## What happens on a fresh connect (boot, first plug) — works without help

connect → firmware link config → `cb_hotplug(1)` → `dcp_hotplug()` → uevent → Hyprland adds DP-1 as a
new output → atomic commit with CRTC off→on → `atomic_enable`: `dcp_poweron()` + modeset → firmware
runs a second WILL_CHANGE/SET_LINK_RATE round (crossbar down/up, new drive settings) →
`mode_set_gated ... link: 1` → picture. Evidence: `reports/usb4-dpin-v4/attempt1-macos-seq/`.

## What happens on a reconnect — Hyprland keeps stale state

After a link drop, `disconnect` then `connect` produce a perfect kernel-side log (DPRX done, HPD, 7
modes) but no picture: Hyprland still has DP-1 configured, never disabled the CRTC, and its next page
flip is a plain swap. The firmware logs `swap_submit_dcp: swallowed swap ... fControllerPowerState is 0
... timings are not enabled` (it powered the external pipeline down when HPD was removed) and after a
second or so tears the link down itself (WILL_CHANGE_LINK_CONFIG → our crossbar down, SET_LINK_RATE 0 →
PCLK off). Evidence: `attempt2-replug`, `attempt3-inactive-edge`, `attempt4-monitor-powercycle`.

A DPMS off/on from the compositor fixes it because that path goes through `atomic_disable`/
`atomic_enable` with `active_changed`, i.e. `dcp_poweroff` + `dcp_poweron` + modeset. That is what
`scripts/dpin-recover.sh` does (`hyprctl dispatch 'hl.dsp.dpms("off")'` … `("on")`; targeted
`("off","DP-1")` blanked both screens and the IPC timed out during the 8 s modeset).

## The v5 fix, two halves

1. `dcp_crtc_atomic_check()`: if the CRTC is active, the connector connected, `valid_mode` false and
   the commit is not already a modeset, set `crtc_state->mode_changed = true`. The DRM helpers then
   call `atomic_disable`/`atomic_enable` for this CRTC (amdgpu uses the same trick in its atomic_check).
2. `apple_crtc_atomic_enable()`: power the DCP on not only when `active_changed` but also when
   `dcp_needs_poweron()` (`dp_tunnel && !dcp->powered`); `dcp->powered` is set by `dcp_poweron`,
   cleared by `dcp_poweroff` and by the tunnel disconnect path (the firmware powers the external
   pipeline down on HPD removal even though Linux never called poweroff).

Observed on the v5 replug (`reports/usb4-dpin-v5/boot1-auto/`): `DP tunnel up` → `auto connect: 0` →
`dcp_hotplug() connected:1` → `crtc_atomic_check: forcing a modeset (no valid mode)` ×3 →
`dcp_poweron()` → `mode_set_gated ... link: 1`. Hyprland did not disable the CRTC; the forced modeset
is what made it work.

Caveat for a clean rewrite: setting `mode_changed` inside the CRTC's `atomic_check` happens after
`drm_atomic_helper_check_modeset()` ran, so affected connectors/planes are not re-added to the state.
Harmless here (simple encoder, the plane is already in the flip), but a reviewer will ask. The tidier
alternative is to make the disconnect look like a real disconnect long enough for the compositor to
drop the output (see below), and keep the forced modeset only as a fallback.

## Thunderbolt-tunnel-driven hotplug (v5)

Why: the DCP firmware only reports HPD after *we* tell it a sink exists (`hotPlugDetectChangeOccurred`),
and it has no idea when the tunnel disappears. The only entity that knows is the thunderbolt core.

Design:
- `drivers/thunderbolt/tb.c`: a blocking notifier chain. `tb_dp_tunnel_notify(tunnel, up)` is called
  after `tb_tunnel_activate()` succeeds in `tb_tunnel_one_dp()` and at the top of the `TB_TUNNEL_DP`
  case in `tb_deactivate_and_free_tunnel()`. Event data: the host NHI `struct device *` (its
  `of_node` identifies the port), the DP IN adapter number, the remote route and DP OUT number. Only
  tunnels whose source is the host router (`tb_route(src->sw) == 0`) are reported. A small list of
  currently-up tunnels is kept so `tb_dp_tunnel_notifier_register()` can replay them (the DCP may probe
  after the tunnel exists, and the thunderbolt module loads independently).
- `appledrm`: subscribes in probe when routed into a DP IN adapter; DT `apple,tbt-nhi` phandle selects
  the NHI, DP IN 5/6 selects dpin0/dpin1. The callback only records the event and schedules a delayed
  work item (0.5 s after up, immediately on down). The work calls the existing
  `dcp_dptx_connect_oob()` / `dcp_dptx_disconnect_oob()`, retrying every 0.5 s for up to 30 s while
  the DCP endpoints are not up yet (boot ordering). `appledrm.dpin_auto=0` disables it; the debugfs
  `tunnel_hpd` trigger still works.

Timing seen at boot: dcpext up 20:08:22, NHI/tunnel 20:08:24, so the replay path was not even needed
on this machine, but the retry loop was (the DPTX endpoint takes a moment after the DCP boots).

## Other DRM-adjacent facts learned the hard way

- `hyprctl` on this Hyprland uses a Lua dispatcher syntax: `hyprctl dispatch 'hl.dsp.dpms("on")'`.
  The classic `hyprctl dispatch dpms on` fails to parse.
- Hyprland's IPC times out while its main loop is blocked in the 8 s DCP modeset. Wait, do not retry
  in a loop.
- The firmware keeps the DP link and HPD state across our disconnect/connect if we never told it about
  the sink loss; it is the *firmware* that then re-runs link config when the mode is set.
