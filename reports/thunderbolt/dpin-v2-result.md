# V2 boot and first DP-IN connection attempt

Boot ID: `c3b3ee46-280f-4014-bc45-7cac540934ee`.
The running module matched the v2 artifact by ELF build ID. The preflight
confirmed the front-port NHI, pending enabled DP-IN adapter, and timeout
override before the manual request.

## Established

- Both internal and external DCP complete initialization.
- `card1-eDP-1` is connected and `card1-DP-1` is registered.
- No kernel oops: taint remains 4100 (existing CPU-out-of-spec and out-of-tree
  module flags, without the oops bit).
- The LG UltraFine enumerates at `0-1` on the front-port Thunderbolt domain.
- The crossbar switches DPIN0 to dispext0,0.
- Firmware validation of core=1 / ATC=1 / die=0 returns zero.
- Firmware reaches get_supports_hpd, get_max_lane_count, then activate.

## Failure boundary

Link configuration times out after roughly two seconds. The subsequent HPD
assert returns `-110` (timeout). Firmware later calls device_not_responding
(22) and device_not_started (24). There are no set-link-rate or active-lane-count
callbacks in the captured trace. The host DP-IN and LG DP-OUT remain enabled,
but DPRX_DONE is false; DP-1 stays disconnected with no modes.

Evidence: [before](dpin-v2-attempt1/before.json),
[after, including kernel journal](dpin-v2-attempt1/after.json),
[DPTX callback trace](dpin-v2-attempt1/dptx-trace.txt), and
[request result](dpin-v2-attempt1/request.json).

This proves the boot fixes and firmware route acceptance, not a working video
path. Missing Apple DP-IN startup/register initialization and firmware startup
sequencing remain hypotheses, not confirmed causes. The activate callback in
the current prototype does no DP-IN-specific initialization; its optional PHY
operation is a no-op with the NULL physical PHY used for this tunnel.

## Test-harness correction and current state

The journal contains a second connect entry immediately after the failed HPD
write. Buffered `Path.write_text()` can retry flushing during close after a
write error. That second entry returns early because the driver's requested
state is already set; the trace contains only one firmware connect command.
The harness now uses one unbuffered `os.write()` and never retries a timeout or
short write. Three mocked tests cover success, timeout, and short-write paths.

The debugfs requested flag remains set even though the handshake failed.
Preflight now correctly refuses another attempt. No release, cable reset,
display-driver reload, forced mode, or additional firmware connect was issued.
The internal connector remains connected. Next work should establish the
missing DP-IN activation requirements and error cleanup before another trial.
