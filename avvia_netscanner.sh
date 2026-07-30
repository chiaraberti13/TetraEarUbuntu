#!/usr/bin/env bash
# ============================================================
#  avvia_netscanner.sh -- Pannello passivo Network Info TETRA
# ============================================================
#  Uso:
#     ./avvia_netscanner.sh [FREQUENZA_MHz] [argomenti extra...]
#  Esempi:
#     ./avvia_netscanner.sh 392.225                 # modo automatico
#     ./avvia_netscanner.sh 392.225 --run           # forza il ricevitore live
#     ./avvia_netscanner.sh 392.225 --no-tui        # rendering testuale
#
#  Se esiste gia' un log del ricevitore (logs/receiver.log, scritto dalla
#  catena TELIVE-2), il pannello lo SEGUE in tempo reale: cosi' convive con
#  una normale sessione telive senza contendersi la chiavetta. Altrimenti
#  avvia direttamente il ricevitore (--run).
# ============================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FREQ="392.225"
if [ "${1:-}" != "" ] && [[ "${1:-}" =~ ^[0-9.]+$ ]]; then
    FREQ="$1"; shift
fi

cd "$HERE"
mkdir -p logs
RECV_LOG="logs/receiver.log"

# Se l'utente non ha gia' scelto una sorgente, decidila in automatico.
HAS_SOURCE=0
for a in "$@"; do
    case "$a" in
        --run|--attach-file|--attach-udp) HAS_SOURCE=1 ;;
    esac
done

ARGS=(-f "$FREQ")
if [ "$HAS_SOURCE" -eq 0 ]; then
    if [ -f "$RECV_LOG" ]; then
        echo "[info] Seguo $RECV_LOG (convive con telive). Usa --run per il ricevitore diretto."
        ARGS+=(--attach-file "$RECV_LOG" --follow)
    else
        ARGS+=(--run)
    fi
fi

exec python3 "$HERE/tetra_netscanner.py" "${ARGS[@]}" "$@"
