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

SCRIPT_VERSION = "1.4"
MIN_PYTHON = (3, 8)
SUPPORTED_OS_IDS = {"ubuntu", "debian"}

# Repository ufficiale con il codice sorgente di TetraEar. Se questo
# script non viene lanciato da dentro una copia gia' clonata, provvede
# a scaricarlo da qui automaticamente.
TETRAEAR_REPO_URL = "https://github.com/syrex1013/TetraEar.git"

# Versione di TetraEar da installare. Per default fissiamo un commit noto e
# testato (release v2.3), cosi' l'installazione e' RIPRODUCIBILE: un
# cambiamento a monte del progetto non puo' rompere di sorpresa le patch che
# questo installer applica. Per prendere comunque l'ultimo codice, impostare
# la variabile d'ambiente TETRAEAR_REF (a un commit, tag o branch, es.
# "master") oppure passare --ref sulla riga di comando.
TETRAEAR_DEFAULT_REF = "c46141a62c5aec1a68ea7e3c1c570bcf461833e5"  # release v2.3
# Valore effettivo usato a runtime: viene sovrascritto da resolve_tetraear_ref()
# leggendo prima --ref, poi la variabile d'ambiente, poi il default qui sopra.
TETRAEAR_REF = TETRAEAR_DEFAULT_REF
# File in cui registriamo il commit esatto installato: rende l'installazione
# verificabile a posteriori (utile per il supporto e per --check).
TETRAEAR_VERSION_FILE = ".tetraear_version"

# Cartella dove si trova QUESTO script.
INSTALLER_DIR = Path(__file__).resolve().parent
# Tutti i log (installazione compresa) finiscono in ./logs/ accanto allo script.
LOG_DIR = INSTALLER_DIR / "logs"
LOG_FILE = LOG_DIR / "install.log"

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

# Il sito ETSI e' a volte irraggiungibile o risponde 403. Come riserva usiamo
# la copia archiviata dalla Wayback Machine di archive.org (stesso identico
# file). Il download prova le fonti in ordine e si ferma alla prima che
# funziona; il checksum MD5 qui sopra garantisce comunque che qualunque fonte
# serva ESATTAMENTE lo stesso archivio, quindi aggiungere mirror e' sicuro.
ETSI_CODEC_URLS = [
    ETSI_CODEC_URL,
    "https://web.archive.org/web/2id_/" + ETSI_CODEC_URL,
]

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

LOG_DIR.mkdir(parents=True, exist_ok=True)
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

    _clone_tetraear_pinned(TETRAEAR_REPO_URL, TETRAEAR_REF, cloned_dir)

    if not _looks_like_tetraear_root(cloned_dir):
        fail(
            "Il repository e' stato scaricato ma non contiene i file attesi "
            "(requirements.txt e cartella tetraear/). Struttura del repo cambiata?"
        )

    logger.info("[OK] Sorgente di TetraEar scaricato in %s", cloned_dir)
    configure_paths(cloned_dir)
    return cloned_dir


def unify_logs_dir() -> None:
    """
    Unica cartella per TUTTI i log. Se TetraEar e' una sottocartella (il caso
    normale), la sua 'logs/' diventa un link simbolico alla 'logs/' accanto
    all'installer: install.log, install_extra.log, codec_*.log, console_*.log
    ecc. finiscono cosi' fisicamente in un solo posto. Ogni file ha gia' un
    prefisso specifico, quindi non si mescolano. Eventuali log gia' presenti
    in TetraEar/logs vengono spostati, non persi. Best-effort: un errore qui
    non blocca l'installazione.
    """
    if TETRAEAR_ROOT == INSTALLER_DIR:
        return  # lo script e' gia' dentro TetraEar: esiste una sola logs/

    app_logs = TETRAEAR_ROOT / "logs"
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        if app_logs.is_symlink():
            if app_logs.resolve() == LOG_DIR.resolve():
                return  # gia' unificata
            app_logs.unlink()
        elif app_logs.is_dir():
            # Migro i log esistenti nella cartella unificata (senza
            # sovrascrivere eventuali omonimi gia' presenti).
            for entry in app_logs.iterdir():
                target = LOG_DIR / entry.name
                if not target.exists():
                    shutil.move(str(entry), str(target))
            app_logs.rmdir()

        os.symlink(os.path.relpath(LOG_DIR, TETRAEAR_ROOT), app_logs)
        logger.info("[OK] Cartella log unificata: %s -> %s", app_logs, LOG_DIR)
    except OSError as exc:
        logger.warning(
            "[ATTENZIONE] Non sono riuscito a unificare le cartelle dei log (%s): "
            "l'app continuera' a scrivere in %s.", exc, app_logs
        )


def _clone_tetraear_pinned(repo_url: str, ref: str, dest: Path) -> None:
    """
    Clona TetraEar fissando ESATTAMENTE il commit/ref richiesto, cosi'
    l'installazione e' riproducibile: due installazioni con lo stesso `ref`
    ottengono lo stesso codice, e un cambiamento a monte non puo' rompere di
    sorpresa le patch applicate da questo installer.

    Strategia: prima si prova un fetch shallow (--depth 1) del ref specifico
    (funziona per branch, tag e, sui server che lo permettono, anche per SHA);
    se non riesce, si ripiega su un clone completo + checkout, che gestisce
    qualunque SHA anche sui server che non consentono il fetch per commit.
    Il commit risolto viene registrato in TETRAEAR_VERSION_FILE.
    """
    dest_str = str(dest)
    logger.info("Scarico TetraEar da %s (versione fissata: %s) ...", repo_url, ref)

    run(["git", "init", "-q", dest_str])
    run(["git", "-C", dest_str, "remote", "add", "origin", repo_url])

    fetched = run(
        ["git", "-C", dest_str, "fetch", "--depth", "1", "origin", ref],
        check=False,
    )
    if fetched.returncode == 0:
        run(["git", "-C", dest_str, "checkout", "-q", "FETCH_HEAD"])
    else:
        logger.info(
            "Fetch shallow del ref non riuscito (il server potrebbe non "
            "permettere il fetch per commit): provo un clone completo..."
        )
        shutil.rmtree(dest, ignore_errors=True)
        run(["git", "clone", repo_url, dest_str])
        run(["git", "-C", dest_str, "checkout", "-q", ref])

    resolved = run(["git", "-C", dest_str, "rev-parse", "HEAD"], check=False)
    if resolved.returncode == 0:
        sha = resolved.stdout.strip()
        logger.info("[OK] TetraEar fissato al commit %s", sha)
        try:
            (dest / TETRAEAR_VERSION_FILE).write_text(sha + "\n", encoding="utf-8")
        except OSError:
            pass


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


def warn_if_in_trash() -> None:
    """Se l'installer viene lanciato da dentro il Cestino, avvisa: il codice
    e il virtual environment finirebbero in una posizione instabile (spariscono
    svuotando il cestino) e i comandi di avvio non sarebbero riutilizzabili."""
    p = str(INSTALLER_DIR)
    if "/.local/share/Trash/" in p or "/.Trash" in p or "/Trash/files/" in p:
        logger.warning("")
        logger.warning("[ATTENZIONE] Stai eseguendo l'installer da dentro il CESTINO:")
        logger.warning("  %s", INSTALLER_DIR)
        logger.warning("Sposta la cartella nella tua home (o reinstalla li') prima di usarla:")
        logger.warning("  cd ~ && git clone https://github.com/chiaraberti13/TetraEarUbuntu.git")
        logger.warning("  cd ~/TetraEarUbuntu && python3 install_linux.py")
        logger.warning("")


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


# Quanti secondi far attendere ad apt il lock di dpkg prima di arrendersi.
# Subito dopo l'avvio 'unattended-upgrades' (gli aggiornamenti automatici di
# Ubuntu) tiene spesso occupato /var/lib/dpkg/lock-frontend per un paio di
# minuti: senza attendere, apt fallirebbe con "Could not get lock".
APT_LOCK_TIMEOUT = 600  # 10 minuti


def _run_dpkg_configure() -> bool:
    """
    Ripara un dpkg lasciato "a meta'" da una precedente installazione
    interrotta (spegnimento, kill, aggiornamento fallito...). In quello
    stato apt si rifiuta di procedere con il messaggio:

        E: dpkg was interrupted, you must manually run
           'sudo dpkg --configure -a' to correct the problem.

    Eseguiamo esattamente quel comando di recupero al posto dell'utente.
    E' idempotente e innocuo quando non c'e' nulla da riconfigurare.
    Ritorna True se termina con successo.
    """
    cmd = ["dpkg", "--configure", "-a"]
    if os.geteuid() != 0:
        cmd = ["sudo"] + cmd

    logger.info(
        "Rilevato uno stato di dpkg interrotto da una precedente "
        "installazione: eseguo 'sudo dpkg --configure -a' per ripararlo..."
    )
    logger.debug("Eseguo comando (streaming): %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        logger.warning("Comando non trovato: %s (%s)", cmd[0], exc)
        return False

    assert proc.stdout is not None
    for line in proc.stdout:
        logger.info(line.rstrip("\n"))
    returncode = proc.wait()
    logger.debug("Codice di uscita (dpkg --configure -a): %s", returncode)

    if returncode == 0:
        logger.info("[OK] Stato di dpkg ripristinato.")
        return True

    logger.warning(
        "[ATTENZIONE] 'dpkg --configure -a' e' terminato con codice %s.",
        returncode,
    )
    return False


def _run_apt(args: list, _dpkg_recovery_attempted: bool = False) -> None:
    """
    Esegue 'apt-get <args>' con sudo facendogli ATTENDERE il lock di
    dpkg/apt invece di fallire subito se un altro processo lo sta usando.

    Due accorgimenti importanti:

    1. Usiamo l'opzione nativa DPkg::Lock::Timeout: se il lock e' occupato
       (tipicamente da 'unattended-upgrades' appena dopo il boot) apt aspetta
       fino a APT_LOCK_TIMEOUT secondi che si liberi, invece del criptico
       "Could not get lock".

    2. A differenza degli altri comandi, qui NON catturiamo l'output ma lo
       lasciamo scorrere a schermo (e lo salviamo nel log riga per riga).
       Cosi' l'utente vede il download dei pacchetti e soprattutto il
       messaggio "Waiting for cache lock..." di apt mentre attende: altrimenti
       l'installer sembrerebbe "bloccato" durante l'attesa del lock o durante
       un'installazione lunga.
    """
    cmd = ["apt-get", "-o", f"DPkg::Lock::Timeout={APT_LOCK_TIMEOUT}"] + args
    if os.geteuid() != 0:
        cmd = ["sudo"] + cmd

    logger.debug("Eseguo comando (streaming): %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        fail(f"Comando non trovato: {cmd[0]} ({exc})")

    captured = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        captured.append(line)
        logger.info(line)  # console (immediato) + file di log
    returncode = proc.wait()
    logger.debug("Codice di uscita: %s", returncode)

    if returncode == 0:
        return

    output = "\n".join(captured)

    # dpkg lasciato interrotto da una precedente installazione: apt rifiuta
    # di procedere finche' non si esegue 'dpkg --configure -a'. Lo ripariamo
    # in automatico e riproviamo il comando UNA sola volta (per non entrare
    # in un ciclo se il problema fosse un altro).
    dpkg_interrupted = (
        "dpkg was interrupted" in output
        or "dpkg --configure -a" in output
    )
    if dpkg_interrupted and not _dpkg_recovery_attempted:
        if _run_dpkg_configure():
            logger.info("Riprovo il comando apt dopo aver riparato dpkg...")
            _run_apt(args, _dpkg_recovery_attempted=True)
            return
        fail(
            "dpkg era rimasto in uno stato interrotto da una precedente "
            "installazione e la riparazione automatica ('sudo dpkg "
            "--configure -a') non e' riuscita. Esegui a mano "
            "'sudo dpkg --configure -a', controlla gli errori che riporta, "
            "poi rilancia 'python3 install_linux.py'."
        )

    lock_busy = (
        "Could not get lock" in output
        or "frontend lock" in output
        or "is another process using it" in output
    )
    if lock_busy:
        fail(
            "Il gestore pacchetti (dpkg/apt) e' rimasto occupato da un altro "
            f"processo per oltre {APT_LOCK_TIMEOUT // 60} minuti: quasi sempre "
            "sono gli aggiornamenti automatici di Ubuntu "
            "('unattended-upgrades'), che partono da soli subito dopo l'avvio. "
            "Aspetta 2-3 minuti che finiscano e rilancia "
            "'python3 install_linux.py'. Per vedere se sono in corso: "
            "'ps aux | grep -i unattended'."
        )

    # Errore diverso dal lock: l'output e' gia' a schermo e nel log, terminiamo.
    fail(f"Comando fallito: {' '.join(cmd)}")


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
    _run_apt(["update"])

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
    logger.info(
        "(puo' richiedere qualche minuto; se poco dopo l'avvio vedi "
        "'Waiting for cache lock' e' NORMALE: aspetta, sono gli aggiornamenti "
        "automatici di Ubuntu che rilasciano il lock)"
    )
    _run_apt(["install", "-y"] + available)

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
    Scarica un singolo file impostando un User-Agent "da browser". Il sito
    ETSI risponde 403 (bot detection) alle richieste che sembrano provenire
    da script automatici, quindi urllib.request.urlretrieve() da solo non
    basta: serve costruire manualmente la richiesta con gli header.

    Solleva l'eccezione originale in caso di errore: e' il chiamante a
    decidere se provare un mirror alternativo o fermarsi.
    """
    request = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response, open(destination, "wb") as out_file:
        shutil.copyfileobj(response, out_file)


def _download_first_available(urls: list, destination: Path) -> None:
    """
    Scarica da una lista di URL (fonte primaria + mirror di riserva),
    fermandosi al primo che risponde. Il checksum viene verificato a parte
    dal chiamante, quindi qualunque mirror serva un file diverso verra'
    comunque scartato dopo.
    """
    last_error = None
    for index, url in enumerate(urls, start=1):
        logger.info("Scarico (fonte %d/%d): %s", index, len(urls), url)
        try:
            _download_with_browser_headers(url, destination)
            return
        except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError) as exc:
            last_error = exc
            logger.warning("Fonte non raggiungibile (%s), provo la successiva...", exc)

    fail(
        "Download del codec fallito da tutte le fonti disponibili (ETSI e mirror). "
        f"Ultimo errore: {last_error}. Il sito ETSI e' a volte irraggiungibile: "
        "riprova piu' tardi con 'python3 install_linux.py --repair'. Se l'URL e' "
        "cambiato in modo permanente, aggiornare ETSI_CODEC_URL in cima a questo script."
    )


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

    NOTA: su filesystem case-insensitive (utile per coerenza con l'installer
    Windows) il percorso in minuscolo "esiste" perche' e' lo STESSO file: in
    quel caso si rinomina in due passi, senza mai cancellare il file.
    """
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name == path.name:
            continue
        target = path.parent / lower_name
        try:
            same_file = target.exists() and target.samefile(path)
        except OSError:
            same_file = False
        if same_file:
            # Filesystem case-insensitive: rinomina in due passi.
            tmp = path.parent / (path.name + ".tetra-tmp")
            path.rename(tmp)
            tmp.rename(target)
        elif target.exists():
            # Collisione con un file realmente diverso: rimuovo il duplicato.
            path.unlink()
        else:
            path.rename(target)


def _lowercase_dirnames(root: Path) -> None:
    """Rinomina in minuscolo i nomi delle CARTELLE del codec ETSI.

    L'archivio ETSI estrae cartelle in MAIUSCOLO (es. C-CODE/, AMR-CODE/), ma le
    patch ufficiali osmo-tetra referenziano percorsi minuscoli (c-code/source.h,
    amr-code/source.h). Su filesystem case-sensitive (Linux) 'patch' non trova i
    file e SALTA tutte le patch -- inclusa fix_64bit.patch -- producendo un
    cdecoder NON corretto per 64 bit che va in segmentation fault (return -11)
    ad ogni frame vocale: la voce non si decodifica mai.

    Rinominando le cartelle in minuscolo PRIMA di applicare le patch, i percorsi
    combaciano e le patch vengono applicate. Difensivo: gestisce anche i
    filesystem case-insensitive (rinomina in due passi) e non sovrascrive una
    cartella minuscola gia' esistente.
    """
    dirs = sorted(
        (p for p in root.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts), reverse=True,   # dal piu' profondo
    )
    for path in dirs:
        lower = path.name.lower()
        if lower == path.name:
            continue
        target = path.parent / lower
        try:
            same = target.exists() and target.samefile(path)
        except OSError:
            same = False
        try:
            if same:  # FS case-insensitive: rinomina in due passi
                tmp = path.parent / (path.name + ".tetra-tmpdir")
                path.rename(tmp)
                tmp.rename(target)
            elif target.exists():
                continue  # esiste gia' una versione minuscola: non tocco nulla
            else:
                path.rename(target)
        except OSError as exc:
            logger.debug("Non ho potuto rinominare %s -> %s (%s)", path, target, exc)


def _normalize_line_endings(root: Path) -> None:
    """L'archivio ETSI ha alcuni file con fine riga Windows (CRLF); li
    normalizziamo a LF per evitare problemi con patch/make su Linux."""
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix.lower() in (".c", ".h") or path.name.lower() == "makefile"):
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
        logger.debug("Codice di uscita patch %s: %s", patch_name, result.returncode)
        if result.stdout:
            logger.debug("--- stdout ---\n%s", result.stdout.strip())
        if result.stderr:
            logger.debug("--- stderr ---\n%s", result.stderr.strip())
        if result.returncode not in (0, 1):  # 1 = "gia' applicata", non fatale
            logger.error("Applicazione patch fallita: %s\n%s", patch_name, result.stderr)
            fail(f"Patch fallita: {patch_name}")
        # Con exit code 1 'patch' segnala anche gli hunk NON applicati:
        # non blocchiamo (il codec compila comunque), ma deve restare
        # traccia CHIARA nel log, non un finto successo.
        if result.returncode == 1 and "FAILED" in (result.stdout + result.stderr):
            logger.warning(
                "[ATTENZIONE] Alcune parti della patch %s NON sono state "
                "applicate (vedi dettagli in install.log). Il codec verra' "
                "compilato comunque, ma la decodifica potrebbe risentirne.",
                patch_name,
            )

    return True


def install_tetra_codec(fallback_only: bool = False) -> None:
    step("Compilazione del codec vocale ETSI TETRA (cdecoder / sdecoder)")

    work_dir = Path(tempfile.mkdtemp(prefix="tetra-codec-"))
    logger.debug("Cartella temporanea di lavoro: %s", work_dir)

    try:
        zip_path = work_dir / "etsi_codec.zip"
        logger.info("Scarico il codec da ETSI...")
        _download_first_available(ETSI_CODEC_URLS, zip_path)

        logger.info("Verifico il checksum del file scaricato...")
        _verify_checksum(zip_path, ETSI_CODEC_MD5)
        logger.info("[OK] Checksum corretto")

        logger.info("Estraggo l'archivio...")
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(work_dir)

        # L'archivio ETSI usa nomi MAIUSCOLI (cartelle E file); le patch osmo e
        # il Makefile referenziano percorsi minuscoli. Uniformiamo PRIMA di
        # cercare c-code e di applicare le patch: senza la minuscola sulle
        # CARTELLE la patch fix_64bit viene saltata e il cdecoder va in segfault.
        logger.info("Uniformo cartelle e file del codec in minuscolo...")
        _lowercase_dirnames(work_dir)
        _lowercase_filenames(work_dir)

        c_code_dir = find_path_ci(work_dir, "c-code")
        if c_code_dir is None:
            fail("Cartella 'c-code' non trovata nell'archivio ETSI estratto (formato inatteso).")

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
    pyrtlsdr lega MOLTE funzioni di librtlsdr in modo NON opzionale (senza
    try/except): rtlsdr_set_dithering, rtlsdr_set_gpio_output, ecc. Diverse
    di queste esistono solo nel fork 'keenerd' di librtlsdr e NON nella
    versione distribuita da Ubuntu, quindi l'import di 'rtlsdr' fallisce con:

        AttributeError: .../librtlsdr.so: undefined symbol: rtlsdr_set_...

    Invece di correggere ogni singolo binding (sono tanti), avvolgiamo
    l'oggetto libreria in un piccolo proxy: per ogni simbolo realmente
    presente restituisce la funzione vera, per i simboli mancanti
    restituisce uno stub innocuo (che ritorna 0). Cosi' l'import non
    fallisce mai e TetraEar funziona con la librtlsdr standard di Ubuntu
    (quelle funzioni mancanti sono accessorie e non vengono usate).
    """
    step("Compatibilita' pyrtlsdr / librtlsdr")

    matches = list(VENV_DIR.glob("**/site-packages/rtlsdr/librtlsdr.py"))
    if not matches:
        logger.info("[INFO] pyrtlsdr non trovato nel venv, salto la patch.")
        return
    target = matches[0]

    content = target.read_text(encoding="utf-8")
    if "_TetraEarTolerantLib" in content:
        logger.info("[OK] pyrtlsdr gia' compatibile (patch gia' applicata).")
        return

    lines = content.splitlines()
    binding_re = re.compile(r"^\s*f\s*=\s*librtlsdr\.")
    insert_at = next((idx for idx, ln in enumerate(lines) if binding_re.match(ln)), None)
    if insert_at is None:
        logger.warning(
            "[ATTENZIONE] Struttura di pyrtlsdr non riconosciuta: patch non "
            "applicata. Se all'avvio compare 'undefined symbol: rtlsdr_...', segnalalo."
        )
        return

    wrapper = [
        "",
        "# --- Patch di compatibilita' TetraEar --------------------------------",
        "# Avvolge librtlsdr in un proxy che, per i simboli assenti nella libreria",
        "# di sistema (Ubuntu), restituisce uno stub innocuo invece di far fallire",
        "# l'import. Le funzioni interessate (dithering, gpio, ...) sono accessorie.",
        "class _TetraEarTolerantLib:",
        "    def __init__(self, _lib):",
        "        object.__setattr__(self, '_lib', _lib)",
        "    def __getattr__(self, name):",
        "        _lib = object.__getattribute__(self, '_lib')",
        "        try:",
        "            return getattr(_lib, name)",
        "        except AttributeError:",
        "            if name.startswith('__') and name.endswith('__'):",
        "                raise",
        "            def _tetraear_missing(*args, **kwargs):",
        "                return 0",
        "            return _tetraear_missing",
        "librtlsdr = _TetraEarTolerantLib(librtlsdr)",
        "# --- Fine patch di compatibilita' TetraEar ---------------------------",
        "",
    ]

    new_lines = lines[:insert_at] + wrapper + lines[insert_at:]
    new_content = "\n".join(new_lines)
    if content.endswith("\n"):
        new_content += "\n"
    target.write_text(new_content, encoding="utf-8")
    logger.info("[OK] pyrtlsdr reso compatibile con la librtlsdr di sistema.")


def patch_tetraear_source_bugs() -> None:
    """
    Corregge due bug noti nel sorgente di TetraEar (progetto a monte) che
    impediscono la decodifica. Entrambi stanno in tetraear/ui/modern.py,
    dentro CaptureThread.run().

    1) Il codice legge 'self.signal_processor', attributo che non esiste:
       quello giusto - creato in __init__ e usato per demodulare
       (self.processor = SignalProcessor(...)) - si chiama 'self.processor'.
       Ogni frame andava in eccezione con:

           Decode error: 'CaptureThread' object has no attribute 'signal_processor'

       e non veniva decodificato NULLA (tabella frame vuota, nessun audio).

    2) Il path di decodifica vocale usa 'self.tch_assembler', ma
       CaptureThread non lo inizializza mai: l'assembler viene creato solo
       in ModernTetraGUI (un'altra classe). Ogni frame vocale andava in
       eccezione con:

           Voice decode error: 'CaptureThread' object has no attribute 'tch_assembler'

       Lo correggiamo in due modi complementari: rendiamo l'accesso sicuro
       con getattr(...) (niente piu' crash anche se l'__init__ a monte
       cambia) e inizializziamo davvero l'assembler nell'__init__ di
       CaptureThread, cosi' il path TCH viene usato quando disponibile.

    Patch idempotente: se il sorgente e' gia' corretto non fa nulla.
    """
    step("Correzione bug di decodifica nel sorgente di TetraEar")

    target = TETRAEAR_ROOT / "tetraear" / "ui" / "modern.py"
    if not target.is_file():
        logger.info("[INFO] %s non trovato, salto la patch.", target)
        return

    content = target.read_text(encoding="utf-8")
    changed = False

    # --- Bug 1: self.signal_processor -> self.processor ------------------
    occ1 = content.count("self.signal_processor")
    if occ1:
        content = content.replace("self.signal_processor", "self.processor")
        changed = True
        logger.info(
            "[OK] Corretto 'signal_processor' -> 'processor' (%d occorrenza/e).",
            occ1,
        )
    else:
        logger.info("[OK] Bug 'signal_processor' non presente (gia' corretto).")

    # --- Bug 2a: accesso sicuro a self.tch_assembler ---------------------
    occ2 = content.count("if self.tch_assembler:")
    if occ2:
        content = content.replace(
            "if self.tch_assembler:",
            'if getattr(self, "tch_assembler", None):',
        )
        changed = True
        logger.info(
            "[OK] Reso sicuro l'accesso a 'tch_assembler' (%d occorrenza/e).",
            occ2,
        )
    else:
        logger.info("[OK] Accesso a 'tch_assembler' gia' sicuro (gia' corretto).")

    # --- Bug 2b: inizializza tch_assembler in CaptureThread.__init__ -----
    init_marker = "self.tch_assembler = None  # inizializzato da TetraEar installer"
    anchor = "        self.encryption_keys = []  # List of keys for bruteforce\n"
    if init_marker in content:
        logger.info("[OK] 'tch_assembler' gia' inizializzato in CaptureThread.")
    elif anchor in content:
        injection = (
            anchor
            + "        # TetraEar: CaptureThread usa self.tch_assembler nel path di\n"
            + "        # decodifica vocale ma l'upstream non lo crea qui. Lo\n"
            + "        # inizializziamo per evitare l'AttributeError e usare il TCH.\n"
            + "        " + init_marker + "\n"
            + "        try:\n"
            + "            from tetraear.audio.tch import TchFrameAssembler\n"
            + "            self.tch_assembler = TchFrameAssembler()\n"
            + "        except Exception:\n"
            + "            self.tch_assembler = None\n"
        )
        content = content.replace(anchor, injection, 1)
        changed = True
        logger.info("[OK] Inizializzato 'tch_assembler' in CaptureThread.__init__.")
    else:
        logger.warning(
            "[ATTENZIONE] Non ho trovato il punto in cui inizializzare "
            "'tch_assembler' in CaptureThread: la struttura del file a monte "
            "potrebbe essere cambiata. L'accesso resta comunque sicuro (getattr)."
        )

    if changed:
        target.write_text(content, encoding="utf-8")
        logger.info("[OK] modern.py aggiornato.")
    else:
        logger.info("[OK] Nessuna modifica necessaria a modern.py.")


def patch_tetraear_add_toolkit() -> None:
    """
    Aggiunge alla GUI di TetraEar un set completo di tab, riusando gli strumenti
    gia' presenti nel repo. Tutti PASSIVI / a chiave nota: nessun cracking.

      * Network Info -> metadati di rete (MCC/MNC/LA/Colour Code/AIE/...) dal
                        ricevitore TELIVE-2 (motore tetra_netscanner.py)
      * Decrypt      -> catena TELIVE-2: stato, editor keyfile (incl. TEA-1
                        32-bit), avvio GNU Radio/ricevitore/telive, voce
      * Decoders     -> multimon-ng / dump1090 / dsd-fme (modi in chiaro)
      * Reference    -> TETRA vs TETRA2, TEA/TAA, CVE TETRA:BURST, link

    Copia i moduli in tetraear/ui/ e inietta in tetraear/ui/modern.py, dentro
    init_ui e dopo il tab "Statistics", un blocco che registra i tab. Ogni tab
    e' avvolto in try/except: un errore non puo' mai impedire l'avvio dell'app.
    Idempotente (sentinel "TetraEar Toolkit") e tollerante se l'anchor a monte
    cambia (logga e salta). Sostituisce l'eventuale vecchia iniezione del solo
    tab Network Info.
    """
    step("Aggiunta dei tab TETRA (Network Info, Decrypt, Decoders, Reference)")

    ui_dir = TETRAEAR_ROOT / "tetraear" / "ui"
    modern = ui_dir / "modern.py"
    if not modern.is_file():
        logger.info("[INFO] %s non trovato, salto i tab della GUI.", modern)
        return

    # 1) Copia il motore di parsing, gli helper e i widget dei tab.
    to_copy = {
        INSTALLER_DIR / "tetra_netscanner.py": ui_dir / "tetra_netinfo_backend.py",
        INSTALLER_DIR / "tetra_gui_common.py": ui_dir / "tetra_gui_common.py",
        INSTALLER_DIR / "tetra_netinfo_tab.py": ui_dir / "network_info_tab.py",
        INSTALLER_DIR / "tetra_decrypt_tab.py": ui_dir / "tetra_decrypt_tab.py",
        INSTALLER_DIR / "tetra_decoders_tab.py": ui_dir / "tetra_decoders_tab.py",
        INSTALLER_DIR / "tetra_antenna_tab.py": ui_dir / "tetra_antenna_tab.py",
        INSTALLER_DIR / "tetra_reference_tab.py": ui_dir / "tetra_reference_tab.py",
    }
    for src, dst in to_copy.items():
        if not src.is_file():
            logger.warning(
                "[ATTENZIONE] Manca %s: non installo i tab della GUI "
                "(i tool standalone restano comunque disponibili).", src.name,
            )
            return
        try:
            shutil.copy2(src, dst)
            logger.info("[OK] Copiato %s -> tetraear/ui/%s", src.name, dst.name)
        except OSError as exc:
            logger.warning("[ATTENZIONE] Copia di %s fallita (%s): salto i tab.", src.name, exc)
            return

    # 2) Inietta i tab in init_ui (dopo "Statistics") e l'etichetta di stato
    #    nella barra Status. Strip+reinject = upgrade pulito e idempotente.
    content = modern.read_text(encoding="utf-8")
    original = content

    old_single = re.compile(
        r'\n[ \t]*# TetraEar Network Scanner: tab passivo.*?'
        r'Network Info tab non caricato: %s", _nis_e\)',
        re.DOTALL,
    )
    old_block = re.compile(
        r'\n[ \t]*# === TetraEar Toolkit: tab aggiuntivi.*?'
        r'Tab %s non caricato: %s", _tt_lbl, _tt_e\)',
        re.DOTALL,
    )
    content = old_single.sub("", content)
    content = old_block.sub("", content)

    anchor = 'tabs.addTab(stats_widget, "\U0001f4ca Statistics")'
    if anchor in content:
        injection = (
            anchor + "\n"
            "        # === TetraEar Toolkit: tab aggiuntivi (passivi / a chiave nota) ===\n"
            "        for _tt_mod, _tt_cls, _tt_lbl in (\n"
            '            ("tetraear.ui.network_info_tab", "NetworkInfoTab", "\U0001f4f6 Network Info"),\n'
            '            ("tetraear.ui.tetra_decrypt_tab", "DecryptTab", "\U0001f513 Decrypt (TELIVE-2)"),\n'
            '            ("tetraear.ui.tetra_decoders_tab", "DecodersTab", "\U0001f4e1 Decoders"),\n'
            '            ("tetraear.ui.tetra_antenna_tab", "AntennaTab", "\U0001f4fb Antenna/Freq"),\n'
            '            ("tetraear.ui.tetra_reference_tab", "ReferenceTab", "\U0001f4da Reference"),\n'
            "        ):\n"
            "            try:\n"
            "                import importlib as _tt_il\n"
            "                _tt_widget = getattr(_tt_il.import_module(_tt_mod), _tt_cls)(self)\n"
            "                tabs.addTab(_tt_widget, _tt_lbl)\n"
            "            except Exception as _tt_e:\n"
            "                import logging as _tt_log\n"
            '                _tt_log.getLogger("tetraear").warning("Tab %s non caricato: %s", _tt_lbl, _tt_e)'
        )
        content = content.replace(anchor, injection, 1)
        logger.info("[OK] 5 tab TETRA registrati in modern.py (init_ui).")
    else:
        logger.warning(
            "[ATTENZIONE] Anchor del tab 'Statistics' non trovato in modern.py: "
            "non aggiungo i tab (i moduli sono comunque copiati)."
        )

    # Etichetta di stato del toolkit nella barra Status in alto (best-effort).
    status_anchor = "status_group.setLayout(status_layout)"
    if "toolkit_status_label" in content:
        logger.info("[OK] Etichetta di stato del toolkit gia' presente.")
    elif status_anchor in content:
        status_inject = (
            'self.toolkit_status_label = QLabel("\U0001f9f0 Toolkit: pronto")\n'
            '        self.toolkit_status_label.setStyleSheet("font-weight: bold; padding: 5px; color: #888888;")\n'
            "        status_layout.addWidget(self.toolkit_status_label)\n"
            "        " + status_anchor
        )
        content = content.replace(status_anchor, status_inject, 1)
        logger.info("[OK] Etichetta di stato del toolkit aggiunta alla barra Status.")
    else:
        logger.info("[INFO] Gruppo Status non trovato: salto l'etichetta di stato (non essenziale).")

    if content != original:
        modern.write_text(content, encoding="utf-8")
        logger.info("[OK] modern.py aggiornato con i tab TETRA.")
    else:
        logger.info("[OK] modern.py gia' aggiornato (nessuna modifica).")


def patch_voice_hide_codec_window() -> None:
    """
    Evita che ad OGNI frame decodificato si apra una finestra nera del codec.

    Il launcher di TetraEar usa 'pythonw.exe' (nessuna console). In
    tetraear/audio/voice.py, per ogni frame vocale, 'decode_frame()' lancia
    due processi console (cdecoder.exe e sdecoder.exe) con subprocess.run().
    Poiche' il processo padre (pythonw) non ha una console, Windows ne crea
    una NUOVA e VISIBILE per ciascuna chiamata: il risultato e' uno sfarfallio
    continuo di finestrelle che si aprono e chiudono (il sintomo "apre tante
    cartelle/finestre ad ogni decodifica").

    La correzione aggiunge 'creationflags=CREATE_NO_WINDOW' alle chiamate
    subprocess.run() del codec, cosi' i processi girano nascosti. Usiamo
    getattr(subprocess, "CREATE_NO_WINDOW", 0) per restare portabili: su
    Linux la costante non esiste e vale 0 (nessun flag), quindi lo stesso
    sorgente resta valido su entrambi i sistemi.

    Patch idempotente: se 'creationflags' e' gia' presente non fa nulla.
    """
    step("Correzione finestre del codec che compaiono ad ogni decodifica")

    target = TETRAEAR_ROOT / "tetraear" / "audio" / "voice.py"
    if not target.is_file():
        logger.info("[INFO] %s non trovato, salto la patch.", target)
        return

    content = target.read_text(encoding="utf-8")
    if "creationflags" in content:
        logger.info("[OK] Finestre del codec gia' nascoste (patch gia' applicata).")
        return

    needle = (
        "                stdout=subprocess.PIPE,\n"
        "                stderr=subprocess.PIPE,\n"
        "                check=False,\n"
        "                timeout=5,\n"
        "            )"
    )
    replacement = (
        "                stdout=subprocess.PIPE,\n"
        "                stderr=subprocess.PIPE,\n"
        "                check=False,\n"
        "                timeout=5,\n"
        "                creationflags=getattr(subprocess, \"CREATE_NO_WINDOW\", 0),\n"
        "            )"
    )

    occurrences = content.count(needle)
    if occurrences == 0:
        logger.warning(
            "[ATTENZIONE] Non ho riconosciuto le chiamate subprocess.run del "
            "codec in voice.py: la struttura del file a monte potrebbe essere "
            "cambiata. Le finestrelle del codec potrebbero restare visibili."
        )
        return

    patched = content.replace(needle, replacement)
    target.write_text(patched, encoding="utf-8")
    logger.info(
        "[OK] Nascoste le finestre del codec in voice.py "
        "(creationflags=CREATE_NO_WINDOW su %d chiamata/e).",
        occurrences,
    )


def patch_voice_codec_timeout() -> None:
    """
    Rende piu' tollerante (e configurabile) il timeout del codec vocale.

    Per OGNI frame vocale, tetraear/audio/voice.py invoca due processi
    esterni (cdecoder / sdecoder) con 'subprocess.run(..., timeout=5)'. Quel
    tetto di 5 secondi e' generoso a regime (il codec impiega pochi
    millisecondi), ma diventa un problema quando il sistema e' lento o "a
    freddo": alle prime chiamate, mentre l'antivirus analizza gli eseguibili
    appena compilati (tipico su Windows Defender) o su una macchina carica,
    l'esecuzione puo' superare i 5s. In quel caso subprocess.run solleva
    TimeoutExpired: il frame, per quanto decodificabile, viene scartato e la
    voce sembra "non decodificarsi".

    La patch:
      - inietta un timeout configurabile via la variabile d'ambiente
        TETRAEAR_CODEC_TIMEOUT (default 15 secondi, contro i 5 originali);
      - sostituisce i due 'timeout=5' delle chiamate al codec con quel valore.

    Il valore piu' alto non rallenta la decodifica a regime (il codec esce
    comunque in pochi ms): alza solo il tetto oltre cui si rinuncia, cosi'
    non si perdono frame validi quando il sistema e' momentaneamente lento.

    Va applicata DOPO patch_voice_hide_codec_window(): quest'ultima cerca la
    riga 'timeout=5' come ancora, quindi deve trovarla ancora intatta.

    Patch idempotente: se il timeout configurabile e' gia' presente non fa
    nulla.
    """
    step("Timeout del codec vocale piu' tollerante e configurabile")

    target = TETRAEAR_ROOT / "tetraear" / "audio" / "voice.py"
    if not target.is_file():
        logger.info("[INFO] %s non trovato, salto la patch.", target)
        return

    content = target.read_text(encoding="utf-8")
    if "_CODEC_TIMEOUT" in content:
        logger.info("[OK] Timeout del codec gia' configurabile (patch gia' applicata).")
        return

    # 1) Inietta la costante subito dopo la creazione dei logger del modulo.
    anchor = 'codec_logger = logging.getLogger("tetraear.codec")\n'
    definition = (
        anchor
        + "\n"
        + "# --- TetraEar: timeout del codec configurabile -----------------------\n"
        + "# Un timeout troppo aggressivo scarta frame decodificabili quando il\n"
        + "# sistema e' lento o al primo avvio (es. l'antivirus analizza gli\n"
        + "# eseguibili del codec appena compilati). Lo rendiamo configurabile via\n"
        + "# TETRAEAR_CODEC_TIMEOUT (in secondi) con un default piu' tollerante.\n"
        + "def _tetraear_codec_timeout() -> float:\n"
        + "    try:\n"
        + '        value = float(os.environ.get("TETRAEAR_CODEC_TIMEOUT", "15"))\n'
        + "    except (TypeError, ValueError):\n"
        + "        value = 15.0\n"
        + "    return value if value > 0 else 15.0\n"
        + "\n"
        + "\n"
        + "_CODEC_TIMEOUT = _tetraear_codec_timeout()\n"
        + "# --- Fine timeout del codec configurabile ----------------------------\n"
    )
    if anchor not in content:
        logger.warning(
            "[ATTENZIONE] Non ho trovato il punto in cui iniettare il timeout "
            "configurabile in voice.py: la struttura del file a monte potrebbe "
            "essere cambiata. Il timeout del codec resta a 5 secondi."
        )
        return
    content = content.replace(anchor, definition, 1)

    # 2) Usa il timeout configurabile nelle chiamate al codec. L'ancora
    #    'check=False,' + 'timeout=5,' resta valida sia prima sia dopo la
    #    patch delle finestre (che aggiunge 'creationflags' DOPO 'timeout').
    needle = "                check=False,\n                timeout=5,\n"
    replacement = "                check=False,\n                timeout=_CODEC_TIMEOUT,\n"
    occurrences = content.count(needle)
    if occurrences == 0:
        logger.warning(
            "[ATTENZIONE] Non ho riconosciuto le chiamate 'timeout=5' del codec "
            "in voice.py: il timeout resta invariato."
        )
        return
    content = content.replace(needle, replacement)

    target.write_text(content, encoding="utf-8")
    logger.info(
        "[OK] Timeout del codec reso configurabile in voice.py "
        "(TETRAEAR_CODEC_TIMEOUT, default 15s, su %d chiamata/e).",
        occurrences,
    )


# ============================================================
# FASE 4d -- Launcher senza terminale (icona / doppio clic)
# ============================================================

def create_launchers() -> None:
    """
    Crea un file .desktop per avviare TetraEar dal menu applicazioni o con
    doppio clic sull'icona (senza aprire un terminale). Ne mette una copia
    nel menu applicazioni e, se presente, sul Desktop.

    Il .desktop non lancia direttamente python: punta a uno script di avvio
    (run_tetraear.sh) generato accanto all'app. Cosi' anche il doppio clic
    avvia la cattura (--auto-start) con log dettagliato (-v) e salva tutto
    in TetraEar/logs/, incluso un console_*.log che cattura eventuali errori
    di avvio (es. chiavetta non vista) che con Terminal=false andrebbero
    altrimenti persi.
    """
    step("Creazione launcher senza terminale (icona / doppio clic)")

    py = VENV_DIR / "bin" / "python"
    if not py.is_file():
        logger.info("[INFO] venv non pronto, salto la creazione dei launcher.")
        return

    # Script di avvio dedicato: attiva il venv, avvia con --auto-start e
    # redirige l'output di console in un file (con Terminal=false stdout/stderr
    # verrebbero altrimenti scartati). I log di decodifica (codec_*.log, ...)
    # li scrive comunque l'app dentro logs/, relativi a questa cartella.
    run_script = TETRAEAR_ROOT / "run_tetraear.sh"
    run_script_content = (
        "#!/usr/bin/env bash\n"
        "# Avvia TetraEar con cattura automatica e logging completo.\n"
        "# Generato da install_linux.py: usato dal launcher .desktop\n"
        "# (doppio clic) perche' anche cosi' vengano prodotti i log.\n"
        f'cd "{TETRAEAR_ROOT}" || exit 1\n'
        "# logs/ puo' essere un symlink alla cartella log unificata accanto\n"
        "# all'installer: readlink -f la risolve e la (ri)crea se serve.\n"
        'mkdir -p "$(readlink -f logs)"\n'
        'STAMP="$(date +%Y%m%d_%H%M%S)"\n'
        '# shellcheck disable=SC1091\n'
        'source .venv/bin/activate\n'
        '# Ottimizzazioni prestazioni: temp del codec in RAM (tmpfs) e limite\n'
        '# thread BLAS per non saturare i core sottraendo CPU alla GUI.\n'
        'if [ -d /dev/shm ] && [ -w /dev/shm ]; then export TMPDIR="/dev/shm"; fi\n'
        'export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"\n'
        'export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"\n'
        'export MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}"\n'
        'export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-2}"\n'
        'export PYTHONDONTWRITEBYTECODE=1\n'
        'FREQ="${1:-392.225}"\n'
        '# -v (DEBUG) genera moltissimi log e puo rallentare la GUI quando\n'
        '# c-e segnale: di default NON e attivo. Per il debug: TETRAEAR_DEBUG=1\n'
        'VERBOSE=""\n'
        '[ -n "${TETRAEAR_DEBUG:-}" ] && VERBOSE="-v"\n'
        'exec python -m tetraear -f "$FREQ" $VERBOSE --auto-start '
        '>> "logs/console_${STAMP}.log" 2>&1\n'
    )
    try:
        run_script.write_text(run_script_content, encoding="utf-8")
        run_script.chmod(0o755)
        logger.info("[OK] Script di avvio creato: %s", run_script)
    except OSError as exc:
        logger.warning("[ATTENZIONE] Non sono riuscito a creare lo script di avvio: %s", exc)
        return

    icon_line = ""
    banner = INSTALLER_DIR / "assets" / "banner.svg"
    if banner.is_file():
        icon_line = f"Icon={banner}\n"

    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=TetraEar\n"
        "Comment=Decoder TETRA per RTL-SDR / TETRA decoder for RTL-SDR\n"
        f'Exec=/bin/bash "{run_script}"\n'
        f"Path={TETRAEAR_ROOT}\n"
        "Terminal=false\n"
        + icon_line
        + "Categories=HamRadio;Utility;\n"
    )

    desktop_file = TETRAEAR_ROOT / "TetraEar.desktop"
    try:
        desktop_file.write_text(content, encoding="utf-8")
        desktop_file.chmod(0o755)
        logger.info("[OK] Launcher creato: %s", desktop_file)
    except OSError as exc:
        logger.warning("[ATTENZIONE] Non sono riuscito a creare il launcher: %s", exc)
        return

    real_user = os.environ.get("SUDO_USER") or os.environ.get("USER") or ""
    home = Path(os.path.expanduser("~" + real_user)) if real_user else Path.home()
    targets = [
        home / ".local" / "share" / "applications",
        home / "Desktop",
        home / "Scrivania",  # nome della cartella Desktop in italiano
    ]
    for target_dir in targets:
        # Il menu applicazioni lo creiamo sempre; le cartelle Desktop solo se esistono.
        if target_dir.name != "applications" and not target_dir.is_dir():
            continue
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            dst = target_dir / "TetraEar.desktop"
            shutil.copy2(desktop_file, dst)
            dst.chmod(0o755)
            if shutil.which("gio"):  # marca l'icona come "attendibile" su GNOME
                run(["gio", "set", str(dst), "metadata::trusted", "true"], check=False)
        except OSError:
            pass

    logger.info("Puoi avviare TetraEar dal menu applicazioni o dall'icona sul Desktop.")


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
            "verra' rilevata solo quando colleghi una chiavetta e la usi."
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

def sync_working_codec_from_telive2() -> None:
    """Copia in TetraEar il codec vocale gia' PATCHATO e FUNZIONANTE compilato
    dalla catena TELIVE-2.

    La build del codec di TELIVE-2 (osmo download_and_patch.sh) applica
    correttamente le patch ETSI -- inclusa fix_64bit -- quindi il suo
    cdecoder/sdecoder NON va in segfault. Se disponibile, lo usiamo come sorgente
    autorevole per TetraEar: questo elimina il segfault -11 del cdecoder anche
    nei casi in cui la build interna del codec fosse difettosa. Best-effort: se
    il codec TELIVE-2 non e' presente, non fa nulla (resta la build interna)."""
    home = Path(os.path.expanduser("~"))
    candidate_dirs = [
        INSTALLER_DIR / "telive2" / "osmo-tetra-sq5bpf-2" / "codec" / "c-code",
        home / "telive2" / "osmo-tetra-sq5bpf-2" / "codec" / "c-code",
        Path("/tetra") / "bin",
    ]
    src_dir = next((d for d in candidate_dirs if (d / "cdecoder").is_file()), None)
    if src_dir is None:
        logger.info("[INFO] Codec TELIVE-2 non presente: mantengo la build interna del codec.")
        return
    if not CODEC_BIN_DIR.exists():
        logger.info("[INFO] Cartella bin del codec di TetraEar assente: salto la sincronizzazione.")
        return

    step("Uso il codec vocale gia' funzionante compilato da TELIVE-2")
    copied = []
    for name in ("cdecoder", "sdecoder", "ccoder", "scoder"):
        src = src_dir / name
        if not src.is_file():
            continue
        try:
            dst = CODEC_BIN_DIR / name
            shutil.copy2(src, dst)
            dst.chmod(dst.stat().st_mode | 0o111)
            copied.append(name)
        except OSError as exc:
            logger.warning("[ATTENZIONE] Copia di %s fallita (%s).", name, exc)
    if copied:
        logger.info("[OK] Codec TELIVE-2 copiato in TetraEar (%s)", ", ".join(copied))
        logger.info("     Sorgente: %s", src_dir)
        logger.info("     (risolve il segfault -11 del cdecoder: TELIVE-2 applica le patch ETSI)")
    else:
        logger.info("[INFO] Nessun binario del codec TELIVE-2 copiato.")


def do_repair() -> None:
    step("Modalita' --repair: ricompilo il codec vocale e sistemo la compatibilita' pyrtlsdr")
    ensure_tetraear_source(clone_if_missing=True)
    unify_logs_dir()
    patch_tetraear_source_bugs()
    patch_voice_hide_codec_window()
    patch_voice_codec_timeout()
    patch_tetraear_add_toolkit()
    patch_pyrtlsdr_dithering()
    install_tetra_codec_with_fallback()
    # Se la catena TELIVE-2 e' gia' presente da un'installazione precedente, usa
    # il suo codec (correttamente patchato) al posto di quello interno.
    sync_working_codec_from_telive2()
    create_launchers()
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

    logger.info("[OK] Disinstallazione completata (il codice sorgente non e' stato toccato)")


# ============================================================
# MAIN
# ============================================================

def run_extra_decoders(skip: bool) -> None:
    """
    Avvia in AUTOMATICO l'installer dei decoder aggiuntivi (DMR/P25, ADS-B,
    cercapersone), se presente accanto a questo script. E' best-effort: viene
    eseguito DOPO che TetraEar e' gia' installato e verificato, quindi un
    eventuale errore qui non compromette TetraEar. Si disattiva con --no-extra.
    """
    script = INSTALLER_DIR / "install_extra_decoders.py"
    if skip:
        logger.info("[INFO] Decoder aggiuntivi saltati (--no-extra).")
        return
    if not script.is_file():
        return

    step("Installo anche i decoder aggiuntivi (DMR/P25, ADS-B, cercapersone)")
    logger.info("Avvio %s (log in logs/install_extra.log) ...", script.name)
    # Output "dal vivo" (niente cattura): la compilazione puo' durare minuti.
    result = subprocess.run([sys.executable, str(script)])
    if result.returncode != 0:
        logger.warning(
            "[ATTENZIONE] L'installazione di uno o piu' decoder aggiuntivi non e' "
            "andata a buon fine (vedi logs/install_extra.log). TetraEar resta "
            "comunque installato e funzionante."
        )


def run_telive2(skip: bool) -> None:
    """
    Avvia in AUTOMATICO l'installer della catena TELIVE-2 (decifratura vocale
    TETRA a chiave nota), se presente accanto a questo script. E' best-effort:
    viene eseguito DOPO che TetraEar e' gia' installato e verificato, quindi un
    eventuale errore qui non compromette TetraEar. Si disattiva con --no-telive2.
    """
    script = INSTALLER_DIR / "install_telive2.py"
    if skip:
        logger.info("[INFO] Catena TELIVE-2 saltata (--no-telive2).")
        return
    if not script.is_file():
        return

    step("Installo anche TELIVE-2 (decifratura vocale a chiave nota)")
    logger.info("Avvio %s (log in logs/install_telive2.log) ...", script.name)
    # Output "dal vivo" (niente cattura): la build puo' durare diversi minuti.
    result = subprocess.run([sys.executable, str(script)])
    if result.returncode != 0:
        logger.warning(
            "[ATTENZIONE] L'installazione di TELIVE-2 non e' andata a buon fine "
            "(vedi logs/install_telive2.log). TetraEar resta comunque installato "
            "e funzionante."
        )


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
    group.add_argument(
        "--check", action="store_true",
        help="Verifica soltanto lo stato dell'installazione, senza modificare nulla",
    )
    parser.add_argument(
        "--ref", metavar="COMMIT|TAG|BRANCH", default=None,
        help=(
            "Versione di TetraEar da installare (commit, tag o branch). "
            "Ha la precedenza sulla variabile d'ambiente TETRAEAR_REF. Se "
            "omessa, si usa la versione fissata e testata (release v2.3)."
        ),
    )
    parser.add_argument(
        "--no-extra", action="store_true",
        help="Non installare automaticamente i decoder aggiuntivi (DMR/P25, ADS-B, cercapersone)",
    )
    parser.add_argument(
        "--no-telive2", action="store_true",
        help="Non installare automaticamente la catena TELIVE-2 (decifratura vocale a chiave nota)",
    )
    return parser.parse_args()


def resolve_tetraear_ref(cli_ref: str | None) -> str:
    """
    Determina quale versione di TetraEar installare, in ordine di priorita':
      1. --ref sulla riga di comando
      2. variabile d'ambiente TETRAEAR_REF
      3. il commit fissato e testato (TETRAEAR_DEFAULT_REF)
    Aggiorna la variabile globale usata dal clone.
    """
    global TETRAEAR_REF
    env_ref = os.environ.get("TETRAEAR_REF", "").strip()
    TETRAEAR_REF = (cli_ref or "").strip() or env_ref or TETRAEAR_DEFAULT_REF
    if TETRAEAR_REF == TETRAEAR_DEFAULT_REF:
        logger.info("Versione TetraEar: %s (fissata, release v2.3)", TETRAEAR_REF)
    else:
        logger.info("Versione TetraEar: %s (richiesta dall'utente)", TETRAEAR_REF)
    return TETRAEAR_REF


def do_check() -> None:
    """
    Modalita' di sola diagnostica: non installa e non modifica nulla, si
    limita a localizzare il sorgente gia' presente e a rieseguire i
    controlli finali (venv, binari del codec, import di pyrtlsdr, chiavetta).
    Utile per capire cosa manca senza rilanciare l'intera installazione.
    """
    step("Modalita' --check: verifica dello stato dell'installazione")
    root = ensure_tetraear_source(clone_if_missing=False)
    if not _looks_like_tetraear_root(root):
        fail(
            "Sorgente di TetraEar non trovato: sembra che l'installazione non "
            "sia mai stata completata. Esegui 'python3 install_linux.py'."
        )
    version_file = root / TETRAEAR_VERSION_FILE
    if version_file.is_file():
        logger.info("Versione installata (commit): %s", version_file.read_text().strip())
    verify_installation()


def main() -> int:
    args = parse_args()

    logger.info("====== TetraEar Linux Installer v%s ======", SCRIPT_VERSION)
    logger.info("Log completo salvato in: %s", LOG_FILE)
    warn_if_in_trash()

    try:
        if args.uninstall:
            do_uninstall()
            return 0

        if args.check:
            do_check()
            return 0

        check_python_version()
        check_operating_system()
        resolve_tetraear_ref(args.ref)

        if args.repair:
            do_repair()
            return 0

        install_system_dependencies()
        ensure_tetraear_source(clone_if_missing=True)
        unify_logs_dir()
        patch_tetraear_source_bugs()
        patch_voice_hide_codec_window()
        patch_voice_codec_timeout()
        patch_tetraear_add_toolkit()
        create_virtualenv_and_install_requirements()
        # La configurazione della chiavetta viene fatta PRIMA del codec:
        # il codec dipende da un download esterno (ETSI) che potrebbe
        # fallire, ma il dongle dev'essere comunque pronto all'uso.
        configure_rtl_sdr()
        install_tetra_codec_with_fallback()
        create_launchers()
        verify_installation()
        # TetraEar e' pronto: installo anche gli altri decoder in automatico.
        run_extra_decoders(args.no_extra)
        # ...e la catena TELIVE-2 (decifratura vocale a chiave nota).
        run_telive2(args.no_telive2)
        # TELIVE-2 ha appena compilato un codec ETSI correttamente patchato:
        # usalo in TetraEar per evitare il segfault -11 del cdecoder interno.
        sync_working_codec_from_telive2()
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
