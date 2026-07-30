#!/usr/bin/env python3
"""
install_windows.py -- Installer automatico per TetraEar su Windows
==================================================================

Testato per: Windows 10 / 11 (64 bit).

Di norma NON si lancia questo file a mano: si fa doppio clic su
`install_windows.bat`, che si occupa di installare Python se manca e poi
avvia questo script. Se pero' Python e' gia' presente puoi anche eseguire:

    python install_windows.py              # installazione completa
    python install_windows.py --repair     # ricompila solo il codec vocale
    python install_windows.py --uninstall  # rimuove venv + codec compilato

Cosa fa, in ordine:
    1. Controlla versione di Python e che il sistema sia Windows
    2. Installa le dipendenze di sistema tramite winget (Git e MSYS2, che
       fornisce il compilatore C necessario al codec vocale)
    3. Scarica (git clone) il codice sorgente di TetraEar se non e' gia'
       presente accanto a questo script
    4. Crea un virtual environment (.venv) e installa requirements.txt
    5. Scarica e compila il codec vocale ETSI TETRA (cdecoder.exe / sdecoder.exe)
       usando il compilatore fornito da MSYS2
    6. Verifica che tutto sia a posto e stampa un riepilogo finale

Nota sull'hardware RTL-SDR: su Windows la chiavetta richiede il driver
WinUSB installato con Zadig e la libreria rtlsdr.dll nel PATH. Questi due
passaggi sono, per loro natura, semi-manuali e sono spiegati nella guida
(README.md). L'installer avvisa ma non blocca.

Ogni passaggio scrive sia a schermo che nel file install.log.
"""

import argparse
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

TETRAEAR_REPO_URL = "https://github.com/syrex1013/TetraEar.git"

# Versione di TetraEar da installare. Per default fissiamo un commit noto e
# testato (release v2.3), cosi' l'installazione e' RIPRODUCIBILE: un
# cambiamento a monte del progetto non puo' rompere di sorpresa le patch che
# questo installer applica. Per prendere comunque l'ultimo codice, impostare
# la variabile d'ambiente TETRAEAR_REF (a un commit, tag o branch, es.
# "master") oppure passare --ref sulla riga di comando.
TETRAEAR_DEFAULT_REF = "c46141a62c5aec1a68ea7e3c1c570bcf461833e5"  # release v2.3
TETRAEAR_REF = TETRAEAR_DEFAULT_REF
# File in cui registriamo il commit esatto installato: rende l'installazione
# verificabile a posteriori (utile per il supporto e per --check).
TETRAEAR_VERSION_FILE = ".tetraear_version"

INSTALLER_DIR = Path(__file__).resolve().parent
# Tutti i log (installazione compresa) finiscono in ./logs/ accanto allo script.
LOG_DIR = INSTALLER_DIR / "logs"
LOG_FILE = LOG_DIR / "install.log"

# Percorsi derivati, impostati a runtime da configure_paths().
TETRAEAR_ROOT = INSTALLER_DIR
VENV_DIR = TETRAEAR_ROOT / ".venv"
REQUIREMENTS_FILE = TETRAEAR_ROOT / "requirements.txt"
CODEC_BASE_DIR = TETRAEAR_ROOT / "tetraear" / "tetra_codec"
CODEC_BIN_DIR = CODEC_BASE_DIR / "bin"

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

DOWNLOAD_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

OSMO_TETRA_REPO_URLS = [
    "https://gitea.osmocom.org/tetra/osmo-tetra.git",
    "https://github.com/osmocom/osmo-tetra.git",
]

# Pacchetti winget (id ufficiali) da installare se assenti.
WINGET_PACKAGES = {
    "git": "Git.Git",
    "MSYS2": "MSYS2.MSYS2",
}

# Percorsi tipici in cui MSYS2 viene installato da winget.
MSYS2_CANDIDATE_ROOTS = [
    Path(r"C:\msys64"),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "MSYS2",
]

# Toolchain MinGW da installare dentro MSYS2 (fornisce gcc/make/dos2unix).
MSYS2_TOOLCHAIN_PACKAGES = [
    "base-devel",
    "mingw-w64-ucrt-x86_64-gcc",
    "make",
    "patch",
    "dos2unix",
]

# Pacchetto MSYS2 che fornisce la libreria RTL-SDR nativa per Windows
# (rtlsdr.dll + libusb): serve a pyrtlsdr per essere importato, altrimenti
# TetraEar non parte proprio ("cannot find rtlsdr.dll").
MSYS2_RTLSDR_PACKAGE = "mingw-w64-ucrt-x86_64-rtl-sdr"

# DLL da copiare accanto all'interprete Python del venv (dove ctypes le
# trova) per far funzionare pyrtlsdr su Windows.
RTLSDR_DLL_NAMES = ["librtlsdr.dll", "libusb-1.0.dll", "libwinpthread-1.dll"]

# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("tetraear_installer_win")
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
    """Errore gestito: stampato in modo chiaro, niente traceback grezzo."""


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
) -> subprocess.CompletedProcess:
    """Esegue un comando esterno mostrando SEMPRE, in caso di errore, il
    codice di uscita e l'intero stderr. Nessun shell=True."""
    logger.debug("Eseguo comando: %s (cwd=%s)", " ".join(cmd), cwd or INSTALLER_DIR)
    try:
        # encoding esplicito: pacman/git emettono UTF-8, ma su Windows il
        # default sarebbe la codepage di sistema (cp1252) e il log si
        # riempirebbe di caratteri corrotti ("Ã¨" al posto di "e'").
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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
    return (path / "requirements.txt").is_file() and (path / "tetraear").is_dir()


def configure_paths(root: Path) -> None:
    global TETRAEAR_ROOT, VENV_DIR, REQUIREMENTS_FILE, CODEC_BASE_DIR, CODEC_BIN_DIR
    TETRAEAR_ROOT = root
    VENV_DIR = root / ".venv"
    REQUIREMENTS_FILE = root / "requirements.txt"
    CODEC_BASE_DIR = root / "tetraear" / "tetra_codec"
    CODEC_BIN_DIR = CODEC_BASE_DIR / "bin"


def unify_logs_dir() -> None:
    """
    Unica cartella per TUTTI i log, come su Linux. Se TetraEar e' una
    sottocartella, la sua 'logs' diventa una JUNCTION (mklink /J) verso la
    'logs' accanto all'installer: install.log, install_extra.log, codec_*.log,
    console_*.log ecc. finiscono cosi' in un solo posto. Su Windows si usa una
    junction (non un symlink) perche' NON richiede privilegi di amministratore.
    Eventuali log gia' presenti vengono spostati, non persi. Best-effort: un
    errore qui non blocca l'installazione.
    """
    if TETRAEAR_ROOT == INSTALLER_DIR:
        return  # lo script e' gia' dentro TetraEar: esiste una sola logs

    app_logs = TETRAEAR_ROOT / "logs"
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Junction gia' presente e corretta? Niente da fare.
        if app_logs.exists() and app_logs.is_dir():
            try:
                if app_logs.resolve() == LOG_DIR.resolve() and app_logs.is_symlink():
                    return
            except OSError:
                pass

        if app_logs.is_symlink():
            # Junction/symlink verso un'altra destinazione: la rimuovo.
            app_logs.unlink()
        elif app_logs.is_dir():
            # Migro i log esistenti nella cartella unificata (senza
            # sovrascrivere eventuali omonimi gia' presenti).
            for entry in app_logs.iterdir():
                target = LOG_DIR / entry.name
                if not target.exists():
                    shutil.move(str(entry), str(target))
            app_logs.rmdir()

        # 'mklink /J' e' un comando interno di cmd.exe: crea una junction di
        # cartella senza bisogno di permessi elevati.
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(app_logs), str(LOG_DIR)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            logger.info("[OK] Cartella log unificata: %s -> %s", app_logs, LOG_DIR)
        else:
            # Se la junction non si crea, l'app usera' comunque la sua cartella.
            app_logs.mkdir(parents=True, exist_ok=True)
            logger.warning(
                "[ATTENZIONE] Non sono riuscito a unificare le cartelle dei log "
                "(%s): l'app scrivera' in %s.",
                result.stderr.strip() or "mklink fallito", app_logs,
            )
    except OSError as exc:
        logger.warning(
            "[ATTENZIONE] Non sono riuscito a unificare le cartelle dei log (%s): "
            "l'app continuera' a scrivere in %s.", exc, app_logs
        )


def ensure_tetraear_source(clone_if_missing: bool = True) -> Path:
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
        configure_paths(cloned_dir)
        return cloned_dir

    step("Scarico il codice sorgente di TetraEar")
    git_exe = which_git()
    if git_exe is None:
        fail("git non e' installato: impossibile scaricare il sorgente di TetraEar.")

    if cloned_dir.exists():
        logger.info("Rimuovo una copia incompleta preesistente: %s", cloned_dir)
        shutil.rmtree(cloned_dir, ignore_errors=True)

    _clone_tetraear_pinned(git_exe, TETRAEAR_REPO_URL, TETRAEAR_REF, cloned_dir)

    if not _looks_like_tetraear_root(cloned_dir):
        fail(
            "Il repository e' stato scaricato ma non contiene i file attesi "
            "(requirements.txt e cartella tetraear/)."
        )

    logger.info("[OK] Sorgente di TetraEar scaricato in %s", cloned_dir)
    configure_paths(cloned_dir)
    return cloned_dir


def _clone_tetraear_pinned(git_exe: str, repo_url: str, ref: str, dest: Path) -> None:
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

    run([git_exe, "init", "-q", dest_str])
    run([git_exe, "-C", dest_str, "remote", "add", "origin", repo_url])

    fetched = run(
        [git_exe, "-C", dest_str, "fetch", "--depth", "1", "origin", ref],
        check=False,
    )
    if fetched.returncode == 0:
        run([git_exe, "-C", dest_str, "checkout", "-q", "FETCH_HEAD"])
    else:
        logger.info(
            "Fetch shallow del ref non riuscito (il server potrebbe non "
            "permettere il fetch per commit): provo un clone completo..."
        )
        shutil.rmtree(dest, ignore_errors=True)
        run([git_exe, "clone", repo_url, dest_str])
        run([git_exe, "-C", dest_str, "checkout", "-q", ref])

    resolved = run([git_exe, "-C", dest_str, "rev-parse", "HEAD"], check=False)
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


def check_operating_system() -> None:
    step("Controllo sistema operativo")
    if platform.system() != "Windows":
        fail("Questo script serve solo per Windows. Su Ubuntu/Debian usa install_linux.py.")
    logger.info("[OK] Sistema operativo: %s %s", platform.system(), platform.release())


# ============================================================
# FASE 2 -- Dipendenze di sistema (winget + MSYS2)
# ============================================================

def which_git() -> str | None:
    """git potrebbe non essere ancora nel PATH della sessione corrente
    subito dopo l'installazione con winget: controlliamo anche i percorsi
    tipici."""
    found = shutil.which("git")
    if found:
        return found
    for candidate in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd" / "git.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Git" / "cmd" / "git.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _winget_available() -> bool:
    return shutil.which("winget") is not None


def _winget_package_installed(package_id: str) -> bool:
    result = run(["winget", "list", "--id", package_id, "-e"], check=False)
    return result.returncode == 0 and package_id.lower() in result.stdout.lower()


def install_system_dependencies() -> None:
    step("Installazione dipendenze di sistema (winget + MSYS2)")

    if not _winget_available():
        fail(
            "winget non trovato. winget e' incluso in Windows 10/11 aggiornati "
            "(App Installer dal Microsoft Store). Installalo e riprova, oppure "
            "installa manualmente Git e MSYS2 come spiegato nella guida."
        )

    for human_name, package_id in WINGET_PACKAGES.items():
        if _winget_package_installed(package_id):
            logger.info("[OK] %s gia' installato", human_name)
            continue
        logger.info("Installo %s (%s) tramite winget...", human_name, package_id)
        run(
            [
                "winget", "install", "--id", package_id, "-e",
                "--accept-source-agreements", "--accept-package-agreements",
                "--silent",
            ]
        )
        logger.info("[OK] %s installato", human_name)

    ensure_msys2_toolchain()


def find_msys2_root() -> Path | None:
    for root in MSYS2_CANDIDATE_ROOTS:
        if (root / "usr" / "bin" / "bash.exe").is_file():
            return root
    return None


def ensure_msys2_toolchain() -> Path:
    """Assicura che dentro MSYS2 sia presente il compilatore C (gcc/make).
    Ritorna il percorso di bash.exe di MSYS2."""
    msys2_root = find_msys2_root()
    if msys2_root is None:
        fail(
            "MSYS2 risulta installato ma non trovo la sua cartella "
            "(cercato in: " + ", ".join(str(p) for p in MSYS2_CANDIDATE_ROOTS) + "). "
            "Riavvia il PC e rilancia l'installer, oppure indica il percorso a mano."
        )

    bash_exe = msys2_root / "usr" / "bin" / "bash.exe"
    logger.info("Aggiorno i pacchetti base di MSYS2 (puo' richiedere qualche minuto)...")
    run([str(bash_exe), "-lc", "pacman -Syu --noconfirm --needed"], check=False)

    pkgs = " ".join(MSYS2_TOOLCHAIN_PACKAGES)
    logger.info("Installo la toolchain di compilazione dentro MSYS2: %s", pkgs)
    run([str(bash_exe), "-lc", f"pacman -S --noconfirm --needed {pkgs}"])

    logger.info("[OK] Toolchain MSYS2 pronta")
    return bash_exe


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

    python_path = VENV_DIR / "Scripts" / "python.exe"
    if not python_path.is_file():
        fail(f"python non trovato dentro il virtual environment: {python_path}")

    logger.info("Aggiorno pip...")
    run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])

    logger.info("Installo i pacchetti elencati in requirements.txt (puo' richiedere qualche minuto)...")
    run([str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)])

    logger.info("[OK] Ambiente Python pronto in %s", VENV_DIR)

    patch_pyrtlsdr_dithering()


def patch_pyrtlsdr_dithering() -> None:
    """
    pyrtlsdr lega MOLTE funzioni di librtlsdr in modo NON opzionale
    (rtlsdr_set_dithering, rtlsdr_set_gpio_output, ...): diverse esistono
    solo nel fork 'keenerd'. Con una rtlsdr.dll che non le espone, l'import
    di 'rtlsdr' fallisce ('undefined symbol: ...'). Avvolgiamo la libreria
    in un proxy che, per i simboli mancanti, restituisce uno stub innocuo,
    cosi' l'import non fallisce (quelle funzioni sono accessorie).
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
        "# Avvolge librtlsdr in un proxy che, per i simboli assenti nella DLL",
        "# di sistema, restituisce uno stub innocuo invece di far fallire l'import.",
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
    logger.info("[OK] pyrtlsdr reso compatibile con la libreria RTL-SDR.")


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
    esterni (cdecoder.exe / sdecoder.exe) con 'subprocess.run(..., timeout=5)'.
    Quel tetto di 5 secondi e' generoso a regime (il codec impiega pochi
    millisecondi), ma diventa un problema quando il sistema e' lento o "a
    freddo": alle prime chiamate, mentre Windows Defender analizza gli
    eseguibili appena compilati o su una macchina carica, l'esecuzione puo'
    superare i 5s. In quel caso subprocess.run solleva TimeoutExpired: il
    frame, per quanto decodificabile, viene scartato e la voce sembra "non
    decodificarsi".

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
        + "# sistema e' lento o al primo avvio (es. Windows Defender analizza gli\n"
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


def patch_tetraear_add_network_info() -> None:
    """
    Aggiunge alla GUI di TetraEar un tab "Network Info": un pannello PASSIVO
    coi parametri di rete trasmessi in chiaro nel broadcast TETRA (MCC/MNC/LA/
    Colour Code/modo/portante/AIE/Security Class/Cipher Key ID/autenticazione),
    ispirato al plugin dell'articolo "Interception of TETRA radio". I dati
    arrivano dal ricevitore TELIVE-2 'tetra-rx' (che decodifica il SYSINFO); il
    parsing riusa lo stesso motore del tool standalone tetra_netscanner.py. Il
    tab NON decifra nulla.

    Copia il motore (tetra_netscanner.py) e il widget del tab
    (tetra_netinfo_tab.py) dentro il pacchetto (tetraear/ui/) e inietta in
    tetraear/ui/modern.py, dentro init_ui e dopo il tab "Statistics", una riga
    che registra il tab. Idempotente (sentinel "network_info_tab") e difensiva:
    l'addTab e' avvolto in try/except, cosi' non puo' mai impedire l'avvio.
    """
    step("Aggiunta del tab 'Network Info' alla GUI di TetraEar")

    ui_dir = TETRAEAR_ROOT / "tetraear" / "ui"
    modern = ui_dir / "modern.py"
    if not modern.is_file():
        logger.info("[INFO] %s non trovato, salto il tab Network Info.", modern)
        return

    to_copy = {
        INSTALLER_DIR / "tetra_netscanner.py": ui_dir / "tetra_netinfo_backend.py",
        INSTALLER_DIR / "tetra_netinfo_tab.py": ui_dir / "network_info_tab.py",
    }
    for src, dst in to_copy.items():
        if not src.is_file():
            logger.warning(
                "[ATTENZIONE] Manca %s: non installo il tab Network Info "
                "(il tool standalone resta comunque disponibile).", src.name,
            )
            return
        try:
            shutil.copy2(src, dst)
            logger.info("[OK] Copiato %s -> tetraear/ui/%s", src.name, dst.name)
        except OSError as exc:
            logger.warning("[ATTENZIONE] Copia di %s fallita (%s): salto il tab.", src.name, exc)
            return

    content = modern.read_text(encoding="utf-8")
    if "network_info_tab" in content:
        logger.info("[OK] Tab Network Info gia' presente in modern.py.")
        return
    anchor = 'tabs.addTab(stats_widget, "\U0001f4ca Statistics")'
    if anchor not in content:
        logger.warning(
            "[ATTENZIONE] Anchor del tab 'Statistics' non trovato in modern.py: "
            "la struttura del sorgente a monte potrebbe essere cambiata. Non "
            "aggiungo il tab (i moduli sono comunque copiati)."
        )
        return
    injection = (
        anchor + "\n"
        "        # TetraEar Network Scanner: tab passivo dei metadati di rete\n"
        "        # (SYSINFO via ricevitore TELIVE-2). Opzionale: mai bloccare l'avvio.\n"
        "        try:\n"
        "            from tetraear.ui.network_info_tab import NetworkInfoTab\n"
        "            self.network_info_tab = NetworkInfoTab(self)\n"
        '            tabs.addTab(self.network_info_tab, "\U0001f4f6 Network Info")\n'
        "        except Exception as _nis_e:\n"
        "            import logging as _nis_log\n"
        '            _nis_log.getLogger("tetraear").warning("Network Info tab non caricato: %s", _nis_e)'
    )
    content = content.replace(anchor, injection, 1)
    modern.write_text(content, encoding="utf-8")
    logger.info("[OK] Tab 'Network Info' registrato in modern.py (init_ui).")


# ============================================================
# FASE 4 -- Compilazione del codec vocale ETSI TETRA (via MSYS2)
# ============================================================

def _download_with_browser_headers(url: str, destination: Path) -> None:
    """
    Scarica un singolo file con un User-Agent "da browser". Solleva
    l'eccezione originale in caso di errore: e' il chiamante a decidere se
    provare un mirror alternativo o fermarsi.
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
        "riprova piu' tardi con 'python install_windows.py --repair'. Se l'URL e' "
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
            f"atteso {expected_md5}, ottenuto {actual}."
        )


def _lowercase_filenames(directory: Path) -> None:
    """
    L'archivio ETSI usa nomi MAIUSCOLI (SCODER.C, MAKEFILE) ma il Makefile
    li richiama in minuscolo. Uniformiamo in minuscolo tutti i file.

    ATTENZIONE: su Windows il filesystem NTFS e' case-insensitive, quindi
    per 'MAKEFILE' il percorso 'makefile' risulta gia' esistente (e' lo
    STESSO file). In quel caso NON bisogna cancellarlo: si rinomina in due
    passi (via nome temporaneo) per forzare il cambio di maiuscole/minuscole.
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


def _normalize_line_endings(root: Path) -> None:
    """L'archivio ETSI ha file con fine riga Windows (CRLF): li normalizziamo
    a LF, altrimenti le patch osmocom falliscono con
    'Hunk FAILED (different line endings)'."""
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix.lower() in (".c", ".h") or path.name.lower() == "makefile"):
            try:
                raw = path.read_bytes()
                if b"\r\n" in raw:
                    path.write_bytes(raw.replace(b"\r\n", b"\n"))
            except OSError:
                pass


def _fix_makefile_for_modern_gcc(makefile_path: Path) -> None:
    data = makefile_path.read_text(encoding="utf-8", errors="ignore")
    data = re.sub(r"(?m)^ACC\s*=\s*acc\b", "ACC = gcc", data)
    data = re.sub(r"(?m)^(\s*)acc\b", r"\1gcc", data)
    data = re.sub(r"\bacc\b", "gcc", data)
    if "-fcommon" not in data:
        data = re.sub(r"(?m)^CFLAGS\s*=\s*(.*)$", r"CFLAGS = -fcommon \1", data)
    data = data.replace("-Werror", "")
    makefile_path.write_text(data, encoding="utf-8")


def _msys2_bash() -> Path:
    root = find_msys2_root()
    if root is None:
        fail("MSYS2 non trovato: impossibile compilare il codec. Reinstalla MSYS2.")
    return root / "usr" / "bin" / "bash.exe"


def _to_msys_path(bash_exe: Path, win_path: Path) -> str:
    """Converte un percorso Windows (C:\\x) nel formato MSYS (/c/x) usando
    cygpath, cosi' make/gcc lo capiscono."""
    result = run([str(bash_exe), "-lc", f'cygpath -u "{win_path}"'])
    return result.stdout.strip()


def _apply_osmo_tetra_patches(bash_exe: Path, codec_dir: Path, work_dir: Path) -> bool:
    git_exe = which_git()
    if git_exe is None:
        return False

    osmo_dir = work_dir / "osmo-tetra"
    cloned = False
    for repo_url in OSMO_TETRA_REPO_URLS:
        logger.info("Provo a scaricare le patch da %s ...", repo_url)
        # -c core.autocrlf=false: su Windows Git convertirebbe i file patch in
        # CRLF, facendo fallire l'applicazione con "different line endings".
        result = run(
            [git_exe, "-c", "core.autocrlf=false", "-c", "core.eol=lf",
             "clone", "--depth", "1", repo_url, str(osmo_dir)],
            check=False,
        )
        if result.returncode == 0:
            cloned = True
            break
        logger.warning("Mirror non raggiungibile, provo il successivo...")

    if not cloned:
        logger.warning(
            "[ATTENZIONE] Impossibile scaricare le patch ufficiali. "
            "Procedo con il metodo di riserva (compilazione diretta, senza patch)."
        )
        return False

    patch_dir = osmo_dir / "etsi_codec-patches"
    series_file = patch_dir / "series"
    if not series_file.is_file():
        logger.warning("File 'series' delle patch non trovato, uso il metodo di riserva.")
        return False

    # Doppia sicurezza: normalizziamo comunque i file .patch a LF, cosi' le
    # fini riga combaciano con i sorgenti (anch'essi normalizzati a LF).
    for pf in patch_dir.glob("*.patch"):
        try:
            raw = pf.read_bytes()
            if b"\r\n" in raw:
                pf.write_bytes(raw.replace(b"\r\n", b"\n"))
        except OSError:
            pass

    codec_msys = _to_msys_path(bash_exe, codec_dir)
    for patch_name in series_file.read_text(encoding="utf-8").splitlines():
        patch_name = patch_name.strip()
        if not patch_name or patch_name.startswith("#"):
            continue
        patch_file = patch_dir / patch_name
        if not patch_file.is_file():
            logger.warning("Patch elencata ma non trovata: %s (la salto)", patch_name)
            continue
        logger.info("Applico patch: %s", patch_name)
        patch_msys = _to_msys_path(bash_exe, patch_file)
        result = run(
            [str(bash_exe), "-lc", f'cd "{codec_msys}" && patch --batch -p1 -N -E < "{patch_msys}"'],
            check=False,
        )
        if result.returncode not in (0, 1):  # 1 = gia' applicata
            logger.error("Applicazione patch fallita: %s\n%s", patch_name, result.stderr)
            fail(f"Patch fallita: {patch_name}")
        # Con exit code 1 'patch' segnala anche gli hunk NON applicati:
        # non blocchiamo (il codec compila comunque), ma deve restare
        # traccia CHIARA nel log, non un finto successo.
        if result.returncode == 1 and "FAILED" in (result.stdout + result.stderr):
            logger.warning(
                "[ATTENZIONE] Alcune parti della patch %s NON sono state "
                "applicate (vedi dettagli sopra nel log). Il codec verra' "
                "compilato comunque, ma la decodifica potrebbe risentirne.",
                patch_name,
            )

    return True


def install_tetra_codec(fallback_only: bool = False) -> None:
    step("Compilazione del codec vocale ETSI TETRA (cdecoder.exe / sdecoder.exe)")

    bash_exe = _msys2_bash()
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

        c_code_dir = find_path_ci(work_dir, "c-code")
        if c_code_dir is None:
            fail("Cartella 'c-code' non trovata nell'archivio ETSI estratto (formato inatteso).")

        # L'archivio ETSI usa nomi MAIUSCOLI ma il Makefile li richiama in
        # minuscolo: uniformiamo prima di compilare.
        logger.info("Uniformo i nomi dei file del codec in minuscolo...")
        _lowercase_filenames(c_code_dir)

        # Normalizziamo CRLF -> LF, altrimenti le patch osmocom falliscono.
        _normalize_line_endings(work_dir)

        if not fallback_only:
            _apply_osmo_tetra_patches(bash_exe, c_code_dir.parent, work_dir)
        else:
            logger.info("Modalita' di riserva: salto l'applicazione delle patch ufficiali.")

        makefile_path = find_path_ci(c_code_dir, "makefile")
        if makefile_path is None:
            fail("Makefile non trovato dentro c-code/.")

        logger.info("Sistemo il Makefile per un compilatore GCC moderno...")
        _fix_makefile_for_modern_gcc(makefile_path)

        logger.info("Compilo con il compilatore MSYS2 (make)...")
        c_code_msys = _to_msys_path(bash_exe, c_code_dir)
        # Aggiungiamo la toolchain UCRT al PATH dentro la shell MSYS2 e
        # compiliamo forzando CC=gcc.
        build_cmd = (
            'export PATH="/ucrt64/bin:$PATH" && '
            f'cd "{c_code_msys}" && '
            f'make -f "{makefile_path.name}" CC=gcc'
        )
        run([str(bash_exe), "-lc", build_cmd])

        CODEC_BIN_DIR.mkdir(parents=True, exist_ok=True)
        # Su Windows i binari possono chiamarsi con o senza estensione .exe.
        wanted = ["cdecoder", "sdecoder", "ccoder", "scoder"]
        missing = []
        for base_name in wanted:
            src = find_path_ci(c_code_dir, base_name + ".exe") or find_path_ci(c_code_dir, base_name)
            if src is None:
                missing.append(base_name)
                continue
            dst = CODEC_BIN_DIR / (base_name + ".exe")
            shutil.copy2(src, dst)
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
    try:
        install_tetra_codec(fallback_only=False)
    except InstallError:
        logger.warning("")
        logger.warning("Il metodo con patch ufficiali e' fallito, provo il metodo di riserva...")
        install_tetra_codec(fallback_only=True)


# ============================================================
# FASE 4c -- Libreria RTL-SDR nativa per Windows (rtlsdr.dll)
# ============================================================

def install_windows_rtlsdr_dll() -> None:
    """
    Su Windows pyrtlsdr carica 'rtlsdr.dll' via ctypes al momento
    dell'import: se la DLL non c'e', TetraEar NON parte affatto (l'import
    di 'rtlsdr' fallisce). Su Linux la libreria la fornisce apt; su Windows
    dobbiamo fornirla noi. Installiamo il pacchetto rtl-sdr di MSYS2 e
    copiamo le DLL accanto all'interprete Python del venv (la cartella di
    python.exe fa parte del percorso di ricerca DLL di Windows).
    """
    step("Libreria RTL-SDR per Windows (rtlsdr.dll)")

    bash_exe = _msys2_bash()
    msys2_root = find_msys2_root()
    if msys2_root is None:
        logger.warning("[ATTENZIONE] MSYS2 non trovato: salto la copia di rtlsdr.dll.")
        return

    logger.info("Installo %s in MSYS2...", MSYS2_RTLSDR_PACKAGE)
    run([str(bash_exe), "-lc", f"pacman -S --noconfirm --needed {MSYS2_RTLSDR_PACKAGE}"], check=False)

    ucrt_bin = msys2_root / "ucrt64" / "bin"
    scripts_dir = VENV_DIR / "Scripts"
    # Copiamo le DLL sia accanto a python.exe (venv Scripts, gia' nel percorso
    # di ricerca DLL) sia dove l'app le cerca esplicitamente: capture.py su
    # Windows aggiunge 'tetraear/bin' e 'tetraear/' con os.add_dll_directory().
    pkg_dir = TETRAEAR_ROOT / "tetraear"
    destinations = [scripts_dir, TETRAEAR_ROOT, pkg_dir, pkg_dir / "bin"]

    copied = []
    for dll in RTLSDR_DLL_NAMES:
        src = ucrt_bin / dll
        if not src.is_file():
            logger.warning("[ATTENZIONE] DLL non trovata in MSYS2: %s", src)
            continue
        for dest in destinations:
            try:
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest / dll)
            except OSError as exc:
                logger.warning("[ATTENZIONE] Copia di %s in %s fallita: %s", dll, dest, exc)
        copied.append(dll)

    # pyrtlsdr cerca la libreria anche col nome 'rtlsdr.dll'.
    librtlsdr = ucrt_bin / "librtlsdr.dll"
    if librtlsdr.is_file():
        for dest in destinations:
            try:
                shutil.copy2(librtlsdr, dest / "rtlsdr.dll")
            except OSError:
                pass

    if copied:
        logger.info("[OK] DLL RTL-SDR copiate (%s) in %s", ", ".join(copied), scripts_dir)
    else:
        logger.warning(
            "[ATTENZIONE] Nessuna DLL RTL-SDR copiata: l'app potrebbe non "
            "partire. Controlla che il pacchetto %s sia disponibile in MSYS2.",
            MSYS2_RTLSDR_PACKAGE,
        )


def verify_pyrtlsdr_import() -> None:
    """Controllo end-to-end: prova a importare 'rtlsdr' nel venv. E' qui che
    si vede se la DLL rtlsdr.dll e' raggiungibile e l'app puo' partire."""
    python_path = VENV_DIR / "Scripts" / "python.exe"
    if not python_path.is_file():
        return
    result = run([str(python_path), "-c", "from rtlsdr import RtlSdr"], check=False)
    if result.returncode == 0:
        logger.info("[OK] Il modulo Python 'rtlsdr' (pyrtlsdr) si importa correttamente.")
    else:
        logger.warning(
            "[ATTENZIONE] Import di 'rtlsdr' fallito: rtlsdr.dll potrebbe non "
            "essere raggiungibile. L'app potrebbe non partire. Dettaglio:\n%s",
            result.stderr.strip(),
        )


# ============================================================
# FASE 4d -- Launcher senza terminale (doppio clic)
# ============================================================

def create_launchers() -> None:
    """
    Crea un launcher avviabile con doppio clic, SENZA finestra del
    terminale: un file .vbs che lancia pythonw.exe (interprete Python senza
    console) con il modulo tetraear. Lo mette nella cartella di TetraEar e,
    se possibile, ne copia una scorciatoia sul Desktop.
    """
    step("Creazione launcher senza terminale (doppio clic)")

    pythonw = VENV_DIR / "Scripts" / "pythonw.exe"
    python_exe = VENV_DIR / "Scripts" / "python.exe"
    interp = pythonw if pythonw.is_file() else python_exe

    vbs_path = TETRAEAR_ROOT / "Avvia TetraEar.vbs"
    vbs = (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.CurrentDirectory = "{TETRAEAR_ROOT}"\r\n'
        f'sh.Run """{interp}"" -m tetraear -f 392.225", 0, False\r\n'
    )
    try:
        vbs_path.write_text(vbs, encoding="utf-8")
        logger.info("[OK] Launcher creato: %s (doppio clic per avviare)", vbs_path)
    except OSError as exc:
        logger.warning("[ATTENZIONE] Non sono riuscito a creare il launcher: %s", exc)
        return

    # Copia sul Desktop, se raggiungibile (best effort).
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if desktop.is_dir():
        try:
            shutil.copy2(vbs_path, desktop / "Avvia TetraEar.vbs")
            logger.info("[OK] Copia del launcher sul Desktop: %s", desktop / "Avvia TetraEar.vbs")
        except OSError:
            pass


# ============================================================
# FASE 5 -- Verifica finale
# ============================================================

def verify_installation() -> None:
    step("Verifica finale dell'installazione")

    all_ok = True

    python_path = VENV_DIR / "Scripts" / "python.exe"
    if python_path.is_file():
        logger.info("[OK] Virtual environment presente: %s", VENV_DIR)
    else:
        logger.error("[FALLITO] Virtual environment non trovato")
        all_ok = False

    for base_name in ("cdecoder", "sdecoder"):
        binary_path = CODEC_BIN_DIR / (base_name + ".exe")
        if binary_path.is_file():
            logger.info("[OK] Binario codec presente: %s", binary_path)
        else:
            logger.error("[FALLITO] Binario codec mancante: %s", binary_path)
            all_ok = False

    dll_path = VENV_DIR / "Scripts" / "rtlsdr.dll"
    if dll_path.is_file():
        logger.info("[OK] rtlsdr.dll presente: %s", dll_path)
    else:
        logger.warning("[ATTENZIONE] rtlsdr.dll non trovata in %s", dll_path)

    verify_pyrtlsdr_import()          # verifica che l'app possa partire
    warn_about_rtl_sdr_on_windows()  # solo informativo (driver Zadig)

    if not all_ok:
        fail("Uno o piu' controlli finali non sono andati a buon fine (vedi sopra).")

    logger.info("")
    logger.info("========================================================")
    logger.info(" Installazione completata con successo!")
    logger.info("")
    logger.info(" Per avviare TetraEar SENZA terminale:")
    logger.info("   doppio clic su 'Avvia TetraEar.vbs' (nella cartella TetraEar o sul Desktop)")
    logger.info("")
    logger.info(" Oppure da Prompt dei comandi:")
    logger.info("   cd %s", TETRAEAR_ROOT)
    logger.info(r"   .venv\Scripts\activate")
    logger.info("   python -m tetraear -f 392.225")
    logger.info("========================================================")


def warn_about_rtl_sdr_on_windows() -> None:
    """La libreria rtlsdr.dll ora la installa l'installer. Resta manuale solo
    il driver WinUSB (Zadig), che Windows richiede per accedere al dongle."""
    logger.info("")
    logger.warning(
        "[IMPORTANTE] rtlsdr.dll e' stata installata automaticamente. Per USARE "
        "la chiavetta resta un solo passaggio manuale:\n"
        "  installare il driver WinUSB con Zadig (https://zadig.akeo.ie/).\n"
        "  Vedi la sezione 'RTL-SDR su Windows' in README.md."
    )


# ============================================================
# --repair e --uninstall
# ============================================================

def do_repair() -> None:
    step("Modalita' --repair: ricompilo il codec, sistemo pyrtlsdr e rtlsdr.dll")
    ensure_tetraear_source(clone_if_missing=True)
    unify_logs_dir()
    patch_tetraear_source_bugs()
    patch_voice_hide_codec_window()
    patch_voice_codec_timeout()
    patch_tetraear_add_network_info()
    patch_pyrtlsdr_dithering()
    ensure_msys2_toolchain()
    install_windows_rtlsdr_dll()
    install_tetra_codec_with_fallback()
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
    Avvia in AUTOMATICO l'installer Windows dei decoder aggiuntivi (dsd-fme +
    guide per dump1090/multimon-ng), se presente accanto a questo script. E'
    best-effort: gira DOPO che TetraEar e' gia' installato, quindi un errore
    qui non compromette TetraEar. Si disattiva con --no-extra.
    """
    script = INSTALLER_DIR / "install_extra_decoders_windows.py"
    if skip:
        logger.info("[INFO] Decoder aggiuntivi saltati (--no-extra).")
        return
    if not script.is_file():
        return

    step("Installo anche i decoder aggiuntivi (DMR/P25, ADS-B, cercapersone)")
    logger.info("Avvio %s (log in logs/install_extra.log) ...", script.name)
    result = subprocess.run([sys.executable, str(script)])
    if result.returncode != 0:
        logger.warning(
            "[ATTENZIONE] L'installazione di uno o piu' decoder aggiuntivi non e' "
            "andata a buon fine (vedi logs/install_extra.log). TetraEar resta "
            "comunque installato e funzionante."
        )


def run_telive2(skip: bool) -> None:
    """
    Avvia in AUTOMATICO l'installer Windows della catena TELIVE-2 (decifratura
    vocale TETRA a chiave nota, eseguita dentro WSL2), se presente accanto a
    questo script. E' best-effort: gira DOPO che TetraEar e' gia' installato,
    quindi un errore qui non compromette TetraEar. Si disattiva con --no-telive2.
    """
    script = INSTALLER_DIR / "install_telive2_windows.py"
    if skip:
        logger.info("[INFO] Catena TELIVE-2 saltata (--no-telive2).")
        return
    if not script.is_file():
        return

    step("Installo anche TELIVE-2 (decifratura vocale a chiave nota, via WSL2)")
    logger.info("Avvio %s (log in logs/install_telive2.log) ...", script.name)
    result = subprocess.run([sys.executable, str(script)])
    if result.returncode != 0:
        logger.warning(
            "[ATTENZIONE] L'installazione di TELIVE-2 non e' andata a buon fine "
            "(vedi logs/install_telive2.log). Spesso basta abilitare WSL2 e "
            "rilanciare 'python install_telive2_windows.py'. TetraEar resta "
            "comunque installato e funzionante."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installer TetraEar per Windows 10/11"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--repair", action="store_true",
        help="Ricompila solo il codec vocale",
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
        help="Non installare automaticamente la catena TELIVE-2 (decifratura vocale a chiave nota, via WSL2)",
    )
    return parser.parse_args()


def resolve_tetraear_ref(cli_ref) -> str:
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
    controlli finali (venv, binari del codec, rtlsdr.dll, import di
    pyrtlsdr). Utile per capire cosa manca senza rilanciare l'installazione.
    """
    step("Modalita' --check: verifica dello stato dell'installazione")
    root = ensure_tetraear_source(clone_if_missing=False)
    if not _looks_like_tetraear_root(root):
        fail(
            "Sorgente di TetraEar non trovato: sembra che l'installazione non "
            "sia mai stata completata. Esegui l'installer completo."
        )
    version_file = root / TETRAEAR_VERSION_FILE
    if version_file.is_file():
        logger.info("Versione installata (commit): %s", version_file.read_text().strip())
    verify_installation()


def main() -> int:
    args = parse_args()

    logger.info("====== TetraEar Windows Installer v%s ======", SCRIPT_VERSION)
    logger.info("Log completo salvato in: %s", LOG_FILE)

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
        patch_tetraear_add_network_info()
        create_virtualenv_and_install_requirements()
        install_windows_rtlsdr_dll()
        install_tetra_codec_with_fallback()
        create_launchers()
        verify_installation()
        # TetraEar e' pronto: installo anche gli altri decoder in automatico.
        run_extra_decoders(args.no_extra)
        # ...e la catena TELIVE-2 (decifratura vocale a chiave nota, via WSL2).
        run_telive2(args.no_telive2)
        return 0

    except InstallError:
        # Errore gia' stampato in modo chiaro da fail(): usciamo.
        return 1
    except KeyboardInterrupt:
        logger.error("\nInstallazione interrotta dall'utente.")
        return 130
    except Exception:
        # Rete di sicurezza: qualsiasi errore NON previsto viene comunque
        # salvato per intero (con traceback) in install.log.
        logger.error("")
        logger.error("[ERRORE IMPREVISTO] Si e' verificato un errore non gestito.")
        logger.error("Il traceback completo e' stato salvato in: %s", LOG_FILE)
        logger.debug("Traceback completo dell'errore imprevisto:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
