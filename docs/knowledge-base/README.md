# Knowledge base: LG UltraFine (DP over Thunderbolt) on the M1 MacBook Air

Purpose: everything needed to **re-implement the DP-IN bring-up yourself**, from the hardware
chain down to every register write, with the reasoning behind each step and the evidence it rests
on. It is written for a rewrite, not for copying: the walkthrough marks what is a hack, what is
guessed, and what a clean implementation should look like.

Provenance note: the kernel patches here and most of the analysis were produced with an LLM
(Claude) driving the experiments; the hypervisor traces, register dumps and photos are raw data
produced by m1n1 and by the hardware. Asahi Linux's Generative AI policy forbids LLM-produced
material contributions, so treat these documents as private study notes and the patches as a
reference implementation to learn from, not as something to send anywhere.

| file | what |
|---|---|
| `01-architecture.md` | The hardware chain from dcpext to the LG, the firmware protocol, why DP alt mode is not an option |
| `02-macos-sequence.md` | The exact macOS 13.5 bring-up captured with the m1n1 hypervisor: every register write, every DCP call and reply, PLL value decode |
| `03-linux-walkthrough.md` | Hunk-by-hunk walkthrough of the cumulative diff (v3+v4+v5), grouped by subsystem, with rationale, evidence and "hack or keep" verdicts |
| `04-drm-and-hotplug.md` | What the compositor does on connect/reconnect, why a modeset must be forced, the Thunderbolt-tunnel-driven hotplug design |
| `05-rewrite-plan.md` | A step-by-step order to rebuild it from scratch, each step with a concrete test, plus the shape of an upstream-quality design |
| `06-evidence-index.md` | Where every trace, dump, log and photo lives; the dead ends already ruled out |
| `07-glossary.md` | Terms and register names |
| `dpin-cumulative-v3-v5.diff` | The complete diff of the working state against the USB4-transport base (`5f7d34c83`), 12 files |
| `01-v3-experiment.patch`, `02-v4-macos-sequence.patch`, `03-v5-auto-hotplug.patch` | The three WIP commits as `git format-patch` output |

Suggested reading order: 01 → 02 → 04 → 03 → 05. Keep `02-macos-sequence.md` open while reading
the walkthrough; almost every line of the diff maps to a line of the trace.

Kernel base the diff applies to: `sources/linux-usb4-backport` branch `thunderbolt-7.1.13-gpu`
tip `5f7d34c83`, which is Asahi `asahi-7.1.13-3` (`94fb23346`) plus Sven Peter's Apple USB4
transport work (`thunderbolt: Add Apple Silicon support` and friends, ~35 commits: NHI driver,
ACIO/CIO reset, tipd Thunderbolt switch, PHY USB4 pipehandler). That transport layer is not part
of this work and is not covered here beyond what the DP-IN path needs from it.
