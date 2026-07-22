#!/usr/bin/env python3
"""
install_telive2.py -- TELIVE-2: ricezione e DECIFRATURA vocale TETRA (Linux)
============================================================================

TetraEar (install_linux.py) decodifica il TETRA in chiaro. Questo installer,
complementare, prepara la catena TELIVE-2 di Jacek Lipkowski (SQ5BPF), che
aggiunge una cosa che TetraEar NON ha: la decifratura vocale a CHIAVE NOTA,
inclusa la chiave TEA-1 accorciata a 32 bit (il "backdoor" documentato da
Team Midnight Blue nel 2023).

La catena e' composta da tre progetti open source che qui vengono clonati,
compilati e collegati fra loro:

    * osmo-tetra-sq5bpf-2  -> il ricevitore 'tetra-rx' (con crypto TEA1/2/3
                              REALE e il flag '-k keyfile' per le chiavi note)
    * codec ETSI TETRA     -> 'cdecoder'/'sdecoder' che trasformano l'ACELP
                              in audio (scaricato da ETSI e patchato)
    * telive-2             -> l'interfaccia 'telive' + gli script 'tplay'/
                              'tetrad' e i flowgraph GNU Radio

Uso:
    python3 install_telive2.py            # installa e compila tutta la catena
    python3 install_telive2.py --check    # verifica soltanto cosa e' presente
    python3 install_telive2.py --no-gnuradio   # salta GNU Radio (gia' presente)

Filosofia identica agli altri installer del repo: ogni passo viene scritto a
schermo e nel file logs/install_telive2.log; dove possibile si prosegue anche
se un passo secondario fallisce, riportando l'errore in chiaro.

IMPORTANTE (come nel video da cui nasce questo script): TELIVE-2 NON permette
di "craccare" il TETRA. Decifra la voce SOLO se la chiave e' GIA' NOTA:
craccare e decifrare sono due cose diverse. Vedi DISCLAIMER.md: usa questi
strumenti solo dove consentito dalle leggi della tua giurisdizione.
"""

import argparse
import logging
import os
import platform
import re
import shutil
import stat
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
LOG_FILE = LOG_DIR / "install_telive2.log"

# I sorgenti clonati stanno raccolti in una sola cartella accanto all'installer.
TELIVE2_DIR = INSTALLER_DIR / "telive2"
OSMO_DIR = TELIVE2_DIR / "osmo-tetra-sq5bpf-2"
TELIVE_DIR = TELIVE2_DIR / "telive-2"

OSMO_REPO = "https://github.com/sq5bpf/osmo-tetra-sq5bpf-2.git"
TELIVE_REPO = "https://github.com/sq5bpf/telive-2.git"

# telive-2 e tetra-rx usano una cartella di lavoro FISSA: /tetra (vedi
# telive-2/install.sh e def_outdir="/tetra/in" in telive.c). E' li' che
# finiscono cdecoder/sdecoder, gli script e i file audio .out.
TETRA_DIR = Path("/tetra")
TETRA_BIN = TETRA_DIR / "bin"

# Flowgraph GNU Radio incluso in telive-2 (invia i campioni via UDP a telive).
GRC_RELATIVE = "gnuradio-companion/python3_based_gnuradio/telive_1ch_simple_gr310_udp_xmlrpc.grc"

# --- Codec vocale ETSI TETRA (ACELP) ----------------------------------------
# Lo stesso pacchetto usato da install_linux.py: il download_and_patch.sh di
# osmo lo scarica da ETSI, ma ETSI risponde spesso 403 alle richieste che non
# sembrano un browser. Ce lo scarichiamo noi (User-Agent "da browser", con
# mirror su web.archive.org come riserva) e lo mettiamo dove lo script se lo
# aspetta, cosi' aggira il 403 senza dipendere dallo stato del sito.
ETSI_CODEC_URL = (
    "http://www.etsi.org/deliver/etsi_en/300300_300399/30039502/"
    "01.03.01_60/en_30039502v010301p0.zip"
)
ETSI_CODEC_MD5 = "a8115fe68ef8f8cc466f4192572a1e3e"
ETSI_CODEC_URLS = [
    ETSI_CODEC_URL,
    "https://web.archive.org/web/2id_/" + ETSI_CODEC_URL,
]
# Nome del file locale atteso da etsi_codec-patches/download_and_patch.sh.
ETSI_LOCAL_ZIP_NAME = "etsi_tetra_codec.zip"
DOWNLOAD_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# --- Dipendenze di sistema (apt) --------------------------------------------
# Toolchain + librerie di build comuni a tutta la catena.
APT_BUILD = [
    "build-essential", "gcc", "make", "git", "pkg-config", "patch",
    "unzip", "wget", "ca-certificates",
]
# osmo-tetra-sq5bpf-2 compila contro libosmocore.
APT_OSMO = ["libosmocore-dev"]
# telive: ncurses + libxml2 (vedi il suo Makefile: pkg-config ncurses / xml2-config).
APT_TELIVE = ["libncurses-dev", "libxml2-dev"]
# RTL-SDR (la chiavetta) e USB.
APT_RTLSDR = ["librtlsdr-dev", "rtl-sdr", "libusb-1.0-0-dev"]
# Ricezione a runtime: socat (riceve i campioni UDP nel receiver1udp) + audio.
APT_RUNTIME = ["socat", "alsa-utils", "sox", "vorbis-tools"]
# GNU Radio + sorgente osmosdr per la chiavetta (installabile a parte con --no-gnuradio).
APT_GNURADIO = ["gnuradio", "gr-osmosdr"]

# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("telive2")


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


def run(cmd: list, *, cwd: Path | None = None, check: bool = True, sudo: bool = False,
        env: dict | None = None) -> subprocess.CompletedProcess:
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
            env=env,
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
        fail("Questo installer e' solo per Linux (TELIVE-2 usa GNU Radio e tool POSIX).")
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


# ============================================================
# DIPENDENZE DI SISTEMA
# ============================================================

def install_system_dependencies(with_gnuradio: bool) -> None:
    step("Installazione dipendenze di sistema (apt)")
    run(["apt-get", "update"], sudo=True, check=False)

    packages = APT_BUILD + APT_OSMO + APT_TELIVE + APT_RTLSDR + APT_RUNTIME
    if with_gnuradio:
        packages += APT_GNURADIO
    else:
        logger.info("Salto GNU Radio (--no-gnuradio): assicurati di averlo gia' installato.")

    # Un solo apt install: se un pacchetto manca nei repo, apt lo segnala.
    run(["apt-get", "install", "-y"] + packages, sudo=True)
    logger.info("[OK] Dipendenze installate.")

    # libosmocore e' indispensabile per compilare tetra-rx: verifichiamolo.
    if subprocess.run(["pkg-config", "--exists", "libosmocore"]).returncode != 0:
        logger.warning(
            "[ATTENZIONE] pkg-config non trova 'libosmocore'. Su alcune distro il "
            "pacchetto si chiama diversamente: la compilazione dell'osmo receiver "
            "potrebbe fallire. Cerca l'equivalente di 'libosmocore-dev' per il tuo sistema."
        )


# ============================================================
# CLONE DEI SORGENTI
# ============================================================

def _clone_or_update(repo_url: str, dest: Path) -> None:
    if (dest / ".git").is_dir():
        logger.info("Sorgente gia' presente in %s: aggiorno (git pull)...", dest)
        run(["git", "-C", str(dest), "pull", "--ff-only"], check=False)
        return
    if dest.exists():
        # Cartella esistente ma non e' un repo git: la rimuoviamo e riclonaimo.
        logger.info("Rimuovo una copia incompleta preesistente: %s", dest)
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--depth", "1", repo_url, str(dest)])


def clone_sources() -> None:
    step("Download dei sorgenti (osmo-tetra-sq5bpf-2 e telive-2)")
    _clone_or_update(OSMO_REPO, OSMO_DIR)
    _clone_or_update(TELIVE_REPO, TELIVE_DIR)
    logger.info("[OK] Sorgenti in %s", TELIVE2_DIR)


# ============================================================
# COMPATIBILITA' COMPILATORE (GCC 14/15)
# ============================================================
#
# I sorgenti di SQ5BPF (osmo-tetra, telive) e il codec ETSI sono C "vecchio":
# contengono costrutti che GCC 14 e soprattutto GCC 15 (Ubuntu 25.10) hanno
# promosso da warning a ERRORE per default (es. 'return' senza valore in
# funzione non-void -> -Wreturn-mismatch, chiamate implicite, ecc.). Su GCC 13
# (Ubuntu 24.04) sono ancora warning e la build passa.
#
# Per far compilare lo STESSO installer su entrambe le distro (e su x86 e
# ARM64), riportiamo quei pochi errori a warning con i flag '-Wno-error=...'.
# Attenzione: un flag SCONOSCIUTO fa fallire gcc; percio' teniamo solo quelli
# che il compilatore locale accetta davvero (li proviamo uno per uno).

_GCC_COMPAT_CANDIDATES = [
    "-Wno-error=implicit-int",
    "-Wno-error=implicit-function-declaration",
    "-Wno-error=int-conversion",
    "-Wno-error=incompatible-pointer-types",
    "-Wno-error=return-mismatch",
    "-Wno-error=declaration-missing-parameter-type",
    "-Wno-error=old-style-definition",
]

_COMPAT_CFLAGS_CACHE: str | None = None


def _compat_cflags() -> str:
    """Sottoinsieme di _GCC_COMPAT_CANDIDATES accettato dal compilatore locale.
    Calcolato una volta sola: su GCC 13 restano i flag noti, su GCC 15 si
    aggiungono quelli nuovi (es. -Wno-error=return-mismatch) che sbloccano la
    build. Cosi' lo stesso codice va su 24.04 e su 25.10."""
    global _COMPAT_CFLAGS_CACHE
    if _COMPAT_CFLAGS_CACHE is not None:
        return _COMPAT_CFLAGS_CACHE

    cc = os.environ.get("CC") or "cc"
    accepted = []
    try:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "probe.c"
            src.write_text("int main(void){return 0;}\n", encoding="utf-8")
            obj = Path(td) / "probe.o"
            for flag in _GCC_COMPAT_CANDIDATES:
                try:
                    result = subprocess.run(
                        [cc, flag, "-c", str(src), "-o", str(obj)],
                        capture_output=True,
                    )
                    if result.returncode == 0:
                        accepted.append(flag)
                except OSError:
                    pass
    except OSError:
        pass

    _COMPAT_CFLAGS_CACHE = " ".join(accepted)
    if _COMPAT_CFLAGS_CACHE:
        logger.info("[INFO] Flag di compatibilita' compilatore: %s", _COMPAT_CFLAGS_CACHE)
    return _COMPAT_CFLAGS_CACHE


def _inject_compat_cflags(makefile: Path) -> None:
    """Aggiunge i flag di compatibilita' alla prima riga 'CFLAGS=' di un
    Makefile (subito dopo l'uguale, cosi' eventuali commenti a fine riga
    restano fuori). Idempotente e best-effort: se non trova CFLAGS non fa nulla."""
    extra = _compat_cflags()
    if not extra or not makefile.is_file():
        return
    text = makefile.read_text(encoding="utf-8", errors="ignore")
    marker = extra.split()[0]
    if marker in text:
        return  # gia' iniettato
    new_text = re.sub(r"(?m)^(CFLAGS\s*=)", r"\1 " + extra + " ", text, count=1)
    if new_text != text:
        makefile.write_text(new_text, encoding="utf-8")
        logger.info("[OK] Compatibilita' compilatore applicata a %s", makefile.relative_to(TELIVE2_DIR) if TELIVE2_DIR in makefile.parents else makefile.name)


# ============================================================
# BUILD 1 -- osmo-tetra-sq5bpf-2 (ricevitore tetra-rx)
# ============================================================

def build_osmo_tetra() -> bool:
    step("Compilazione dell'osmo receiver (tetra-rx, float_to_bits)")
    src = OSMO_DIR / "src"
    if not src.is_dir():
        fail(f"Cartella sorgente non trovata: {src} (clone fallito?).")
    _inject_compat_cflags(src / "Makefile")
    run(["make", f"-j{os.cpu_count() or 1}"], cwd=src, check=False)

    ok = True
    for binary in ("tetra-rx", "float_to_bits"):
        if (src / binary).is_file():
            logger.info("[OK] Compilato %s", binary)
        else:
            logger.error("[FALLITO] Manca il binario %s dopo la compilazione.", binary)
            ok = False
    return ok


# ============================================================
# BUILD 2 -- codec vocale ETSI (cdecoder / sdecoder)
# ============================================================

def _download_first_available(urls: list, dest: Path) -> None:
    """Scarica il primo URL disponibile impostando un User-Agent 'da browser'
    (ETSI risponde 403 alle richieste che non sembrano un browser)."""
    import urllib.request

    last_error = None
    for url in urls:
        try:
            logger.info("Scarico il codec da %s ...", url.split("/web/")[0] if "web.archive" in url else url)
            request = urllib.request.Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response, open(dest, "wb") as out:
                shutil.copyfileobj(response, out)
            if dest.stat().st_size > 0:
                return
        except Exception as exc:  # noqa: BLE001 -- vogliamo provare il mirror successivo
            last_error = exc
            logger.warning("[ATTENZIONE] Download fallito da questa fonte: %s", exc)
    raise InstallError(f"Download del codec ETSI fallito da tutte le fonti. Ultimo errore: {last_error}")


def _verify_md5(path: Path, expected: str) -> bool:
    import hashlib

    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    got = h.hexdigest()
    if got.lower() != expected.lower():
        logger.warning("[ATTENZIONE] MD5 del codec inatteso (%s != %s).", got, expected)
        return False
    logger.info("[OK] MD5 del codec verificato.")
    return True


def _harden_patch_script(script: Path, force_browser_download: bool) -> None:
    """
    Rende robusto etsi_codec-patches/download_and_patch.sh (lo stesso problema
    risolto a mano nel video con un 'sed').

    Due modalita':
      * force_browser_download=False (abbiamo gia' messo lo zip valido accanto
        allo script): forziamo il ramo "file esistente" cosi' lo script NON
        scarica e usa il nostro file. Correggiamo anche 'print'->'echo' (bug
        POSIX presente nell'originale).
      * force_browser_download=True (non siamo riusciti a pre-scaricare): come
        nel video, forziamo il download aggiungendo uno User-Agent da browser
        al wget e correggiamo 'print'->'echo'.
    """
    text = script.read_text(encoding="utf-8", errors="ignore")
    original = text

    # In entrambi i casi: 'print "..."' non e' POSIX -> usiamo 'echo'.
    text = text.replace('print "MD5sum', 'echo "MD5sum')

    if force_browser_download:
        # Forza l'esecuzione del wget (ramo "file non presente") e usa un UA browser.
        text = text.replace("[ ! -f $LOCAL_FILE ]", "true")
        text = text.replace("wget -O", f'wget -U "{DOWNLOAD_USER_AGENT}" -O')
    else:
        # Forza il ramo "file gia' presente": niente download, usa il nostro zip.
        text = text.replace("[ ! -f $LOCAL_FILE ]", "false")

    if text != original:
        script.write_text(text, encoding="utf-8")
        logger.info("[OK] download_and_patch.sh reso robusto (fix 403/print).")


def build_etsi_codec() -> bool:
    step("Codec vocale ETSI TETRA (cdecoder / sdecoder)")
    patch_dir = OSMO_DIR / "etsi_codec-patches"
    script = patch_dir / "download_and_patch.sh"
    if not script.is_file():
        logger.error("[FALLITO] Non trovo %s (struttura del repo cambiata?).", script)
        return False

    # 1) Proviamo a pre-scaricare noi lo zip ETSI (aggira il 403). Lo mettiamo
    #    col nome che lo script si aspetta, cosi' lo puo' riutilizzare.
    local_zip = patch_dir / ETSI_LOCAL_ZIP_NAME
    have_valid_zip = False
    try:
        _download_first_available(ETSI_CODEC_URLS, local_zip)
        have_valid_zip = _verify_md5(local_zip, ETSI_CODEC_MD5)
    except InstallError as exc:
        logger.warning("[ATTENZIONE] Pre-download del codec non riuscito: %s", exc)

    # 2) Adattiamo lo script: se abbiamo lo zip lo facciamo saltare il download,
    #    altrimenti lo facciamo scaricare con User-Agent da browser (come il video).
    _harden_patch_script(script, force_browser_download=not have_valid_zip)

    # 3) Eseguiamo download_and_patch.sh: scompatta lo zip in ../codec e applica
    #    le patch osmo (rende il vecchio codec ETSI compilabile con gcc moderno).
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    run(["sh", "./download_and_patch.sh"], cwd=patch_dir)

    # 4) Compiliamo il codec: produce cdecoder e sdecoder.
    codec_ccode = OSMO_DIR / "codec" / "c-code"
    if not codec_ccode.is_dir():
        logger.error("[FALLITO] Cartella codec %s assente dopo il patch.", codec_ccode)
        return False
    _inject_compat_cflags(codec_ccode / "Makefile")
    run(["make", f"-j{os.cpu_count() or 1}"], cwd=codec_ccode, check=False)

    ok = True
    for binary in ("cdecoder", "sdecoder"):
        if (codec_ccode / binary).is_file():
            logger.info("[OK] Compilato %s", binary)
        else:
            logger.error("[FALLITO] Manca il binario %s del codec.", binary)
            ok = False
    return ok


# ============================================================
# BUILD 3 -- telive
# ============================================================

def _patch_telive_missing_includes() -> None:
    """telive_receiver.h usa 'time_t' ma non include <time.h>: sulle glibc
    recenti (Ubuntu 24.04/25.10) time.h non e' piu' incluso implicitamente e la
    build fallisce con "unknown type name 'time_t'". Aggiungiamo l'include che
    lo stesso GCC suggerisce. Idempotente e best-effort."""
    header = TELIVE_DIR / "telive_receiver.h"
    if not header.is_file():
        return
    text = header.read_text(encoding="utf-8", errors="ignore")
    if "#include <time.h>" in text:
        return
    if "#include <stdint.h>" in text:
        new_text = text.replace(
            "#include <stdint.h>", "#include <stdint.h>\n#include <time.h>", 1
        )
    else:
        new_text = "#include <time.h>\n" + text
    header.write_text(new_text, encoding="utf-8")
    logger.info("[OK] Aggiunto #include <time.h> a telive_receiver.h (glibc recenti)")


def build_telive() -> bool:
    step("Compilazione di telive (interfaccia)")
    if not (TELIVE_DIR / "Makefile").is_file():
        fail(f"Makefile di telive non trovato in {TELIVE_DIR} (clone fallito?).")
    _inject_compat_cflags(TELIVE_DIR / "Makefile")
    _patch_telive_missing_includes()
    run(["make", f"-j{os.cpu_count() or 1}"], cwd=TELIVE_DIR, check=False)
    if (TELIVE_DIR / "telive").is_file():
        logger.info("[OK] Compilato telive")
        return True
    logger.error("[FALLITO] Binario 'telive' assente dopo la compilazione.")
    return False


# ============================================================
# SETUP /tetra E COLLEGAMENTO DEI BINARI
# ============================================================

def _invoking_user() -> str:
    """Utente reale (anche se l'installer gira sotto sudo)."""
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or "root"


def setup_tetra_dir() -> None:
    step("Preparazione della cartella di lavoro /tetra")
    user = _invoking_user()

    # /tetra sta nella radice del filesystem: serve sudo per crearla. La
    # rendiamo poi scrivibile dall'utente (telive/tetra-rx ci scrivono i .out).
    # Se non e' scrivibile dal processo corrente, la prepariamo via sudo.
    run(["mkdir", "-p", str(TETRA_DIR)], sudo=True)
    if not os.access(TETRA_DIR, os.W_OK):
        run(["chown", f"{user}:{user}", str(TETRA_DIR)], sudo=True, check=False)

    for sub in ("in", "out", "log", "tmp", "bin"):
        (TETRA_DIR / sub).mkdir(parents=True, exist_ok=True)
    (TETRA_DIR / "log" / "telive.log").touch(exist_ok=True)

    # Copiamo in /tetra/bin gli script di telive-2 (tplay, tetrad, ...) e i
    # binari appena compilati (telive, cdecoder, sdecoder). tplay si aspetta
    # cdecoder/sdecoder proprio in /tetra/bin.
    for item in (TELIVE_DIR / "bin").glob("*"):
        shutil.copy2(item, TETRA_BIN / item.name)
        (TETRA_BIN / item.name).chmod((TETRA_BIN / item.name).stat().st_mode | 0o111)

    for built in (
        TELIVE_DIR / "telive",
        OSMO_DIR / "codec" / "c-code" / "cdecoder",
        OSMO_DIR / "codec" / "c-code" / "sdecoder",
    ):
        if built.is_file():
            dst = TETRA_BIN / built.name
            shutil.copy2(built, dst)
            dst.chmod(dst.stat().st_mode | 0o111)
            logger.info("[OK] Copiato in /tetra/bin: %s", built.name)

    # Come ultimo passo garantiamo che TUTTA /tetra (sottocartelle e file appena
    # creati) sia dell'utente reale: se l'installer gira sotto sudo, i file
    # sarebbero altrimenti di root e telive non potrebbe scriverci.
    run(["chown", "-R", f"{user}:{user}", str(TETRA_DIR)], sudo=True, check=False)

    logger.info("[OK] /tetra pronta (in/out/log/tmp/bin).")


def add_bin_to_path() -> None:
    """Aggiunge /tetra/bin al PATH via ~/.bashrc (idempotente), cosi' tplay e i
    decoder sono richiamabili ovunque -- come l'export mostrato nel video."""
    user = _invoking_user()
    home = Path(os.path.expanduser(f"~{user}"))
    bashrc = home / ".bashrc"
    line = 'export PATH="$PATH:/tetra/bin"'
    try:
        existing = bashrc.read_text(encoding="utf-8", errors="ignore") if bashrc.is_file() else ""
        if "/tetra/bin" in existing:
            logger.info("[OK] /tetra/bin gia' nel PATH (~/.bashrc).")
            return
        with open(bashrc, "a", encoding="utf-8") as f:
            f.write(f"\n# TELIVE-2: decoder vocali TETRA\n{line}\n")
        logger.info("[OK] Aggiunto /tetra/bin al PATH in %s (riapri il terminale).", bashrc)
    except OSError as exc:
        logger.warning("[ATTENZIONE] Non ho potuto aggiornare il PATH (%s). Aggiungi a mano: %s", exc, line)


# ============================================================
# VERIFICA / RIEPILOGO
# ============================================================

def _binary_present(name: str) -> bool:
    return shutil.which(name) is not None or (TETRA_BIN / name).is_file()


def _grc_path() -> Path:
    return TELIVE_DIR / GRC_RELATIVE


def verify_and_summary(completed_install: bool = True) -> bool:
    step("Verifica finale")
    checks = {
        "tetra-rx (receiver)": (OSMO_DIR / "src" / "tetra-rx").is_file(),
        "cdecoder": _binary_present("cdecoder"),
        "sdecoder": _binary_present("sdecoder"),
        "telive": (TELIVE_DIR / "telive").is_file() or _binary_present("telive"),
        "gnuradio-companion": shutil.which("gnuradio-companion") is not None,
        "socat": shutil.which("socat") is not None,
        "aplay (audio)": shutil.which("aplay") is not None,
    }
    for name, ok in checks.items():
        logger.info("  %s %s", "[OK]   " if ok else "[MANCA]", name)

    all_ok = all(checks.values())

    if completed_install:
        logger.info("")
        logger.info("========================================================")
        logger.info(" Installazione TELIVE-2 completata!")
        logger.info("========================================================")

    grc = _grc_path()
    osmo_src = OSMO_DIR / "src"

    logger.info("")
    logger.info("=" * 60)
    logger.info(" Come ricevere e decodificare (tre terminali)")
    logger.info("=" * 60)
    logger.info("")
    logger.info(" 1) GNU Radio -- sorgente dalla chiavetta, invia via UDP a telive:")
    logger.info("      gnuradio-companion \\")
    logger.info("        %s", grc)
    logger.info("    Imposta la frequenza del tuo TETRA e premi Run.")
    logger.info("")
    logger.info(" 2) Ricevitore osmo (in un secondo terminale):")
    logger.info("      cd %s", osmo_src)
    logger.info("      ./receiver1udp 1")
    logger.info("")
    logger.info(" 3) Interfaccia telive (in un terzo terminale):")
    logger.info("      cd %s && ./telive", TELIVE_DIR)
    logger.info("")
    logger.info(" Ascolto voce: i file .out finiscono in /tetra/out, riproducili con:")
    logger.info("      tplay /tetra/out/<file>.out")

    logger.info("")
    logger.info("=" * 60)
    logger.info(" DECIFRATURA a chiave NOTA (TEA1, anche chiave 32-bit)")
    logger.info("=" * 60)
    logger.info(" Il ricevitore decifra se gli passi un keyfile con la chiave GIA' nota:")
    logger.info("   ./tetra-rx -r -k <keyfile> -s /dev/stdin")
    logger.info(" (receiver1udp usa gia' '-k sample_keyfile'; modificalo con la tua chiave)")
    logger.info(" Esempio di riga nel keyfile (vedi %s/sample_keyfile):", osmo_src)
    logger.info("   network mcc 0123 mnc 1337 ksg_type 1 security_class 2")
    logger.info("   key mcc 0123 mnc 1337 addr 00000000 key_type 1  key_num 0 key 11111111111111111111")
    logger.info(" Chiave TEA-1 accorciata a 32 bit (backdoor): key_type 16, padding a 80 bit:")
    logger.info("   key mcc 0123 mnc 1337 addr 00000000 key_type 16 key_num 0 key 12345678000000000000")
    logger.info("")
    logger.info(" NOTA: si DECIFRA solo con chiave gia' nota. Questi strumenti non craccano il TETRA.")

    logger.info("")
    logger.info(" Log completo in: %s", LOG_FILE)
    if not all_ok:
        logger.warning(
            "\n[NOTA] Alcuni componenti non risultano presenti (vedi sopra). Consulta "
            "%s per l'errore specifico e rilancia l'installer.", LOG_FILE
        )
    return all_ok


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installer della catena TELIVE-2 (ricezione + decifratura vocale TETRA a chiave nota) per Linux"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verifica soltanto quali componenti sono presenti, senza installare nulla",
    )
    parser.add_argument(
        "--no-gnuradio", action="store_true",
        help="Non installare GNU Radio via apt (usalo se ce l'hai gia')",
    )
    return parser.parse_args()


def main() -> int:
    setup_logging()
    args = parse_args()

    logger.info("====== Installer TELIVE-2 v%s ======", SCRIPT_VERSION)
    logger.info("Log completo in: %s", LOG_FILE)

    try:
        if args.check:
            verify_and_summary(completed_install=False)
            return 0

        check_python_version()
        check_operating_system()
        install_system_dependencies(with_gnuradio=not args.no_gnuradio)
        clone_sources()

        # I passi di build sono indipendenti: se uno fallisce lo segnaliamo ma
        # proseguiamo con gli altri, cosi' il riepilogo finale dice cosa manca.
        results = {}
        results["osmo"] = build_osmo_tetra()
        results["codec"] = build_etsi_codec()
        results["telive"] = build_telive()

        setup_tetra_dir()
        add_bin_to_path()

        all_ok = verify_and_summary()
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
