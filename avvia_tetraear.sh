#!/usr/bin/env bash
# ============================================================
#  avvia_tetraear.sh — avvia TetraEar con logging completo
# ============================================================
#  Uso:
#     ./avvia_tetraear.sh [FREQUENZA_MHz]
#  Esempio:
#     ./avvia_tetraear.sh 392.225
#
#  Attiva il virtual environment, avvia la cattura (--auto-start) con
#  log dettagliato (-v) e salva tutto in TetraEar/logs/, cosi' in caso di
#  problemi di decodifica basta inviare quei file.
# ============================================================
set -euo pipefail

FREQ="${1:-392.225}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# Individua la root di TetraEar (dove ci sono tetraear/ e .venv).
if [ -d "$HERE/TetraEar/.venv" ] && [ -d "$HERE/TetraEar/tetraear" ]; then
    ROOT="$HERE/TetraEar"
elif [ -d "$HERE/.venv" ] && [ -d "$HERE/tetraear" ]; then
    ROOT="$HERE"
else
    echo "[ERRORE] Non trovo un'installazione di TetraEar (cartella .venv)."
    echo "         Esegui prima:  python3 install_linux.py"
    exit 1
fi

cd "$ROOT"

# Unica cartella per tutti i log: se TetraEar e' una sottocartella, la sua
# logs/ e' (o diventa) un link simbolico a quella accanto all'installer,
# cosi' i log dell'app e quelli di installazione stanno in un posto solo.
if [ "$ROOT" != "$HERE" ] && [ ! -L "logs" ]; then
    mkdir -p "$HERE/logs"
    if [ -d "logs" ]; then
        mv logs/* "$HERE/logs/" 2>/dev/null || true
        rmdir logs 2>/dev/null || true
    fi
    if [ ! -e "logs" ]; then
        ln -s ../logs logs
    fi
fi
mkdir -p "$(readlink -f logs)"
STAMP="$(date +%Y%m%d_%H%M%S)"
CONSOLE_LOG="logs/console_${STAMP}.log"

echo "============================================================"
echo " Avvio TetraEar su ${FREQ} MHz"
echo " Cartella:  $ROOT"
echo " Log app:   $ROOT/logs/  (codec_*.log, decoder_*.log, ...)"
echo " Console:   $ROOT/$CONSOLE_LOG"
echo " Premi Ctrl+C per fermare."
echo "============================================================"

# shellcheck disable=SC1091
source .venv/bin/activate

# ---------------------------------------------------------------------------
# Ottimizzazioni prestazioni (riducono il rallentamento quando c'e' segnale)
# ---------------------------------------------------------------------------
# 1) File temporanei del codec in RAM: cdecoder scrive/legge 2 file per ogni
#    frame vocale (~20/s); su tmpfs (/dev/shm) e' molto piu' veloce e non usura
#    il disco. Ricade sul default se /dev/shm non e' scrivibile.
if [ -d /dev/shm ] && [ -w /dev/shm ]; then export TMPDIR="/dev/shm"; fi
# 2) Evita che numpy/BLAS aprano un thread per core saturando la CPU e
#    sottraendo tempo alla GUI (l'FFT dello spettro e' piccola). Sovrascrivibile.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-2}"
# 3) Niente scrittura dei .pyc a runtime.
export PYTHONDONTWRITEBYTECODE=1

# Di default NIENTE -v: il logging DEBUG e' enorme (ogni frame + ogni chiamata
# al codec) e rallenta la GUI quando c'e' segnale. Per il debug dettagliato usa
# './avvia_tetraear.sh <freq> --debug' oppure TETRAEAR_DEBUG=1.
VERBOSE=""
case "${2:-}" in --debug|-v|debug) VERBOSE="-v" ;; esac
[ -n "${TETRAEAR_DEBUG:-}" ] && VERBOSE="-v"

# --auto-start avvia subito la cattura · aggiungi -m per sentire l'audio.
# L'output a schermo viene anche salvato nel file di console.
python -m tetraear -f "$FREQ" $VERBOSE --auto-start 2>&1 | tee "$CONSOLE_LOG"
