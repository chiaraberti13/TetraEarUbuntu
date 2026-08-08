#!/usr/bin/env python3
"""
install_tetra_netscanner_windows.py -- Pannello Network Info TETRA (Windows)
===========================================================================

Versione Windows, complementare a install_tetra_netscanner.py (Linux). Prepara
`tetra_netscanner.py`: il pannello PASSIVO che mostra i parametri di rete
trasmessi in chiaro nel broadcast TETRA (MCC/MNC/LA/Colour Code, portante,
stato cifratura AIE, security class, cipher key id) -- ispirato all'articolo
"Interception of TETRA radio".

COME SU WINDOWS
---------------
Il pannello LIVE legge l'output del ricevitore osmo-tetra 'tetra-rx', che su
Windows -- esattamente come tutta la catena TELIVE-2 -- gira dentro WSL2
(Ubuntu dentro Windows): li' viene gia' preparato in automatico dall'installer
Linux (install_telive2.py -> install_tetra_netscanner.py), col launcher
avvia_netscanner.sh.

Su Windows NATIVO restano comunque disponibili le funzioni che non usano la
chiavetta (Python puro, nessuna dipendenza):
    * il calcolo della lunghezza d'antenna
    * il --self-test del parser
    * la rilettura di un log del ricevitore (--attach-file)

Questo installer:
  1. verifica Python (e, informativo, il modulo curses; c'e' comunque il
     fallback testuale);
  2. crea il launcher nativo "Avvia NetScanner.bat" (che usa WSL per il
     pannello live se presente, altrimenti mostra il calcolo antenna);
  3. non compila nulla (il tool e' Python puro).

Uso:
    python install_tetra_netscanner_windows.py            # verifica + crea il .bat
    python install_tetra_netscanner_windows.py --check    # solo verifica
    python install_tetra_netscanner_windows.py --no-launcher

DISCLAIMER: strumento PASSIVO (nessuna decifratura, nessun recupero chiavi).
Usa solo dove consentito dalle leggi della tua giurisdizione. Vedi DISCLAIMER.md.
"""

import argparse
import logging
import platform
import shutil
import sys
from pathlib import Path

# ============================================================
# CONFIGURAZIONE
# ============================================================

SCRIPT_VERSION = "1.0"
MIN_PYTHON = (3, 8)

INSTALLER_DIR = Path(__file__).resolve().parent
LOG_DIR = INSTALLER_DIR / "logs"
LOG_FILE = LOG_DIR / "install_netscanner.log"

TOOL = INSTALLER_DIR / "tetra_netscanner.py"
LAUNCHER_BAT = INSTALLER_DIR / "Avvia NetScanner.bat"

logger = logging.getLogger("netscanner_win")


# ============================================================
# LOGGING / UTILITY
# ============================================================

def setup_logging() -> None:
    logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
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


def _wsl_exe() -> str | None:
    return shutil.which("wsl") or shutil.which("wsl.exe")


# ============================================================
# VERIFICHE
# ============================================================

def check_python_version() -> bool:
    ok = sys.version_info >= MIN_PYTHON
    logger.info("  %s Python %d.%d (trovato %d.%d)",
                "[OK]   " if ok else "[MANCA]",
                MIN_PYTHON[0], MIN_PYTHON[1],
                sys.version_info[0], sys.version_info[1])
    return ok


def check_curses() -> bool:
    try:
        import curses  # noqa: F401
        ok = True
    except ImportError:
        ok = False
    if ok:
        logger.info("  [OK]    modulo curses (pannello TUI)")
    else:
        logger.info("  [NOTA]  modulo curses assente su Windows nativo: c'e' il "
                    "fallback testuale. Per il pannello a colori: pip install windows-curses")
    return ok


def check_tool() -> bool:
    ok = TOOL.is_file()
    logger.info("  %s tetra_netscanner.py", "[OK]   " if ok else "[MANCA]")
    return ok


def check_wsl() -> bool:
    ok = _wsl_exe() is not None
    logger.info("  %s WSL (per il pannello LIVE col ricevitore TETRA)",
                "[OK]   " if ok else "[NOTA] ")
    if not ok:
        logger.info("          Senza WSL restano attive le funzioni offline "
                    "(--antenna, --self-test, --attach-file).")
    return ok


def verify(completed_install: bool = True) -> bool:
    step("Verifica")
    py_ok = check_python_version()
    check_curses()   # informativo
    tool_ok = check_tool()
    wsl_ok = check_wsl()

    if not wsl_ok:
        logger.info("")
        logger.info("  Per il pannello LIVE su Windows serve WSL2 + la catena TELIVE-2:")
        logger.info("      python install_telive2_windows.py")
        logger.info("  (prepara tutto DENTRO WSL, incluso avvia_netscanner.sh)")
    logger.info("")
    logger.info("  Funzioni disponibili SUBITO su Windows nativo (senza chiavetta):")
    logger.info("      python tetra_netscanner.py --antenna 392.225")
    logger.info("      python tetra_netscanner.py --self-test")

    core_ok = py_ok and tool_ok
    if completed_install and core_ok:
        logger.info("")
        logger.info("[OK] Network Scanner pronto (Windows).")
    return core_ok


# ============================================================
# LAUNCHER NATIVO (.bat)
# ============================================================

def create_launcher() -> None:
    step("Creazione del launcher 'Avvia NetScanner.bat'")
    # Il .bat usa WSL per il pannello LIVE (li' c'e' il ricevitore tetra-rx);
    # senza WSL mostra il calcolo antenna (offline, Python puro).
    content = (
        "@echo off\r\n"
        "REM ============================================================\r\n"
        "REM  Avvia NetScanner.bat -- Pannello passivo Network Info TETRA\r\n"
        "REM  Uso:  \"Avvia NetScanner.bat\" [FREQUENZA_MHz]\r\n"
        "REM  Il pannello LIVE gira in WSL (dove c'e' il ricevitore TETRA).\r\n"
        "REM  Senza WSL viene mostrato il solo calcolo antenna (offline).\r\n"
        "REM ============================================================\r\n"
        "setlocal\r\n"
        "set \"FREQ=%~1\"\r\n"
        "if \"%FREQ%\"==\"\" set \"FREQ=392.225\"\r\n"
        "where wsl >nul 2>nul\r\n"
        "if %errorlevel%==0 (\r\n"
        "  echo [info] Avvio del pannello Network Info dentro WSL su %FREQ% MHz ...\r\n"
        "  echo [info] ^(Live: richiede la catena TELIVE-2 gia' compilata in WSL^)\r\n"
        "  wsl -e bash -lic \"cd \\\"$(wslpath -a '%~dp0')\\\" 2>/dev/null && ./avvia_netscanner.sh %FREQ%\"\r\n"
        ") else (\r\n"
        "  echo [info] WSL non trovato: mostro il calcolo antenna ^(offline^).\r\n"
        "  python \"%~dp0tetra_netscanner.py\" --antenna %FREQ%\r\n"
        "  echo.\r\n"
        "  echo Per il pannello LIVE installa WSL2 e la catena TELIVE-2:\r\n"
        "  echo     python install_telive2_windows.py\r\n"
        ")\r\n"
        "endlocal\r\n"
        "pause\r\n"
    )
    try:
        LAUNCHER_BAT.write_text(content, encoding="utf-8")
        logger.info("[OK] Launcher creato: %s", LAUNCHER_BAT)
        # Copia sul Desktop, best-effort (come fanno gli altri installer Windows).
        try:
            desktop = Path.home() / "Desktop"
            if desktop.is_dir():
                shutil.copy2(LAUNCHER_BAT, desktop / LAUNCHER_BAT.name)
                logger.info("[OK] Copia sul Desktop: %s", desktop / LAUNCHER_BAT.name)
        except OSError:
            pass
    except OSError as exc:
        logger.warning("[ATTENZIONE] Non ho potuto creare il launcher (%s).", exc)


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prepara il pannello passivo Network Info TETRA su Windows (tetra_netscanner.py)."
    )
    p.add_argument("--check", action="store_true",
                   help="Verifica soltanto cosa e' presente, senza creare nulla")
    p.add_argument("--no-launcher", action="store_true",
                   help="Non creare 'Avvia NetScanner.bat'")
    return p.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()
    logger.info("====== Installer TETRA Network Scanner (Windows) v%s ======", SCRIPT_VERSION)
    logger.info("Log completo in: %s", LOG_FILE)

    if platform.system() != "Windows":
        logger.warning(
            "[ATTENZIONE] Questo installer e' pensato per Windows. Su Linux usa "
            "direttamente install_tetra_netscanner.py."
        )

    if args.check:
        verify(completed_install=False)
        return 0

    if not TOOL.is_file():
        logger.error("[ERRORE] Manca %s accanto a questo installer.", TOOL)
        return 1

    if not args.no_launcher:
        create_launcher()

    ok = verify(completed_install=True)
    logger.info("")
    logger.info("Come si usa (pannello PASSIVO, nessuna decifratura):")
    logger.info("  doppio clic su 'Avvia NetScanner.bat'  (o passagli la frequenza)")
    logger.info("  python tetra_netscanner.py --antenna 392.225   # calcolo antenna")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
