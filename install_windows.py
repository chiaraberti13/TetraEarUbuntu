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

# Toolchain MinGW da installare dentro MSYS2 (fornisce gcc/make).
MSYS2_TOOLCHAIN_PACKAGES = [
    "base-devel",
    "mingw-w64-ucrt-x86_64-gcc",
    "make",
    "patch",
]

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
    """L'archivio ETSI usa nomi MAIUSCOLI (SCODER.C, MAKEFILE) ma il
    Makefile li richiama in minuscolo. Uniformiamo in minuscolo tutti i
    file (utile soprattutto quando si compila su filesystem
    case-sensitive)."""
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name == path.name:
            continue
        target = path.parent / lower_name
        if target.exists():
            path.unlink()
        else:
            path.rename(target)


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
        result = run([git_exe, "clone", "--depth", "1", repo_url, str(osmo_dir)], check=False)
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

    warn_about_rtl_sdr_on_windows()  # solo informativo

    if not all_ok:
        fail("Uno o piu' controlli finali non sono andati a buon fine (vedi sopra).")

    logger.info("")
    logger.info("========================================================")
    logger.info(" Installazione completata con successo!")
    logger.info("")
    logger.info(" Per avviare TetraEar (Prompt dei comandi):")
    logger.info("   cd %s", TETRAEAR_ROOT)
    logger.info(r"   .venv\Scripts\activate")
    logger.info("   python -m tetraear -f 392.225")
    logger.info("========================================================")


def warn_about_rtl_sdr_on_windows() -> None:
    """Su Windows il supporto RTL-SDR richiede driver WinUSB (Zadig) e
    rtlsdr.dll: passaggi semi-manuali. Ricordiamo all'utente di leggerli
    nella guida, senza bloccare l'installazione."""
    logger.info("")
    logger.warning(
        "[IMPORTANTE] Prima di usare la chiavetta RTL-SDR su Windows devi:\n"
        "  1) installare il driver WinUSB con Zadig (https://zadig.akeo.ie/);\n"
        "  2) avere rtlsdr.dll raggiungibile nel PATH.\n"
        "  Vedi la sezione 'RTL-SDR su Windows' in README.md."
    )


# ============================================================
# --repair e --uninstall
# ============================================================

def do_repair() -> None:
    step("Modalita' --repair: ricompilo solo il codec vocale")
    ensure_tetraear_source(clone_if_missing=True)
    ensure_msys2_toolchain()
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
        # salvato per intero (con traceback) in install.log.
        logger.error("")
        logger.error("[ERRORE IMPREVISTO] Si e' verificato un errore non gestito.")
        logger.error("Il traceback completo e' stato salvato in: %s", LOG_FILE)
        logger.debug("Traceback completo dell'errore imprevisto:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
