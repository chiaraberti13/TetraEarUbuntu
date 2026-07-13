#!/usr/bin/env python3
"""
install_linux.py -- Installer automatico per TetraEar su Linux
================================================================

Testato per: Ubuntu 24.04 e Debian 12 (dovrebbe funzionare anche su
derivate recenti, es. Linux Mint, Pop!_OS).

Uso:
    python3 install_linux.py              # installazione completa
    python3 install_linux.py --repair     # ricompila solo il codec vocale
    python3 install_linux.py --uninstall  # rimuove venv + codec compilato

Cosa fa, in ordine:
    1. Controlla versione di Python e sistema operativo
    2. Installa le dipendenze di sistema via apt (compilatore, librerie
       RTL-SDR, librerie Qt necessarie a PyQt6, ecc.)
    3. Scarica (git clone) il codice sorgente di TetraEar se non e' gia'
       presente accanto a questo script
    4. Crea un virtual environment (.venv) e installa requirements.txt
    5. Scarica e compila il codec vocale ETSI TETRA (cdecoder/sdecoder)
    6. Verifica che tutto sia a posto e stampa un riepilogo finale

Non serve clonare niente a mano: basta scaricare questo file, renderlo
eseguibile (o lanciarlo con python3) e lui fa tutto il resto.

Ogni passaggio scrive sia a schermo che nel file install.log, cosi' chi
deve fare supporto puo' vedere l'intera cronologia di cosa e' successo.
"""

import argparse
import ctypes.util
import hashlib
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# ============================================================
# CONFIGURAZIONE
# ============================================================

SCRIPT_VERSION = "1.1"
MIN_PYTHON = (3, 8)
SUPPORTED_OS_IDS = {"ubuntu", "debian"}

# Repository ufficiale con il codice sorgente di TetraEar. Se questo
# script non viene lanciato da dentro una copia gia' clonata, provvede
# a scaricarlo da qui automaticamente.
TETRAEAR_REPO_URL = "https://github.com/syrex1013/TetraEar.git"

# Cartella dove si trova QUESTO script.
INSTALLER_DIR = Path(__file__).resolve().parent
LOG_FILE = INSTALLER_DIR / "install.log"

# I percorsi che dipendono dalla posizione del sorgente di TetraEar
# vengono impostati a runtime da configure_paths(), dopo aver localizzato
# (o clonato) il repository. Qui li inizializziamo con dei valori di
# default ragionevoli.
TETRAEAR_ROOT = INSTALLER_DIR
VENV_DIR = TETRAEAR_ROOT / ".venv"
REQUIREMENTS_FILE = TETRAEAR_ROOT / "requirements.txt"
CODEC_BASE_DIR = TETRAEAR_ROOT / "tetraear" / "tetra_codec"
CODEC_BIN_DIR = CODEC_BASE_DIR / "bin"

# Il pacchetto del codec vocale TETRA (ACELP) pubblicato da ETSI.
# Se in futuro questo URL smette di funzionare, aggiornare qui.
ETSI_CODEC_URL = (
    "http://www.etsi.org/deliver/etsi_en/300300_300399/30039502/"
    "01.03.01_60/en_30039502v010301p0.zip"
)
ETSI_CODEC_MD5 = "a8115fe68ef8f8cc466f4192572a1e3e"

# ETSI blocca le richieste che non sembrano provenire da un browser
# (risposta 403 "bot detection"). Un User-Agent realistico risolve il problema.
DOWNLOAD_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Le patch ufficiali (dal progetto Osmocom osmo-tetra) che rendono il
# codice ETSI compilabile con un compilatore moderno. Proviamo prima il
# mirror gitea ufficiale, poi il mirror GitHub come riserva.
OSMO_TETRA_REPO_URLS = [
    "https://gitea.osmocom.org/tetra/osmo-tetra.git",
    "https://github.com/osmocom/osmo-tetra.git",
]

# Pacchetti di sistema richiesti (validi sia per Ubuntu 24.04 che Debian 12).
# NOTA: qui NON mettiamo la libreria runtime di RTL-SDR (librtlsdrN) perche'
# il suo nome cambia da release a release (es. librtlsdr0 su bookworm/22.04,
# librtlsdr2 su noble 24.04). La gestiamo a parte con una lista di candidati,
# e comunque "librtlsdr-dev" e "rtl-sdr" tirano dietro la runtime corretta.
APT_PACKAGES = [
    # Toolchain per compilare il codec vocale (e' codice C, non Python)
    "build-essential", "gcc", "make", "patch", "git", "wget", "unzip", "ca-certificates",
    # Ambiente Python: venv + header per eventuali estensioni C dei pacchetti pip
    "python3-venv", "python3-dev", "python3-pip",
    # RTL-SDR: header di sviluppo + tool a riga di comando (rtl_test, ecc.)
    # + regole udev che permettono di usare la chiavetta senza sudo
    "librtlsdr-dev", "rtl-sdr",
    "libusb-1.0-0", "libusb-1.0-0-dev",
    # PyQt6: librerie di sistema richieste dal plugin grafico "xcb" su
    # installazioni Ubuntu/Debian minime (senza queste la GUI non parte
    # e da' errore "could not load the Qt platform plugin xcb")
    "libxcb-cursor0", "libxkbcommon-x11-0", "libgl1", "libegl1", "libdbus-1-3",
    # sounddevice: libreria audio nativa (PortAudio)
    "libportaudio2",
]

# Nome della libreria runtime RTL-SDR: proviamo i candidati in ordine e
# usiamo il primo effettivamente disponibile nei repository della distro.
# (piu' recente per primo)
APT_RTLSDR_RUNTIME_CANDIDATES = ["librtlsdr2", "librtlsdr0"]

REQUIRED_TOOLS = ("gcc", "make", "patch", "git")

# Moduli del kernel del driver DVB-T che "rubano" la chiavetta RTL2832U
# all'uso come SDR: vanno messi in blacklist, altrimenti pyrtlsdr non
# riesce a prendere il controllo del dongle ("usb_claim_interface error").
RTL_SDR_BLACKLIST_MODULES = [
    "dvb_usb_rtl28xxu",
    "rtl2832",
    "rtl2830",
    "rtl2832_sdr",
    "dvb_usb_v2",
]
RTL_SDR_BLACKLIST_PATH = Path("/etc/modprobe.d/blacklist-rtlsdr.conf")

# Regole udev che danno accesso alla chiavetta senza sudo (gruppo plugdev).
# Il pacchetto rtl-sdr di solito ne installa gia' una copia; se manca del
# tutto, ne scriviamo una noi come riserva.
RTL_SDR_UDEV_PATH = Path("/etc/udev/rules.d/60-tetraear-rtlsdr.rules")
RTL_SDR_UDEV_RULES = (
    '# RTL2832U usato come RTL-SDR - accesso al gruppo plugdev\n'
    'SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", '
    'GROUP="plugdev", MODE="0666", SYMLINK+="rtl_sdr"\n'
    'SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", '
    'GROUP="plugdev", MODE="0666", SYMLINK+="rtl_sdr"\n'
)

# ============================================================
# LOGGING
# ============================================================
# Tutto quello che stampiamo va sia a schermo sia su install.log,
# cosi' in caso di problemi basta allegare quel file per il supporto.

logger = logging.getLogger("tetraear_installer")
logger.setLevel(logging.DEBUG)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter("%(message)s"))

_file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
)

logger.addHandler(_console_handler)
logger.addHandler(_file_handler)


class InstallError(Exception):
    """Errore "gestito": lo stampiamo in modo chiaro e usciamo, senza
    mostrare un traceback illeggibile all'utente."""


def fail(message: str) -> "typing.NoReturn":
    logger.error("")
    logger.error("[ERRORE] %s", message)
    logger.error("Dettagli completi disponibili in: %s", LOG_FILE)
    raise InstallError(message)


def step(title: str) -> None:
    logger.info("")
    logger.info("==> %s", title)


def run(
    cmd: list,
    *,
    cwd: Path | None = None,
    env: dict | None = None,
    check: bool = True,
    sudo: bool = False,
) -> subprocess.CompletedProcess:
    """
    Esegue un comando esterno mostrando SEMPRE, in caso di errore, il
    codice di uscita e l'intero stderr (mai un traceback nudo di Python).

    Nota di sicurezza: passiamo sempre una lista di argomenti e non usiamo
    mai shell=True, cosi' non c'e' rischio di "shell injection" anche se
    in futuro qualche pezzo di comando dovesse dipendere da input esterno.
    """
    if sudo and os.geteuid() != 0:
        cmd = ["sudo"] + cmd

    logger.debug("Eseguo comando: %s (cwd=%s)", " ".join(cmd), cwd or INSTALLER_DIR)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        fail(f"Comando non trovato: {cmd[0]} ({exc})")

    logger.debug("Codice di uscita: %s", result.returncode)
    if result.stdout:
        logger.debug("--- stdout ---\n%s", result.stdout.strip())
    if result.stderr:
        logger.debug("--- stderr ---\n%s", result.stderr.strip())

    if check and result.returncode != 0:
        logger.error("Il comando '%s' e' fallito (codice %s).", " ".join(cmd), result.returncode)
        if result.stderr.strip():
            logger.error("--- Messaggio di errore completo ---\n%s", result.stderr.strip())
        fail(f"Comando fallito: {' '.join(cmd)}")

    return result


def find_path_ci(base: Path, name: str) -> Path | None:
    """
    Cerca un file o una cartella chiamata `name` dentro `base`, ignorando
    maiuscole/minuscole (utile perche' gli archivi ETSI a volte usano nomi
    tipo "C-CODE" invece di "c-code" a seconda della versione dello zip).
    """
    target = name.lower()
    for dirpath, dirnames, filenames in os.walk(base):
        for entry in dirnames + filenames:
            if entry.lower() == target:
                return Path(dirpath) / entry
    return None


# ============================================================
# LOCALIZZAZIONE / DOWNLOAD DEL SORGENTE DI TETRAEAR
# ============================================================

def _looks_like_tetraear_root(path: Path) -> bool:
    """Una cartella e' una copia valida di TetraEar se contiene sia
    requirements.txt sia il package Python tetraear/."""
    return (path / "requirements.txt").is_file() and (path / "tetraear").is_dir()


def configure_paths(root: Path) -> None:
    """Imposta tutti i percorsi derivati una volta noto dove si trova
    davvero il codice sorgente di TetraEar."""
    global TETRAEAR_ROOT, VENV_DIR, REQUIREMENTS_FILE, CODEC_BASE_DIR, CODEC_BIN_DIR
    TETRAEAR_ROOT = root
    VENV_DIR = root / ".venv"
    REQUIREMENTS_FILE = root / "requirements.txt"
    CODEC_BASE_DIR = root / "tetraear" / "tetra_codec"
    CODEC_BIN_DIR = CODEC_BASE_DIR / "bin"


def ensure_tetraear_source(clone_if_missing: bool = True) -> Path:
    """
    Trova il codice sorgente di TetraEar. In ordine:
      1. Lo script e' gia' dentro una copia di TetraEar? -> usa quella cartella.
      2. Esiste una sottocartella ./TetraEar accanto allo script? -> usa quella.
      3. Altrimenti (se consentito) clona il repository ufficiale.

    Ritorna il percorso della root di TetraEar e configura i percorsi derivati.
    """
    if _looks_like_tetraear_root(INSTALLER_DIR):
        logger.info("[OK] Sorgente di TetraEar trovato nella cartella corrente")
        configure_paths(INSTALLER_DIR)
        return INSTALLER_DIR

    cloned_dir = INSTALLER_DIR / "TetraEar"
    if _looks_like_tetraear_root(cloned_dir):
        logger.info("[OK] Sorgente di TetraEar gia' presente in %s", cloned_dir)
        configure_paths(cloned_dir)
        return cloned_dir

    if not clone_if_missing:
        # Usato dalla disinstallazione: non vogliamo scaricare niente,
        # restituiamo comunque il percorso "atteso" per la pulizia.
        configure_paths(cloned_dir)
        return cloned_dir

    step("Scarico il codice sorgente di TetraEar")
    if shutil.which("git") is None:
        fail("git non e' installato: impossibile scaricare il sorgente di TetraEar.")

    if cloned_dir.exists():
        # Cartella esistente ma incompleta (clone precedente interrotto):
        # la rimuoviamo per ripartire pulito.
        logger.info("Rimuovo una copia incompleta preesistente: %s", cloned_dir)
        shutil.rmtree(cloned_dir, ignore_errors=True)

    logger.info("Clono %s in %s ...", TETRAEAR_REPO_URL, cloned_dir)
    run(["git", "clone", "--depth", "1", TETRAEAR_REPO_URL, str(cloned_dir)])

    if not _looks_like_tetraear_root(cloned_dir):
        fail(
            "Il repository e' stato scaricato ma non contiene i file attesi "
            "(requirements.txt e cartella tetraear/). Struttura del repo cambiata?"
        )

    logger.info("[OK] Sorgente di TetraEar scaricato in %s", cloned_dir)
    configure_paths(cloned_dir)
    return cloned_dir


# ============================================================
# FASE 1 -- Controlli preliminari
# ============================================================

def check_python_version() -> None:
    step("Controllo versione di Python")
    current = sys.version_info[:2]
    if current < MIN_PYTHON:
        fail(
            f"E' richiesto Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} o superiore, "
            f"trovato {current[0]}.{current[1]}. Aggiorna Python e riprova."
        )
    logger.info("[OK] Python %s.%s rilevato", *current)


def read_os_release() -> dict:
    os_release_path = Path("/etc/os-release")
    if not os_release_path.is_file():
        return {}
    data = {}
    for line in os_release_path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip().strip('"')
    return data


def check_operating_system() -> None:
    step("Controllo sistema operativo")
    if platform.system() != "Linux":
        fail("Questo script serve solo per Linux. Su Windows usa install_windows.py (o install_windows.bat).")

    info = read_os_release()
    os_id = info.get("ID", "").lower()
    os_name = info.get("PRETTY_NAME", "distribuzione Linux sconosciuta")

    if os_id not in SUPPORTED_OS_IDS:
        logger.warning(
            "[ATTENZIONE] Distribuzione non ufficialmente testata: %s. "
            "Si prosegue comunque, ma in caso di problemi la causa potrebbe "
            "essere questa (pacchetti apt con nomi diversi).",
            os_name,
        )
    else:
        logger.info("[OK] Sistema operativo supportato: %s", os_name)


# ============================================================
# FASE 2 -- Dipendenze di sistema (apt)
# ============================================================

def ensure_sudo() -> None:
    """
    Se non siamo root, chiediamo SUBITO la password a sudo con un prompt
    VISIBILE. Serve perche' le successive chiamate a sudo hanno l'output
    catturato (per finire nel log): senza questo passo il loro prompt
    "[sudo] password" resterebbe invisibile e lo script sembrerebbe
    bloccato. `sudo -v` inoltre rinfresca il timer, quindi possiamo
    richiamarlo prima di ogni fase che usa sudo senza infastidire l'utente.
    """
    if os.geteuid() == 0:
        return
    if shutil.which("sudo") is None:
        fail(
            "Questo script ha bisogno di 'sudo' per installare i pacchetti di "
            "sistema, ma 'sudo' non e' presente. Installalo o esegui come root."
        )
    logger.info("Autenticazione amministratore: inserisci la password se richiesta.")
    try:
        result = subprocess.run(["sudo", "-v"])  # niente capture: prompt visibile
    except FileNotFoundError:
        fail("Comando 'sudo' non trovato.")
    if result.returncode != 0:
        fail("Autenticazione sudo fallita: impossibile installare le dipendenze di sistema.")


def _apt_package_available(pkg: str) -> bool:
    """Ritorna True se il pacchetto esiste nei repository configurati.
    Usiamo 'apt-cache show' (non richiede root): esce con codice 0 e
    stampa qualcosa solo se il pacchetto e' davvero disponibile."""
    result = run(["apt-cache", "show", pkg], check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def _resolve_rtlsdr_runtime_package() -> str | None:
    """Trova il nome giusto della libreria runtime RTL-SDR per questa
    distro (varia tra release), provando i candidati in ordine."""
    for candidate in APT_RTLSDR_RUNTIME_CANDIDATES:
        if _apt_package_available(candidate):
            logger.info("Libreria runtime RTL-SDR trovata: %s", candidate)
            return candidate
    logger.info(
        "Nessun pacchetto runtime RTL-SDR con nome noto trovato: verra' "
        "comunque tirato dietro da 'librtlsdr-dev'/'rtl-sdr'."
    )
    return None


def install_system_dependencies() -> None:
    step("Installazione dipendenze di sistema (apt)")

    ensure_sudo()

    if shutil.which("apt-get") is None:
        fail(
            "apt-get non trovato: questo script funziona solo su distribuzioni "
            "basate su Debian/Ubuntu."
        )

    logger.info("Aggiorno l'elenco pacchetti (apt-get update)...")
    run(["apt-get", "update"], sudo=True)

    # Costruiamo la lista definitiva: pacchetti base + la runtime RTL-SDR
    # col nome corretto per questa distro.
    wanted = list(APT_PACKAGES)
    runtime_pkg = _resolve_rtlsdr_runtime_package()
    if runtime_pkg:
        wanted.append(runtime_pkg)

    # Filtriamo tenendo solo i pacchetti realmente disponibili: cosi' una
    # singola differenza di nome tra distro non fa fallire tutto il resto.
    # I pacchetti mancanti vengono segnalati (e verificati piu' sotto per
    # quelli davvero indispensabili).
    available, skipped = [], []
    for pkg in wanted:
        (available if _apt_package_available(pkg) else skipped).append(pkg)

    if skipped:
        logger.warning(
            "[ATTENZIONE] Pacchetti non presenti nei repository di questa "
            "distribuzione, saltati: %s", ", ".join(skipped)
        )

    logger.info("Installo %d pacchetti: %s", len(available), ", ".join(available))
    run(["apt-get", "install", "-y"] + available, sudo=True)

    # Controllo degli strumenti davvero indispensabili (compilazione codec).
    missing_tools = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing_tools:
        fail(
            "Anche dopo l'installazione mancano questi strumenti nel PATH: "
            + ", ".join(missing_tools)
        )

    # Controllo "morbido" della libreria RTL-SDR: avvisa ma non blocca.
    if ctypes.util.find_library("rtlsdr") is None:
        logger.warning(
            "[ATTENZIONE] La libreria librtlsdr non risulta ancora presente "
            "nel sistema. Se all'avvio TetraEar non vede la chiavetta, "
            "controlla che 'librtlsdr-dev' o 'rtl-sdr' siano stati installati."
        )

    logger.info("[OK] Dipendenze di sistema installate correttamente")


# ============================================================
# FASE 3 -- Virtual environment e dipendenze Python
# ============================================================

def create_virtualenv_and_install_requirements() -> None:
    step("Creazione virtual environment (.venv) e installazione pacchetti Python")

    if not REQUIREMENTS_FILE.is_file():
        fail(f"File non trovato: {REQUIREMENTS_FILE}. Il sorgente di TetraEar non e' completo.")

    if not VENV_DIR.is_dir():
        logger.info("Creo il virtual environment in %s", VENV_DIR)
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    else:
        logger.info("Virtual environment gia' presente in %s, lo riuso", VENV_DIR)

    pip_path = VENV_DIR / "bin" / "pip"
    if not pip_path.is_file():
        fail(f"pip non trovato dentro il virtual environment: {pip_path}")

    logger.info("Aggiorno pip...")
    run([str(pip_path), "install", "--upgrade", "pip"])

    logger.info("Installo i pacchetti elencati in requirements.txt (puo' richiedere qualche minuto)...")
    run([str(pip_path), "install", "-r", str(REQUIREMENTS_FILE)])

    logger.info("[OK] Ambiente Python pronto in %s", VENV_DIR)

    # Rende pyrtlsdr compatibile con la librtlsdr standard di Ubuntu.
    patch_pyrtlsdr_dithering()


# ============================================================
# FASE 4 -- Compilazione del codec vocale ETSI TETRA
# ============================================================

def _download_with_browser_headers(url: str, destination: Path) -> None:
    """
    Scarica un file impostando un User-Agent "da browser". Il sito ETSI
    risponde 403 (bot detection) alle richieste che sembrano provenire
    da script automatici, quindi urllib.request.urlretrieve() da solo
    non basta: serve costruire manualmente la richiesta con gli header.
    """
    request = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(destination, "wb") as out_file:
            shutil.copyfileobj(response, out_file)
    except urllib.error.HTTPError as exc:
        fail(
            f"Download fallito ({exc.code} {exc.reason}) da {url}. "
            "Se il problema persiste, l'URL potrebbe essere cambiato: "
            "verificare manualmente sul sito ETSI e aggiornare ETSI_CODEC_URL "
            "in cima a questo script."
        )
    except urllib.error.URLError as exc:
        fail(f"Download fallito: impossibile raggiungere {url} ({exc.reason}).")


def _verify_checksum(file_path: Path, expected_md5: str) -> None:
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    actual = md5.hexdigest()
    if actual != expected_md5:
        file_path.unlink(missing_ok=True)
        fail(
            f"Checksum MD5 non corrispondente per {file_path.name}: "
            f"atteso {expected_md5}, ottenuto {actual}. Il file scaricato "
            "potrebbe essere corrotto o l'archivio ETSI e' cambiato di versione."
        )


def _fix_makefile_for_modern_gcc(makefile_path: Path) -> None:
    """
    Il Makefile originale ETSI del 2005 usa un compilatore chiamato "acc"
    (Sun/HP-UX, non esiste su Linux moderno) e non compila con GCC 10+
    senza qualche aggiustamento. Questa funzione applica le stesse
    correzioni gia' note e testate da anni nella comunita' (vedi il
    progetto "install-tetra-codec" di sq5bpf):
      - ACC = acc  ->  ACC = gcc
      - aggiunge -fcommon (richiesto da GCC 10 in poi)
      - rimuove -Werror (altrimenti anche semplici warning bloccano la build)
    """
    data = makefile_path.read_text(encoding="utf-8", errors="ignore")

    data = re.sub(r"(?m)^ACC\s*=\s*acc\b", "ACC = gcc", data)
    data = re.sub(r"(?m)^(\s*)acc\b", r"\1gcc", data)
    data = re.sub(r"\bacc\b", "gcc", data)

    if "-fcommon" not in data:
        data = re.sub(r"(?m)^CFLAGS\s*=\s*(.*)$", r"CFLAGS = -fcommon \1", data)

    data = data.replace("-Werror", "")

    makefile_path.write_text(data, encoding="utf-8")


def _lowercase_filenames(directory: Path) -> None:
    """
    L'archivio ETSI del codec contiene i file con i nomi in MAIUSCOLO
    (es. SCODER.C, MAKEFILE), ma il Makefile al suo interno li referenzia
    in minuscolo (scoder.c). Su Linux, che distingue maiuscole/minuscole,
    'make' fallisce con "No such file or directory". Rinominiamo quindi in
    minuscolo tutti i file, esattamente come fa lo script noto di sq5bpf.

    Rinominiamo solo i file (non le cartelle): il Makefile referenzia i
    sorgenti in modo "piatto", nella stessa directory.
    """
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name == path.name:
            continue
        target = path.parent / lower_name
        if target.exists():
            # Una versione minuscola esiste gia' (es. creata da una patch):
            # teniamo quella e rimuoviamo il duplicato in maiuscolo.
            path.unlink()
        else:
            path.rename(target)


def _normalize_line_endings(root: Path) -> None:
    """L'archivio ETSI ha alcuni file con fine riga Windows (CRLF); li
    normalizziamo a LF per evitare problemi con patch/make su Linux."""
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in (".c", ".h") or path.name.lower() == "makefile":
            try:
                raw = path.read_bytes()
                if b"\r\n" in raw:
                    path.write_bytes(raw.replace(b"\r\n", b"\n"))
            except OSError:
                pass


def _apply_osmo_tetra_patches(codec_dir: Path, work_dir: Path) -> bool:
    """
    Metodo primario: clona il repository osmo-tetra (che contiene le
    patch ufficiali per rendere il codec ETSI decodificabile a partire
    dai bit ricevuti via radio) e le applica in ordine.

    Ritorna True se le patch sono state applicate, False se il metodo
    non e' disponibile (es. nessuna connessione ai mirror) e bisogna
    ricorrere al metodo di riserva.
    """
    osmo_dir = work_dir / "osmo-tetra"
    cloned = False
    for repo_url in OSMO_TETRA_REPO_URLS:
        logger.info("Provo a scaricare le patch da %s ...", repo_url)
        result = run(["git", "clone", "--depth", "1", repo_url, str(osmo_dir)], check=False)
        if result.returncode == 0:
            cloned = True
            break
        logger.warning("Mirror non raggiungibile, provo il successivo...")

    if not cloned:
        logger.warning(
            "[ATTENZIONE] Impossibile scaricare le patch ufficiali da nessun mirror. "
            "Procedo con il metodo di riserva (compilazione diretta, senza patch)."
        )
        return False

    patch_dir = osmo_dir / "etsi_codec-patches"
    series_file = patch_dir / "series"
    if not series_file.is_file():
        logger.warning("File 'series' delle patch non trovato, uso il metodo di riserva.")
        return False

    for patch_name in series_file.read_text(encoding="utf-8").splitlines():
        patch_name = patch_name.strip()
        if not patch_name or patch_name.startswith("#"):
            continue
        patch_file = patch_dir / patch_name
        if not patch_file.is_file():
            logger.warning("Patch elencata ma non trovata: %s (la salto)", patch_name)
            continue
        logger.info("Applico patch: %s", patch_name)
        with open(patch_file, "rb") as f:
            result = subprocess.run(
                ["patch", "--batch", "-p1", "-N", "-E"],
                cwd=str(codec_dir),
                stdin=f,
                capture_output=True,
                text=True,
            )
        if result.returncode not in (0, 1):  # 1 = "gia' applicata", non fatale
            logger.error("Applicazione patch fallita: %s\n%s", patch_name, result.stderr)
            fail(f"Patch fallita: {patch_name}")

    return True


def install_tetra_codec(fallback_only: bool = False) -> None:
    step("Compilazione del codec vocale ETSI TETRA (cdecoder / sdecoder)")

    work_dir = Path(tempfile.mkdtemp(prefix="tetra-codec-"))
    logger.debug("Cartella temporanea di lavoro: %s", work_dir)

    try:
        zip_path = work_dir / "etsi_codec.zip"
        logger.info("Scarico il codec da ETSI...")
        _download_with_browser_headers(ETSI_CODEC_URL, zip_path)

        logger.info("Verifico il checksum del file scaricato...")
        _verify_checksum(zip_path, ETSI_CODEC_MD5)
        logger.info("[OK] Checksum corretto")

        logger.info("Estraggo l'archivio...")
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(work_dir)

        c_code_dir = find_path_ci(work_dir, "c-code")
        if c_code_dir is None:
            fail("Cartella 'c-code' non trovata nell'archivio ETSI estratto (formato inatteso).")

        # L'archivio ETSI usa nomi MAIUSCOLI ma il Makefile richiama i
        # sorgenti in minuscolo: su Linux va uniformato prima di compilare.
        logger.info("Uniformo i nomi dei file del codec in minuscolo...")
        _lowercase_filenames(c_code_dir)

        _normalize_line_endings(work_dir)

        if not fallback_only:
            _apply_osmo_tetra_patches(c_code_dir.parent, work_dir)
        else:
            logger.info("Modalita' di riserva: salto l'applicazione delle patch ufficiali.")

        makefile_path = find_path_ci(c_code_dir, "makefile")
        if makefile_path is None:
            fail("Makefile non trovato dentro c-code/.")

        logger.info("Sistemo il Makefile per un compilatore GCC moderno...")
        _fix_makefile_for_modern_gcc(makefile_path)

        logger.info("Compilo (make)...")
        run(["make", "-f", makefile_path.name], cwd=c_code_dir)

        CODEC_BIN_DIR.mkdir(parents=True, exist_ok=True)
        wanted_binaries = ["cdecoder", "sdecoder", "ccoder", "scoder"]
        missing = []
        for binary_name in wanted_binaries:
            src = find_path_ci(c_code_dir, binary_name)
            if src is None:
                missing.append(binary_name)
                continue
            dst = CODEC_BIN_DIR / binary_name
            shutil.copy2(src, dst)
            dst.chmod(dst.stat().st_mode | 0o111)  # +x
            logger.info("  + %s", dst)

        if missing:
            fail(
                "Compilazione terminata ma mancano questi binari: "
                + ", ".join(missing)
                + ". Guarda install.log per l'output completo di 'make'."
            )

        logger.info("[OK] Codec installato in %s", CODEC_BIN_DIR)

    finally:
        logger.debug("Pulizia cartella temporanea %s", work_dir)
        shutil.rmtree(work_dir, ignore_errors=True)


def install_tetra_codec_with_fallback() -> None:
    """
    Prova prima il metodo con le patch ufficiali (piu' corretto). Se
    fallisce per un motivo di rete/ambiente, ritenta automaticamente con
    il metodo di riserva (compilazione diretta senza patch, come faceva
    gia' lo script Windows del progetto). Se anche questo fallisce,
    l'errore viene mostrato con dettagli completi.
    """
    try:
        install_tetra_codec(fallback_only=False)
    except InstallError:
        logger.warning("")
        logger.warning("Il metodo con patch ufficiali e' fallito, provo il metodo di riserva...")
        install_tetra_codec(fallback_only=True)


# ============================================================
# FASE 4b -- Configurazione hardware RTL-SDR
# ============================================================

def _write_root_file(destination: Path, content: str) -> None:
    """Scrive un file di sistema (serve root) passando da un file
    temporaneo + copia con sudo, senza usare shell=True."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="rtlsdr-cfg-"))
    try:
        tmp_file = tmp_dir / destination.name
        tmp_file.write_text(content, encoding="utf-8")
        run(["cp", str(tmp_file), str(destination)], sudo=True)
        run(["chmod", "644", str(destination)], sudo=True, check=False)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def configure_rtl_sdr() -> None:
    """
    Rende la chiavetta RTL-SDR (chip RTL2832U) davvero utilizzabile:
      1. mette in blacklist i driver DVB-T del kernel che altrimenti
         "occupano" la chiavetta impedendone l'uso come SDR;
      2. scarica subito quel driver se e' gia' caricato (best effort);
      3. installa/ricarica le regole udev per l'accesso senza sudo;
      4. aggiunge l'utente al gruppo plugdev.

    E' tutto "best effort": se qualcosa non riesce l'installazione non si
    blocca, ma l'errore resta comunque scritto in install.log.
    """
    step("Configurazione della chiavetta RTL-SDR (driver kernel e permessi)")

    # Rinfresca l'autenticazione sudo: tra l'apt e questo punto sono passati
    # l'installazione di pip e altre fasi lunghe, il timer sudo potrebbe
    # essere scaduto e le chiamate sudo successive (con output catturato)
    # resterebbero altrimenti bloccate su un prompt invisibile.
    ensure_sudo()

    # 1. Blacklist dei moduli DVB-T
    blacklist_content = (
        "# Generato da TetraEar install_linux.py\n"
        "# Impedisce ai driver DVB-T del kernel di occupare la chiavetta RTL2832U,\n"
        "# cosi' puo' essere usata come RTL-SDR.\n"
        + "".join(f"blacklist {m}\n" for m in RTL_SDR_BLACKLIST_MODULES)
    )
    logger.info("Scrivo la blacklist dei driver DVB-T in %s", RTL_SDR_BLACKLIST_PATH)
    try:
        _write_root_file(RTL_SDR_BLACKLIST_PATH, blacklist_content)
    except InstallError:
        logger.warning("[ATTENZIONE] Non sono riuscito a scrivere la blacklist (vedi install.log).")

    # 2. Scarico subito il driver DVB-T se attualmente caricato
    for module in ("dvb_usb_rtl28xxu", "rtl2832_sdr", "rtl2832"):
        run(["modprobe", "-r", module], sudo=True, check=False)

    # 3. Regole udev: se il pacchetto rtl-sdr non ne ha gia' installata una,
    #    ne mettiamo una nostra. In ogni caso ricarichiamo le regole.
    existing_rules = list(Path("/etc/udev/rules.d").glob("*rtlsdr*")) + \
        list(Path("/lib/udev/rules.d").glob("*rtlsdr*")) + \
        list(Path("/usr/lib/udev/rules.d").glob("*rtlsdr*"))
    if existing_rules:
        logger.info("Regole udev RTL-SDR gia' presenti: %s", ", ".join(str(p) for p in existing_rules))
    else:
        logger.info("Installo regole udev di riserva in %s", RTL_SDR_UDEV_PATH)
        try:
            _write_root_file(RTL_SDR_UDEV_PATH, RTL_SDR_UDEV_RULES)
        except InstallError:
            logger.warning("[ATTENZIONE] Non sono riuscito a scrivere le regole udev (vedi install.log).")

    if shutil.which("udevadm"):
        run(["udevadm", "control", "--reload-rules"], sudo=True, check=False)
        run(["udevadm", "trigger"], sudo=True, check=False)

    # 4. Aggiungo l'utente reale (non root) al gruppo plugdev
    real_user = os.environ.get("SUDO_USER") or os.environ.get("USER") or ""
    if real_user and real_user != "root":
        result = run(["usermod", "-aG", "plugdev", real_user], sudo=True, check=False)
        if result.returncode == 0:
            logger.info(
                "Utente '%s' aggiunto al gruppo plugdev "
                "(effettua logout/login perche' abbia effetto).",
                real_user,
            )
        else:
            logger.warning("[ATTENZIONE] Non sono riuscito ad aggiungere '%s' a plugdev.", real_user)

    logger.info("[OK] Configurazione RTL-SDR applicata")
    logger.warning(
        "[IMPORTANTE] Se la chiavetta era gia' collegata, SCOLLEGALA e "
        "RICOLLEGALA (oppure riavvia) affinche' la blacklist del driver "
        "DVB-T e le nuove regole udev abbiano effetto."
    )


def patch_pyrtlsdr_dithering() -> None:
    """
    Il wrapper Python pyrtlsdr lega la funzione 'rtlsdr_set_dithering' in
    modo NON opzionale (altre funzioni recenti sono in try/except, questa
    no). Quel simbolo esiste solo nel fork 'keenerd' di librtlsdr, NON
    nella versione distribuita da Ubuntu: senza intervento TetraEar non
    parte, con l'errore:

        AttributeError: .../librtlsdr.so: undefined symbol: rtlsdr_set_dithering

    Rendiamo quel binding tollerante: se il simbolo manca, installiamo uno
    stub innocuo. Il dithering e' una funzione accessoria (serve solo a
    disattivare il dithering di frequenza) e TetraEar non ne ha bisogno,
    quindi l'app funziona perfettamente con la librtlsdr standard di Ubuntu.
    """
    step("Compatibilita' pyrtlsdr / librtlsdr (patch dithering)")

    matches = list(VENV_DIR.glob("**/site-packages/rtlsdr/librtlsdr.py"))
    if not matches:
        logger.info("[INFO] pyrtlsdr non trovato nel venv, salto la patch.")
        return
    target = matches[0]

    content = target.read_text(encoding="utf-8")
    if "_rtlsdr_set_dithering_stub" in content:
        logger.info("[OK] pyrtlsdr gia' compatibile (patch gia' applicata).")
        return

    lines = content.splitlines()
    out = []
    patched = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            not patched
            and line.strip() == "f = librtlsdr.rtlsdr_set_dithering"
            and i + 1 < len(lines)
            and "f.restype" in lines[i + 1]
        ):
            indent = line[: len(line) - len(line.lstrip())]
            restype_line = lines[i + 1].strip()
            out.append(f"{indent}try:")
            out.append(f"{indent}    f = librtlsdr.rtlsdr_set_dithering")
            out.append(f"{indent}    {restype_line}")
            out.append(f"{indent}except AttributeError:")
            out.append(f"{indent}    # Simbolo assente nella librtlsdr di Ubuntu: stub innocuo.")
            out.append(f"{indent}    def _rtlsdr_set_dithering_stub(dev, dither):")
            out.append(f"{indent}        return 0")
            out.append(f"{indent}    librtlsdr.rtlsdr_set_dithering = _rtlsdr_set_dithering_stub")
            i += 2
            patched = True
            continue
        out.append(line)
        i += 1

    if not patched:
        logger.warning(
            "[ATTENZIONE] Non ho trovato il punto da correggere in pyrtlsdr "
            "(versione diversa del pacchetto?). Se all'avvio compare "
            "'undefined symbol: rtlsdr_set_dithering', segnalalo."
        )
        return

    new_content = "\n".join(out)
    if content.endswith("\n"):
        new_content += "\n"
    target.write_text(new_content, encoding="utf-8")
    logger.info("[OK] pyrtlsdr reso compatibile con la librtlsdr di sistema.")


# ============================================================
# FASE 5 -- Verifica finale
# ============================================================

def verify_installation() -> None:
    step("Verifica finale dell'installazione")

    all_ok = True

    pip_path = VENV_DIR / "bin" / "pip"
    if pip_path.is_file():
        logger.info("[OK] Virtual environment presente: %s", VENV_DIR)
    else:
        logger.error("[FALLITO] Virtual environment non trovato")
        all_ok = False

    for binary_name in ("cdecoder", "sdecoder"):
        binary_path = CODEC_BIN_DIR / binary_name
        if binary_path.is_file() and os.access(binary_path, os.X_OK):
            logger.info("[OK] Binario codec presente ed eseguibile: %s", binary_path)
        else:
            logger.error("[FALLITO] Binario codec mancante o non eseguibile: %s", binary_path)
            all_ok = False

    verify_pyrtlsdr_import()  # controlla il mismatch libreria/pyrtlsdr
    check_rtl_sdr_dongle()    # solo informativo, non blocca l'installazione

    if not all_ok:
        fail("Uno o piu' controlli finali non sono andati a buon fine (vedi sopra).")

    logger.info("")
    logger.info("========================================================")
    logger.info(" Installazione completata con successo!")
    logger.info("")
    logger.info(" Per avviare TetraEar:")
    logger.info("   cd %s", TETRAEAR_ROOT)
    logger.info("   source .venv/bin/activate")
    logger.info("   python -m tetraear -f 392.225")
    logger.info("========================================================")


def verify_pyrtlsdr_import() -> None:
    """
    Controllo end-to-end: prova a importare 'rtlsdr' dentro il venv. E' qui
    che si manifesta l'incompatibilita' fra pyrtlsdr e la libreria librtlsdr
    di sistema ('undefined symbol: rtlsdr_set_dithering'). Non blocca
    l'installazione, ma segnala chiaramente il problema in caso.
    """
    python_path = VENV_DIR / "bin" / "python"
    if not python_path.is_file():
        return
    result = run(
        [str(python_path), "-c", "from rtlsdr import RtlSdr"],
        check=False,
    )
    if result.returncode == 0:
        logger.info("[OK] Il modulo Python 'rtlsdr' (pyrtlsdr) si importa correttamente.")
    else:
        logger.warning(
            "[ATTENZIONE] Import di 'rtlsdr' fallito: incompatibilita' tra "
            "pyrtlsdr e la libreria librtlsdr di sistema. Riesegui l'installer "
            "(o 'python3 install_linux.py --repair') per applicare la patch di "
            "compatibilita'. Dettaglio:\n%s",
            result.stderr.strip(),
        )


def check_rtl_sdr_dongle() -> None:
    """
    Controllo "morbido": verifica solo se sembra esserci una chiavetta
    RTL-SDR collegata, senza bloccare l'installazione se non c'e' (magari
    l'utente la collega dopo, o sta solo installando in anticipo).
    """
    if ctypes.util.find_library("rtlsdr") is None:
        logger.warning(
            "[INFO] Libreria librtlsdr non trovata nel sistema: "
            "verrà rilevata solo quando colleghi una chiavetta e la usi."
        )

    if shutil.which("lsusb") is None:
        logger.info("[INFO] 'lsusb' non disponibile, salto il controllo della chiavetta RTL-SDR.")
        return

    result = run(["lsusb"], check=False)
    # 0bda:2838 e 0bda:2832 sono i vendor/product ID piu' comuni per le
    # chiavette RTL2832U usate come RTL-SDR
    if re.search(r"0bda:283[28]", result.stdout):
        logger.info("[OK] Chiavetta RTL-SDR rilevata via USB")
    else:
        logger.warning(
            "[INFO] Nessuna chiavetta RTL-SDR rilevata al momento. "
            "Non e' un problema per l'installazione: collegala prima di avviare TetraEar."
        )


# ============================================================
# --repair e --uninstall
# ============================================================

def do_repair() -> None:
    step("Modalita' --repair: ricompilo il codec vocale e sistemo la compatibilita' pyrtlsdr")
    ensure_tetraear_source(clone_if_missing=True)
    patch_pyrtlsdr_dithering()
    install_tetra_codec_with_fallback()
    verify_installation()


def do_uninstall() -> None:
    step("Disinstallazione")
    ensure_tetraear_source(clone_if_missing=False)

    if VENV_DIR.is_dir():
        logger.info("Rimuovo il virtual environment: %s", VENV_DIR)
        shutil.rmtree(VENV_DIR, ignore_errors=True)
    else:
        logger.info("Nessun virtual environment da rimuovere")

    if CODEC_BIN_DIR.is_dir():
        logger.info("Rimuovo i binari del codec compilati: %s", CODEC_BIN_DIR)
        shutil.rmtree(CODEC_BIN_DIR, ignore_errors=True)
    else:
        logger.info("Nessun binario del codec da rimuovere")

    logger.info("[OK] Disinstallazione completata (il codice sorgente non è stato toccato)")


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installer TetraEar per Linux (Ubuntu 24.04 / Debian 12)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--repair", action="store_true",
        help="Ricompila solo il codec vocale (utile se e' l'unica cosa rotta)",
    )
    group.add_argument(
        "--uninstall", action="store_true",
        help="Rimuove il virtual environment e il codec compilato",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    logger.info("====== TetraEar Linux Installer v%s ======", SCRIPT_VERSION)
    logger.info("Log completo salvato in: %s", LOG_FILE)

    try:
        if args.uninstall:
            do_uninstall()
            return 0

        check_python_version()
        check_operating_system()

        if args.repair:
            do_repair()
            return 0

        install_system_dependencies()
        ensure_tetraear_source(clone_if_missing=True)
        create_virtualenv_and_install_requirements()
        # La configurazione della chiavetta viene fatta PRIMA del codec:
        # il codec dipende da un download esterno (ETSI) che potrebbe
        # fallire, ma il dongle dev'essere comunque pronto all'uso.
        configure_rtl_sdr()
        install_tetra_codec_with_fallback()
        verify_installation()
        return 0

    except InstallError:
        # Errore gia' stampato in modo chiaro da fail(): usciamo.
        return 1
    except KeyboardInterrupt:
        logger.error("\nInstallazione interrotta dall'utente.")
        return 130
    except Exception:
        # Rete di sicurezza: qualsiasi errore NON previsto viene comunque
        # salvato per intero (con traceback) in install.log, cosi' non si
        # perde niente da sottoporre a chi fa supporto.
        logger.error("")
        logger.error("[ERRORE IMPREVISTO] Si e' verificato un errore non gestito.")
        logger.error("Il traceback completo e' stato salvato in: %s", LOG_FILE)
        logger.debug("Traceback completo dell'errore imprevisto:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
