#!/usr/bin/env python3
"""
install_tetra_netscanner.py -- Pannello "Network Info" TETRA (wiring)
====================================================================

Strumento complementare alla suite TetraEar. Prepara e collega
`tetra_netscanner.py`: un pannello PASSIVO che mostra i parametri di rete
trasmessi in chiaro nel broadcast TETRA (MCC/MNC/LA/Colour Code, portante,
stato cifratura AIE, security class, cipher key id) -- ispirato al plugin
descritto nell'articolo "Interception of TETRA radio".

Il pannello legge le righe del ricevitore osmo-tetra 'tetra-rx', che viene
compilato dalla catena TELIVE-2 (install_telive2.py). Questo installer NON
ricompila nulla di pesante: verifica soltanto che il ricevitore ci sia, crea
il launcher `avvia_netscanner.sh` e registra i log in logs/.

Uso:
    python3 install_tetra_netscanner.py            # verifica + crea il launcher
    python3 install_tetra_netscanner.py --check    # solo verifica, non tocca nulla
    python3 install_tetra_netscanner.py --no-launcher

Filosofia identica agli altri installer del repo: ogni passo a schermo e in
logs/install_netscanner.log; best-effort dove possibile.

DISCLAIMER: strumento PASSIVO (nessuna decifratura, nessun recupero chiavi).
Usa solo dove consentito dalle leggi della tua giurisdizione. Vedi DISCLAIMER.md.
"""

import argparse
import logging
import os
import shutil
import stat
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
LAUNCHER = INSTALLER_DIR / "avvia_netscanner.sh"

# Percorsi dove la catena TELIVE-2 lascia il ricevitore (vedi install_telive2.py).
TETRA_BIN = Path("/tetra") / "bin"
OSMO_SRC = INSTALLER_DIR / "telive2" / "osmo-tetra-sq5bpf-2" / "src"

logger = logging.getLogger("netscanner_install")


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
# VERIFICHE
# ============================================================

def find_receiver() -> Path | None:
    """Individua un launcher/binario del ricevitore TELIVE-2, se presente."""
    candidates = [
        OSMO_SRC / "run_receiver.sh",
        OSMO_SRC / "receiver1udp",
        TETRA_BIN / "tetra-rx",
        OSMO_SRC / "tetra-rx",
    ]
    for c in candidates:
        if c.exists():
            return c
    which = shutil.which("tetra-rx")
    return Path(which) if which else None


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
    logger.info("  %s modulo curses (pannello TUI; opzionale, c'e' il fallback testuale)",
                "[OK]   " if ok else "[NOTA] ")
    return ok


def check_tool() -> bool:
    ok = TOOL.is_file()
    logger.info("  %s tetra_netscanner.py", "[OK]   " if ok else "[MANCA]")
    return ok


def check_receiver() -> bool:
    receiver = find_receiver()
    if receiver is not None:
        logger.info("  [OK]    ricevitore TELIVE-2: %s", receiver)
        return True
    logger.info("  [MANCA] ricevitore 'tetra-rx' (catena TELIVE-2 non compilata)")
    return False


def verify(completed_install: bool = True) -> bool:
    step("Verifica")
    py_ok = check_python_version()
    check_curses()  # solo informativo
    tool_ok = check_tool()
    rx_ok = check_receiver()

    if not rx_ok:
        logger.info("")
        logger.info("  Per la modalita' live serve il ricevitore TETRA. Compilalo con:")
        logger.info("      python3 install_telive2.py")
        logger.info("  In alternativa puoi comunque usare:")
        logger.info("      python3 tetra_netscanner.py --antenna 392.225   (calcolo antenna)")
        logger.info("      python3 tetra_netscanner.py --self-test         (prova il parser)")
        logger.info("      python3 tetra_netscanner.py --attach-file <log> (rilettura di un log)")

    core_ok = py_ok and tool_ok
    if completed_install and core_ok:
        logger.info("")
        logger.info("[OK] Network Scanner pronto%s.",
                    "" if rx_ok else " (modalita' offline; ricevitore assente)")
    return core_ok


# ============================================================
# LAUNCHER
# ============================================================

def create_launcher() -> None:
    step("Creazione del launcher avvia_netscanner.sh")
    content = f"""#!/usr/bin/env bash
# ============================================================
#  avvia_netscanner.sh -- Pannello passivo Network Info TETRA
# ============================================================
#  Uso:
#     ./avvia_netscanner.sh [FREQUENZA_MHz] [argomenti extra...]
#  Esempi:
#     ./avvia_netscanner.sh 392.225                 # modo automatico
#     ./avvia_netscanner.sh 392.225 --run           # forza il ricevitore live
#     ./avvia_netscanner.sh 392.225 --no-tui        # rendering testuale
#
#  Se esiste gia' un log del ricevitore (logs/receiver.log, scritto dalla
#  catena TELIVE-2), il pannello lo SEGUE in tempo reale: cosi' convive con
#  una normale sessione telive senza contendersi la chiavetta. Altrimenti
#  avvia direttamente il ricevitore (--run).
# ============================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FREQ="392.225"
if [ "${{1:-}}" != "" ] && [[ "${{1:-}}" =~ ^[0-9.]+$ ]]; then
    FREQ="$1"; shift
fi

cd "$HERE"
mkdir -p logs
RECV_LOG="logs/receiver.log"

# Se l'utente non ha gia' scelto una sorgente, decidila in automatico.
HAS_SOURCE=0
for a in "$@"; do
    case "$a" in
        --run|--attach-file|--attach-udp) HAS_SOURCE=1 ;;
    esac
done

ARGS=(-f "$FREQ")
if [ "$HAS_SOURCE" -eq 0 ]; then
    if [ -f "$RECV_LOG" ]; then
        echo "[info] Seguo $RECV_LOG (convive con telive). Usa --run per il ricevitore diretto."
        ARGS+=(--attach-file "$RECV_LOG" --follow)
    else
        ARGS+=(--run)
    fi
fi

exec python3 "$HERE/tetra_netscanner.py" "${{ARGS[@]}}" "$@"
"""
    try:
        LAUNCHER.write_text(content, encoding="utf-8")
        LAUNCHER.chmod(LAUNCHER.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        logger.info("[OK] Launcher creato: %s", LAUNCHER)
        logger.info("     Avvio: ./avvia_netscanner.sh 392.225")
    except OSError as exc:
        logger.warning("[ATTENZIONE] Non ho potuto creare il launcher (%s).", exc)


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prepara il pannello passivo Network Info TETRA (tetra_netscanner.py)."
    )
    p.add_argument("--check", action="store_true",
                   help="Verifica soltanto cosa e' presente, senza creare nulla")
    p.add_argument("--no-launcher", action="store_true",
                   help="Non creare avvia_netscanner.sh")
    return p.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()
    logger.info("====== Installer TETRA Network Scanner v%s ======", SCRIPT_VERSION)
    logger.info("Log completo in: %s", LOG_FILE)

    if args.check:
        verify(completed_install=False)
        return 0

    if not TOOL.is_file():
        logger.error("[ERRORE] Manca %s accanto a questo installer.", TOOL)
        return 1

    # Il tool e' Python puro (stdlib): niente da compilare. Rendiamolo eseguibile.
    try:
        TOOL.chmod(TOOL.stat().st_mode | stat.S_IEXEC)
    except OSError:
        pass

    if not args.no_launcher:
        create_launcher()

    ok = verify(completed_install=True)
    logger.info("")
    logger.info("Come si usa (pannello PASSIVO, nessuna decifratura):")
    logger.info("  ./avvia_netscanner.sh 392.225")
    logger.info("  python3 tetra_netscanner.py --antenna 392.225   # calcolo antenna")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
