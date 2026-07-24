#!/usr/bin/env python3
"""
install_telive2_windows.py -- TELIVE-2 su Windows tramite WSL2
==============================================================

Versione Windows, complementare a install_telive2.py (Linux). Prepara la
catena TELIVE-2 (osmo-tetra-sq5bpf-2 + codec ETSI + telive) che aggiunge a
TetraEar la DECIFRATURA vocale a CHIAVE NOTA, inclusa la chiave TEA-1
accorciata a 32 bit (backdoor Midnight Blue).

DIFFERENZA IMPORTANTE RISPETTO A LINUX
--------------------------------------
La catena TELIVE-2 e' profondamente POSIX: usa 'libosmocore', GNU Radio, script
di shell, ncurses/libxml2 e una cartella di lavoro fissa '/tetra'. Non esiste
una build Windows nativa affidabile di telive/osmo-tetra, e MSYS2 (usato da
install_windows.py per il solo codec) non pacchettizza 'libosmocore'.

La via Windows CORRETTA e AFFIDABILE e' quindi WSL2 (Ubuntu dentro Windows):
li' gira, IDENTICO e senza modifiche, l'installer Linux install_telive2.py.
Questo script:

  1. verifica che WSL2 sia disponibile e che ci sia una distro Ubuntu/Debian;
  2. se c'e', lancia dentro WSL il nostro install_telive2.py (build completa);
  3. se manca, stampa i passi guidati per abilitare WSL (nessuna azione
     distruttiva) e poi rilanciare.

Uso:
    python install_telive2_windows.py              # rileva WSL ed esegue la build
    python install_telive2_windows.py --check      # verifica soltanto lo stato
    python install_telive2_windows.py --guide-only # stampa solo i passi guidati

NOTA: questo script NON e' stato testato su Windows reale (l'ambiente di
sviluppo e' Linux). E' scritto per essere prudente: non installa nulla in
automatico sull'host Windows; la build vera avviene dentro WSL con lo stesso
codice della versione Linux.

DISCLAIMER: si DECIFRA solo con chiave gia' nota. Questi strumenti non craccano
il TETRA. Usa solo dove consentito dalle leggi della tua giurisdizione. Vedi
DISCLAIMER.md.
"""

import argparse
import logging
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ============================================================
# CONFIGURAZIONE
# ============================================================

SCRIPT_VERSION = "1.0"
MIN_PYTHON = (3, 8)

INSTALLER_DIR = Path(__file__).resolve().parent
# Tutti i log finiscono in ./logs/ accanto allo script (come gli altri installer).
LOG_DIR = INSTALLER_DIR / "logs"
LOG_FILE = LOG_DIR / "install_telive2.log"

# L'installer Linux vero e proprio (viene eseguito DENTRO WSL).
LINUX_INSTALLER = INSTALLER_DIR / "install_telive2.py"

# Distro consigliata da installare via 'wsl --install'.
RECOMMENDED_DISTRO = "Ubuntu"

# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("telive2_win")


def setup_logging() -> None:
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        logger.addHandler(fh)
    except OSError:
        pass


def step(title: str) -> None:
    logger.info("")
    logger.info("=" * 60)
    logger.info(" %s", title)
    logger.info("=" * 60)


# ============================================================
# CONTROLLI PRELIMINARI
# ============================================================

def check_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        logger.error("Serve Python >= %s.%s, trovato %s.", *MIN_PYTHON, platform.python_version())
        raise SystemExit(1)
    logger.info("[OK] Python %s", platform.python_version())


def check_operating_system() -> None:
    if platform.system() != "Windows":
        logger.warning(
            "[ATTENZIONE] Questo installer e' pensato per Windows. Su Linux usa "
            "direttamente install_telive2.py."
        )


def log_system_diagnostics() -> None:
    """Registra le informazioni di sistema utili a diagnosticare i problemi:
    versione di Windows, architettura, stato e distribuzioni WSL. I dettagli
    piu' verbosi (output di 'wsl --status' / 'wsl -l -v') vanno nel file di log."""
    logger.info("")
    logger.info("----- DIAGNOSTICA DI SISTEMA -----")
    logger.info(" sistema       : %s %s (%s)", platform.system(), platform.release(), platform.machine())
    logger.info(" python        : %s", platform.python_version())
    wsl = _wsl_exe()
    logger.info(" wsl.exe       : %s", wsl or "assente")
    if wsl:
        try:
            status = subprocess.run([wsl, "--status"], capture_output=True, timeout=30)
            logger.debug(" wsl --status:\n%s", _decode_wsl_output(status.stdout).strip())
            listing = subprocess.run([wsl, "-l", "-v"], capture_output=True, timeout=30)
            logger.debug(" wsl -l -v:\n%s", _decode_wsl_output(listing.stdout).strip())
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug(" (impossibile interrogare WSL: %s)", exc)
    logger.info(" (dettagli WSL completi nel file %s)", LOG_FILE)
    logger.info("----------------------------------")


# ============================================================
# RILEVAMENTO WSL
# ============================================================

def _wsl_exe() -> str | None:
    """Percorso di wsl.exe, se presente nel PATH di Windows."""
    return shutil.which("wsl") or shutil.which("wsl.exe")


def _decode_wsl_output(raw: bytes) -> str:
    """L'output di 'wsl.exe -l' e' spesso in UTF-16LE. Proviamo UTF-16, poi UTF-8."""
    for enc in ("utf-16-le", "utf-16", "utf-8"):
        try:
            text = raw.decode(enc)
            # UTF-16 mal-decodificato lascia molti '\x00': se ne restano, riprova.
            if "\x00" not in text:
                return text
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="ignore")


def wsl_available() -> bool:
    wsl = _wsl_exe()
    if not wsl:
        return False
    try:
        result = subprocess.run([wsl, "--status"], capture_output=True, timeout=30)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def wsl_distros() -> list:
    """Elenco dei nomi delle distro WSL installate (vuoto se nessuna)."""
    wsl = _wsl_exe()
    if not wsl:
        return []
    try:
        result = subprocess.run([wsl, "-l", "-q"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    text = _decode_wsl_output(result.stdout)
    return [line.strip() for line in text.splitlines() if line.strip()]


# ============================================================
# ESECUZIONE DENTRO WSL
# ============================================================

def _to_wsl_path(win_path: Path) -> str | None:
    """Converte un percorso Windows nel corrispondente percorso WSL (/mnt/...)."""
    wsl = _wsl_exe()
    if not wsl:
        return None
    try:
        result = subprocess.run(
            [wsl, "wslpath", "-a", str(win_path)],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0:
            return _decode_wsl_output(result.stdout).strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def run_in_wsl(extra_args: list) -> int:
    """Esegue install_telive2.py DENTRO WSL, con stdio ereditato (cosi' l'utente
    puo' rispondere ai prompt sudo/apt). Ritorna il codice di uscita."""
    wsl = _wsl_exe()
    if not wsl:
        logger.error("[ERRORE] wsl.exe non trovato.")
        return 1

    wsl_installer = _to_wsl_path(LINUX_INSTALLER)
    if not wsl_installer:
        logger.error(
            "[ERRORE] Non riesco a convertire il percorso dell'installer per WSL. "
            "Aprilo a mano: dentro Ubuntu esegui 'python3 <percorso>/install_telive2.py'."
        )
        return 1

    # -l shell di login (PATH completo, incl. python3), -i interattiva (prompt sudo).
    args_str = " ".join(f"'{a}'" for a in extra_args)
    remote_cmd = f"python3 '{wsl_installer}' {args_str}".strip()
    step("Avvio della build TELIVE-2 dentro WSL (Ubuntu)")
    logger.info("Eseguo in WSL: %s", remote_cmd)
    logger.info("(potrebbe chiederti la password sudo dentro Ubuntu)")
    try:
        # Nessun capture: stdio ereditato per i prompt interattivi.
        result = subprocess.run([wsl, "-e", "bash", "-lic", remote_cmd])
        return result.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("[ERRORE] Esecuzione in WSL fallita: %s", exc)
        return 1


# ============================================================
# PASSI GUIDATI (quando WSL non c'e')
# ============================================================

def print_wsl_setup_guide() -> None:
    step("Come abilitare WSL2 (una volta sola)")
    logger.info(
        "La catena TELIVE-2 gira su Windows tramite WSL2 (Ubuntu dentro Windows).\n"
        "\n"
        "1) Apri PowerShell COME AMMINISTRATORE ed esegui:\n"
        "       wsl --install -d %s\n"
        "   poi RIAVVIA il PC quando richiesto.\n"
        "\n"
        "2) Al primo avvio Ubuntu ti chiede di creare un utente e una password\n"
        "   (servira' per 'sudo'). Aggiorna i pacchetti:\n"
        "       sudo apt update\n"
        "\n"
        "3) Rilancia QUESTO installer da Windows:\n"
        "       python install_telive2_windows.py\n"
        "   (rilevera' WSL ed eseguira' la build dentro Ubuntu)\n"
        "\n"
        "   In alternativa, dentro Ubuntu puoi eseguire direttamente l'installer\n"
        "   Linux, che si trova sul disco Windows sotto /mnt/ :\n"
        "       python3 /mnt/c/.../TetraEarUbuntu/install_telive2.py\n"
        "\n"
        "NOTA GUI: il flowgraph GNU Radio (gnuradio-companion) e' un'app grafica.\n"
        "Su Windows 11 WSLg mostra le finestre Linux automaticamente. Su Windows 10\n"
        "serve un server X (es. VcXsrv) e 'export DISPLAY=...'.",
        RECOMMENDED_DISTRO,
    )


# ============================================================
# VERIFICA / RIEPILOGO
# ============================================================

def _telive_built_in_wsl() -> bool:
    """True se dentro WSL risulta gia' compilato telive (o e' in /tetra/bin)."""
    wsl = _wsl_exe()
    if not wsl:
        return False
    try:
        result = subprocess.run(
            [wsl, "-e", "bash", "-lic",
             "command -v telive >/dev/null 2>&1 || test -x /tetra/bin/telive"],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def verify_and_summary(completed: bool = True) -> bool:
    step("Riepilogo")
    has_wsl = wsl_available()
    distros = wsl_distros() if has_wsl else []
    built = _telive_built_in_wsl() if has_wsl and distros else False

    logger.info("  %s WSL2 disponibile", "[OK]   " if has_wsl else "[MANCA]")
    logger.info("  %s Distro WSL installate: %s",
                "[OK]   " if distros else "[MANCA]",
                ", ".join(distros) if distros else "(nessuna)")
    logger.info("  %s telive compilato dentro WSL", "[OK]   " if built else "[DA FARE]")

    logger.info("")
    logger.info("Guida d'uso completa: README.md (sezione TELIVE-2 / Windows)")
    logger.info("Log di questo launcher : %s", LOG_FILE)
    logger.info("Log DETTAGLIATI della build (dentro WSL): la cartella logs/ creata")
    logger.info("dall'installer Linux, accanto a install_telive2.py — contiene")
    logger.info("install_telive2.log (DEBUG su file), receiver.log, gnuradio.log")
    logger.info("e telive-runtime.log.")

    if built:
        logger.info("")
        logger.info("Per USARLO, apri Ubuntu (WSL) e segui le stesse istruzioni della")
        logger.info("versione Linux stampate al termine di install_telive2.py:")
        logger.info("  - GNU Radio:   gnuradio-companion <...>.grc")
        logger.info("  - receiver:    cd .../osmo-tetra-sq5bpf-2/src && ./receiver1udp 1")
        logger.info("  - telive:      cd .../telive-2 && ./telive")
        logger.info("  - decifra:     ./tetra-rx -r -k <keyfile> -s   (chiave GIA' nota)")
    return built


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installer TELIVE-2 per Windows (esegue la catena Linux dentro WSL2)"
    )
    parser.add_argument("--check", action="store_true",
                        help="Verifica soltanto lo stato (WSL, distro, build), senza fare nulla")
    parser.add_argument("--guide-only", action="store_true",
                        help="Stampa solo i passi guidati, senza eseguire la build")
    parser.add_argument("--no-gnuradio", action="store_true",
                        help="Passa --no-gnuradio all'installer Linux (GNU Radio gia' presente in WSL)")
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()

    logger.info("====== Installer TELIVE-2 (Windows/WSL) v%s ======", SCRIPT_VERSION)
    logger.info("Log completo in: %s", LOG_FILE)
    log_system_diagnostics()

    if args.check:
        verify_and_summary(completed=False)
        return 0

    check_python_version()
    check_operating_system()

    if not LINUX_INSTALLER.is_file():
        logger.error(
            "[ERRORE] Non trovo %s accanto a questo script. Servono entrambi i file "
            "nella stessa cartella.", LINUX_INSTALLER.name,
        )
        return 1

    if args.guide_only:
        print_wsl_setup_guide()
        return 0

    step("Rilevamento WSL2")
    if not wsl_available():
        logger.warning("[ATTENZIONE] WSL2 non risulta disponibile su questo sistema.")
        print_wsl_setup_guide()
        return 1

    distros = wsl_distros()
    if not distros:
        logger.warning(
            "[ATTENZIONE] WSL c'e', ma non e' installata nessuna distro Linux."
        )
        print_wsl_setup_guide()
        return 1

    logger.info("[OK] WSL2 disponibile. Distro trovate: %s", ", ".join(distros))

    extra_args = ["--no-gnuradio"] if args.no_gnuradio else []
    rc = run_in_wsl(extra_args)

    ok = verify_and_summary()
    if rc != 0 and not ok:
        logger.warning(
            "\n[NOTA] La build in WSL non risulta completata (codice %s). Controlla i "
            "messaggi qui sopra e in %s.", rc, LOG_FILE,
        )
    return 0 if ok else (rc or 1)


if __name__ == "__main__":
    sys.exit(main())
