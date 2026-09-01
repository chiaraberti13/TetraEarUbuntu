<p align="center"><img src="../assets/banner.svg" alt="TetraEar" width="100%"></p>

<p align="center"><a href="manual.en.md">🇬🇧 English</a> · <a href="manual.it.md">🇮🇹 Italiano</a></p>

<p align="center"><a href="../README.md">Project overview</a> · <a href="../SECURITY.md">Security</a> · <a href="../LICENSE">Licence</a></p>

---

## 🇬🇧 English

### Overview

**TetraEar** is a TETRA (Terrestrial Trunked Radio) decoder for RTL-SDR
dongles (RTL2832U chip). This repository provides **fully automated
installers** that, from a single command, set up everything TetraEar needs:
system packages, the Python environment, the ETSI voice codec, and the
RTL-SDR configuration.

You don't need to clone TetraEar yourself — the installer downloads its
source code automatically.

> ⚠️ **Read the [legal disclaimer](DISCLAIMER.md) before using this
> software.** TetraEar is for educational and research purposes only, and
> only where permitted by the laws of your jurisdiction.

### What the installers do

1. Check Python and the operating system.
2. Install system dependencies (compiler, RTL-SDR libraries, Qt, audio).
3. Download the TetraEar source code.
4. Create a Python virtual environment (`.venv`) and install the `pip` packages.
5. Configure the RTL-SDR dongle (on Linux, automatically).
6. Download and compile the ETSI TETRA voice codec.
7. Verify that everything is in place.

Everything that happens is recorded in **`logs/install.log`** (all logs,
including the app's, live in the `logs/` folder) — attach that file if you
ever need support.

### Requirements

- An internet connection.
- An **RTL-SDR** dongle (RTL2832U chip) with an antenna — needed only when
  you *use* TetraEar, not to install it.
- Administrator rights (Linux asks for your `sudo` password; on Windows the
  window elevates itself).

---

### 🐧 Ubuntu / Debian

Tested on **Ubuntu 24.04** and **Debian 12** (should also work on recent
derivatives such as Linux Mint and Pop!_OS).

**1. Install**

```bash
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
python3 install_linux.py
```

You'll be asked for your `sudo` password (to install system packages). The
process takes a few minutes. When it finishes, the installer will have
created a `TetraEar/` folder next to itself, containing the source code, the
`.venv` environment and the compiled codec.

**2. The RTL-SDR dongle is configured automatically**

On Linux nothing is done by hand: the installer blacklists the DVB-T kernel
drivers that would otherwise grab the dongle, installs/reloads the udev
rules, and adds your user to the `plugdev` group.

> ⚠️ **Required final step:** after installation, **unplug and re-plug** the
> dongle (or reboot) so the driver blacklist and udev rules take effect.
> Then check it with:
>
> ```bash
> rtl_test -t
> ```
>
> If it shows "Found 1 device(s)" you're good. `usb_claim_interface error -6`
> means the DVB-T driver is still loaded → re-plug or reboot.

**3. Run TetraEar**

```bash
cd TetraEar
source .venv/bin/activate
python -m tetraear -f 392.225          # GUI
# or, headless:
python -m tetraear --no-gui -f 392.225 --auto-start
```

(replace `392.225` with the frequency in MHz you want).

**Without a terminal:** the installer also creates a **TetraEar** entry in
your applications menu and a **`TetraEar.desktop`** icon on the Desktop —
double-click to launch, no terminal needed. The icon starts capture
automatically with verbose logging, so it writes the same
`TetraEar/logs/` files (plus a `console_*.log`) as the command line — handy
if voice doesn't decode and you need to send the logs.

**Restart the app (after logout or reboot)** — just three lines:

```bash
cd ~/TetraEarUbuntu/TetraEar
source .venv/bin/activate
python -m tetraear -f 392.225
```

To launch it with a single word, create an alias once:

```bash
echo "alias tetraear='cd ~/TetraEarUbuntu/TetraEar && source .venv/bin/activate && python -m tetraear -f 392.225'" >> ~/.bashrc && source ~/.bashrc
```

Then just type `tetraear`. There is also a helper script — from the
`TetraEarUbuntu` folder run `./avvia_tetraear.sh 392.225`.

**Voice decoding & logs.** On every run the app writes detailed logs to
`TetraEar/logs/`: `codec_<id>.log`, `decoder_<id>.log`, `audio_<id>.log`,
`tetraear_<id>.log`. Run with `-v --auto-start` (add `-m` to hear the
audio) to exercise decoding, then send those files if voice doesn't come
through — the `avvia_tetraear.sh` script does exactly this.

> ℹ️ **Why voice may not decode.** Most professional TETRA networks
> **encrypt** their voice (TEA1–4): encrypted calls cannot be decoded
> without the keys and appear as 🔐 in the frames table. You also need to
> be tuned to a frequency carrying an actual **unencrypted** voice call,
> with enough gain/signal. If the frames arrive but audio is silent, check
> `codec_<id>.log` — a working codec logs `cdecoder exited 0` / `sdecoder
> exited 0`.
>
> **Status says "Signal Detected (Decoding…)" but the frames table is
> empty?** It's usually the table filters: set **Filter** to **All** and
> **uncheck "Decrypted/Text Only"** — otherwise only already-decrypted
> audio/text rows are shown. If frames then appear all marked 🔐, the
> traffic is encrypted and the lock counter (e.g. `0/0` = no keys loaded)
> confirms you have no keys, so voice can't be recovered. Also note a
> continuous carrier is often a **control channel** (signalling): voice
> only appears during an actual call.

**4. Useful commands**

| Command | What it does |
| --- | --- |
| `python3 install_linux.py` | Full installation |
| `python3 install_linux.py --repair` | Recompile only the voice codec + re-apply fixes |
| `python3 install_linux.py --uninstall` | Remove `.venv` and the codec (keeps the source) |
| `python3 install_linux.py --check` | Verify the installation (venv, codec, pyrtlsdr) without changing anything |
| `python3 install_linux.py --ref <commit\|tag\|branch>` | Install a specific TetraEar version |

> ℹ️ **Reproducible installs.** The installer pins TetraEar to a known,
> tested release (currently `v2.3`) instead of always pulling the latest
> `master`, so an upstream change can't silently break the patches it
> applies. The exact installed commit is recorded in
> `TetraEar/.tetraear_version`. To install a different version, use `--ref`
> (or set the `TETRAEAR_REF` environment variable). The ETSI voice codec is
> downloaded from ETSI with an automatic archive.org fallback if the ETSI
> site is unreachable; the download is always MD5-verified.

**5. Troubleshooting (Linux)**

- **`Could not get lock /var/lib/dpkg/lock-frontend` (held by
  `unattended-upgr`)**: Ubuntu's automatic updates run right after boot and
  hold the package lock. The installer now waits for it automatically; if it
  ever gives up, wait 2–3 minutes for the updates to finish and re-run
  `python3 install_linux.py`.
- **`dpkg was interrupted, you must manually run 'sudo dpkg --configure -a'`**:
  a previous package operation was left half-finished (an interrupted update,
  a forced shutdown…), so `apt` refuses to continue. The installer now detects
  this and runs `sudo dpkg --configure -a` for you automatically, then retries.
  If the automatic repair itself fails, run `sudo dpkg --configure -a` by hand,
  read the errors it prints, then re-run `python3 install_linux.py`.
- **GUI won't start, "could not load the Qt platform plugin xcb"**: the
  installer already installs the required Qt libraries; make sure you are in
  a graphical session (not headless SSH).
- **Dongle not detected / `usb_claim_interface error -6`**: the DVB-T driver
  is still loaded. Unplug/re-plug the dongle (or reboot), then `rtl_test -t`.
- **`rtl_test` works only with sudo**: log out and back in once (to activate
  the `plugdev` group membership).
- **On start: `undefined symbol: rtlsdr_set_dithering` (or similar)**: an
  incompatibility between `pyrtlsdr` and Ubuntu's `librtlsdr` (which lacks
  some functions found only in the *keenerd* fork). The installer patches
  `pyrtlsdr` to tolerate the missing symbols; if you updated the script,
  re-run `python3 install_linux.py` (or `--repair`). This is **not** related
  to whether a dongle is connected — it happens at import time.
- **ETSI codec download fails**: try again later (the ETSI site is sometimes
  unreachable), then `python3 install_linux.py --repair`.
- **Nothing decodes, `decoder.log`/`app.log` full of `Decode error:
  'CaptureThread' object has no attribute 'signal_processor'`**: a bug in the
  upstream TetraEar source (a wrong attribute name in the capture thread).
  The installer patches it automatically; if you updated the script, re-run
  `python3 install_linux.py` (or `--repair`).
- **Voice is choppy / decodes only in part on a slow machine**: each voice
  frame runs the ETSI codec as an external process. On a loaded or "cold"
  system (e.g. the first calls, while the antivirus scans the freshly compiled
  codec) that can exceed the codec's per-frame timeout, so otherwise-decodable
  frames get dropped. The installer raises the default timeout from 5 s to
  15 s; you can tune it with the `TETRAEAR_CODEC_TIMEOUT` environment variable
  (in seconds). Re-run `python3 install_linux.py` (or `--repair`) to apply the
  patch. This depends on the upstream project and your signal, not on the
  installer.

---

### 📡 Additional decoders (DMR, P25, ADS-B, pagers) — Linux

TetraEar decodes TETRA. An RTL-SDR dongle can receive many other modes too —
the same ones closed programs like OpenEar covered, but here with **open
source** tools:

| Tool | Decodes |
| --- | --- |
| **multimon-ng** | POCSAG / FLEX pagers and other FSK/AFSK modes |
| **dump1090** | ADS-B 1090 MHz (aircraft positions, web map) |
| **dsd-fme** | DMR / P25 / NXDN / dPMR (**unencrypted** digital voice) |

**These are installed automatically** at the end of `python3 install_linux.py`
(logs in `logs/install_extra.log`, each decoder independent). Pass `--no-extra`
to skip them, or run the companion script on its own later:

```bash
python3 install_extra_decoders.py                 # (re)install all three
python3 install_extra_decoders.py --only dump1090 # just one (or a subset)
python3 install_extra_decoders.py --check         # see what's installed
```

After install, typical usage (needs the dongle plugged in):

```bash
# Pagers (POCSAG), e.g. 439.9875 MHz
rtl_fm -f 439.9875M -s 22050 -g 42 - | \
  multimon-ng -t raw -a POCSAG1200 -f alpha /dev/stdin
# Aircraft (ADS-B), web map on http://localhost:8080
dump1090 --interactive --net
# DMR/P25 clear voice, e.g. 446.09375 MHz
rtl_fm -f 446.09375M -s 48000 -g 42 - | dsd-fme -i - -o /dev/null
```

> ℹ️ As always: you'll only see traffic if you're on the right frequency with
> enough signal, and **encrypted** voice/data can't be decoded without the
> keys — by any software. Use only where permitted by law (see
> [DISCLAIMER](DISCLAIMER.md)).

📖 Full step-by-step usage (frequencies, commands, Windows notes) is in the
sections below. On Windows use `install_extra_decoders_windows.py`.

---

### 🔓 Known-key voice decryption — TELIVE-2 (Linux & Windows via WSL)

TetraEar decodes **clear** TETRA voice. If you already *own* the encryption
key, the **TELIVE-2** chain (osmo-tetra-sq5bpf-2 + the ETSI codec + telive)
by Jacek Lipkowski (SQ5BPF) can also **decrypt** voice — including the
**32-bit shortened TEA-1 key** (the backdoor documented by Team Midnight Blue
in 2023).

> ✅ **This runs automatically** at the end of `install_linux.py` — you don't
> need a separate step. Pass `--no-telive2` to the main installer to skip it.
> The build is heavy (GNU Radio, `libosmocore`, the ETSI codec), so it adds a
> few minutes.

You can also run (or re-run) the complementary installer on its own:

```bash
python3 install_telive2.py            # build & wire up the whole chain
python3 install_telive2.py --check    # just report what's present
python3 install_telive2.py --no-gnuradio   # skip GNU Radio (already installed)
```

Prefer a plain shell script? `install_telive2.sh` does the same, standalone
(run it as a normal user, **not** with sudo). It is portable across
**Ubuntu 24.04 (x86)** and **25.10 (ARM64)** — it auto-detects the compiler
flags needed to build the older SQ5BPF C sources on GCC 15:

```bash
bash install_telive2.sh
```

It clones and builds `osmo-tetra-sq5bpf-2` (the `tetra-rx` receiver with the
**real** TEA1/2/3 crypto and the `-k keyfile` flag), downloads and patches the
**ETSI voice codec** (`cdecoder`/`sdecoder`, with the same browser-User-Agent
trick used by `install_linux.py` so the ETSI `403 Forbidden` never bites),
builds `telive`, and sets up the `/tetra` working folder plus the bundled GNU
Radio flowgraph. Usage (receiver → telive → play) is printed at the end.

**Providing the known key** — pass a keyfile to the receiver
(`./tetra-rx -r -k <keyfile> -s`; `receiver1udp` already does). One line per
key, e.g.:

```
network mcc 0123 mnc 1337 ksg_type 1 security_class 2
key mcc 0123 mnc 1337 addr 00000000 key_type 1  key_num 0 key 11111111111111111111
# 32-bit shortened TEA-1 key (pad to 80 bits): key_type 16
key mcc 0123 mnc 1337 addr 00000000 key_type 16 key_num 0 key 12345678000000000000
```

> ℹ️ **Why not TetraEar's own key loader?** TetraEar's GUI *does* have a
> "🔑 Load Keys" button and a key-file loader, but its `core/crypto.py`
> TEA1–4 are **simplified placeholder** implementations (its own docstrings
> note the real algorithms are proprietary), so a real key won't correctly
> decrypt real traffic there. The **working** known-key path is TELIVE-2's
> `tetra-rx -k`.

> ⚠️ **Decryption ≠ cracking.** These tools only decrypt when the key is
> **already known** — none of them recovers a key. Use only where permitted
> by law (see [DISCLAIMER](DISCLAIMER.md)).

**On Windows** the TELIVE-2 chain runs through **WSL2** (Ubuntu inside
Windows), because it is deeply POSIX (`libosmocore`, GNU Radio, shell scripts,
the fixed `/tetra` folder) and has no reliable native Windows build. The
companion installer detects WSL and runs the *same* Linux installer inside it:

```bat
python install_telive2_windows.py              REM detects WSL and builds inside Ubuntu
python install_telive2_windows.py --check      REM just report WSL / build status
python install_telive2_windows.py --guide-only REM print the WSL setup steps only
```

If WSL isn't enabled yet, it prints the one-time setup (`wsl --install -d
Ubuntu`, reboot, create a user) and then you re-run it. GNU Radio's GUI shows
up automatically via WSLg on Windows 11 (on Windows 10 you need an X server).

---

### 📶 TETRA Network Scanner — passive network-info panel

Inspired by the *"Interception of TETRA radio"* write-up, whose SDR# plugin's
distinctive feature is a **passive panel of the network's broadcast metadata**.
TetraEar decodes voice/text frames but shows **none** of those fields; this
companion tool adds them by reading the output of the TELIVE-2 receiver
(`tetra-rx`, built by `install_telive2.py`).

It displays, live: **MCC / MNC / MNI**, **Location Area**, **Colour Code**,
operating mode, **main carrier** (+ neighbour cells seen), the **🔓/🔐 Air
Interface Encryption (AIE)** status, **Security Class**, **Cipher Key ID / TEA
type**, the **authentication-required-on-cell** flag, plus an **antenna-length
calculator** (the ANT-500 tip from the article). It reuses the same `KEY:VALUE` tokens (`MCC:`, `MNC:`, `LA:`,
`CCODE:`, `CRYPT:`, `ENC:`…) that `telive` itself parses, so it stays robust.

**Two ways to see it:**

- **Inside the TetraEar GUI** — the main installer (`install_linux.py` /
  `install_windows.py`) adds a whole set of tabs to the TetraEar window, next to
  *Decoded Frames · Calls · … · Statistics*:
  - **📶 Network Info** — the passive metadata panel (MCC/MNC/LA/Colour Code/AIE/
    Security Class/…); pick a source (default: the receiver log), press **▶ Avvia**.
  - **🔓 Decrypt (TELIVE-2)** — chain status, a keyfile editor (incl. the TEA-1
    32-bit key), and buttons to launch GNU Radio → receiver → telive and open the
    decrypted-voice folder. Known-key only, no cracking.
  - **📡 Decoders** — launch multimon-ng (POCSAG), dump1090 (ADS-B + web map) and
    dsd-fme (DMR/P25) with the documented frequencies.
  - **📻 Antenna/Freq** — antenna-length calculator + a TETRA band plan whose
    presets **tune TetraEar** with one click.
  - **📚 Reference** — TETRA vs TETRA2, the TEA/TAA suites, the five TETRA:BURST
    CVEs and all the source links.

  Toolkit actions (tuning, launching a chain/decoder) also show up in the app's
  top **Status** panel (a "🧰 Toolkit" line). Already installed? Get the tabs by
  re-running `python3 install_linux.py --repair` (Windows: re-run the installer).
  Each tab is wrapped in a `try/except`, so it can never prevent the app from
  starting.
- **As the standalone tool** (`tetra_netscanner.py` / `avvia_netscanner.sh`),
  documented below — it is the shared engine the GUI tab reuses.

> ⚠️ **One RTL-SDR at a time.** The tab's *live* data comes from the TELIVE-2
> receiver, which needs the dongle — so it can't run at the same instant as
> TetraEar's own capture on a single dongle. The default *Log file* source
> (tail `logs/receiver.log`) is what makes them coexist: run the TELIVE-2 chain
> (or use a second dongle) and watch the tab.

> ✅ It is **prepared automatically** at the end of `install_telive2.py` (skip
> with `--no-netscanner`). You can also wire it up on its own — nothing heavy is
> compiled, it's pure Python:
>
> ```bash
> python3 install_tetra_netscanner.py            # verify + create the launcher
> python3 install_tetra_netscanner.py --check    # just report what's present
> ```

Usage:

```bash
# Auto: follows logs/receiver.log if present (coexists with telive), else runs the receiver
./avvia_netscanner.sh 392.225
# Drive the receiver directly:
python3 tetra_netscanner.py --run -f 392.225
# Coexist with a running telive session (tail its receiver log):
python3 tetra_netscanner.py --attach-file logs/receiver.log --follow
# No hardware needed:
python3 tetra_netscanner.py --antenna 392.225     # antenna-length calculator
python3 tetra_netscanner.py --self-test           # exercise the parser
```

**On Windows** the *live* panel runs under **WSL2**, exactly like the TELIVE-2
chain: `install_telive2_windows.py` builds `tetra-rx` inside WSL and wires the
scanner there automatically. It also drops a native **`Avvia NetScanner.bat`**
on the Windows host (double-click, or pass a frequency) that launches the live
panel through WSL, or shows the antenna calculator offline if WSL isn't present.
The no-hardware features run on native Windows Python too:

```bat
python install_tetra_netscanner_windows.py        REM verify + create the .bat launcher
python tetra_netscanner.py --antenna 392.225       REM antenna calculator (no hardware)
python tetra_netscanner.py --self-test             REM exercise the parser
```

> ⚠️ **Passive & read-only.** The scanner only *displays* broadcast metadata and
> whether encryption is on — it performs **no decryption and no key recovery**
> (known-key decryption remains TELIVE-2's job). It shows real values only where
> the receiver actually decodes them, on a channel with enough signal. Use only
> where permitted by law (see [DISCLAIMER](DISCLAIMER.md)).

---

### 🪟 Windows

Tested on **Windows 10** and **Windows 11** (64-bit).

> ✅ **By default, TetraEar now installs and runs inside WSL2** (Ubuntu on
> Windows), exactly like the TELIVE-2 chain. This way the **whole suite — the
> app, all five GUI tabs, TELIVE-2 and the extra decoders — runs in one Linux
> environment and works just like on Ubuntu**; the Qt window appears via WSLg
> (Windows 11) or an X server (Windows 10). `install_windows.bat` detects WSL,
> runs `install_linux.py` inside it, and drops an **`Avvia TetraEar (WSL).vbs`**
> launcher on your Desktop.
>
> - If WSL isn't set up yet, the installer prints the one-time steps
>   (`wsl --install -d Ubuntu`, reboot) and you re-run it.
> - To use the **RTL-SDR dongle inside WSL** you attach it once per session with
>   **usbipd-win** (`winget install usbipd`, then `usbipd bind/attach --wsl`) —
>   the installer prints the exact commands. No-hardware features (antenna,
>   Reference, keyfile editor) work without it.
> - Prefer the **old native Windows build**? Run `install_windows.bat --native`
>   (note: in native mode the Decrypt/Decoders tabs may not see the WSL tools).

**1. Get the installers**

With **Git for Windows** the simplest way is to clone the repository
(Command Prompt or PowerShell):

```bat
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
```

Without Git: open
<https://github.com/chiaraberti13/TetraEarUbuntu>, click **Code → Download
ZIP**, extract it and open the folder. Either way you need
`install_windows.bat` and `install_windows.py` in the same folder.

**2. Install**

**Double-click `install_windows.bat`.**

- Windows asks to **allow changes** (administrator rights): accept.
- If Python isn't installed, the installer installs it via `winget`. When it
  tells you to, **close the window and double-click `install_windows.bat`
  again** — the second run finds Python in the PATH and continues.
- The `.bat` then runs `install_windows.py`, which installs **Git** and
  **MSYS2** (the C compiler needed for the codec), downloads TetraEar,
  creates the environment, installs the Python packages and compiles the
  codec.
- At the end it also sets up the **additional decoders** automatically
  (`install_extra_decoders_windows.py`): it downloads the official **dsd-fme**
  Windows build and prints guided steps for **dump1090** and **multimon-ng**
  (which have no single official Windows binary). Pass `--no-extra` to skip.
  All logs go to `logs/`.

**3. RTL-SDR on Windows (a one-time step)**

`rtlsdr.dll` (plus `libusb`) is **installed automatically** by the installer —
you no longer need to download it by hand. Only the driver is manual, **once**:

- **WinUSB driver with Zadig** — download [Zadig](https://zadig.akeo.ie/),
  plug in the dongle, then *Options → List All Devices*, select
  **"Bulk-In, Interface (Interface 0)"** (or "RTL2832U"), choose the
  **WinUSB** driver and press *Replace Driver*.

**4. Run TetraEar**

**Without a terminal:** double-click **`Avvia TetraEar.vbs`** — the installer
creates it inside the `TetraEar` folder and copies it to your **Desktop**. It
launches the app with no console window.

Or from the **Command Prompt**, in the `TetraEar` folder created by the
installer:

```bat
cd TetraEar
.venv\Scripts\activate
python -m tetraear -f 392.225
```

**5. Useful commands**

| Command | What it does |
| --- | --- |
| double-click `install_windows.bat` | Full installation |
| `python install_windows.py --repair` | Recompile only the voice codec + re-apply fixes |
| `python install_windows.py --uninstall` | Remove `.venv` and the codec (keeps the source) |
| `python install_windows.py --check` | Verify the installation (venv, codec, rtlsdr.dll) without changing anything |
| `python install_windows.py --ref <commit\|tag\|branch>` | Install a specific TetraEar version |

> ℹ️ **Reproducible installs.** Same as Linux: TetraEar is pinned to a known,
> tested release (currently `v2.3`), the installed commit is recorded in
> `TetraEar\.tetraear_version`, and the ETSI codec download has an
> archive.org fallback and is MD5-verified. Use `--ref` or the `TETRAEAR_REF`
> environment variable to install a different version.

**6. Troubleshooting (Windows)**

- **"winget not available"**: update *App Installer* from the Microsoft
  Store, or install Python, Git and MSYS2 by hand and re-run
  `install_windows.py`.
- **MSYS2 installed but not found**: reboot and re-run the installer.
- **Codec won't compile**: run `python install_windows.py --repair`; if it
  persists, check `logs/install.log`.
- **On start: `undefined symbol: rtlsdr_set_dithering`**: same fix as Linux —
  the installer patches `pyrtlsdr`. Re-run the installer (or `--repair`).
- **Nothing decodes, logs full of `'CaptureThread' object has no attribute
  'signal_processor'`**: same upstream bug as Linux — the installer patches
  the TetraEar source automatically. Re-run the installer (or `--repair`).
- **A black window flashes open on every decode**: the no-console launcher
  (`pythonw`) makes each per-frame codec call (`cdecoder.exe`/`sdecoder.exe`)
  spawn a visible console window. The installer now patches `voice.py` to run
  the codec hidden (`CREATE_NO_WINDOW`). Re-run the installer (or
  `python install_windows.py --repair`) to apply it.
- **Voice is choppy / decodes only in part on a slow machine**: each voice
  frame runs the ETSI codec (`cdecoder.exe`/`sdecoder.exe`) as an external
  process. On a loaded or "cold" system — typically the first calls, while
  Windows Defender scans the freshly compiled codec — that can exceed the
  codec's per-frame timeout, so otherwise-decodable frames get dropped. The
  installer raises the default timeout from 5 s to 15 s; you can tune it with
  the `TETRAEAR_CODEC_TIMEOUT` environment variable (in seconds). Re-run the
  installer (or `python install_windows.py --repair`) to apply the patch. This
  depends on the upstream project and your signal, not on the installer.

---

### If something goes wrong (both systems)

1. Open (or attach) **`logs/install.log`** (in the `logs/` folder) — it
   contains the full history and error details, including tracebacks of
   unexpected errors. **This is the file to send when asking for help.**
2. Use `--repair` if the problem is only the codec or the RTL-SDR
   compatibility.
3. To start over, use `--uninstall` and then reinstall.

---
