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

import math
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Flowgraph GNU Radio incluso in telive-2 (stesso path usato da install_telive2.py).
GRC_RELATIVE = "gnuradio-companion/python3_based_gnuradio/telive_1ch_simple_gr310_udp_xmlrpc.grc"

# Limiti di sintonia tipici di una RTL-SDR (R820T/R828D). Fuori da qui non ha
# senso lanciare rtl_fm; il controllo serve anche a rifiutare input non numerici.
RTLSDR_MIN_MHZ = 24.0
RTLSDR_MAX_MHZ = 1766.0


# ============================================================
# VALIDAZIONE INPUT (stdlib puro: testabile senza PyQt6)
# ============================================================

def validate_frequency_mhz(text) -> tuple[bool, Optional[float], str]:
    """Valida una frequenza (MHz) da un campo utente. Accetta SOLO un numero
    finito nell'intervallo RTL-SDR; qualsiasi altro carattere viene rifiutato
    (niente da interpolare in un comando shell). Ritorna (ok, valore, messaggio)."""
    raw = (str(text) if text is not None else "").strip().replace(",", ".")
    if not raw:
        return False, None, "Inserisci una frequenza in MHz."
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return False, None, "Frequenza non valida: inserisci solo un numero in MHz."
    if not math.isfinite(val):
        return False, None, "Frequenza non valida (valore non finito)."
    if not (RTLSDR_MIN_MHZ <= val <= RTLSDR_MAX_MHZ):
        return False, None, (
            f"Fuori dai limiti RTL-SDR ({RTLSDR_MIN_MHZ:g}–{RTLSDR_MAX_MHZ:g} MHz)."
        )
    return True, val, ""


def validate_keyfile_text(text: str) -> tuple[bool, str]:
    """Validazione minima di un keyfile TELIVE-2: ogni riga non vuota e non
    commentata deve iniziare con 'network' (con mcc/mnc) o 'key' (con un campo
    'key <hex>'). Ritorna (ok, messaggio). Non giudica la correttezza della
    chiave, solo la forma."""
    errors = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        toks = s.split()
        kind = toks[0].lower()
        if kind == "network":
            if "mcc" not in toks or "mnc" not in toks:
                errors.append(f"riga {i}: 'network' senza mcc/mnc")
        elif kind == "key":
            rest = toks[1:]
            if "key" not in rest or rest.index("key") == len(rest) - 1:
                errors.append(f"riga {i}: 'key' senza campo 'key <hex>'")
        else:
            errors.append(f"riga {i}: atteso 'network' o 'key', trovato '{toks[0]}'")
    if errors:
        return False, "; ".join(errors[:6]) + (" …" if len(errors) > 6 else "")
    return True, "OK"


def shell_quote(value) -> str:
    """Quoting robusto per inserire un valore in un comando shell."""
    return shlex.quote(str(value))


# Maschera il valore della chiave nelle righe 'key ... key <hex>'. Lunghezza
# fissa: non rivela la lunghezza reale della chiave.
_KEY_SECRET_RE = re.compile(r"(\bkey\s+)([0-9a-fA-F]{2,})")
_KEY_MASK = "•" * 8  # ••••••••


def mask_keyfile_text(text: str) -> str:
    """Restituisce il keyfile con i valori delle chiavi mascherati (per il
    display). Le righe 'network' e la struttura restano intatte; solo il valore
    esadecimale dopo la parola chiave 'key' viene sostituito con ••••••••."""
    out = []
    for line in text.splitlines():
        if line.strip().lower().startswith("key"):
            out.append(_KEY_SECRET_RE.sub(lambda m: m.group(1) + _KEY_MASK, line))
        else:
            out.append(line)
    return "\n".join(out)


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
        ["xfce4-terminal", "-x", "bash", "-lc", keep],
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


# ============================================================
# INTEGRAZIONE CON LA FINESTRA PRINCIPALE (best-effort)
# ============================================================

def tune_main_window(main_window, freq_mhz) -> tuple[bool, str]:
    """Sintonizza TetraEar sulla frequenza data (MHz), riusando i metodi della
    finestra principale. Difensivo: se la struttura a monte cambia, ritorna un
    messaggio senza sollevare eccezioni."""
    if main_window is None:
        return False, "GUI non disponibile."
    try:
        freq = float(freq_mhz)
    except (TypeError, ValueError):
        return False, f"Frequenza non valida: {freq_mhz}"
    try:
        fn = getattr(main_window, "on_tune_from_spectrum", None)
        if callable(fn):
            fn(freq)
            return True, f"Sintonizzato a {freq:.3f} MHz."
        freq_input = getattr(main_window, "freq_input", None)
        if freq_input is not None:
            freq_input.setText(f"{freq:.3f}")
            tune = getattr(main_window, "on_tune", None)
            if callable(tune):
                tune()
            return True, f"Sintonizzato a {freq:.3f} MHz."
        return False, "Campo frequenza non trovato nella GUI."
    except Exception as exc:  # difensivo
        return False, f"Tune fallito: {exc}"


def set_app_status(main_window, text: str) -> None:
    """Mostra un messaggio di stato del toolkit nella finestra principale:
    aggiorna l'etichetta 'toolkit_status_label' (se iniettata) e la status bar."""
    if main_window is None:
        return
    try:
        lbl = getattr(main_window, "toolkit_status_label", None)
        if lbl is not None:
            lbl.setText("🧰 " + text)
    except Exception:
        pass
    try:
        sb = main_window.statusBar()
        if sb is not None:
            sb.showMessage(text, 8000)
    except Exception:
        pass
