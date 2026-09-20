# PRINTABLE CHECKLIST — trace macOS lighting the LG with the m1n1 hypervisor

Two machines: **TARGET** = this M1 MacBook Air (dual-boots Omarchy Linux / macOS 14.3).
**HOST** = your other Mac. One USB-C cable between them. The LG on its Thunderbolt cable.

Core idea (read once): the TARGET does **not** boot normal macOS for the trace. It boots into
**m1n1 in proxy mode** (a small loader that just waits on USB). The HOST then tells m1n1 to boot
macOS *as a guest under m1n1's hypervisor*, with our tracers watching the display registers. macOS
runs normally on the TARGET's screen; every register write to the DP-IN bridge / crossbar / DCP is
logged on the HOST.

Ports on the TARGET (important, the hypervisor hides the tether port from macOS):
- **Left-BACK USB-C  = tether cable to the HOST.**
- **Left-FRONT USB-C = the LG (Thunderbolt cable).** The LG also powers the laptop.

--------------------------------------------------------------------------------------------------
## PART A — one-time prep (do these in any order, ~30 min)

### A1. On the TARGET, get the macOS kernelcache file (boot into macOS once for this)
- [ ] Boot the TARGET into macOS (hold power → Macintosh HD).
- [ ] Open Terminal:
      ```
      ls /System/Volumes/Preboot/*/boot/*/System/Library/Caches/com.apple.kernelcaches/kernelcache
      ```
      That prints one path. Copy that file to the HOST (AirDrop is easiest; it is ~30–60 MB).
      If AirDrop complains, `cp <that path> ~/Desktop/kernelcache` first, then AirDrop.
- [ ] Shut the TARGET down when done (full shutdown, not restart).

### A2. On the HOST (other Mac): tools + the m1n1 proxyclient
- [ ] `python3 -m pip install --user pyserial construct`
- [ ] Get our m1n1 fork (has the trace module already):
      ```
      git clone -b thunderbolt-dpin-trace https://github.com/mertcanekiz/m1n1 ~/m1n1
      ```
- [ ] Install img4tool (to unwrap the kernelcache):
      ```
      brew tap aderuelle/homebrew-tap && brew install img4tool
      ```
      (If that tap fails: `python3 -m pip install pyimg4` and use the pyimg4 line in A3.)

### A3. On the HOST: turn the kernelcache into a Mach-O
- [ ] With img4tool:
      ```
      img4tool -ep out.im4p ~/Downloads/kernelcache
      img4tool -eo ~/kernelcache.macho out.im4p
      ```
      or with pyimg4:
      ```
      pyimg4 im4p extract -i ~/Downloads/kernelcache -o ~/kernelcache.macho
      ```
- [ ] `ls -la ~/kernelcache.macho` — should be tens of MB.

### A4. On the TARGET (Linux): the proxy-mode loader is ALREADY STAGED
Already done by the last session, nothing to do now — for reference:
- `/boot/efi/m1n1/boot.bin.hvproxy`        = bare m1n1 (no payload → drops into proxy mode)
- `/boot/efi/m1n1/boot.bin.before-hvproxy` = backup of the current Linux loader
Why this works: Asahi's stage-1 m1n1 (in the Linux stub) chainloads `m1n1/boot.bin` from the EFI.
A bare m1n1 finds no payload and prints "No valid payload found" → proxy mode. macOS is untouched.

--------------------------------------------------------------------------------------------------
## PART B — the trace session (each time)

### B1. TARGET: switch the loader to proxy mode  (Linux WON'T boot until B6 restores it)
- [ ] Boot the TARGET into Linux (any entry), open a terminal:
      ```
      sudo cp /boot/efi/m1n1/boot.bin.hvproxy /boot/efi/m1n1/boot.bin && sudo sync
      ```
- [ ] Shut down fully.

### B2. Cable up
- [ ] USB-C cable: TARGET **left-back** port ↔ HOST.
- [ ] LG Thunderbolt cable: TARGET **left-front** port. (Or plug the LG in later at B5 — better for
      catching the whole bring-up live.)

### B3. TARGET: boot into m1n1 proxy mode
- [ ] Press+hold power until "Loading startup options…", choose the **Omarchy / Asahi Linux** volume,
      Continue.
- [ ] Screen should show the m1n1 boot text ending in something like "No valid payload found" /
      "Proxy mode" and then wait. That's correct — it is waiting for the HOST.

### B4. HOST: start the hypervisor with our tracers
- [ ] Find the serial device: `ls /dev/cu.usbmodem*`  (m1n1's default name is `/dev/cu.usbmodemP_01`)
- [ ] Run (one command):
      ```
      cd ~/m1n1/proxyclient
      export M1N1DEVICE=/dev/cu.usbmodemP_01        # ← use the name you saw
      export TRACE_DCP=dcpext                        # trace the EXTERNAL display controller
      python3 tools/run_guest.py \
          -m hv/trace_dcp.py \
          -m hv/trace_atc.py \
          -m hv/trace_dpin_bringup.py \
          -l ~/dpin-trace.log \
          ~/kernelcache.macho \
          -- "debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam wdt=-1 clpc=0"
      ```
- [ ] Wait. macOS boots on the TARGET's screen under the hypervisor (slower than normal; SYNC
      tracing costs speed — that is expected). The HOST terminal streams trace lines.
- [ ] Optional, only if run_guest complains about ABI/version: first run
      `python3 tools/chainload.py <path to m1n1.macho>` (copy `build/m1n1.macho` from the TARGET's
      `sources/m1n1-thunderbolt/build/` via AirDrop), then rerun the command above.

### B5. Trigger the bring-up while tracing
- [ ] Once macOS is at the desktop/login: **plug the LG into the left-front port** (or unplug/replug
      it if already connected).
- [ ] Watch the LG. Note the wall-clock moment it lights.
- [ ] Watch `~/dpin-trace.log` grow. Let it run ~30 s after the LG lights, then Ctrl-C run_guest.
- [ ] Keep the log. Also note in a text file: did the panel light? roughly when relative to the
      trace? (This ordering is the whole point — see "what to look for".)

### B6. TARGET: restore the Linux loader (don't skip)
- [ ] Power off the TARGET. Boot Linux? It can't yet — restore from **macOS** or from Linux:
  - From macOS (hold power → Macintosh HD → Terminal):
        ```
        diskutil mount "EFI - OMARC"
        cp "/Volumes/EFI - OMARC/m1n1/boot.bin.before-hvproxy" "/Volumes/EFI - OMARC/m1n1/boot.bin"
        diskutil unmount "EFI - OMARC"
        ```
  - Or, if you kept a Linux boot: `sudo cp /boot/efi/m1n1/boot.bin.before-hvproxy /boot/efi/m1n1/boot.bin && sudo sync`
- [ ] Reboot → Linux boots normally again.

### B7. Bring the log home
- [ ] AirDrop `~/dpin-trace.log` to the TARGET (or keep on HOST) and drop it in
      `reports/usb4-dpin-v3/` of the project repo. Tell the next session "the trace is in".

--------------------------------------------------------------------------------------------------
## What to look for in the log (the two questions this answers)

1. **Did the panel light BEFORE any USB / "Display Controls" HID traffic?**
   - Yes → the video path is the whole story; Linux is missing DP-side register writes. Small fix.
   - No, only after USB traffic → backlight/scaler is USB-gated; the PCIe/USB tunnel path is
     mandatory. Big job (likely rebase onto Sven Peter's upstream Thunderbolt series).
2. **The exact `atc1-dpin0` (0x501e50000) and `atc1-dpxbar` (0x50304c000) write sequence** around
   the DCP `activate` / `set_link_rate` calls — especially `bringConnectionUp`. That is the recipe to
   fold into the Linux driver.

--------------------------------------------------------------------------------------------------
## If something goes wrong

- **No `/dev/cu.usbmodem*` on the HOST:** the TARGET isn't in proxy mode, or the cable is on the wrong
  port / not data-capable. Re-check B1/B3; try the other cable.
- **`M1N1DEVICE` opens but run_guest hangs at the start:** the wrong volume was chosen at B3 (it must
  be the Asahi/Omarchy stub, not Macintosh HD).
- **macOS guest boots but the display stack fails / no LG:** possible firmware mismatch — the Linux
  stub carries firmware 13.5 while macOS is 14.3 (`asahi,os-fw-version = 13.5`). Fallback: obtain a
  macOS 13.5 kernelcache (13.5 InstallAssistant from Apple/archive.org, extract the same way) and use
  that as the guest. Upstream lists 13.5 as a supported guest.
- **Everything's too slow:** edit `~/m1n1/proxyclient/hv/trace_dpin_bringup.py` and change
  `TraceMode.SYNC` → `TraceMode.ASYNC`, rerun B4.
- **Panic / stuck:** hold power to reset the TARGET, redo B3+B4. Nothing persistent changed except
  `boot.bin`, which B6 restores. macOS is never modified.
- **Want Linux back without doing the trace:** do B6.

Upstream references (the base procedure is theirs; this checklist only adds our specifics):
asahilinux.org → docs → "Running macOS under the m1n1 hypervisor" and "Tethered boot".
