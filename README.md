# TetraEar

<p align="center">
  <img src="assets/banner.svg" alt="TetraEar - installer per decoder TETRA su RTL-SDR" width="100%" />
</p>

<p align="center">
  <b>Installer automatizzati per <a href="https://github.com/syrex1013/TetraEar">TetraEar</a> — decoder TETRA per chiavette RTL-SDR — su Ubuntu/Debian e Windows.</b>
</p>

[English](#english) | [Italiano](#italiano)

---

<a name="english"></a>
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

<a name="italiano"></a>
## 🇮🇹 Italiano

### Panoramica

**TetraEar** è un decoder TETRA (Terrestrial Trunked Radio) per chiavette
RTL-SDR (chip RTL2832U). Questa repository contiene degli **installer
completamente automatizzati** che, con un solo comando, preparano tutto ciò
che serve a TetraEar: pacchetti di sistema, ambiente Python, codec vocale
ETSI e configurazione della chiavetta RTL-SDR.

Non devi clonare tu TetraEar: l'installer ne scarica il codice sorgente
automaticamente.

> ⚠️ **Leggi il [disclaimer legale](DISCLAIMER.md) prima di usare questo
> software.** TetraEar è destinato solo a scopi didattici e di ricerca, e
> solo dove consentito dalle leggi della tua giurisdizione.

### Cosa fanno gli installer

1. Controllano Python e il sistema operativo.
2. Installano le dipendenze di sistema (compilatore, librerie RTL-SDR, Qt, audio).
3. Scaricano il codice sorgente di TetraEar.
4. Creano un ambiente virtuale Python (`.venv`) e installano i pacchetti `pip`.
5. Configurano la chiavetta RTL-SDR (su Linux in automatico).
6. Scaricano e compilano il codec vocale ETSI TETRA.
7. Verificano che tutto sia a posto.

Tutto ciò che accade viene registrato in **`logs/install.log`** (tutti i log,
compresi quelli dell'app, stanno nella cartella `logs/` accanto all'installer)
— allega quel file se hai bisogno di supporto.

### Cosa ti serve

- Una connessione a Internet.
- Una chiavetta **RTL-SDR** (chip RTL2832U) con antenna — serve solo quando
  *usi* TetraEar, non per installarlo.
- I permessi di amministratore (su Linux la password `sudo`; su Windows la
  finestra si eleva da sola).

---

### 🐧 Ubuntu / Debian

Testato su **Ubuntu 24.04** e **Debian 12** (dovrebbe funzionare anche su
derivate recenti come Linux Mint e Pop!_OS).

**1. Installazione**

```bash
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
python3 install_linux.py
```

Ti verrà chiesta la password di `sudo` (per installare i pacchetti di
sistema). Il processo richiede qualche minuto. Al termine l'installer avrà
creato accanto a sé una cartella `TetraEar/` con il codice sorgente,
l'ambiente `.venv` e il codec compilato.

**2. La chiavetta RTL-SDR è configurata in automatico**

Su Linux non devi fare nulla a mano: l'installer mette in blacklist i driver
DVB-T del kernel che altrimenti "occupano" la chiavetta, installa/ricarica le
regole udev e aggiunge il tuo utente al gruppo `plugdev`.

> ⚠️ **Passaggio finale obbligatorio:** dopo l'installazione **scollega e
> ricollega** la chiavetta (oppure riavvia), così la blacklist del driver e
> le regole udev hanno effetto. Poi verifica con:
>
> ```bash
> rtl_test -t
> ```
>
> Se compare "Found 1 device(s)" sei a posto. `usb_claim_interface error -6`
> significa che il driver DVB-T è ancora caricato → ricollega o riavvia.

**3. Avvia TetraEar**

```bash
cd TetraEar
source .venv/bin/activate
python -m tetraear -f 392.225          # interfaccia grafica
# oppure senza GUI:
python -m tetraear --no-gui -f 392.225 --auto-start
```

(sostituisci `392.225` con la frequenza in MHz che ti interessa).

**Senza terminale:** l'installer crea anche una voce **TetraEar** nel menu
applicazioni e un'icona **`TetraEar.desktop`** sul Desktop — doppio clic per
avviare, senza terminale. L'icona avvia già la cattura in automatico con log
dettagliato, quindi scrive gli stessi file in `TetraEar/logs/` (più un
`console_*.log`) del comando da terminale — comodo se la voce non si
decodifica e devi inviare i log.

**Riavviare l'app (dopo logout o riavvio)** — bastano tre righe:

```bash
cd ~/TetraEarUbuntu/TetraEar
source .venv/bin/activate
python -m tetraear -f 392.225
```

Per avviarla con una sola parola, crea un alias una volta sola:

```bash
echo "alias tetraear='cd ~/TetraEarUbuntu/TetraEar && source .venv/bin/activate && python -m tetraear -f 392.225'" >> ~/.bashrc && source ~/.bashrc
```

Da allora basta digitare `tetraear`. C'è anche uno script pronto: dalla
cartella `TetraEarUbuntu` esegui `./avvia_tetraear.sh 392.225`.

**Decodifica vocale e log.** A ogni avvio l'app scrive log dettagliati in
`TetraEar/logs/`: `codec_<id>.log`, `decoder_<id>.log`, `audio_<id>.log`,
`tetraear_<id>.log`. Avvia con `-v --auto-start` (aggiungi `-m` per sentire
l'audio) per esercitare la decodifica, poi inviami quei file se la voce non
esce — lo script `avvia_tetraear.sh` fa esattamente questo.

> ℹ️ **Perché la voce può non decodificarsi.** Nelle reti TETRA
> professionali la voce è quasi sempre **cifrata** (TEA1–4): le chiamate
> cifrate non sono decodificabili senza le chiavi e compaiono come 🔐 nella
> tabella dei frame. Inoltre devi essere sintonizzato su una frequenza con
> una chiamata vocale **in chiaro** realmente attiva, con guadagno/segnale
> sufficienti. Se i frame arrivano ma l'audio è muto, guarda
> `codec_<id>.log`: un codec funzionante scrive `cdecoder exited 0` /
> `sdecoder exited 0`.
>
> **Lo stato dice "Signal Detected (Decoding…)" ma la tabella dei frame è
> vuota?** Di solito sono i filtri: imposta **Filter** su **All/Tutti** e
> **deseleziona "Decrypted/Text Only"** — altrimenti vedi solo le righe
> audio/testo già decifrate. Se poi i frame compaiono tutti con 🔐 il
> traffico è cifrato e il contatore del lucchetto (es. `0/0` = nessuna
> chiave caricata) conferma che non hai chiavi, quindi la voce non è
> recuperabile. Ricorda inoltre che un portante continuo è spesso un
> **canale di controllo** (segnalazione): la voce compare solo durante una
> chiamata reale.

**4. Comandi utili**

| Comando | Cosa fa |
| --- | --- |
| `python3 install_linux.py` | Installazione completa |
| `python3 install_linux.py --repair` | Ricompila solo il codec vocale + riapplica le correzioni |
| `python3 install_linux.py --uninstall` | Rimuove `.venv` e il codec (lascia il sorgente) |
| `python3 install_linux.py --check` | Verifica l'installazione (venv, codec, pyrtlsdr) senza modificare nulla |
| `python3 install_linux.py --ref <commit\|tag\|branch>` | Installa una versione specifica di TetraEar |

> ℹ️ **Installazioni riproducibili.** L'installer fissa TetraEar a una release
> nota e testata (attualmente `v2.3`) invece di prendere sempre l'ultimo
> `master`, così un cambiamento a monte non può rompere di nascosto le patch
> applicate. Il commit esatto installato è registrato in
> `TetraEar/.tetraear_version`. Per installare una versione diversa usa
> `--ref` (o la variabile d'ambiente `TETRAEAR_REF`). Il codec vocale ETSI
> viene scaricato da ETSI con fallback automatico su archive.org se il sito
> ETSI è irraggiungibile; il download è sempre verificato con MD5.

**5. Problemi comuni (Linux)**

- **`Could not get lock /var/lib/dpkg/lock-frontend` (occupato da
  `unattended-upgr`)**: gli aggiornamenti automatici di Ubuntu partono subito
  dopo l'avvio e tengono occupato il lock dei pacchetti. L'installer ora
  attende in automatico; se dovesse arrendersi, aspetta 2-3 minuti che gli
  aggiornamenti finiscano e rilancia `python3 install_linux.py`.
- **`dpkg was interrupted, you must manually run 'sudo dpkg --configure -a'`**:
  una precedente operazione sui pacchetti è rimasta a metà (un aggiornamento
  interrotto, uno spegnimento forzato…), così `apt` si rifiuta di proseguire.
  L'installer ora rileva questa situazione ed esegue automaticamente
  `sudo dpkg --configure -a` al posto tuo, poi riprova. Se la riparazione
  automatica fallisce a sua volta, esegui a mano `sudo dpkg --configure -a`,
  leggi gli errori che riporta e poi rilancia `python3 install_linux.py`.
- **La GUI non parte, "could not load the Qt platform plugin xcb"**:
  l'installer installa già le librerie Qt necessarie; assicurati di essere in
  una sessione grafica (non SSH senza display).
- **Chiavetta non rilevata / `usb_claim_interface error -6`**: il driver
  DVB-T è ancora caricato. Scollega/ricollega la chiavetta (o riavvia), poi
  `rtl_test -t`.
- **`rtl_test` funziona solo con sudo**: fai logout/login una volta (per
  attivare l'appartenenza al gruppo `plugdev`).
- **All'avvio: `undefined symbol: rtlsdr_set_dithering` (o simile)**: è
  un'incompatibilità tra `pyrtlsdr` e la `librtlsdr` di Ubuntu (che non ha
  alcune funzioni presenti solo nel fork *keenerd*). L'installer applica una
  patch a `pyrtlsdr` che tollera i simboli mancanti; se hai aggiornato lo
  script, rilancia `python3 install_linux.py` (o `--repair`). **Non dipende**
  dalla chiavetta: l'errore compare all'`import`.
- **Il download del codec da ETSI fallisce**: riprova più tardi (a volte il
  sito ETSI è irraggiungibile), poi `python3 install_linux.py --repair`.
- **Non decodifica nulla, `decoder.log`/`app.log` pieni di `Decode error:
  'CaptureThread' object has no attribute 'signal_processor'`**: è un bug del
  sorgente TetraEar a monte (nome di attributo errato nel thread di cattura).
  L'installer lo corregge in automatico; se hai aggiornato lo script, rilancia
  `python3 install_linux.py` (o `--repair`).
- **La voce è a scatti / si decodifica solo in parte su una macchina lenta**:
  ogni frame vocale esegue il codec ETSI come processo esterno. Su un sistema
  carico o "a freddo" (es. alle prime chiamate, mentre l'antivirus analizza il
  codec appena compilato) l'esecuzione può superare il timeout per-frame del
  codec, così i frame altrimenti decodificabili vengono scartati. L'installer
  alza il timeout predefinito da 5 s a 15 s; puoi regolarlo con la variabile
  d'ambiente `TETRAEAR_CODEC_TIMEOUT` (in secondi). Rilancia
  `python3 install_linux.py` (o `--repair`) per applicare la patch. Dipende dal
  progetto a monte e dal tuo segnale, non dall'installer.

---

### 📡 Decoder aggiuntivi (DMR, P25, ADS-B, cercapersone) — Linux

TetraEar decodifica il TETRA. Ma una chiavetta RTL-SDR riceve molti altri modi
— gli stessi che programmi chiusi come OpenEar coprivano, qui però con
strumenti **open source**:

| Strumento | Cosa decodifica |
| --- | --- |
| **multimon-ng** | cercapersone POCSAG / FLEX e altri modi FSK/AFSK |
| **dump1090** | ADS-B 1090 MHz (posizione aerei, mappa web) |
| **dsd-fme** | DMR / P25 / NXDN / dPMR (voce digitale **in chiaro**) |

**Vengono installati in automatico** al termine di `python3 install_linux.py`
(log in `logs/install_extra.log`, ogni decoder indipendente). Usa `--no-extra`
per saltarli, oppure rilancia lo script complementare da solo più tardi:

```bash
python3 install_extra_decoders.py                 # (re)installa tutti e tre
python3 install_extra_decoders.py --only dump1090 # solo uno (o un sottoinsieme)
python3 install_extra_decoders.py --check         # vedi cosa è installato
```

Dopo l'installazione, uso tipico (con la chiavetta collegata):

```bash
# Cercapersone (POCSAG), es. 439.9875 MHz
rtl_fm -f 439.9875M -s 22050 -g 42 - | \
  multimon-ng -t raw -a POCSAG1200 -f alpha /dev/stdin
# Aerei (ADS-B), mappa web su http://localhost:8080
dump1090 --interactive --net
# Voce DMR/P25 in chiaro, es. 446.09375 MHz
rtl_fm -f 446.09375M -s 48000 -g 42 - | dsd-fme -i - -o /dev/null
```

> ℹ️ Come sempre: vedi traffico solo se sei sulla frequenza giusta con segnale
> sufficiente, e la voce/dati **cifrati** non sono decodificabili senza le
> chiavi — da nessun software. Usa solo dove consentito dalla legge (vedi
> [DISCLAIMER](DISCLAIMER.md)).

📖 La guida d'uso completa (frequenze, comandi, note per Windows) è nelle
sezioni seguenti. Su Windows usa `install_extra_decoders_windows.py`.

---

### 🔓 Decifratura vocale a chiave nota — TELIVE-2 (Linux e Windows via WSL)

TetraEar decodifica la voce TETRA **in chiaro**. Se possiedi *già* la chiave
di cifratura, la catena **TELIVE-2** (osmo-tetra-sq5bpf-2 + codec ETSI +
telive) di Jacek Lipkowski (SQ5BPF) sa anche **decifrare** la voce — inclusa
la **chiave TEA-1 accorciata a 32 bit** (il backdoor documentato da Team
Midnight Blue nel 2023).

> ✅ **Viene installata in automatico** alla fine di `install_linux.py` — non
> serve un passo separato. Per saltarla, passa `--no-telive2` all'installer
> principale. La build è pesante (GNU Radio, `libosmocore`, codec ETSI),
> quindi aggiunge qualche minuto.

Puoi comunque eseguire (o rieseguire) l'installer complementare da solo:

```bash
python3 install_telive2.py            # compila e collega tutta la catena
python3 install_telive2.py --check    # controlla soltanto cosa è presente
python3 install_telive2.py --no-gnuradio   # salta GNU Radio (se ce l'hai già)
```

Preferisci un semplice script di shell? `install_telive2.sh` fa lo stesso, in
modo autonomo (lancialo da utente normale, **non** con sudo). È portabile fra
**Ubuntu 24.04 (x86)** e **25.10 (ARM64)** — rileva da solo i flag del
compilatore necessari a compilare i vecchi sorgenti C di SQ5BPF su GCC 15:

```bash
bash install_telive2.sh
```

Clona e compila `osmo-tetra-sq5bpf-2` (il ricevitore `tetra-rx` con la crypto
TEA1/2/3 **reale** e il flag `-k keyfile`), scarica e patcha il **codec vocale
ETSI** (`cdecoder`/`sdecoder`, con lo stesso trucco dello User-Agent «da
browser» usato da `install_linux.py`, così il `403 Forbidden` di ETSI non si
presenta), compila `telive` e prepara la cartella di lavoro `/tetra` più il
flowgraph GNU Radio incluso. Le istruzioni d'uso (ricevitore → telive →
riproduzione) vengono stampate alla fine.

**Come si fornisce la chiave nota** — si passa un keyfile al ricevitore
(`./tetra-rx -r -k <keyfile> -s`; `receiver1udp` lo fa già). Una riga per
chiave, ad esempio:

```
network mcc 0123 mnc 1337 ksg_type 1 security_class 2
key mcc 0123 mnc 1337 addr 00000000 key_type 1  key_num 0 key 11111111111111111111
# chiave TEA-1 accorciata a 32 bit (padding a 80 bit): key_type 16
key mcc 0123 mnc 1337 addr 00000000 key_type 16 key_num 0 key 12345678000000000000
```

> ℹ️ **Perché non il caricatore chiavi di TetraEar?** La GUI di TetraEar *ha*
> un pulsante «🔑 Load Keys» e un loader di keyfile, ma i suoi TEA1–4 in
> `core/crypto.py` sono implementazioni **segnaposto semplificate** (lo dicono
> i suoi stessi docstring: gli algoritmi reali sono proprietari), quindi lì
> una chiave reale non decifra correttamente il traffico reale. Il percorso a
> chiave nota **funzionante** è `tetra-rx -k` di TELIVE-2.

> ⚠️ **Decifrare ≠ craccare.** Questi strumenti decifrano solo con chiave
> **già nota**: nessuno di essi recupera una chiave. Usa solo dove consentito
> dalla legge (vedi [DISCLAIMER](DISCLAIMER.md)).

**Su Windows** la catena TELIVE-2 gira tramite **WSL2** (Ubuntu dentro
Windows), perché è profondamente POSIX (`libosmocore`, GNU Radio, script di
shell, la cartella fissa `/tetra`) e non ha una build Windows nativa
affidabile. L'installer complementare rileva WSL ed esegue al suo interno lo
*stesso* installer Linux:

```bat
python install_telive2_windows.py              REM rileva WSL e compila dentro Ubuntu
python install_telive2_windows.py --check      REM verifica solo lo stato WSL / build
python install_telive2_windows.py --guide-only REM stampa solo i passi per abilitare WSL
```

Se WSL non è ancora attivo, stampa la configurazione iniziale (`wsl --install
-d Ubuntu`, riavvio, creazione utente) e poi lo rilanci. La GUI di GNU Radio
compare automaticamente via WSLg su Windows 11 (su Windows 10 serve un server X).

---

### 📶 TETRA Network Scanner — pannello passivo di rete

Ispirato all'articolo *"Interception of TETRA radio"*, la cui funzione
distintiva (nel plugin per SDR#) è un **pannello passivo dei metadati di rete**
trasmessi nel broadcast TETRA. TetraEar decodifica la voce/testo ma **non**
mostra quei campi; questo strumento complementare li aggiunge leggendo l'output
del ricevitore TELIVE-2 (`tetra-rx`, compilato da `install_telive2.py`).

Mostra in tempo reale: **MCC / MNC / MNI**, **Location Area**, **Colour Code**,
modo operativo, **portante principale** (+ celle vicine viste), lo stato
**🔓/🔐 Air Interface Encryption (AIE)**, la **Security Class**, il **Cipher Key
ID / tipo TEA**, il flag **autenticazione richiesta sulla cella**, più un
**calcolatore della lunghezza d'antenna** (il consiglio sull'ANT-500 citato
nell'articolo). Usa gli stessi token `KEY:VALUE` (`MCC:`,
`MNC:`, `LA:`, `CCODE:`, `CRYPT:`, `ENC:`…) che analizza `telive`, così resta
robusto.

> ✅ Viene **preparato in automatico** alla fine di `install_telive2.py` (per
> saltarlo: `--no-netscanner`). Puoi comunque collegarlo da solo — non compila
> nulla di pesante, è Python puro:
>
> ```bash
> python3 install_tetra_netscanner.py            # verifica + crea il launcher
> python3 install_tetra_netscanner.py --check    # controlla soltanto cosa c'è
> ```

Uso:

```bash
# Automatico: segue logs/receiver.log se presente (convive con telive), altrimenti avvia il ricevitore
./avvia_netscanner.sh 392.225
# Avvia direttamente il ricevitore:
python3 tetra_netscanner.py --run -f 392.225
# Convivi con una sessione telive già attiva (segue il suo log del ricevitore):
python3 tetra_netscanner.py --attach-file logs/receiver.log --follow
# Senza chiavetta:
python3 tetra_netscanner.py --antenna 392.225     # calcolo della lunghezza d'antenna
python3 tetra_netscanner.py --self-test           # prova il parser
```

**Su Windows** il pannello *live* gira dentro **WSL2**, esattamente come la
catena TELIVE-2: `install_telive2_windows.py` compila `tetra-rx` in WSL e ci
collega il pannello in automatico. Crea inoltre sull'host Windows un launcher
nativo **`Avvia NetScanner.bat`** (doppio clic, o passagli una frequenza) che
avvia il pannello live via WSL, oppure mostra il calcolo antenna offline se WSL
non c'è. Le funzioni senza chiavetta girano anche su Windows nativo:

```bat
python install_tetra_netscanner_windows.py        REM verifica + crea il launcher .bat
python tetra_netscanner.py --antenna 392.225       REM calcolo antenna (senza hardware)
python tetra_netscanner.py --self-test             REM prova il parser
```

> ⚠️ **Passivo e in sola lettura.** Il pannello si limita a *mostrare* i metadati
> di broadcast e se la cifratura è attiva — **non decifra nulla e non recupera
> chiavi** (la decifratura a chiave nota resta compito di TELIVE-2). Mostra
> valori reali solo dove il ricevitore li decodifica davvero, su un canale con
> segnale sufficiente. Usa solo dove consentito dalla legge (vedi
> [DISCLAIMER](DISCLAIMER.md)).

---

### 🪟 Windows

Testato su **Windows 10** e **Windows 11** (64 bit).

**1. Scarica gli installer**

Con **Git per Windows** la via più semplice è clonare la repository (Prompt
dei comandi o PowerShell):

```bat
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
```

Senza Git: apri <https://github.com/chiaraberti13/TetraEarUbuntu>, premi
**Code → Download ZIP**, estrai e apri la cartella. In entrambi i casi ti
servono `install_windows.bat` e `install_windows.py` nella stessa cartella.

**2. Installazione**

**Fai doppio clic su `install_windows.bat`.**

- Windows chiederà di **consentire le modifiche** (permessi di
  amministratore): accetta.
- Se Python non è installato, l'installer lo installa tramite `winget`.
  Quando te lo chiede, **chiudi la finestra e rifai doppio clic** su
  `install_windows.bat`: alla seconda esecuzione trova Python nel PATH e
  prosegue.
- Il `.bat` avvia poi `install_windows.py`, che installa **Git** e **MSYS2**
  (il compilatore C per il codec), scarica TetraEar, crea l'ambiente,
  installa i pacchetti Python e compila il codec.
- Alla fine prepara **in automatico** anche i **decoder aggiuntivi**
  (`install_extra_decoders_windows.py`): scarica la build Windows ufficiale di
  **dsd-fme** e stampa i passi guidati per **dump1090** e **multimon-ng** (che
  su Windows non hanno un binario ufficiale unico). Usa `--no-extra` per
  saltarli. Tutti i log finiscono in `logs/`.

**3. RTL-SDR su Windows (un passaggio, una volta sola)**

`rtlsdr.dll` (con `libusb`) viene **installata automaticamente** dall'installer:
non devi più scaricarla a mano. Resta manuale solo il driver, **una volta sola**:

- **Driver WinUSB con Zadig** — scarica [Zadig](https://zadig.akeo.ie/),
  collega la chiavetta, poi *Options → List All Devices*, seleziona
  **"Bulk-In, Interface (Interface 0)"** (o "RTL2832U"), scegli il driver
  **WinUSB** e premi *Replace Driver*.

**4. Avvia TetraEar**

**Senza terminale:** fai doppio clic su **`Avvia TetraEar.vbs`** — l'installer
lo crea nella cartella `TetraEar` e ne mette una copia sul **Desktop**. Avvia
l'app senza finestra del terminale.

Oppure dal **Prompt dei comandi**, nella cartella `TetraEar` creata
dall'installer:

```bat
cd TetraEar
.venv\Scripts\activate
python -m tetraear -f 392.225
```

**5. Comandi utili**

| Comando | Cosa fa |
| --- | --- |
| doppio clic su `install_windows.bat` | Installazione completa |
| `python install_windows.py --repair` | Ricompila solo il codec vocale + riapplica le correzioni |
| `python install_windows.py --uninstall` | Rimuove `.venv` e il codec (lascia il sorgente) |
| `python install_windows.py --check` | Verifica l'installazione (venv, codec, rtlsdr.dll) senza modificare nulla |
| `python install_windows.py --ref <commit\|tag\|branch>` | Installa una versione specifica di TetraEar |

> ℹ️ **Installazioni riproducibili.** Come su Linux: TetraEar è fissato a una
> release nota e testata (attualmente `v2.3`), il commit installato è
> registrato in `TetraEar\.tetraear_version`, e il download del codec ETSI ha
> un fallback su archive.org ed è verificato con MD5. Usa `--ref` o la
> variabile d'ambiente `TETRAEAR_REF` per installare una versione diversa.

**6. Problemi comuni (Windows)**

- **"winget non disponibile"**: aggiorna *Programma di installazione app* dal
  Microsoft Store, oppure installa Python, Git e MSYS2 a mano e rilancia
  `install_windows.py`.
- **MSYS2 installato ma non trovato**: riavvia e rilancia l'installer.
- **Il codec non compila**: esegui `python install_windows.py --repair`; se
  persiste, controlla `logs/install.log`.
- **All'avvio: `undefined symbol: rtlsdr_set_dithering`**: stessa soluzione di
  Linux — l'installer applica la patch a `pyrtlsdr`. Rilancia l'installer (o
  `--repair`).
- **Non decodifica nulla, log pieni di `'CaptureThread' object has no attribute
  'signal_processor'`**: stesso bug a monte di Linux — l'installer corregge in
  automatico il sorgente di TetraEar. Rilancia l'installer (o `--repair`).
- **Ad ogni decodifica compare/lampeggia una finestra nera**: il launcher senza
  console (`pythonw`) fa aprire una finestra a ogni chiamata del codec
  (`cdecoder.exe`/`sdecoder.exe`), una per frame. L'installer ora corregge
  `voice.py` per eseguire il codec nascosto (`CREATE_NO_WINDOW`). Rilancia
  l'installer (o `python install_windows.py --repair`) per applicare la modifica.
- **La voce è a scatti / si decodifica solo in parte su una macchina lenta**:
  ogni frame vocale esegue il codec ETSI (`cdecoder.exe`/`sdecoder.exe`) come
  processo esterno. Su un sistema carico o "a freddo" — tipicamente alle prime
  chiamate, mentre Windows Defender analizza il codec appena compilato —
  l'esecuzione può superare il timeout per-frame del codec, così i frame
  altrimenti decodificabili vengono scartati. L'installer alza il timeout
  predefinito da 5 s a 15 s; puoi regolarlo con la variabile d'ambiente
  `TETRAEAR_CODEC_TIMEOUT` (in secondi). Rilancia l'installer (o
  `python install_windows.py --repair`) per applicare la patch. Dipende dal
  progetto a monte e dal tuo segnale, non dall'installer.

---

### In caso di problemi (entrambi i sistemi)

1. Apri (o allega) **`logs/install.log`** (nella cartella `logs/`): contiene
   la cronologia completa e i dettagli degli errori, compresi i traceback
   degli errori imprevisti. **È il file da inviare per chiedere supporto.**
2. Usa `--repair` se il problema riguarda solo il codec o la compatibilità
   RTL-SDR.
3. Per ripartire da zero, usa `--uninstall` e poi reinstalla.

---

<p align="center">
  <sub>Usa TetraEar solo nel rispetto delle leggi vigenti · Use TetraEar only in compliance with applicable laws — <a href="DISCLAIMER.md">DISCLAIMER</a></sub>
</p>
