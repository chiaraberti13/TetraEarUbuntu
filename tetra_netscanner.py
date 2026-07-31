#!/usr/bin/env python3
"""
tetra_netscanner.py -- Pannello passivo "Network Info" per reti TETRA
=====================================================================

Ispirato all'articolo "Interception of TETRA radio" (allthewriteups): la
funzione distintiva del plugin TETRA per SDR# descritto nell'articolo NON e'
la decifratura, ma un pannello che mostra i PARAMETRI DI RETE trasmessi in
CHIARO nel broadcast di sistema (System Information):

    MCC / MNC / MNI  ..... identita' della rete (ITU-T E.212)
    Location Area .......  area di posizione della cella
    Colour Code .........  codice colore della cella
    Operating mode ......  Voice+Data / Direct Mode
    Main carrier ........  portante principale (frequenza)
    AIE (cifratura) .....  Air Interface Encryption on/off
    Security class ......  classe di sicurezza / algoritmo TEA
    Cipher Key ID .......  identificatore della chiave

Questi campi sono METADATI di broadcast: si leggono in modo PASSIVO, senza
decifrare nulla. Questo strumento NON decifra la voce e NON recupera chiavi
(la decifratura a chiave nota resta compito della catena TELIVE-2, immutata).

Come funziona
-------------
Il ricevitore osmo-tetra 'tetra-rx' (compilato dalla catena TELIVE-2,
install_telive2.py) decodifica MAC/MLE/MM e, per ogni evento, emette messaggi
di testo nel formato usato da telive:

    TETMON_begin FUNC:... MCC:... MNC:... LA:... CCODE:... CRYPT:... ENC:... TETMON_end

Questo tool legge quelle righe (dallo stdout del ricevitore, da un file di log
o da una socket UDP), ne estrae i token KEY:VALUE -- esattamente come fa
telive -- e li mostra in un pannello aggiornato in tempo reale.

Il parser e' PERMISSIVO: prende qualunque token KEY:VALUE riconosciuto e ignora
il resto, cosi' non si rompe se il ricevitore aggiunge campi o cambia il FUNC.

Uso
---
    python3 tetra_netscanner.py --antenna 392.225      # solo calcolo antenna (no hardware)
    python3 tetra_netscanner.py --self-test            # test del parser (no hardware)
    python3 tetra_netscanner.py --run                  # lancia il ricevitore e mostra il pannello
    python3 tetra_netscanner.py --attach-file logs/receiver.log --follow
    python3 tetra_netscanner.py --attach-udp 7379      # legge i datagrammi TETMON

DISCLAIMER: usa questo strumento solo dove consentito dalle leggi della tua
giurisdizione. Vedi DISCLAIMER.md.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Iterator, Optional

# ============================================================
# CONFIGURAZIONE
# ============================================================

SCRIPT_VERSION = "1.0"

INSTALLER_DIR = Path(__file__).resolve().parent
LOG_DIR = INSTALLER_DIR / "logs"

# Percorsi dove la catena TELIVE-2 mette il ricevitore (vedi install_telive2.py):
#   * /tetra/bin              -> cartella di lavoro fissa, con i binari copiati
#   * ./telive2/osmo-tetra-sq5bpf-2/src -> sorgenti + receiver1udp + tetra-rx
TETRA_BIN = Path("/tetra") / "bin"
OSMO_SRC = INSTALLER_DIR / "telive2" / "osmo-tetra-sq5bpf-2" / "src"
RECEIVER_LOG_DEFAULT = LOG_DIR / "receiver.log"

# Porta UDP predefinita su cui telive riceve i messaggi TETMON dal ricevitore.
DEFAULT_TETMON_UDP_PORT = 7379

# Banda TETRA e preset comuni (380-430 MHz). Solo indicativi.
TETRA_BAND_MHZ = (380.0, 430.0)
BAND_PRESETS_MHZ = {
    "380-385 (TETRA I DL, forze dell'ordine EU)": 392.0,
    "410-420 (uso commerciale/PMR)": 415.0,
    "420-430 (uso commerciale/PMR)": 425.0,
}

logger = logging.getLogger("netscanner")


# ============================================================
# CALCOLATORE ANTENNA (l'helper citato nell'articolo)
# ============================================================

# Velocity factor pratico per uno stilo/telescopica in aria libera.
_ANTENNA_VELOCITY_FACTOR = 0.95
_C = 299_792_458.0  # velocita' della luce, m/s


def antenna_length(freq_mhz: float) -> dict:
    """Ritorna le lunghezze d'antenna utili per una data frequenza (MHz).

    - full_wave/half_wave/quarter_wave: lunghezze teoriche in aria (m).
    - quarter_wave_practical_mm: quarto d'onda con velocity factor ~0.95,
      cioe' la lunghezza fisica consigliata di uno stilo verticale (mm).

    Per una ANT-500 (telescopica, elementi ~=~ 24 mm ciascuno) stimiamo anche
    quanti elementi/segmenti estrarre per avvicinarsi al quarto d'onda.
    """
    if freq_mhz <= 0:
        raise ValueError("La frequenza deve essere > 0 MHz")
    f_hz = freq_mhz * 1e6
    wavelength_m = _C / f_hz
    quarter_m = wavelength_m / 4.0
    quarter_practical_mm = quarter_m * _ANTENNA_VELOCITY_FACTOR * 1000.0

    # Segmento telescopico ANT-500 ~ 24 mm; stima grossolana del numero di
    # segmenti da estrarre per un quarto d'onda pratico.
    ant500_segment_mm = 24.0
    ant500_segments = max(1, round(quarter_practical_mm / ant500_segment_mm))

    return {
        "freq_mhz": freq_mhz,
        "wavelength_m": wavelength_m,
        "half_wave_m": wavelength_m / 2.0,
        "quarter_wave_m": quarter_m,
        "quarter_wave_practical_mm": quarter_practical_mm,
        "ant500_segments": ant500_segments,
        "ant500_segment_mm": ant500_segment_mm,
    }


def format_antenna(freq_mhz: float) -> str:
    a = antenna_length(freq_mhz)
    in_band = TETRA_BAND_MHZ[0] <= freq_mhz <= TETRA_BAND_MHZ[1]
    band_note = "" if in_band else "  (fuori dalla banda TETRA 380-430 MHz)"
    lines = [
        f"Calcolo antenna per {freq_mhz:.4f} MHz{band_note}",
        f"  Lunghezza d'onda (lambda) : {a['wavelength_m']*100:.1f} cm",
        f"  Mezz'onda  (lambda/2)     : {a['half_wave_m']*100:.1f} cm",
        f"  Quarto d'onda (lambda/4)  : {a['quarter_wave_m']*100:.1f} cm (teorico)",
        f"  Stilo consigliato (~.95)  : {a['quarter_wave_practical_mm']/10:.1f} cm"
        f" ({a['quarter_wave_practical_mm']:.0f} mm)",
        f"  ANT-500 (telescopica)     : ~{a['ant500_segments']} segmenti estratti"
        f" (~{a['ant500_segment_mm']:.0f} mm/segmento)",
        "",
        "Preset di banda TETRA (380-430 MHz):",
    ]
    for name, mhz in BAND_PRESETS_MHZ.items():
        lines.append(f"  {mhz:7.1f} MHz  -  {name}")
    lines += [
        "",
        "Parametri di ricezione TETRA (riferimento):",
        "  Banda            : 380-430 MHz",
        "  Spaziatura canali: 25 kHz tra le portanti",
        "  Larghezza (WFM)  : ~=~ 32 kHz (impostazione tipo SDR#)",
        "  Accesso          : TDMA, 4 canali duplex per portante",
    ]
    return "\n".join(lines)


# ============================================================
# MODELLO DEL PANNELLO
# ============================================================

@dataclass
class Cell:
    """Una cella/portante osservata."""
    location_area: Optional[int] = None
    colour_code: Optional[int] = None
    dl_freq_hz: Optional[int] = None
    ul_freq_hz: Optional[int] = None
    last_seen: float = field(default_factory=time.time)


@dataclass
class NetworkInfo:
    """Metadati di rete estratti dal broadcast di sistema (tutti opzionali)."""
    mcc: Optional[int] = None
    mnc: Optional[int] = None
    location_area: Optional[int] = None
    colour_code: Optional[int] = None
    operating_mode: Optional[str] = None
    main_carrier_hz: Optional[int] = None
    ul_carrier_hz: Optional[int] = None
    aie_enabled: Optional[bool] = None          # Air Interface Encryption on/off
    encryption_type: Optional[int] = None        # valore ENC (algoritmo/KSG)
    security_class: Optional[int] = None
    cipher_key_id: Optional[int] = None
    authentication_required: Optional[bool] = None   # "Authentication Required On Cell"
    # Contatori/attivita'
    total_messages: int = 0
    encrypted_events: int = 0
    clear_events: int = 0
    last_ssi: Optional[str] = None
    last_update: float = field(default_factory=time.time)
    # Celle vicine osservate: chiave = (LA, CCODE) o freq
    cells: dict = field(default_factory=dict)

    @property
    def mni(self) -> Optional[str]:
        """Mobile Network Identity = MCC + MNC (rappresentazione compatta)."""
        if self.mcc is None or self.mnc is None:
            return None
        return f"{self.mcc}-{self.mnc}"

    def tea_label(self) -> str:
        """Etichetta leggibile per il tipo di cifratura air-interface."""
        if self.aie_enabled is False:
            return "CLEAR (nessuna AIE)"
        if self.encryption_type is None:
            return "ENCRYPTED (AIE)" if self.aie_enabled else "sconosciuto"
        # Mappa best-effort: il byte ENC indica l'algoritmo/KSG in uso.
        names = {0: "nessuna", 1: "TEA1", 2: "TEA2", 3: "TEA3", 4: "TEA4"}
        name = names.get(self.encryption_type, f"tipo 0x{self.encryption_type:02x}")
        return f"ENCRYPTED (AIE) - {name}"

    def security_class_label(self) -> str:
        if self.security_class is None:
            # Inferenza prudente solo come suggerimento, mai spacciata per certa.
            if self.aie_enabled is True:
                return "? (AIE attiva -> probabilmente classe 3)"
            if self.aie_enabled is False:
                return "? (nessuna AIE -> probabilmente classe 1)"
            return "?"
        descr = {1: "Classe 1 (clear)", 2: "Classe 2 (SCK)", 3: "Classe 3 (DCK/AIE)"}
        return descr.get(self.security_class, f"Classe {self.security_class}")


# ============================================================
# PARSER DEI MESSAGGI (token-based, come telive)
# ============================================================

# Estrae ogni blocco "TETMON_begin ... TETMON_end" da una riga.
_TETMON_RE = re.compile(r"TETMON_begin\s+(.*?)\s+TETMON_end")
# Token KEY:VALUE (VALUE = fino allo spazio successivo).
_TOKEN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(\S+)")

# Righe di debug "in chiaro" del ricevitore (non TETMON) da cui ricaviamo
# comunque qualcosa. Confermate dal sorgente osmo-tetra-sq5bpf-2.
_BNCH_SYSINFO_RE = re.compile(
    r"BNCH SYSINFO\s*\(DL\s+(\d+)\s*Hz,\s*UL\s+(\d+)\s*Hz\)"
    r"(?:.*service_details\s+0x([0-9a-fA-F]+))?"
)
_PLAIN_SECCLASS_RE = re.compile(r"security[_ ]?class[\s:=]+(\d+)", re.IGNORECASE)
_PLAIN_COLOUR_RE = re.compile(r"colou?r[_ ]?code[\s:=]+(\d+)", re.IGNORECASE)
_PLAIN_AUTH_RE = re.compile(r"authentication\s+required", re.IGNORECASE)


def _to_int(value: str) -> Optional[int]:
    try:
        if value.lower().startswith("0x"):
            return int(value, 16)
        return int(value)
    except (ValueError, TypeError):
        return None


class NetInfoParser:
    """Aggiorna un NetworkInfo a partire dalle righe del ricevitore."""

    def __init__(self) -> None:
        self.info = NetworkInfo()

    # -- API principale ------------------------------------------------------
    def feed_line(self, line: str) -> None:
        line = line.rstrip("\n")
        if not line:
            return
        handled = False
        for match in _TETMON_RE.finditer(line):
            self._handle_tetmon(match.group(1))
            handled = True
        if not handled:
            self._handle_plain(line)

    def feed(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.feed_line(line)

    # -- Messaggi strutturati TETMON ----------------------------------------
    def _handle_tetmon(self, body: str) -> None:
        tokens = {k.upper(): v for k, v in _TOKEN_RE.findall(body)}
        if not tokens:
            return
        info = self.info
        info.total_messages += 1
        info.last_update = time.time()

        if "MCC" in tokens:
            info.mcc = _to_int(tokens["MCC"]) or info.mcc
        if "MNC" in tokens:
            info.mnc = _to_int(tokens["MNC"]) if _to_int(tokens["MNC"]) is not None else info.mnc
        if "LA" in tokens:
            info.location_area = _to_int(tokens["LA"])
        if "CCODE" in tokens:
            info.colour_code = _to_int(tokens["CCODE"])
        if "DLF" in tokens:
            dl = _to_int(tokens["DLF"])
            if dl:
                info.main_carrier_hz = _normalize_freq_hz(dl)
        if "ULF" in tokens:
            ul = _to_int(tokens["ULF"])
            if ul:
                info.ul_carrier_hz = _normalize_freq_hz(ul)
        if "SECCLASS" in tokens or "SECURITY_CLASS" in tokens:
            info.security_class = _to_int(tokens.get("SECCLASS") or tokens.get("SECURITY_CLASS"))
        if "CKID" in tokens or "CIPHER_KEY_ID" in tokens:
            info.cipher_key_id = _to_int(tokens.get("CKID") or tokens.get("CIPHER_KEY_ID"))
        for akey in ("AUTH", "AUTHREQ", "AUTHENTICATION"):
            if akey in tokens:
                av = _to_int(tokens[akey])
                if av is not None:
                    info.authentication_required = bool(av)
                break
        if "SSI" in tokens:
            info.last_ssi = tokens["SSI"]

        # Cifratura: CRYPT/ENCR indicano l'uso dell'AIE; ENC indica l'algoritmo.
        crypt_flag = None
        for key in ("CRYPT", "ENCR", "DECR"):
            if key in tokens:
                v = _to_int(tokens[key])
                if v is not None:
                    crypt_flag = crypt_flag or bool(v)
        if crypt_flag is not None:
            info.aie_enabled = crypt_flag
            if crypt_flag:
                info.encrypted_events += 1
            else:
                info.clear_events += 1
        if "ENC" in tokens:
            enc = _to_int(tokens["ENC"])
            if enc is not None:
                info.encryption_type = enc
                if enc > 0:
                    info.aie_enabled = True

        self._update_cell(info)

    def _update_cell(self, info: NetworkInfo) -> None:
        if info.location_area is None and info.main_carrier_hz is None:
            return
        key = (info.location_area, info.colour_code, info.main_carrier_hz)
        cell = info.cells.get(key) or Cell()
        cell.location_area = info.location_area
        cell.colour_code = info.colour_code
        cell.dl_freq_hz = info.main_carrier_hz
        cell.ul_freq_hz = info.ul_carrier_hz
        cell.last_seen = time.time()
        info.cells[key] = cell

    # -- Righe di debug in chiaro -------------------------------------------
    def _handle_plain(self, line: str) -> None:
        info = self.info
        m = _BNCH_SYSINFO_RE.search(line)
        if m:
            info.total_messages += 1
            info.last_update = time.time()
            info.main_carrier_hz = _normalize_freq_hz(int(m.group(1)))
            info.ul_carrier_hz = _normalize_freq_hz(int(m.group(2)))
            info.operating_mode = info.operating_mode or "Voice+Data"
            self._update_cell(info)
            return
        m = _PLAIN_SECCLASS_RE.search(line)
        if m:
            info.security_class = _to_int(m.group(1))
        m = _PLAIN_COLOUR_RE.search(line)
        if m:
            info.colour_code = _to_int(m.group(1))
        if _PLAIN_AUTH_RE.search(line):
            info.authentication_required = True


def _normalize_freq_hz(value: int) -> int:
    """Uniforma un valore di frequenza a Hz (alcuni campi arrivano in kHz)."""
    if value <= 0:
        return value
    # Se sembra kHz (banda TETRA 380-430 MHz => 380000-430000 kHz), scala a Hz.
    if 100_000 <= value <= 1_000_000:
        return value * 1000
    return value


# ============================================================
# SORGENTI DI RIGHE (run / attach-file / attach-udp)
# ============================================================

def _find_receiver(rx_bin: Optional[str]) -> Optional[Path]:
    """Individua un launcher/binario del ricevitore TELIVE-2."""
    if rx_bin:
        p = Path(rx_bin)
        return p if p.exists() else None
    candidates = [
        OSMO_SRC / "run_receiver.sh",   # wrapper con log creato da install_telive2.py
        OSMO_SRC / "receiver1udp",      # wrapper del ricevitore osmo
        TETRA_BIN / "tetra-rx",
        OSMO_SRC / "tetra-rx",
    ]
    for c in candidates:
        if c.exists():
            return c
    which = shutil.which("tetra-rx")
    return Path(which) if which else None


def source_from_process(rx_bin: Optional[str], rxid: str = "1") -> Iterator[str]:
    """Lancia il ricevitore e restituisce le sue righe di stdout una a una."""
    receiver = _find_receiver(rx_bin)
    if receiver is None:
        raise FileNotFoundError(
            "Ricevitore 'tetra-rx' non trovato. Compila prima la catena TELIVE-2:\n"
            "  python3 install_telive2.py\n"
            "oppure indica il percorso con --rx-bin."
        )
    cmd = [str(receiver)]
    if receiver.name in ("run_receiver.sh", "receiver1udp"):
        cmd.append(rxid)
    logger.info("Avvio ricevitore: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd, cwd=str(receiver.parent),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            yield line
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def source_from_file(path: str, follow: bool = False) -> Iterator[str]:
    """Legge le righe da un file di log; con follow=True fa 'tail -f'."""
    p = Path(path)
    if not follow:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            yield from f
        return
    # Modalita' follow: coesiste con una sessione telive che scrive receiver.log.
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                time.sleep(0.2)


def source_from_udp(port: int, host: str = "127.0.0.1") -> Iterator[str]:
    """Riceve datagrammi UDP (i messaggi TETMON) e li restituisce come righe.
    Bind di default su 127.0.0.1: il ricevitore invia a telive in locale, quindi
    non serve esporsi su tutte le interfacce (passa host='0.0.0.0' se davvero
    ricevi da un'altra macchina)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    logger.info("In ascolto su UDP %s:%d per i messaggi TETMON...", host, port)
    try:
        while True:
            data, _ = sock.recvfrom(65535)
            text = data.decode("utf-8", errors="ignore")
            for line in text.splitlines():
                yield line
    finally:
        sock.close()


# ============================================================
# RENDERING
# ============================================================

def _fmt_hz(hz: Optional[int]) -> str:
    if not hz:
        return "-"
    return f"{hz/1e6:.4f} MHz"


def _fmt(value) -> str:
    return "-" if value is None else str(value)


def _fmt_bool(value: Optional[bool]) -> str:
    if value is None:
        return "-"
    return "si'" if value else "no"


def render_plain(info: NetworkInfo, freq_mhz: Optional[float]) -> str:
    lock = "??"
    if info.aie_enabled is True:
        lock = "🔐 ENCRYPTED (AIE)"
    elif info.aie_enabled is False:
        lock = "🔓 CLEAR"
    lines = [
        "==================== TETRA NETWORK INFO ====================",
        f" Sintonia         : {freq_mhz:.4f} MHz" if freq_mhz else " Sintonia         : -",
        f" MCC / MNC (MNI)  : {_fmt(info.mcc)} / {_fmt(info.mnc)}   (MNI {_fmt(info.mni)})",
        f" Location Area    : {_fmt(info.location_area)}",
        f" Colour Code      : {_fmt(info.colour_code)}",
        f" Operating mode   : {_fmt(info.operating_mode)}",
        f" Main carrier     : {_fmt_hz(info.main_carrier_hz)}   (UL {_fmt_hz(info.ul_carrier_hz)})",
        "------------------------ SICUREZZA -------------------------",
        f" Air Iface Encr.  : {lock}",
        f" Algoritmo        : {info.tea_label()}",
        f" Security class   : {info.security_class_label()}",
        f" Cipher Key ID    : {_fmt(info.cipher_key_id)}",
        f" Auth. su cella   : {_fmt_bool(info.authentication_required)}",
        "------------------------ ATTIVITA' -------------------------",
        f" Messaggi totali  : {info.total_messages}"
        f"  (cifrati {info.encrypted_events} / chiari {info.clear_events})",
        f" Ultimo SSI       : {_fmt(info.last_ssi)}",
        f" Celle viste      : {len(info.cells)}",
    ]
    for (la, cc, dl), cell in list(info.cells.items())[:8]:
        lines.append(f"   - LA {_fmt(la)}  CC {_fmt(cc)}  {_fmt_hz(dl)}")
    lines.append("============================================================")
    return "\n".join(lines)


def run_plain_loop(source: Iterator[str], freq_mhz: Optional[float],
                   as_json: bool, refresh: float = 1.0) -> None:
    parser = NetInfoParser()

    def _emit() -> None:
        if as_json:
            data = asdict(parser.info)
            data.pop("cells", None)
            data["mni"] = parser.info.mni
            print(json.dumps(data), flush=True)
        else:
            print(render_plain(parser.info, freq_mhz), flush=True)

    last_render = 0.0
    for line in source:
        parser.feed_line(line)
        now = time.time()
        if now - last_render >= refresh:
            last_render = now
            _emit()
    # Render finale: garantisce lo stato completo quando la sorgente e' finita
    # (es. un file non in follow) o dopo l'ultima riga arrivata.
    _emit()


def run_tui_loop(source: Iterator[str], freq_mhz: Optional[float]) -> None:
    """Pannello curses aggiornato in tempo reale. Se curses non e' disponibile,
    ricade sul rendering testuale."""
    try:
        import curses
    except ImportError:
        logger.warning("curses non disponibile: uso il rendering testuale.")
        run_plain_loop(source, freq_mhz, as_json=False)
        return

    parser = NetInfoParser()

    def _draw(stdscr) -> None:
        curses.curs_set(0)
        stdscr.nodelay(True)
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
        except curses.error:
            pass
        last = 0.0
        while True:
            try:
                line = next(source)
                parser.feed_line(line)
            except StopIteration:
                pass
            now = time.time()
            if now - last >= 0.5:
                last = now
                _paint(stdscr, curses, parser.info, freq_mhz)
            ch = stdscr.getch()
            if ch in (ord("q"), ord("Q")):
                break
            if not line:
                time.sleep(0.05)

    def _line(stdscr, curses_mod, y, label, value, color=0):
        try:
            stdscr.addstr(y, 2, f"{label:<18}", curses_mod.color_pair(3))
            stdscr.addstr(y, 22, str(value), curses_mod.color_pair(color))
        except curses_mod.error:
            pass

    def _paint(stdscr, curses_mod, info: NetworkInfo, freq: Optional[float]) -> None:
        stdscr.erase()
        try:
            stdscr.box()
            stdscr.addstr(0, 3, " TETRA NETWORK INFO (passivo) ", curses_mod.A_BOLD)
        except curses_mod.error:
            pass
        y = 2
        _line(stdscr, curses_mod, y, "Sintonia", f"{freq:.4f} MHz" if freq else "-"); y += 1
        _line(stdscr, curses_mod, y, "MCC / MNC", f"{_fmt(info.mcc)} / {_fmt(info.mnc)}  (MNI {_fmt(info.mni)})"); y += 1
        _line(stdscr, curses_mod, y, "Location Area", _fmt(info.location_area)); y += 1
        _line(stdscr, curses_mod, y, "Colour Code", _fmt(info.colour_code)); y += 1
        _line(stdscr, curses_mod, y, "Operating mode", _fmt(info.operating_mode)); y += 1
        _line(stdscr, curses_mod, y, "Main carrier", f"{_fmt_hz(info.main_carrier_hz)}  (UL {_fmt_hz(info.ul_carrier_hz)})"); y += 2

        if info.aie_enabled is True:
            _line(stdscr, curses_mod, y, "Encryption", "🔐 ENCRYPTED (AIE)", 2)
        elif info.aie_enabled is False:
            _line(stdscr, curses_mod, y, "Encryption", "🔓 CLEAR", 1)
        else:
            _line(stdscr, curses_mod, y, "Encryption", "?")
        y += 1
        _line(stdscr, curses_mod, y, "Algoritmo", info.tea_label()); y += 1
        _line(stdscr, curses_mod, y, "Security class", info.security_class_label()); y += 1
        _line(stdscr, curses_mod, y, "Cipher Key ID", _fmt(info.cipher_key_id)); y += 1
        _line(stdscr, curses_mod, y, "Auth. su cella", _fmt_bool(info.authentication_required)); y += 2

        _line(stdscr, curses_mod, y, "Messaggi", f"{info.total_messages}  (enc {info.encrypted_events}/clr {info.clear_events})"); y += 1
        _line(stdscr, curses_mod, y, "Ultimo SSI", _fmt(info.last_ssi)); y += 1
        _line(stdscr, curses_mod, y, "Celle viste", len(info.cells)); y += 1
        for (la, cc, dl), _cell in list(info.cells.items())[:6]:
            _line(stdscr, curses_mod, y, "  cella", f"LA {_fmt(la)}  CC {_fmt(cc)}  {_fmt_hz(dl)}"); y += 1
        try:
            maxy = stdscr.getmaxyx()[0]
            stdscr.addstr(maxy - 1, 2, " q = esci  |  passivo: nessuna decifratura ", curses_mod.A_DIM)
        except curses_mod.error:
            pass
        stdscr.refresh()

    import curses as _c
    _c.wrapper(_draw)


# ============================================================
# SELF-TEST (senza hardware)
# ============================================================

# Righe di esempio nel formato reale emesso dal ricevitore osmo-tetra-sq5bpf-2
# (i FUNC sono illustrativi: il parser e' agnostico al FUNC ed estrae i token).
_FIXTURE_LINES = [
    "TETMON_begin FUNC:NETINFO MCC:222 MNC:1 LA:1234 CCODE:12 DLF:392225000 ULF:382225000 AUTH:1 RX:1 TETMON_end",
    "BNCH SYSINFO (DL 392225000 Hz, UL 382225000 Hz), service_details 0x1234",
    "TETMON_begin FUNC:ENCINFO1 CRYPT:1 ENC:03 RX:1 TETMON_end",
    "TETMON_begin FUNC:CALL SSI:00012345 IDX:001 IDT:0 ENCR:1 RX:1 TETMON_end",
    "some unrelated debug line that must be ignored",
    "security_class: 3",
]


def run_self_test() -> int:
    parser = NetInfoParser()
    parser.feed(_FIXTURE_LINES)
    info = parser.info
    checks = {
        "MCC=222": info.mcc == 222,
        "MNC=1": info.mnc == 1,
        "MNI=222-1": info.mni == "222-1",
        "LA=1234": info.location_area == 1234,
        "ColourCode=12": info.colour_code == 12,
        "MainCarrier=392.225MHz": info.main_carrier_hz == 392_225_000,
        "AIE=on": info.aie_enabled is True,
        "EncType=3(TEA3)": info.encryption_type == 3,
        "SecurityClass=3": info.security_class == 3,
        "AuthRequired=on": info.authentication_required is True,
        "SSI parsed": info.last_ssi == "00012345",
        "OperatingMode set": info.operating_mode == "Voice+Data",
        "Cells>=1": len(info.cells) >= 1,
    }
    print("Self-test parser NetInfo:")
    ok = True
    for name, passed in checks.items():
        print(f"  [{'OK' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print()
    print(render_plain(info, freq_mhz=392.225))
    print()
    print("Self-test antenna (392.225 MHz):")
    print(format_antenna(392.225))
    return 0 if ok else 1


# ============================================================
# CLI
# ============================================================

def setup_logging(logfile: Optional[str]) -> None:
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        target = Path(logfile) if logfile else (LOG_DIR / "netscanner.log")
        fh = logging.FileHandler(target, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    except OSError:
        pass


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Pannello passivo Network Info per TETRA (parte della suite TetraEar).",
    )
    src = p.add_mutually_exclusive_group()
    src.add_argument("--run", action="store_true",
                     help="Lancia il ricevitore TELIVE-2 e mostra il pannello (default se non specifichi altro)")
    src.add_argument("--attach-file", metavar="PATH",
                     help="Legge le righe da un file di log del ricevitore (usa --follow per tail -f)")
    src.add_argument("--attach-udp", type=int, nargs="?", const=DEFAULT_TETMON_UDP_PORT,
                     metavar="PORT", help=f"Legge i messaggi TETMON da UDP (default porta {DEFAULT_TETMON_UDP_PORT})")
    p.add_argument("--follow", action="store_true", help="Con --attach-file: segue il file in tempo reale")
    p.add_argument("--rx-bin", metavar="PATH", help="Percorso esplicito del ricevitore (tetra-rx/receiver1udp/run_receiver.sh)")
    p.add_argument("--rxid", default="1", help="RXID passato al ricevitore (default 1)")
    p.add_argument("-f", "--freq", type=float, metavar="MHZ", help="Frequenza sintonizzata (solo per il display)")
    p.add_argument("--antenna", type=float, metavar="MHZ", help="Stampa il calcolo antenna per questa frequenza ed esce")
    p.add_argument("--json", action="store_true", help="Emette una riga JSON per aggiornamento invece del pannello")
    p.add_argument("--no-tui", action="store_true", help="Rendering testuale invece del pannello curses")
    p.add_argument("--self-test", action="store_true", help="Prova il parser su dati di esempio ed esce (no hardware)")
    p.add_argument("--log", metavar="FILE", help="File di log (default logs/netscanner.log)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    # Percorsi che non toccano l'hardware: gestiti prima del logging pesante.
    if args.antenna is not None:
        print(format_antenna(args.antenna))
        return 0
    if args.self_test:
        return run_self_test()

    setup_logging(args.log)
    logger.info("====== TETRA Network Scanner v%s (passivo) ======", SCRIPT_VERSION)

    # Selezione della sorgente.
    try:
        if args.attach_file:
            source = source_from_file(args.attach_file, follow=args.follow)
            logger.info("Sorgente: file %s%s", args.attach_file, " (follow)" if args.follow else "")
        elif args.attach_udp is not None:
            source = source_from_udp(args.attach_udp)
            logger.info("Sorgente: UDP porta %d", args.attach_udp)
        else:
            source = source_from_process(args.rx_bin, rxid=args.rxid)
            logger.info("Sorgente: ricevitore live (--run)")
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2

    try:
        if args.json or args.no_tui:
            run_plain_loop(source, args.freq, as_json=args.json)
        else:
            run_tui_loop(source, args.freq)
    except KeyboardInterrupt:
        logger.info("\nInterrotto.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
