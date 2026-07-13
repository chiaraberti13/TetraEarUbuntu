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
mkdir -p logs
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

# -v verbose · --auto-start avvia subito la cattura · aggiungi -m per sentire l'audio.
# L'output a schermo viene anche salvato nel file di console.
python -m tetraear -f "$FREQ" -v --auto-start 2>&1 | tee "$CONSOLE_LOG"
