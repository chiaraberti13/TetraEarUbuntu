"""
tetra_gui_common.py -- helper condivisi dai tab aggiuntivi della GUI TetraEar
============================================================================

NON fa parte del pacchetto originale di TetraEar: viene COPIATO dentro l'app
(in tetraear/ui/tetra_gui_common.py) dall'installer, insieme ai moduli dei tab
"Network Info", "Decrypt (TELIVE-2)", "Decoders" e "Reference".

Raccoglie due cose usate da piu' tab:
  * open_terminal(): lancia un comando in un terminale grafico (serve per
    telive/ncurses e per i decoder interattivi), provando i terminali comuni;
  * localizzazione dei componenti installati dagli installer del repo
    (ricevitore TELIVE-2, telive, flowgraph GNU Radio, decoder extra, log).

Tutte le funzioni sono difensive: se qualcosa non c'e' ritornano None / un
messaggio, senza sollevare eccezioni che possano disturbare la GUI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Flowgraph GNU Radio incluso in telive-2 (stesso path usato da install_telive2.py).
GRC_RELATIVE = "gnuradio-companion/python3_based_gnuradio/telive_1ch_simple_gr310_udp_xmlrpc.grc"


# ============================================================
# LOCALIZZAZIONE DEI COMPONENTI
# ============================================================

def repo_root() -> Path:
    """Cartella dell'installer (TetraEarUbuntu): contiene telive2/, decoders/,
    logs/ e gli script install_*. L'app sta in TetraEar/ dentro di essa."""
    here = Path(__file__).resolve()
    candidates = []
    # .../TetraEar/tetraear/ui/tetra_gui_common.py -> parents[3] = TetraEarUbuntu
    if len(here.parents) > 3:
        candidates.append(here.parents[3])
    candidates.append(here.parents[2] if len(here.parents) > 2 else here.parent)
    candidates.append(Path.home() / "TetraEarUbuntu")
    for c in candidates:
        if (c / "install_telive2.py").is_file() or (c / "telive2").is_dir():
            return c
    return candidates[0]


def telive2_base() -> Optional[Path]:
    """Cartella con i sorgenti TELIVE-2 (repo/telive2 oppure ~/telive2)."""
    for c in (repo_root() / "telive2", Path.home() / "telive2"):
        if c.is_dir():
            return c
    return None


def osmo_src() -> Optional[Path]:
    base = telive2_base()
    if base:
        p = base / "osmo-tetra-sq5bpf-2" / "src"
        if p.is_dir():
            return p
    return None


def telive_dir() -> Optional[Path]:
    base = telive2_base()
    if base:
        p = base / "telive-2"
        if p.is_dir():
            return p
    return None


def tetra_bin() -> Path:
    return Path("/tetra") / "bin"


def find_bin(name: str) -> Optional[Path]:
    """Trova un binario: PATH, /tetra/bin, sorgenti osmo/telive, decoders/bin."""
    which = shutil.which(name)
    if which:
        return Path(which)
    places = [tetra_bin() / name]
    src = osmo_src()
    if src:
        places += [src / name]
    td = telive_dir()
    if td:
        places += [td / name]
    places += [repo_root() / "decoders" / "bin" / name]
    for p in places:
        if p.is_file():
            return p
    return None


def receiver_launcher() -> Optional[Path]:
    """Launcher del ricevitore osmo (run_receiver.sh o receiver1udp)."""
    src = osmo_src()
    if src:
        for name in ("run_receiver.sh", "receiver1udp", "tetra-rx"):
            if (src / name).is_file():
                return src / name
    tb = tetra_bin() / "tetra-rx"
    return tb if tb.is_file() else None


def gnuradio_launcher() -> Optional[Path]:
    td = telive_dir()
    if td and (td / "run_gnuradio.sh").is_file():
        return td / "run_gnuradio.sh"
    return None


def grc_file() -> Optional[Path]:
    td = telive_dir()
    if td and (td / GRC_RELATIVE).is_file():
        return td / GRC_RELATIVE
    return None


def keyfile_default() -> Optional[Path]:
    src = osmo_src()
    if src:
        return src / "sample_keyfile"
    return None


def receiver_log() -> Path:
    return repo_root() / "logs" / "receiver.log"


def voice_out_dir() -> Path:
    return Path("/tetra") / "out"


# ============================================================
# TERMINALE GRAFICO
# ============================================================

def open_terminal(command: str, cwd=None) -> tuple[bool, str]:
    """Esegue `command` in un terminale grafico che resta aperto a fine comando.
    Prova i terminali piu' comuni; ritorna (ok, messaggio)."""
    cwd = str(cwd) if cwd else None
    keep = f'{command}; echo; echo "[premi INVIO per chiudere]"; read _'
    candidates = [
        ["x-terminal-emulator", "-e", "bash", "-lc", keep],
        ["gnome-terminal", "--", "bash", "-lc", keep],
        ["konsole", "-e", "bash", "-lc", keep],
        ["xfce4-terminal", "-e", f"bash -lc '{keep}'"],
        ["mate-terminal", "--", "bash", "-lc", keep],
        ["xterm", "-e", "bash", "-lc", keep],
    ]
    for argv in candidates:
        if shutil.which(argv[0]):
            try:
                subprocess.Popen(argv, cwd=cwd)
                return True, f"Avviato in {argv[0]}."
            except OSError:
                continue
    return False, "Nessun terminale grafico trovato. Esegui a mano:\n  " + command
