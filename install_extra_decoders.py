#!/usr/bin/env python3
"""
install_extra_decoders.py -- Decoder radio aggiuntivi per RTL-SDR (Linux)
=========================================================================

TetraEar decodifica il TETRA. Questo installer, complementare, prepara i
decoder OPEN SOURCE per gli ALTRI modi che una chiavetta RTL-SDR puo'
ricevere -- gli stessi che programmi chiusi come OpenEar coprivano, ma qui
con software libero e legale:

    * multimon-ng  -> POCSAG / FLEX (cercapersone), e altri modi FSK/AFSK
    * dump1090     -> ADS-B 1090 MHz (posizione degli aerei)
    * dsd-fme      -> DMR / P25 / NXDN / dPMR / ecc. (voce digitale in chiaro)

Uso:
    python3 install_extra_decoders.py                 # installa tutti e tre
    python3 install_extra_decoders.py --only multimon-ng dump1090
    python3 install_extra_decoders.py --check         # verifica cosa e' presente

Filosofia identica a install_linux.py: ogni passo viene scritto a schermo e
nel file install_extra.log, e ogni decoder e' indipendente -- se la
compilazione di uno fallisce, gli altri vengono comunque installati.

NOTA IMPORTANTE: come per ogni cosa radio, questi decoder mostrano qualcosa
solo se sei sintonizzato sulla frequenza giusta, con segnale sufficiente, e
il traffico e' IN CHIARO. La voce/dati cifrati non sono decodificabili senza
le chiavi, da nessun software.

DISCLAIMER: usa questi strumenti solo dove consentito dalle leggi della tua
giurisdizione. Vedi DISCLAIMER.md.
"""

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ============================================================
# CONFIGURAZIONE
# ============================================================

SCRIPT_VERSION = "1.0"
MIN_PYTHON = (3, 8)
SUPPORTED_OS_IDS = {"ubuntu", "debian"}

INSTALLER_DIR = Path(__file__).resolve().parent
# Tutti i log (installazione compresa) finiscono in ./logs/ accanto allo script.
LOG_DIR = INSTALLER_DIR / "logs"
LOG_FILE = LOG_DIR / "install_extra.log"

# I binari compilati che NON si installano di sistema vengono messi qui, cosi'
# restano raccolti in un posto solo accanto all'installer.
LOCAL_BIN_DIR = INSTALLER_DIR / "decoders" / "bin"

# Dipendenze di sistema comuni a piu' decoder (compilatore + RTL-SDR + git).
APT_COMMON = [
    "build-essential", "cmake", "pkg-config", "git",
    "librtlsdr-dev", "rtl-sdr", "libusb-1.0-0-dev",
]

# Sorgenti dei decoder che si compilano da codice.
DUMP1090_REPO = "https://github.com/antirez/dump1090.git"
MBELIB_REPO = "https://github.com/szechyjs/mbelib.git"
DSDFME_REPO = "https://github.com/lwvmobile/dsd-fme.git"

# Elenco dei decoder gestiti (per --only e --check).
DECODERS = ("multimon-ng", "dump1090", "dsd-fme")

# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("extra_decoders")


def setup_logging() -> None:
    logger.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        logger.addHandler(file_handler)
    except OSError:
        # Se non possiamo scrivere il log su file proseguiamo comunque a schermo.
        pass


class InstallError(Exception):
    """Errore gia' segnalato in modo leggibile: il main esce senza traceback."""


def fail(message: str) -> "typing.NoReturn":  # type: ignore # noqa
    logger.error("")
    logger.error("[ERRORE] %s", message)
    raise InstallError(message)


def step(title: str) -> None:
    logger.info("")
    logger.info("=" * 60)
    logger.info(" %s", title)
    logger.info("=" * 60)


def run(cmd: list, *, cwd: Path | None = None, check: bool = True, sudo: bool = False) -> subprocess.CompletedProcess:
    """
    Esegue un comando esterno. In caso di errore mostra codice di uscita e
    stderr per intero (mai un traceback nudo). Non usa mai shell=True.
    """
    if sudo and os.geteuid() != 0:
        cmd = ["sudo"] + cmd

    logger.debug("Eseguo: %s (cwd=%s)", " ".join(cmd), cwd or INSTALLER_DIR)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
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
            logger.error("--- Messaggio di errore ---\n%s", result.stderr.strip())
        fail(f"Comando fallito: {' '.join(cmd)}")

    return result


# ============================================================
# CONTROLLI PRELIMINARI
# ============================================================

def check_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        fail(f"Serve Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}, trovato {platform.python_version()}.")
    logger.info("[OK] Python %s", platform.python_version())


def read_os_release() -> dict:
    data = {}
    path = Path("/etc/os-release")
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                data[key.strip()] = value.strip().strip('"')
    return data


def check_operating_system() -> None:
    if platform.system() != "Linux":
        fail("Questo installer e' solo per Linux. Su Windows usa install_windows.py per TetraEar.")
    os_info = read_os_release()
    os_id = os_info.get("ID", "").lower()
    id_like = os_info.get("ID_LIKE", "").lower()
    if os_id in SUPPORTED_OS_IDS or any(x in id_like for x in SUPPORTED_OS_IDS):
        logger.info("[OK] Sistema: %s", os_info.get("PRETTY_NAME", os_id or "Linux"))
    else:
        logger.warning(
            "[ATTENZIONE] Distribuzione non riconosciuta (%s). L'installer e' pensato "
            "per Ubuntu/Debian; proseguo ma i comandi apt potrebbero non funzionare.",
            os_id or "sconosciuta",
        )


def install_common_dependencies() -> None:
    step("Installazione dipendenze di sistema comuni (apt)")
    run(["apt-get", "update"], sudo=True, check=False)
    run(["apt-get", "install", "-y"] + APT_COMMON, sudo=True)
    logger.info("[OK] Dipendenze comuni installate.")


def _apt_install(packages: list) -> None:
    run(["apt-get", "install", "-y"] + packages, sudo=True)


def _command_works(cmd_bin: str) -> bool:
    """Un comando e' DAVVERO utilizzabile solo se lo si riesce a lanciare:
    non basta che apt lo dia installato o che sia nel PATH (su sistemi con
    stato dpkg incoerente puo' esserci ma non caricarsi, es. librerie
    condivise mancanti)."""
    try:
        result = subprocess.run([cmd_bin, "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except (OSError, FileNotFoundError):
        return False


def _ensure_working_cmake() -> str | None:
    """
    Restituisce il percorso di un cmake FUNZIONANTE, o None se impossibile.

    Passi, dal piu' leggero al piu' robusto:
      1. cmake di sistema, se si lancia davvero;
      2. reinstallazione forzata via apt (per stati dpkg incoerenti);
      3. fallback definitivo: una copia di cmake installata via pip in un
         piccolo venv dedicato. Il wheel di PyPI e' self-contained (porta con
         se' le proprie librerie), quindi funziona anche su sistemi in cui il
         cmake di sistema e' rotto (es. 'librhash.so.1' mancante).
    """
    if _command_works("cmake"):
        return "cmake"

    logger.warning("[ATTENZIONE] 'cmake' assente o non funzionante: provo a reinstallarlo via apt...")
    run(["apt-get", "install", "--reinstall", "-y", "cmake"], sudo=True, check=False)
    if _command_works("cmake"):
        logger.info("[OK] 'cmake' di sistema ora funziona.")
        return "cmake"

    logger.warning(
        "[ATTENZIONE] Il 'cmake' di sistema non e' utilizzabile (dipendenze "
        "rotte). Installo una copia autonoma di cmake via pip..."
    )
    venv_dir = INSTALLER_DIR / "decoders" / "buildtools"
    cmake_bin = venv_dir / "bin" / "cmake"
    try:
        if not cmake_bin.exists():
            # 'ensurepip' a volte manca: assicuriamo python3-venv (best effort).
            run(["apt-get", "install", "-y", "python3-venv", "python3-pip"], sudo=True, check=False)
            run([sys.executable, "-m", "venv", str(venv_dir)])
            pip = str(venv_dir / "bin" / "pip")
            run([pip, "install", "--upgrade", "pip"], check=False)
            # cmake 4.x rifiuta i progetti vecchi (mbelib): pinniamo alla 3.x,
            # che e' comunque self-contained e compila senza problemi di policy.
            run([pip, "install", "cmake<4"])
    except InstallError:
        pass

    if _command_works(str(cmake_bin)):
        logger.info("[OK] Uso una copia autonoma di cmake (via pip): %s", cmake_bin)
        return str(cmake_bin)

    logger.error(
        "[FALLITO] Impossibile ottenere un cmake funzionante. Il tuo sistema "
        "ha uno stato pacchetti incoerente; prova a mano: "
        "'sudo apt install --reinstall cmake librhash0' e rilancia."
    )
    return None


def _install_local_binary(built_path: Path, name: str) -> Path:
    """Copia un binario compilato in decoders/bin/ e prova a metterlo anche in
    /usr/local/bin (best effort) cosi' e' subito richiamabile dal PATH."""
    LOCAL_BIN_DIR.mkdir(parents=True, exist_ok=True)
    local_copy = LOCAL_BIN_DIR / name
    shutil.copy2(built_path, local_copy)
    local_copy.chmod(local_copy.stat().st_mode | 0o111)
    result = run(["cp", str(local_copy), f"/usr/local/bin/{name}"], sudo=True, check=False)
    if result.returncode == 0:
        logger.info("[OK] %s installato in /usr/local/bin (nel PATH).", name)
    else:
        logger.info("[OK] %s disponibile in %s", name, local_copy)
    return local_copy


# ============================================================
# DECODER 1 -- multimon-ng (POCSAG / FLEX / ...)
# ============================================================

def install_multimon_ng() -> bool:
    step("multimon-ng (cercapersone POCSAG/FLEX e altri modi FSK)")
    # multimon-ng e' pacchettizzato su Ubuntu/Debian: la via piu' affidabile.
    result = run(["apt-get", "install", "-y", "multimon-ng"], sudo=True, check=False)
    if result.returncode == 0 and shutil.which("multimon-ng"):
        logger.info("[OK] multimon-ng installato da apt.")
        return True

    logger.info("Pacchetto apt non disponibile: compilo multimon-ng dai sorgenti...")
    _apt_install(["libpulse-dev", "libx11-dev", "qtbase5-dev"])
    work = Path(tempfile.mkdtemp(prefix="multimon-"))
    try:
        src = work / "multimon-ng"
        run(["git", "clone", "--depth", "1", "https://github.com/EliasOenal/multimon-ng.git", str(src)])
        build = src / "build"
        build.mkdir()
        run(["cmake", ".."], cwd=build)
        run(["make"], cwd=build)
        run(["make", "install"], cwd=build, sudo=True)
        run(["ldconfig"], sudo=True, check=False)
        if shutil.which("multimon-ng"):
            logger.info("[OK] multimon-ng compilato e installato.")
            return True
        logger.error("[FALLITO] multimon-ng non risulta nel PATH dopo l'installazione.")
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ============================================================
# DECODER 2 -- dump1090 (ADS-B 1090 MHz)
# ============================================================

def install_dump1090() -> bool:
    step("dump1090 (ADS-B 1090 MHz -- posizione degli aerei)")
    work = Path(tempfile.mkdtemp(prefix="dump1090-"))
    try:
        src = work / "dump1090"
        run(["git", "clone", "--depth", "1", DUMP1090_REPO, str(src)])
        run(["make"], cwd=src)
        binary = src / "dump1090"
        if not binary.is_file():
            logger.error("[FALLITO] La compilazione non ha prodotto il binario dump1090.")
            return False
        _install_local_binary(binary, "dump1090")
        logger.info("[OK] dump1090 pronto.")
        return True
    except InstallError:
        logger.warning(
            "[ATTENZIONE] Compilazione di dump1090 non riuscita. Su Debian/Ubuntu "
            "puoi in alternativa installare il pacchetto 'dump1090-mutability' con apt."
        )
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ============================================================
# DECODER 3 -- dsd-fme (DMR / P25 / NXDN / dPMR ...)
# ============================================================

def _build_and_install_cmake(repo_url: str, name: str, cmake_bin: str, extra_cmake: list | None = None) -> None:
    work = Path(tempfile.mkdtemp(prefix=f"{name}-"))
    try:
        src = work / name
        run(["git", "clone", "--depth", "1", repo_url, str(src)])
        build = src / "build"
        build.mkdir()
        # -DCMAKE_POLICY_VERSION_MINIMUM=3.5 permette anche ai cmake 4.x di
        # compilare progetti vecchi (mbelib) che chiedono una policy < 3.5.
        cmake_args = ["-DCMAKE_POLICY_VERSION_MINIMUM=3.5"] + (extra_cmake or [])
        run([cmake_bin] + cmake_args + [".."], cwd=build)
        run(["make"], cwd=build)
        run(["make", "install"], cwd=build, sudo=True)
        run(["ldconfig"], sudo=True, check=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def install_dsd_fme() -> bool:
    step("dsd-fme (voce digitale in chiaro: DMR / P25 / NXDN / dPMR)")
    # dsd-fme si compila con cmake: ci procuriamo un cmake DAVVERO funzionante
    # (di sistema se possibile, altrimenti una copia autonoma via pip).
    cmake_bin = _ensure_working_cmake()
    if cmake_bin is None:
        logger.warning("[ATTENZIONE] Salto dsd-fme: nessun 'cmake' utilizzabile.")
        return False
    # dsd-fme dipende dalla libreria mbelib (vocoder AMBE) e da alcune -dev.
    _apt_install([
        "libsndfile1-dev", "libitpp-dev", "libncurses-dev", "libpulse-dev",
    ])
    try:
        logger.info("Compilo la libreria mbelib (prerequisito del vocoder)...")
        _build_and_install_cmake(MBELIB_REPO, "mbelib", cmake_bin)
        logger.info("Compilo dsd-fme...")
        _build_and_install_cmake(DSDFME_REPO, "dsd-fme", cmake_bin)
    except InstallError:
        logger.warning(
            "[ATTENZIONE] Compilazione di dsd-fme non riuscita. E' il decoder piu' "
            "complesso da costruire; i dettagli sono in install_extra.log. Le "
            "istruzioni ufficiali aggiornate sono su https://github.com/lwvmobile/dsd-fme"
        )
        return False

    if shutil.which("dsd-fme"):
        logger.info("[OK] dsd-fme installato.")
        return True
    logger.error("[FALLITO] dsd-fme non risulta nel PATH dopo l'installazione.")
    return False


# ============================================================
# VERIFICA / RIEPILOGO
# ============================================================

def _binary_present(name: str) -> bool:
    if shutil.which(name):
        return True
    return (LOCAL_BIN_DIR / name).is_file()


def _tetraear_root() -> Path:
    """Individua la copia di TetraEar con la stessa logica di install_linux.py:
    lo script e' dentro una copia di TetraEar, oppure c'e' ./TetraEar accanto."""
    if (INSTALLER_DIR / "requirements.txt").is_file() and (INSTALLER_DIR / "tetraear").is_dir():
        return INSTALLER_DIR
    return INSTALLER_DIR / "TetraEar"


def verify_and_summary(selected: list, completed_install: bool = True) -> bool:
    step("Verifica finale")
    status = {name: _binary_present(name) for name in selected}
    for name, ok in status.items():
        logger.info("  %s %s", "[OK]   " if ok else "[MANCA]", name)

    # Riquadro finale di fine installazione (non in modalita' --check, dove
    # non e' stato installato nulla).
    if completed_install:
        logger.info("")
        logger.info("========================================================")
        logger.info(" Installazione completata con successo!")
        logger.info("")
        logger.info(" Per avviare TetraEar:")
        logger.info("   cd %s", _tetraear_root())
        logger.info("   source .venv/bin/activate")
        logger.info("   python -m tetraear -f 392.225")
        logger.info("========================================================")

    logger.info("")
    logger.info("=" * 60)
    logger.info(" Come usare i decoder (esempi tipici)")
    logger.info("=" * 60)
    if status.get("multimon-ng"):
        logger.info("")
        logger.info(" POCSAG (cercapersone), esempio a 439.9875 MHz:")
        logger.info("   rtl_fm -f 439.9875M -s 22050 -g 42 - | \\")
        logger.info("     multimon-ng -t raw -a POCSAG512 -a POCSAG1200 -a POCSAG2400 -f alpha /dev/stdin")
    if status.get("dump1090"):
        logger.info("")
        logger.info(" ADS-B (aerei), con mappa web su http://localhost:8080 :")
        logger.info("   dump1090 --interactive --net")
    if status.get("dsd-fme"):
        logger.info("")
        logger.info(" DMR/P25 in chiaro, esempio a 446.09375 MHz:")
        logger.info("   rtl_fm -f 446.09375M -s 48000 -g 42 - | dsd-fme -i - -o /dev/null")

    logger.info("")
    logger.info(" Log completo in: %s", LOG_FILE)
    all_ok = all(status.values())
    if not all_ok:
        logger.warning(
            "\n[NOTA] Alcuni decoder non risultano installati (vedi sopra). Rilancia "
            "l'installer, oppure consulta install_extra.log per l'errore specifico."
        )
    return all_ok


# ============================================================
# MAIN
# ============================================================

INSTALLERS = {
    "multimon-ng": install_multimon_ng,
    "dump1090": install_dump1090,
    "dsd-fme": install_dsd_fme,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installer di decoder RTL-SDR aggiuntivi (POCSAG, ADS-B, DMR/P25) per Linux"
    )
    parser.add_argument(
        "--only", nargs="+", choices=DECODERS, metavar="DECODER",
        help=f"Installa solo i decoder indicati (fra: {', '.join(DECODERS)})",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verifica soltanto quali decoder sono presenti, senza installare nulla",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()
    selected = list(args.only) if args.only else list(DECODERS)

    logger.info("====== Installer decoder aggiuntivi v%s ======", SCRIPT_VERSION)
    logger.info("Log completo in: %s", LOG_FILE)
    logger.info("Decoder richiesti: %s", ", ".join(selected))

    try:
        if args.check:
            verify_and_summary(selected, completed_install=False)
            return 0

        check_python_version()
        check_operating_system()
        install_common_dependencies()

        # Ogni decoder e' indipendente: un errore in uno non blocca gli altri.
        results = {}
        for name in selected:
            try:
                results[name] = INSTALLERS[name]()
            except InstallError:
                # Errore gia' loggato: registriamo il fallimento e proseguiamo.
                results[name] = False

        all_ok = verify_and_summary(selected)
        return 0 if all_ok else 1

    except InstallError:
        return 1
    except KeyboardInterrupt:
        logger.error("\nInstallazione interrotta dall'utente.")
        return 130
    except Exception:
        logger.error("")
        logger.error("[ERRORE IMPREVISTO] Errore non gestito; traceback in %s", LOG_FILE)
        logger.debug("Traceback completo:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
