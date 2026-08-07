#!/usr/bin/env bash
# ============================================================
#  avvia_osmo.sh — apre AUTOMATICAMENTE i 3 terminali della
#  catena osmo-tetra-sq5bpf (v1): GNU Radio, ricevitore, telive.
# ============================================================
#  Uso:
#     ./avvia_osmo.sh [FREQUENZA_MHz]
#  Esempio:
#     ./avvia_osmo.sh 392.225
#
#  Invece di aprire e configurare tre terminali a mano, questo script li
#  lancia da solo, in ordine e con le giuste pause:
#     1) GNU Radio col flowgraph di telive (imposti la frequenza e premi Run)
#     2) il ricevitore osmo  (./receiver1udp 1)
#     3) l'interfaccia telive
#
#  Lo script si "auto-localizza": trova da solo il flowgraph .grc, il
#  ricevitore e il binario telive prodotti da install_osmo.py, ovunque sia
#  stata scompattata la cartella osmo_v1/.
# ============================================================
set -euo pipefail

FREQ="${1:-392.225}"
RXID="${2:-1}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# 1) Individua i componenti (auto-localizzazione, robusta agli spostamenti)
# ---------------------------------------------------------------------------
# Cartella dei sorgenti v1: di norma ./osmo_v1 accanto a questo script.
find_one() {
    # find_one <base> <relative-glob-or-name>  -> stampa il primo match trovato
    local base="$1" pat="$2" hit
    hit="$(find "$base" -type f -name "$pat" 2>/dev/null | head -n1 || true)"
    [ -n "$hit" ] && { echo "$hit"; return 0; }
    return 1
}

OSMO_ROOT=""
for cand in "$HERE/osmo_v1" "$HERE"; do
    if [ -d "$cand" ]; then OSMO_ROOT="$cand"; break; fi
done
[ -n "$OSMO_ROOT" ] || OSMO_ROOT="$HERE"

# Flowgraph GNU Radio (python3), ricevitore, binario telive.
GRC="$(find_one "$OSMO_ROOT" 'telive_1ch_simple_gr310_udp_xmlrpc.grc' || true)"
RECV="$(find "$OSMO_ROOT" -type f -name 'receiver1udp' 2>/dev/null | head -n1 || true)"
TELIVE_BIN="$(find "$OSMO_ROOT" -type f -name 'telive' -perm -u+x 2>/dev/null | head -n1 || true)"
[ -n "$TELIVE_BIN" ] || TELIVE_BIN="$(find "$OSMO_ROOT" -type f -name 'telive' 2>/dev/null | head -n1 || true)"

missing=0
if ! command -v gnuradio-companion >/dev/null 2>&1; then
    echo "[ERRORE] 'gnuradio-companion' non trovato. Installa con: python3 install_osmo.py"
    missing=1
fi
[ -n "$GRC" ]        || { echo "[ERRORE] Flowgraph .grc non trovato sotto $OSMO_ROOT"; missing=1; }
[ -n "$RECV" ]       || { echo "[ERRORE] 'receiver1udp' non trovato sotto $OSMO_ROOT"; missing=1; }
[ -n "$TELIVE_BIN" ] || { echo "[ERRORE] Binario 'telive' non trovato sotto $OSMO_ROOT"; missing=1; }
if [ "$missing" -ne 0 ]; then
    echo
    echo "Esegui prima l'installazione:  python3 install_osmo.py"
    exit 1
fi

RECV_DIR="$(dirname "$RECV")"
TELIVE_DIR="$(dirname "$TELIVE_BIN")"

echo "============================================================"
echo " Avvio catena osmo-tetra-sq5bpf (v1)"
echo "   Frequenza (da impostare in GNU Radio): ${FREQ} MHz"
echo "   Flowgraph : $GRC"
echo "   Ricevitore: $RECV  (RXID $RXID)"
echo "   telive    : $TELIVE_BIN"
echo "============================================================"

# ---------------------------------------------------------------------------
# 2) Prepara i 3 comandi come piccoli script temporanei (niente quoting-hell)
# ---------------------------------------------------------------------------
TMPDIR_LAUNCH="$(mktemp -d /tmp/avvia_osmo.XXXXXX)"
trap 'rm -rf "$TMPDIR_LAUNCH"' EXIT

# Ogni terminale resta aperto a fine comando cosi' puoi leggere i messaggi.
make_step() {
    # make_step <file> <titolo> <corpo>
    local file="$1" title="$2" body="$3"
    cat > "$file" <<EOF
#!/usr/bin/env bash
echo "==== $title ===="
export PATH="\$PATH:/tetra/bin"
$body
echo
echo "[$title terminato — premi INVIO per chiudere questa finestra]"
read -r _
EOF
    chmod +x "$file"
}

S1="$TMPDIR_LAUNCH/1_gnuradio.sh"
S2="$TMPDIR_LAUNCH/2_receiver.sh"
S3="$TMPDIR_LAUNCH/3_telive.sh"

make_step "$S1" "1) GNU Radio (imposta ${FREQ} MHz e premi Run)" \
    "cd \"$(dirname "$GRC")\"; exec gnuradio-companion \"$GRC\""
make_step "$S2" "2) Ricevitore osmo (receiver1udp $RXID)" \
    "cd \"$RECV_DIR\"; exec ./receiver1udp \"$RXID\""
make_step "$S3" "3) Interfaccia telive" \
    "cd \"$TELIVE_DIR\"; exec ./telive"

# ---------------------------------------------------------------------------
# 3) Rileva un emulatore di terminale e apri le 3 finestre
# ---------------------------------------------------------------------------
open_term() {
    # open_term <titolo> <script>
    local title="$1" script="$2"
    if command -v gnome-terminal >/dev/null 2>&1; then
        gnome-terminal --title="$title" -- bash "$script" &
    elif command -v konsole >/dev/null 2>&1; then
        konsole --hold -p "tabtitle=$title" -e bash "$script" &
    elif command -v xfce4-terminal >/dev/null 2>&1; then
        xfce4-terminal --title="$title" --hold -x bash "$script" &
    elif command -v mate-terminal >/dev/null 2>&1; then
        mate-terminal --title="$title" -- bash "$script" &
    elif command -v tilix >/dev/null 2>&1; then
        tilix -t "$title" -e bash "$script" &
    elif command -v xterm >/dev/null 2>&1; then
        xterm -T "$title" -e bash "$script" &
    elif command -v x-terminal-emulator >/dev/null 2>&1; then
        x-terminal-emulator -e bash "$script" &
    else
        return 1
    fi
    return 0
}

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "[ATTENZIONE] Nessun display grafico rilevato (DISPLAY/WAYLAND_DISPLAY vuoti)."
    echo "             Su WSL serve WSLg. Apri i 3 comandi manualmente:"
    echo "   1) gnuradio-companion \"$GRC\""
    echo "   2) cd \"$RECV_DIR\" && ./receiver1udp $RXID"
    echo "   3) cd \"$TELIVE_DIR\" && ./telive"
    exit 1
fi

# Apri nell'ordine giusto, con pause: prima GNU Radio (la sorgente), poi il
# ricevitore, infine telive. Le pause danno tempo a ciascun passo di avviarsi.
if ! open_term "GNU Radio" "$S1"; then
    echo "[ERRORE] Nessun emulatore di terminale trovato (gnome-terminal, konsole,"
    echo "         xfce4-terminal, xterm...). Installane uno oppure apri i 3 comandi a mano:"
    echo "   1) gnuradio-companion \"$GRC\""
    echo "   2) cd \"$RECV_DIR\" && ./receiver1udp $RXID"
    echo "   3) cd \"$TELIVE_DIR\" && ./telive"
    exit 1
fi
echo " -> Aperto terminale 1 (GNU Radio). Imposta ${FREQ} MHz e premi Run."
sleep 6

open_term "Ricevitore osmo" "$S2" || true
echo " -> Aperto terminale 2 (ricevitore)."
sleep 3

open_term "telive" "$S3" || true
echo " -> Aperto terminale 3 (telive)."

echo
echo "Tutti e tre i terminali sono stati aperti."
echo "Se non senti/decodifichi nulla: in GNU Radio controlla la frequenza"
echo "(${FREQ} MHz) e che il flowgraph sia in Run; i .out finiscono in /tetra/out."
# Diamo tempo agli emulatori 'fire-and-forget' di leggere gli script prima che
# il trap EXIT rimuova la cartella temporanea.
sleep 3
