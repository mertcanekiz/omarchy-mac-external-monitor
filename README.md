# LG UltraFine over Thunderbolt on an M1 MacBook Air — project map

Goal: make the **LG 24MD4KL UltraFine** (a Thunderbolt-3-only monitor) show a picture on an
**M1 MacBook Air (t8103 / j313)** running Asahi/Omarchy Linux.

**Status (2026-09-19):** Thunderbolt transport works and a DisplayPort tunnel negotiates to the
monitor (valid EDID, HBR2 x4 caps, HPD). **No picture yet** — main-link training and pixel delivery
are not verifiable from Linux, and the leading (unproven) hypothesis is the monitor's scaler/backlight
are USB-managed and the USB path is unimplemented on M1 Linux. Next step is an m1n1 hypervisor trace
of macOS. Read the docs below before acting; several earlier confident claims were later corrected.

## Start here (read in this order)

1. **`reports/usb4-dpin-v3/HANDOFF.md`** — the single source of truth. Current state, what is proven
   vs not, how to reproduce, the exact remaining blocker, and every dead end already ruled out.
2. **`reports/usb4-dpin-v3/REVIEW.md`** (rev 2) — the claims stated precisely with reproducible
   proof, an adversarial review, and the corrections adopted from it. Read this to know exactly how
   strong each claim is. Its evidence is in `reports/usb4-dpin-v3/evidence-*/` (self-contained,
   includes decoder scripts).
3. **`reports/usb4-dpin-v3/M1N1-TRACE-RUNBOOK.md`** — the planned next step: tracing macOS under the
   m1n1 hypervisor to get ground truth. Trace module:
   `sources/m1n1-thunderbolt/proxyclient/hv/trace_dpin_bringup.py`.
4. Persistent memory (loaded each session): `dpin-failure-analysis.md` in the Claude memory dir —
   condensed history and corrections, so you don't re-derive or repeat overclaims.
5. `NEXT-STEPS.md` — older running log of every experiment (cable tests → DP-IN v1/v2 → USB4 backport
   → DP-IN v3). Useful history; HANDOFF.md supersedes its "what to do next".

Printable step-by-step: `reports/usb4-dpin-v3/M1N1-TRACE-CHECKLIST.md` (do this one; the runbook is the background).

## The current live experiment: DP-IN v3

- **Boot entry:** GRUB → *Omarchy - Asahi 7.1 USB4 DP-IN v3 (manual)*. Kernel `7.1.13-usb4-gpu-test`.
- **Reproduce the best result** (DP tunnel to the monitor; still no picture): see HANDOFF.md
  "Reproduce". In short: `scripts/run-dpin-v3.py` + a one-word `/dev/mem` write via `artifacts/mmio/mmio-rw`.
- **Check for a picture objectively:** `scripts/webcam-snap.sh` grabs a FaceTime-cam frame; Read the
  jpg. Do not claim a picture without one.
- **Restore the plain kernel:** `sudo python3 scripts/stage-usb4-dpin-v3.py restore`. Stock loader
  backup is on the EFI (`boot.bin.before-display-test`); recovery text in `config/USB4-GPU-RECOVERY.txt`.
- **Source:** `sources/linux-usb4-backport`, branch `thunderbolt-7.1.13-dpin-v3`. Patch exported at
  `patches/thunderbolt-dpin-v3-experiment.patch`.

## Source trees on GitHub (the `sources/` dir is gitignored here)

- Kernel: **https://github.com/mertcanekiz/linux** (fork of AsahiLinux/linux). Branches
  `thunderbolt-7.1.13-dpin-v3` (active), `thunderbolt-7.1.13-gpu` (baseline), `thunderbolt-7.1.13-dpalt`.
- m1n1: **https://github.com/mertcanekiz/m1n1** (fork of AsahiLinux/m1n1). Branch `thunderbolt-dpin-trace`
  (adds `proxyclient/hv/trace_dpin_bringup.py`).

To recreate `sources/` from scratch:
```sh
git clone -b thunderbolt-7.1.13-dpin-v3 https://github.com/mertcanekiz/linux sources/linux-usb4-backport
git clone -b thunderbolt-dpin-trace   https://github.com/mertcanekiz/m1n1  sources/m1n1-thunderbolt
```

## Directory map

| Path | What's in it |
| --- | --- |
| `reports/usb4-dpin-v3/` | **The active work.** HANDOFF, REVIEW, trace runbook, per-attempt captures (`attempt*/`), evidence bundle (`evidence-*/`), register dumps, macOS-dump-derived findings. |
| `reports/macos-dump/` | macOS 14.3 ioreg/ADT/kernel-log dump captured with the LG working. **Primary reverse-engineering source.** Re-dump script: `/boot/efi/dump-macos.sh` (also `config/dump-macos.sh`). |
| `reports/` (top level) | Older experiment evidence (cable tests, DP-IN v1/v2, USB4 backport). History. |
| `scripts/` | All helpers (see below). |
| `patches/` | The experiment patches. `thunderbolt-dpin-v3-experiment.patch` is current; `usb4-backport/` holds the USB4 transport backport series. |
| `config/` | GRUB entries, mkinitcpio configs, recovery texts, the macOS dump script. |
| `artifacts/` | Build outputs and tools. `artifacts/mmio/` has `mmio-rw` / `mmio-dump` (`/dev/mem` register tools) + their C source. `.gitignore`d, large. |
| `sources/` | Kernel + m1n1 trees (see below). `.gitignore`d, large. |
| `snapshots/` | Verified boot/firmware backups. |
| `packaging/` | Distro packaging bits. |

### `sources/` trees
| Tree | Role |
| --- | --- |
| `linux-usb4-backport` | **Active kernel.** Stock Asahi 7.1.13 + USB4 transport backport + DP-IN v3 changes (branch `thunderbolt-7.1.13-dpin-v3`). |
| `m1n1-thunderbolt` | m1n1 fork with the USB4 device tree + the hypervisor trace tooling (`proxyclient/hv/`, incl. our `trace_dpin_bringup.py`). |
| `linux-thunderbolt` | The 7.2 Asahi WIP tree the DP-IN prototype was first developed against. |
| `linux` | Asahi `fairydust` reference tree (DP-alt work). |
| `linux-dpalt` | dpin-v3 + fairydust DP-alt port (branch `thunderbolt-7.1.13-dpalt`), see `reports/dp-altmode/`. |
| `asahi-alarm-pkgbuilds`, `community-reference` | Packaging + community references. |

## Key scripts

| Script | Purpose |
| --- | --- |
| `scripts/run-dpin-v3.py` | Drive the DP-IN v3 experiment: `status` / `connect OUTDIR [--dpin N ...]` / `disconnect` / `retunnel`. |
| `scripts/stage-usb4-dpin-v3.py` | `install` / `restore` the whole v3 boot target. |
| `scripts/build-usb4-dpin-v3.sh`, `...-initramfs.sh` | Rebuild the v3 modules / initramfs. |
| `scripts/webcam-snap.sh` | Objective picture check via the FaceTime camera. |
| `scripts/collect-tunnel-registers.py` | Decode Thunderbolt DP adapter registers. |
| `scripts/verify-usb4-gpu-boot.py` | Read-only boot verification for the USB4+GPU baseline. |
| `artifacts/mmio/mmio-rw`, `mmio-dump` | Raw `/dev/mem` register read/write/poll (the DP-IN bridge hack lives here). |

Older scripts (`*-thunderbolt-*`, `*-dpin-test*`, `*-display-*`, cable/trace helpers) belong to the
superseded v1/v2 and cable experiments; keep for history, prefer the v3 equivalents above.

## Ground rules for the next agent

- The device is dual-boot with macOS; never break the stock boot path. Every experiment installs a
  **separate** kernel/initramfs/GRUB entry and keeps a verified loader backup on the EFI partition.
- Register pokes so far are single-word `/dev/mem` writes, non-persistent (a reboot clears them).
- Do not claim a working picture, main-link lock, or a proven root cause without the evidence to back
  it — see REVIEW.md for what each signal actually proves. When in doubt, take a webcam frame.
