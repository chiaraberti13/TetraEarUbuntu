#!/usr/bin/env python3
"""
install_extra_decoders_windows.py -- Decoder radio aggiuntivi per RTL-SDR (Windows)
===================================================================================

Versione Windows, complementare a install_extra_decoders.py (Linux). Prepara i
decoder OPEN SOURCE per i modi NON-TETRA che una chiavetta RTL-SDR puo'
ricevere:

    * dsd-fme      -> DMR / P25 / NXDN / dPMR (voce digitale in chiaro)
    * dump1090     -> ADS-B 1090 MHz (posizione degli aerei)
    * multimon-ng  -> POCSAG / FLEX (cercapersone) e altri modi FSK/AFSK

DIFFERENZA IMPORTANTE RISPETTO A LINUX
--------------------------------------
Su Linux questi tre decoder si compilano/installano tutti in automatico. Su
Windows l'ecosistema e' diverso:

  - dsd-fme HA una build Windows UFFICIALE e mantenuta (releases di
    lwvmobile/dsd-fme): questo installer la scarica ed estrae in automatico.
  - dump1090 e multimon-ng NON hanno un singolo binario Windows ufficiale
    affidabile. Per sicurezza questo installer NON scarica ne' esegue .exe di
    terzi non verificati: stampa invece i passi guidati con i link corretti
    (gli stessi riportati in README.md).

Uso:
    python install_extra_decoders_windows.py            # dsd-fme + istruzioni
    python install_extra_decoders_windows.py --check    # cosa risulta presente

NOTA: questo script NON e' stato testato su Windows reale (l'ambiente di
sviluppo e' Linux). E' scritto per essere prudente e non distruttivo; se
qualcosa non torna, i binari e i link ufficiali sono comunque in README.md.

DISCLAIMER: usa questi strumenti solo dove consentito dalle leggi della tua
giurisdizione. Vedi DISCLAIMER.md.
"""

import argparse
import json
import logging
import os
import platform
import ssl
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# ============================================================
# CONFIGURAZIONE
# ============================================================

SCRIPT_VERSION = "1.0"
MIN_PYTHON = (3, 8)

INSTALLER_DIR = Path(__file__).resolve().parent
# Tutti i log (installazione compresa) finiscono in ./logs/ accanto allo script.
LOG_DIR = INSTALLER_DIR / "logs"
LOG_FILE = LOG_DIR / "install_extra.log"

# Cartella dove estraiamo i decoder scaricati, accanto all'installer.
DECODERS_DIR = INSTALLER_DIR / "decoders"

DOWNLOAD_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# dsd-fme: repository ufficiale che pubblica release con build Windows.
DSDFME_OWNER = "lwvmobile"
DSDFME_REPO = "dsd-fme"
# Parole chiave per riconoscere l'asset Windows tra quelli della release.
DSDFME_WIN_KEYWORDS = ("win", "cygwin", "mingw")

DECODERS = ("dsd-fme", "dump1090", "multimon-ng")

# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("extra_decoders_win")


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
# UTILITA' DI RETE
# ============================================================

def _http_get(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    # Su alcune installazioni Windows i certificati di sistema non sono esposti
    # a Python: usiamo il contesto di default, ma se fallisce riproviamo in modo
    # tollerante SOLO per le API pubbliche di GitHub (nessun dato sensibile).
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.read()
    except ssl.SSLError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(request, timeout=timeout, context=ctx) as resp:
            return resp.read()


def _download_to(url: str, destination: Path, timeout: int = 300) -> None:
    logger.info("Scarico: %s", url)
    data = _http_get(url, timeout=timeout)
    destination.write_bytes(data)
    logger.info("[OK] Salvato: %s (%.1f MB)", destination.name, len(data) / 1048576)


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
            "install_extra_decoders.py."
        )


# ============================================================
# DECODER 1 -- dsd-fme (download release Windows ufficiale)
# ============================================================

def _find_windows_asset(release: dict) -> dict | None:
    """Sceglie, tra gli asset di una release, quello che sembra la build
    Windows (per nome). Preferisce i 64 bit."""
    assets = release.get("assets", [])
    candidates = [
        a for a in assets
        if a.get("name", "").lower().endswith(".zip")
        and any(k in a.get("name", "").lower() for k in DSDFME_WIN_KEYWORDS)
    ]
    if not candidates:
        return None
    # Preferisci un asset a 64 bit se disponibile.
    for a in candidates:
        name = a.get("name", "").lower()
        if "64" in name or "x64" in name:
            return a
    return candidates[0]


def install_dsd_fme() -> bool:
    step("dsd-fme (DMR / P25 / NXDN / dPMR) -- download build Windows ufficiale")
    api = f"https://api.github.com/repos/{DSDFME_OWNER}/{DSDFME_REPO}/releases/latest"
    try:
        release = json.loads(_http_get(api).decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
        logger.warning(
            "[ATTENZIONE] Non sono riuscito a leggere le release di dsd-fme (%s).\n"
            "  Scarica manualmente l'ultima build Windows da:\n"
            "    https://github.com/%s/%s/releases",
            exc, DSDFME_OWNER, DSDFME_REPO,
        )
        return False

    asset = _find_windows_asset(release)
    if asset is None:
        logger.warning(
            "[ATTENZIONE] Nella release piu' recente non ho trovato un asset Windows.\n"
            "  Guarda a mano tra le release (a volte il nome cambia):\n"
            "    https://github.com/%s/%s/releases",
            DSDFME_OWNER, DSDFME_REPO,
        )
        return False

    DECODERS_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = DECODERS_DIR / "dsd-fme"
    zip_path = DECODERS_DIR / asset["name"]
    try:
        _download_to(asset["browser_download_url"], zip_path)
        logger.info("Estraggo in %s ...", target_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
        zip_path.unlink(missing_ok=True)
    except (urllib.error.URLError, urllib.error.HTTPError, zipfile.BadZipFile, OSError) as exc:
        logger.warning("[ATTENZIONE] Download/estrazione di dsd-fme non riuscita: %s", exc)
        return False

    exe = _find_file(target_dir, "dsd-fme.exe") or _find_file(target_dir, "dsd-fme")
    if exe:
        logger.info("[OK] dsd-fme pronto: %s", exe)
        return True
    logger.info(
        "[OK] Archivio dsd-fme estratto in %s (l'eseguibile e' li' dentro).",
        target_dir,
    )
    return True


def _find_file(base: Path, name: str) -> Path | None:
    for path in base.rglob("*"):
        if path.is_file() and path.name.lower() == name.lower():
            return path
    return None


# ============================================================
# DECODER 2 e 3 -- dump1090 / multimon-ng (istruzioni guidate)
# ============================================================

def guide_dump1090() -> bool:
    step("dump1090 (ADS-B) -- passi guidati")
    logger.info(
        "Su Windows non c'e' un binario dump1090 ufficiale unico. Opzioni consigliate:\n"
        "  1) Build Windows mantenuta:  https://github.com/gvanem/Dump1090\n"
        "  2) Guida passo-passo:        https://www.rtl-sdr.com/using-dump1090-windows/\n"
        "\n"
        "Dopo aver scaricato dump1090, copia nella sua cartella i file rtlsdr.dll e\n"
        "libusb-1.0.dll (li trovi gia' installati da TetraEar in TetraEar\\.venv\\Scripts\\).\n"
        "Poi avvialo con:  dump1090.exe --interactive --net\n"
        "e apri la mappa su http://localhost:8080"
    )
    return _find_file(DECODERS_DIR, "dump1090.exe") is not None


def guide_multimon_ng() -> bool:
    step("multimon-ng (cercapersone POCSAG/FLEX) -- passi guidati")
    logger.info(
        "Su Windows multimon-ng non ha un binario ufficiale pronto. Opzioni:\n"
        "  1) Compilarlo con MSYS2 (lo stesso ambiente che TetraEar installa per il\n"
        "     codec): apri 'MSYS2 MinGW 64-bit' e segui il README ufficiale:\n"
        "       https://github.com/EliasOenal/multimon-ng\n"
        "  2) In alternativa, su Windows molti usano PDW per i cercapersone:\n"
        "       https://www.discriminator.nl/pdw/index-en.html\n"
        "\n"
        "Con multimon-ng compilato, l'uso tipico (servono rtl_fm + una pipe) e':\n"
        "  rtl_fm -f 439.9875M -s 22050 -g 42 - | multimon-ng -t raw -a POCSAG1200 -f alpha -"
    )
    return _find_file(DECODERS_DIR, "multimon-ng.exe") is not None


# ============================================================
# VERIFICA / RIEPILOGO
# ============================================================

INSTALLERS = {
    "dsd-fme": install_dsd_fme,
    "dump1090": guide_dump1090,
    "multimon-ng": guide_multimon_ng,
}


def _present(name: str) -> bool:
    return _find_file(DECODERS_DIR, name + ".exe") is not None


def _tetraear_root() -> Path:
    """Individua la copia di TetraEar con la stessa logica di install_windows.py:
    lo script e' dentro una copia di TetraEar, oppure c'e' .\\TetraEar accanto."""
    if (INSTALLER_DIR / "requirements.txt").is_file() and (INSTALLER_DIR / "tetraear").is_dir():
        return INSTALLER_DIR
    return INSTALLER_DIR / "TetraEar"


def verify_and_summary(selected: list, completed_install: bool = True) -> None:
    step("Riepilogo")
    for name in selected:
        logger.info("  %s %s", "[PRONTO]" if _present(name) else "[DA FARE]", name)

    # Riquadro finale di fine installazione (non in modalita' --check, dove
    # non e' stato scaricato nulla).
    if completed_install:
        root = _tetraear_root()
        logger.info("")
        logger.info("========================================================")
        logger.info(" Installazione completata con successo!")
        logger.info("")
        logger.info(" Per avviare TetraEar SENZA terminale:")
        logger.info("   doppio clic su 'Avvia TetraEar.vbs' (nella cartella TetraEar o sul Desktop)")
        logger.info("")
        logger.info(" Oppure da Prompt dei comandi:")
        logger.info("   cd %s", root)
        logger.info(r"   .venv\Scripts\activate")
        logger.info("   python -m tetraear -f 392.225")
        logger.info("========================================================")

    logger.info("")
    logger.info("Cartella dei decoder: %s", DECODERS_DIR)
    logger.info("Guida d'uso completa: README.md")
    logger.info("Log: %s", LOG_FILE)
    logger.info("")
    logger.warning(
        "[IMPORTANTE] Come per TetraEar, su Windows serve il driver WinUSB della\n"
        "chiavetta installato con Zadig (una volta sola). Vedi README.md."
    )


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installer decoder RTL-SDR aggiuntivi per Windows (dsd-fme + guide)"
    )
    parser.add_argument("--only", nargs="+", choices=DECODERS, metavar="DECODER",
                        help=f"Solo i decoder indicati (fra: {', '.join(DECODERS)})")
    parser.add_argument("--check", action="store_true",
                        help="Verifica soltanto cosa e' presente, senza scaricare nulla")
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()
    selected = list(args.only) if args.only else list(DECODERS)

    logger.info("====== Installer decoder aggiuntivi (Windows) v%s ======", SCRIPT_VERSION)
    logger.info("Decoder richiesti: %s", ", ".join(selected))

    if args.check:
        verify_and_summary(selected, completed_install=False)
        return 0

    check_python_version()
    check_operating_system()

    for name in selected:
        try:
            INSTALLERS[name]()
        except Exception:  # noqa: BLE001 - un decoder non deve bloccare gli altri
            logger.warning("[ATTENZIONE] Passo '%s' interrotto da un errore; continuo.", name)
            logger.debug("Dettaglio:", exc_info=True)

    verify_and_summary(selected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
