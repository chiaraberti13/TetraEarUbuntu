#!/usr/bin/env python3
"""
install_osmo.py -- Catena osmo-tetra-sq5bpf (v1) con avvio AUTOMATICO (Ubuntu)
=============================================================================

Questo installer sostituisce completamente il vecchio flusso "TELIVE-2" con la
catena ORIGINALE di Jacek Lipkowski (SQ5BPF) basata su:

    * osmo-tetra-sq5bpf   ->  il ricevitore 'tetra-rx' (+ 'float_to_bits')
                              https://github.com/sq5bpf/osmo-tetra-sq5bpf.git
    * codec ETSI TETRA    ->  'cdecoder'/'sdecoder' (ACELP -> audio)
    * telive              ->  l'interfaccia 'telive' + 'tplay'/'tetrad' + i
                              flowgraph GNU Radio
                              https://github.com/sq5bpf/telive.git

E' la versione che l'utente ha verificato funzionare "perfettamente". La
differenza rispetto alla ricezione manuale e' che qui, dopo l'installazione,
un SOLO comando -- ./avvia_osmo.sh -- apre AUTOMATICAMENTE i tre terminali
necessari (GNU Radio, ricevitore, telive) invece di doverli lanciare a mano.

Uso:
    python3 install_osmo.py            # installa e compila tutta la catena
    python3 install_osmo.py --check    # verifica soltanto cosa e' presente
    python3 install_osmo.py --no-gnuradio   # salta GNU Radio (gia' presente)

Per ora SOLO Ubuntu/Debian (come richiesto): usa GNU Radio e strumenti POSIX.

--- Come funziona (riuso del codice gia' collaudato) --------------------------

Le fasi di build di osmo-tetra e telive sono IDENTICHE a quelle della catena
-2 gia' presente nel repo, quindi qui vengono RIUSATE le funzioni gia' testate
di install_telive2.py, ridirezionandole sui repository v1 (basta sovrascrivere
le costanti del modulo: OSMO_REPO, TELIVE_REPO e le cartelle di destinazione).

L'unica parte diversa e' il CODEC: la v1 di osmo-tetra-sq5bpf NON include lo
script 'download_and_patch.sh' della -2, ma le patch "storiche" osmocom
(cartella etsi_codec-patches/ con il file 'series'). Per ottenere un cdecoder
CORRETTO a 64 bit (senza il quale ogni frame vocale va in segmentation fault)
riusiamo lo stesso metodo GIA' COLLAUDATO in install_linux.py: scarichiamo lo
zip ETSI, uniformiamo maiuscole/minuscole di cartelle e file, applichiamo le
patch ufficiali osmo-tetra (che includono la fix a 64 bit) e compiliamo.

IMPORTANTE (identico agli altri installer): questi strumenti NON "craccano" il
TETRA. tetra-rx decodifica il traffico in chiaro; decifra la voce SOLO se la
chiave e' GIA' NOTA (flag '-k keyfile'). Vedi DISCLAIMER.md e usa tutto solo
dove consentito dalle leggi della tua giurisdizione.
"""

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Riusiamo il motore gia' collaudato della catena -2. Importare il modulo NON
# esegue nulla (il suo main() e' protetto da __name__ == "__main__"): definisce
# soltanto costanti e funzioni, che qui ridirezioniamo sui repository v1.
import install_telive2 as t2

# ============================================================
# CONFIGURAZIONE -- ridireziona install_telive2 sui repo v1
# ============================================================

SCRIPT_VERSION = "1.0"

INSTALLER_DIR = Path(__file__).resolve().parent

# Tutti i sorgenti v1 stanno raccolti in ./osmo_v1/ accanto all'installer, per
# non mischiarli con ./telive2/ della catena -2.
OSMO_V1_DIR = INSTALLER_DIR / "osmo_v1"
OSMO_DIR = OSMO_V1_DIR / "osmo-tetra-sq5bpf"
TELIVE_DIR = OSMO_V1_DIR / "telive"

OSMO_REPO = "https://github.com/sq5bpf/osmo-tetra-sq5bpf.git"
TELIVE_REPO = "https://github.com/sq5bpf/telive.git"

# Le patch "storiche" del codec (con la correzione a 64 bit) stanno nel
# repository osmocom osmo-tetra: stessa fonte gia' usata da install_linux.py.
OSMO_TETRA_PATCH_REPOS = [
    "https://gitea.osmocom.org/tetra/osmo-tetra.git",
    "https://github.com/osmocom/osmo-tetra.git",
]

# Flowgraph GNU Radio incluso in telive v1 (stessa posizione della -2).
GRC_RELATIVE = "gnuradio-companion/python3_based_gnuradio/telive_1ch_simple_gr310_udp_xmlrpc.grc"

# --- Ridirezione delle costanti del modulo install_telive2 ------------------
# Le funzioni di install_telive2 leggono queste variabili dai propri globali:
# sovrascrivendole QUI, prima di chiamarle, le facciamo lavorare sui repo v1.
t2.TELIVE2_DIR = OSMO_V1_DIR
t2.OSMO_DIR = OSMO_DIR
t2.TELIVE_DIR = TELIVE_DIR
t2.OSMO_REPO = OSMO_REPO
t2.TELIVE_REPO = TELIVE_REPO
t2.GRC_RELATIVE = GRC_RELATIVE
# Log dedicato a questa installazione (accanto agli altri, in logs/).
t2.LOG_FILE = t2.LOG_DIR / "install_osmo.log"

# Comodita': usiamo il logger e gli helper gia' pronti di install_telive2.
logger = t2.logger
run = t2.run
step = t2.step
fail = t2.fail
InstallError = t2.InstallError


# ============================================================
# CODEC ETSI (metodo v1: patch osmocom con fix a 64 bit)
# ============================================================

def _lowercase_tree(root: Path) -> None:
    """Uniforma in minuscolo i nomi di CARTELLE e poi FILE dell'archivio ETSI.

    Lo zip ETSI estrae nomi in MAIUSCOLO (C-CODE/, SDECODER.C, ...), ma le patch
    osmocom e i Makefile referenziano percorsi minuscoli. Su filesystem
    case-sensitive (Linux) senza questa uniformazione le patch -- inclusa la fix
    a 64 bit -- vengono SALTATE e il cdecoder va in segmentation fault ad ogni
    frame vocale. Prima le cartelle (dal ramo piu' profondo), poi i file.
    Difensivo anche su filesystem case-insensitive (rinomina in due passi)."""
    # 1) cartelle, dal percorso piu' profondo verso la radice
    for path in sorted((p for p in root.rglob("*") if p.is_dir()),
                       key=lambda p: len(p.parts), reverse=True):
        lower = path.name.lower()
        if lower == path.name:
            continue
        target = path.parent / lower
        try:
            same = target.exists() and target.samefile(path)
            if same:
                tmp = path.parent / (path.name + ".tetra-tmpdir")
                path.rename(tmp)
                tmp.rename(target)
            elif not target.exists():
                path.rename(target)
        except OSError as exc:
            logger.debug("Rinomina cartella %s fallita (%s)", path, exc)
    # 2) file
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower == path.name:
            continue
        target = path.parent / lower
        try:
            same = target.exists() and target.samefile(path)
            if same:
                tmp = path.parent / (path.name + ".tetra-tmp")
                path.rename(tmp)
                tmp.rename(target)
            elif target.exists():
                path.unlink()
            else:
                path.rename(target)
        except OSError as exc:
            logger.debug("Rinomina file %s fallita (%s)", path, exc)


def _find_ci(root: Path, name: str) -> Path | None:
    """Cerca (case-insensitive) una voce di nome 'name' sotto 'root'."""
    target = name.lower()
    if root.name.lower() == target:
        return root
    for path in root.rglob("*"):
        if path.name.lower() == target:
            return path
    return None


def _fix_codec_makefile(makefile: Path) -> None:
    """Adatta il Makefile ETSI del 2005 a un GCC moderno: 'acc' -> 'gcc',
    aggiunge -fcommon (richiesto da GCC 10+), toglie -Werror. Stessi ritocchi
    noti e collaudati (progetto install-tetra-codec di sq5bpf)."""
    import re
    data = makefile.read_text(encoding="utf-8", errors="ignore")
    data = re.sub(r"(?m)^ACC\s*=\s*acc\b", "ACC = gcc", data)
    data = re.sub(r"(?m)^(\s*)acc\b", r"\1gcc", data)
    data = re.sub(r"\bacc\b", "gcc", data)
    if "-fcommon" not in data:
        data = re.sub(r"(?m)^CFLAGS\s*=\s*(.*)$", r"CFLAGS = -fcommon \1", data)
    data = data.replace("-Werror", "")
    makefile.write_text(data, encoding="utf-8")


def _clone_osmo_tetra_patches(work_dir: Path) -> Path | None:
    """Clona osmocom osmo-tetra (patch ufficiali del codec, con la fix a 64 bit)
    e ritorna la cartella etsi_codec-patches, o None se nessun mirror risponde."""
    osmo_dir = work_dir / "osmo-tetra"
    for repo_url in OSMO_TETRA_PATCH_REPOS:
        logger.info("Provo a scaricare le patch del codec da %s ...", repo_url)
        if run(["git", "clone", "--depth", "1", repo_url, str(osmo_dir)], check=False).returncode == 0:
            patch_dir = osmo_dir / "etsi_codec-patches"
            if (patch_dir / "series").is_file():
                return patch_dir
            logger.warning("File 'series' non trovato in %s.", patch_dir)
            return None
        logger.warning("Mirror non raggiungibile, provo il successivo...")
    return None


def _apply_series(patch_dir: Path, codec_root: Path) -> None:
    """Applica in ordine le patch elencate in etsi_codec-patches/series dentro
    codec_root (dove sta la cartella c-code). Come install_linux.py: patch -p1,
    exit 1 = 'gia' applicata' (non fatale), altri codici -> errore."""
    series = patch_dir / "series"
    for line in series.read_text(encoding="utf-8").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        patch_file = patch_dir / name
        if not patch_file.is_file():
            logger.warning("Patch elencata ma assente: %s (la salto)", name)
            continue
        logger.info("Applico patch: %s", name)
        with open(patch_file, "rb") as f:
            result = subprocess.run(
                ["patch", "--batch", "-p1", "-N", "-E"],
                cwd=str(codec_root), stdin=f, capture_output=True, text=True,
            )
        if result.stdout:
            logger.debug("--- stdout patch %s ---\n%s", name, result.stdout.strip())
        if result.stderr:
            logger.debug("--- stderr patch %s ---\n%s", name, result.stderr.strip())
        if result.returncode not in (0, 1):
            fail(f"Applicazione patch fallita: {name}\n{result.stderr}")
        if result.returncode == 1 and "FAILED" in (result.stdout + result.stderr):
            logger.warning(
                "[ATTENZIONE] Alcune parti della patch %s NON sono state applicate "
                "(vedi install_osmo.log). Il codec compila comunque, ma la decodifica "
                "potrebbe risentirne.", name)


def build_etsi_codec_v1() -> bool:
    """Scarica, patcha (osmocom, fix 64 bit) e compila il codec ETSI, lasciando
    cdecoder/sdecoder in OSMO_DIR/codec/c-code -- proprio dove la successiva
    setup_tetra_dir() di install_telive2 li cerca per copiarli in /tetra/bin."""
    step("Codec vocale ETSI TETRA (cdecoder / sdecoder) [metodo v1]")

    codec_root = OSMO_DIR / "codec"
    if codec_root.exists():
        shutil.rmtree(codec_root, ignore_errors=True)
    codec_root.mkdir(parents=True, exist_ok=True)

    work_dir = Path(tempfile.mkdtemp(prefix="tetra-codec-v1-"))
    try:
        # 1) Scarico lo zip ETSI (riuso il downloader "da browser" della -2, che
        #    aggira il 403 di ETSI) e ne verifico l'MD5.
        zip_path = work_dir / "etsi_codec.zip"
        t2._download_first_available(t2.ETSI_CODEC_URLS, zip_path)
        if not t2._verify_md5(zip_path, t2.ETSI_CODEC_MD5):
            logger.warning("[ATTENZIONE] MD5 del codec inatteso: proseguo comunque.")

        # 2) Estraggo dentro codec_root e uniformo maiuscole/minuscole.
        logger.info("Estraggo e uniformo i nomi del codec...")
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(codec_root)
        _lowercase_tree(codec_root)

        c_code = _find_ci(codec_root, "c-code")
        if c_code is None:
            logger.error("[FALLITO] Cartella 'c-code' non trovata nello zip ETSI.")
            return False

        # 3) Patch ufficiali osmocom (includono la fix a 64 bit). Se non
        #    raggiungibili, il codec compila comunque ma puo' andare in segfault:
        #    lo segnaliamo in chiaro.
        patch_dir = _clone_osmo_tetra_patches(work_dir)
        if patch_dir is not None:
            _apply_series(patch_dir, c_code.parent)
        else:
            logger.warning(
                "[ATTENZIONE] Patch osmocom non scaricabili: compilo il codec SENZA "
                "la fix a 64 bit. Se la voce non si decodifica (cdecoder in segfault), "
                "rilancia l'installer quando la rete e' disponibile.")

        # 4) Adatto il Makefile a GCC moderno e compilo.
        makefile = _find_ci(c_code, "makefile")
        if makefile is None:
            logger.error("[FALLITO] Makefile non trovato in c-code/.")
            return False
        _fix_codec_makefile(makefile)
        t2._inject_compat_cflags(makefile)
        run(["make", "-f", makefile.name, f"-j{os.cpu_count() or 1}"], cwd=c_code, check=False)

        # 5) Verifico i binari e li porto nel percorso canonico
        #    OSMO_DIR/codec/c-code (dove setup_tetra_dir li cerca).
        canonical = OSMO_DIR / "codec" / "c-code"
        ok = True
        for binary in ("cdecoder", "sdecoder"):
            built = _find_ci(c_code, binary)
            if built is None or not built.is_file():
                logger.error("[FALLITO] Manca il binario %s del codec.", binary)
                ok = False
                continue
            logger.info("[OK] Compilato %s", binary)
            if built.parent.resolve() != canonical.resolve():
                canonical.mkdir(parents=True, exist_ok=True)
                dst = canonical / binary
                shutil.copy2(built, dst)
                dst.chmod(dst.stat().st_mode | 0o111)
        return ok
    except InstallError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("[FALLITO] Errore imprevisto nella build del codec: %s", exc)
        logger.debug("Traceback:", exc_info=True)
        return False
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ============================================================
# LAUNCHER: apre AUTOMATICAMENTE i 3 terminali
# ============================================================

def write_auto_launcher() -> Path:
    """Copia/aggiorna avvia_osmo.sh accanto all'installer e lo rende eseguibile.

    Lo script sorgente e' versionato nel repo (self-locating: trova da solo il
    flowgraph, il ricevitore e telive), quindi qui basta assicurarne il bit +x.
    Se per qualche motivo non fosse presente, lo rigeneriamo al volo."""
    launcher = INSTALLER_DIR / "avvia_osmo.sh"
    if not launcher.is_file():
        launcher.write_text(_LAUNCHER_FALLBACK, encoding="utf-8")
        logger.info("[OK] Generato %s", launcher.name)
    try:
        launcher.chmod(launcher.stat().st_mode | 0o111)
    except OSError:
        pass
    return launcher


# Copia di riserva del launcher, usata solo se avvia_osmo.sh non e' nel repo.
_LAUNCHER_FALLBACK = r"""#!/usr/bin/env bash
# avvia_osmo.sh (riserva) -- vedi la versione versionata nel repo.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
echo "avvia_osmo.sh di riserva: reinstalla con 'python3 install_osmo.py'."
exit 1
"""


# ============================================================
# RIEPILOGO
# ============================================================

def summary(all_ok: bool, completed_install: bool = True) -> None:
    launcher = INSTALLER_DIR / "avvia_osmo.sh"
    step("Verifica finale")
    checks = {
        "tetra-rx (receiver)": (OSMO_DIR / "src" / "tetra-rx").is_file(),
        "float_to_bits": (OSMO_DIR / "src" / "float_to_bits").is_file(),
        "cdecoder": t2._binary_present("cdecoder"),
        "sdecoder": t2._binary_present("sdecoder"),
        "telive": (TELIVE_DIR / "telive").is_file() or t2._binary_present("telive"),
        "gnuradio-companion": shutil.which("gnuradio-companion") is not None,
        "socat": shutil.which("socat") is not None,
        "aplay (audio)": shutil.which("aplay") is not None,
    }
    for name, ok in checks.items():
        logger.info("  %s %s", "[OK]   " if ok else "[MANCA]", name)

    if completed_install:
        logger.info("")
        logger.info("========================================================")
        logger.info(" Installazione osmo-tetra-sq5bpf (v1) completata!")
        logger.info("========================================================")
    logger.info("")
    logger.info(" AVVIO AUTOMATICO (apre da solo i 3 terminali):")
    logger.info("     %s 392.225", launcher)
    logger.info("")
    logger.info("   1) GNU Radio col flowgraph di telive (imposta la frequenza e premi Run)")
    logger.info("   2) Ricevitore osmo:  ./receiver1udp 1")
    logger.info("   3) Interfaccia telive")
    logger.info("")
    logger.info(" Ascolto voce: i file .out finiscono in /tetra/out; riproduci con")
    logger.info("     tplay /tetra/out/<file>.out")
    logger.info("")
    logger.info(" Pannello passivo Network Info (MCC/MNC/LA/Colour Code/AIE...):")
    logger.info("     ./avvia_netscanner.sh 392.225")
    logger.info("")
    logger.info(" Tutti i log in: %s", t2.LOG_DIR)
    if not all_ok:
        logger.warning("\n[NOTA] Alcuni componenti non risultano presenti (vedi sopra). "
                       "Consulta %s per l'errore specifico.", t2.LOG_FILE)


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Installer della catena osmo-tetra-sq5bpf (v1) con avvio "
                    "automatico dei 3 terminali (solo Ubuntu/Debian)")
    parser.add_argument("--check", action="store_true",
                        help="Verifica soltanto quali componenti sono presenti")
    parser.add_argument("--no-gnuradio", action="store_true",
                        help="Non installare GNU Radio via apt (usalo se ce l'hai gia')")
    return parser.parse_args()


def main() -> int:
    t2.setup_logging()
    args = parse_args()

    logger.info("====== Installer osmo-tetra-sq5bpf v1 (avvio automatico) v%s ======", SCRIPT_VERSION)
    logger.info("Log completo in: %s", t2.LOG_FILE)
    t2.log_system_diagnostics()

    try:
        if args.check:
            summary(all_ok=False, completed_install=False)
            return 0

        t2.check_python_version()
        t2.check_operating_system()
        t2.install_system_dependencies(with_gnuradio=not args.no_gnuradio)
        t2.clone_sources()

        results = {}
        results["osmo"] = t2.build_osmo_tetra()      # tetra-rx, float_to_bits
        results["codec"] = build_etsi_codec_v1()     # cdecoder/sdecoder (metodo v1)
        results["telive"] = t2.build_telive()        # interfaccia telive

        t2.setup_tetra_dir()      # /tetra + copia binari e script in /tetra/bin
        t2.add_bin_to_path()      # /tetra/bin nel PATH
        t2.setup_runtime_logs()   # run_receiver.sh / run_gnuradio.sh + link log
        write_auto_launcher()     # avvia_osmo.sh eseguibile

        all_ok = all(results.values())
        summary(all_ok)

        # Pannello passivo Network Info: ne legge l'output del ricevitore.
        t2.run_netscanner(skip=False)
        return 0 if all_ok else 1

    except InstallError:
        return 1
    except KeyboardInterrupt:
        logger.error("\nInstallazione interrotta dall'utente.")
        return 130
    except Exception:
        logger.error("")
        logger.error("[ERRORE IMPREVISTO] Errore non gestito; traceback in %s", t2.LOG_FILE)
        logger.debug("Traceback completo:", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
