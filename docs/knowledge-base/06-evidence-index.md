# 06 — Evidence index

All paths relative to the project root. Directories under `reports/` are committed; `sources/`,
`artifacts/`, `snapshots/` are gitignored (the kernel/m1n1 trees are on the GitHub forks, see
`reports/usb4-dpin-v3/HANDOFF.md`).

## The trace (ground truth)
| file | content |
|---|---|
| `reports/usb4-dpin-v3/hv-attempt8-macos13.5-trm0-lg-attached.log` | run 8: full m1n1 hypervisor trace, SYNC on atc1-dpin0/dpin1/dpxbar, ASYNC on atc-phy1, DCP EPIC decode; two plug cycles |
| `reports/usb4-dpin-v3/hv-attempt3-8-guest-console.log` | guest xnu serial console, host-timestamped, runs 3–8 (search `17:44:5`) |
| `reports/usb4-dpin-v3/hv-attempt1…7-*.log` | earlier runs, each a setup failure with a lesson (SIO version, rootvp, TRM) |
| `reports/usb4-dpin-v3/HV-TRACE-FINDINGS.md` | the analysis, phases, line numbers, setup corrections |
| `reports/usb4-dpin-v3/M1N1-TRACE-CHECKLIST.md`, `M1N1-TRACE-RUNBOOK.md` | how to reproduce a trace session (tethered boot, 13.5 kernel from the IPSW, `trm_enabled=0`, bogus boot-uuid) |
| `config/m1n1-hv/trace_dpin_bringup.py`, `scripts/host-m1n1-trace.sh`, `scripts/host-vuart-log.py` | the tracer module and host helpers |

## macOS static dump (the LG working under macOS 14.3)
`reports/macos-dump/`: `adt.txt` (IODeviceTree), `atc1-dpin0.txt`, `atc1-dpin1.txt`,
`atc1-dpxbar.txt`, `acio1.txt`, `dcpext.txt`, `dpin-adapters.txt`, `dpout-adapters.txt`,
`tbports.txt`, `tbswitch.txt`, `tb.txt`, `ioreg.txt`, `kernel-log.txt` (macOS op names:
`validateConnection`, `makeDPINAdapterPortActive`, `bringConnectionUp`, `req_bandwidth = 159`).
Contains serial numbers; keep private.

## Linux-side register dumps and attempts
| file | content |
|---|---|
| `reports/usb4-dpin-v3/dpin0-regs-tunnel-pending.txt`, `dpin0-regs-video-active.txt`, `dpin1-regs-idle.txt` | the 0x4000 dpin blocks before/after the DPTX_INACTIVE poke |
| `reports/usb4-dpin-v3/attempt1…8-*/` | v3 connect attempts (journal, dptx trace, before/after adapter state) |
| `reports/usb4-dpin-v3/evidence-20260918-174759/` | the REVIEW.md evidence bundle: adapter regs decoded, EDID, DRM state, PCIe/USB negative result |
| `reports/usb4-dpin-v3/REVIEW.md`, `HANDOFF.md` | the (now historical) claims audit and handoff; useful for the list of overclaims not to repeat |
| `reports/usb4-dpin-v4/attempt1-macos-seq/` | **first picture**: journal, dptx trace, adapter/dpin state, Hyprland state |
| `reports/usb4-dpin-v4/attempt2-replug/`, `attempt3-inactive-edge/` | replug without modeset: the "swallowed swap" failure |
| `reports/usb4-dpin-v4/attempt4-monitor-powercycle/` | power-cycle recovery with webcam before/after photos |
| `reports/usb4-dpin-v4/README.md` | v4 delta table (macOS vs v3 vs v4) and the recovery findings |
| `reports/usb4-dpin-v5/boot1-auto/` | v5: automatic boot + replug journal and state |
| `reports/usb4-dpin-v5/README.md` | v5 design and result |

## Tools
`scripts/run-dpin-v3.py`, `scripts/collect-tunnel-registers.py`, `artifacts/mmio/mmio-rw.c`,
`mmio-dump.c`, `scripts/webcam-snap.sh`, `scripts/dpin-recover.sh`, build/stage scripts
(`scripts/build-usb4-dpin-v5*.sh`, `scripts/stage-usb4-dpin-v5.py`,
`scripts/assemble-thunderbolt-bundle.py`).

## Dead ends already ruled out (with where the evidence is)
- DP alt mode for this monitor: `reports/dp-altmode/INVESTIGATION.md` (cable/mode findings).
- "Panel needs USB/PCIe tunnel": refuted by v4 (`attempt1-macos-seq`, no PCIe/USB path active).
- "Bandwidth allocation / DP_STATUS = 0 is the blocker": refuted, see REVIEW.md rev 2 and
  `HANDOFF.md` "(Superseded) earlier bandwidth theory".
- DPTX_INACTIVE edge before connect: `attempt3-inactive-edge` (no effect), `attempt4` (lit without it).
- v3 PHY approach (`dpin_clocks`, priming at ACTIVATE): `reports/usb4-dpin-v3/attempt*`, never lit.
