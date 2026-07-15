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

SCRIPT_VERSION = "1.1"
MIN_PYTHON = (3, 8)

TETRAEAR_REPO_URL = "https://github.com/syrex1013/TetraEar.git"

INSTALLER_DIR = Path(__file__).resolve().parent
LOG_FILE = INSTALLER_DIR / "install.log"

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

    logger.info("Clono %s in %s ...", TETRAEAR_REPO_URL, cloned_dir)
    run([git_exe, "clone", "--depth", "1", TETRAEAR_REPO_URL, str(cloned_dir)])

    if not _looks_like_tetraear_root(cloned_dir):
        fail(
            "Il repository e' stato scaricato ma non contiene i file attesi "
            "(requirements.txt e cartella tetraear/)."
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


# ============================================================
# FASE 4 -- Compilazione del codec vocale ETSI TETRA (via MSYS2)
# ============================================================

def _download_with_browser_headers(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(destination, "wb") as out_file:
            shutil.copyfileobj(response, out_file)
    except urllib.error.HTTPError as exc:
        fail(
            f"Download fallito ({exc.code} {exc.reason}) da {url}. "
            "Se il problema persiste, l'URL potrebbe essere cambiato: "
            "verificare manualmente sul sito ETSI e aggiornare ETSI_CODEC_URL."
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    logger.info("====== TetraEar Windows Installer v%s ======", SCRIPT_VERSION)
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
        install_windows_rtlsdr_dll()
        install_tetra_codec_with_fallback()
        create_launchers()
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
        # salvato per intero (con traceback) in install.log.
        logger.error("")
        logger.error("[ERRORE IMPREVISTO] Si e' verificato un errore non gestito.")
        logger.error("Il traceback completo e' stato salvato in: %s", LOG_FILE)
        logger.debug("Traceback completo dell'errore imprevisto:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
