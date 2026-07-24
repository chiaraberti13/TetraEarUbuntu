#!/usr/bin/env bash
#
# install_telive2.sh -- Installazione AUTOMATICA di TELIVE-2
# =========================================================================
# Testato per Ubuntu 24.04 (x86) e 25.10 (ARM64). Catena completa (SQ5BPF):
# osmo-tetra-sq5bpf-2 + codec ETSI + telive. Aggiunge la DECIFRATURA vocale a
# CHIAVE NOTA (incl. chiave TEA-1 a 32 bit).
#
# Uso:   bash install_telive2.sh
#
# NOTA: lancialo come UTENTE NORMALE (NON con sudo). Chiedera' la password
# sudo solo per apt e per creare /tetra.
#
# DISCLAIMER: si DECIFRA solo con chiave gia' nota; questi strumenti non
# craccano il TETRA. Usalo solo dove consentito dalla legge.

set -euo pipefail

# ---------------------------------------------------------------------------
# Impostazioni
# ---------------------------------------------------------------------------
OSMO_REPO="https://github.com/sq5bpf/osmo-tetra-sq5bpf-2.git"
TELIVE_REPO="https://github.com/sq5bpf/telive-2.git"
OSMO_DIR="$HOME/osmo-tetra-sq5bpf-2"
TELIVE_DIR="$HOME/telive-2"

ETSI_URL="http://www.etsi.org/deliver/etsi_en/300300_300399/30039502/01.03.01_60/en_30039502v010301p0.zip"
ETSI_MD5="a8115fe68ef8f8cc466f4192572a1e3e"
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

JOBS="$(nproc)"
COMPAT_CFLAGS=""   # riempito da detect_compat_cflags dopo l'installazione di gcc

# ---------------------------------------------------------------------------
# Log: cartella 'logs/' accanto allo script, come per gli installer Python.
# Log il piu' DETTAGLIATO possibile:
#   - logs/install_telive2.log        -> tutto l'output (stdout+stderr) a schermo
#   - logs/install_telive2.debug.log  -> traccia di OGNI comando eseguito
#                                        (xtrace, con orario e numero di riga)
# cosi' e' possibile ricostruire qualunque errore dell'installazione.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
INSTALL_LOG="$LOG_DIR/install_telive2.log"
DEBUG_LOG="$LOG_DIR/install_telive2.debug.log"
if mkdir -p "$LOG_DIR" 2>/dev/null; then
  # sdoppia stdout+stderr: a schermo e nel file di log (append).
  exec > >(tee -a "$INSTALL_LOG") 2>&1
  echo "==== install_telive2.sh -- $(date '+%Y-%m-%d %H:%M:%S') ===="
  echo "Log installazione: $INSTALL_LOG"
  # Traccia dettagliata di ogni comando su un FD separato (non sporca lo schermo).
  if { : >"$DEBUG_LOG"; } 2>/dev/null; then
    export PS4='+ [$(date "+%H:%M:%S")] ${BASH_SOURCE##*/}:${LINENO}: '
    if exec {XTRACE_FD}>>"$DEBUG_LOG" 2>/dev/null; then
      export BASH_XTRACEFD="$XTRACE_FD"
      set -x
      echo "Traccia comandi (dettagliata): $DEBUG_LOG"
    fi
  fi
fi

step() { echo; echo "============================================================"; echo " $*"; echo "============================================================"; }
info() { echo "  -> $*"; }

# Diagnostica di sistema: utilissima quando qualcosa non compila. Finisce sia a
# schermo sia nei log (via tee).
log_system_info() {
  echo
  echo "----- DIAGNOSTICA DI SISTEMA -----"
  echo "data          : $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "utente         : $(id -un)  (uid $(id -u))"
  echo "kernel/arch    : $(uname -srmo 2>/dev/null || uname -a)"
  echo "distribuzione  : $( . /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-sconosciuta}" )"
  echo "cpu core       : $(nproc)"
  echo "gcc            : $(gcc --version 2>/dev/null | head -1 || echo assente)"
  echo "cc             : $(cc --version 2>/dev/null | head -1 || echo assente)"
  echo "make           : $(make --version 2>/dev/null | head -1 || echo assente)"
  echo "git            : $(git --version 2>/dev/null || echo assente)"
  echo "gnuradio       : $(gnuradio-config-info -v 2>/dev/null || echo assente)"
  echo "libosmocore    : $(pkg-config --modversion libosmocore 2>/dev/null || echo assente)"
  echo "libxml2        : $(xml2-config --version 2>/dev/null || echo assente)"
  echo "memoria        : $(free -h 2>/dev/null | awk '/Mem:/{print $2" tot, "$7" disp"}' )"
  echo "disco (\$HOME)  : $(df -h "$HOME" 2>/dev/null | awk 'NR==2{print $4" liberi su "$2}')"
  echo "----------------------------------"
}

# ---------------------------------------------------------------------------
# Compatibilita' compilatore (GCC 14/15)
# ---------------------------------------------------------------------------
# I sorgenti "vecchi" di SQ5BPF contengono costrutti C che GCC 14/15 (Ubuntu
# 25.10) tratta come ERRORE (return-mismatch, chiamate implicite, ...). Su GCC
# 13 (24.04) sono warning. Riportiamo quei pochi a warning con '-Wno-error=...',
# ma teniamo SOLO i flag che il gcc locale accetta (uno sconosciuto rompe gcc):
# cosi' lo stesso script va su 24.04/GCC13 e su 25.10/GCC15.
detect_compat_cflags() {
  local cc="${CC:-cc}" out="" f tmp
  tmp="$(mktemp -d)"
  printf 'int main(void){return 0;}\n' > "$tmp/probe.c"
  for f in -std=gnu17 \
           -Wno-error=implicit-int -Wno-error=implicit-function-declaration \
           -Wno-error=int-conversion -Wno-error=incompatible-pointer-types \
           -Wno-error=return-mismatch -Wno-error=declaration-missing-parameter-type \
           -Wno-error=old-style-definition; do
    if "$cc" "$f" -c "$tmp/probe.c" -o "$tmp/probe.o" >/dev/null 2>&1; then
      out="$out $f"
    fi
  done
  rm -rf "$tmp"
  # trim iniziale
  echo "${out# }"
}

# Inserisce i flag compat subito dopo 'CFLAGS=' nel Makefile indicato ($1).
# Idempotente (salta se gia' presenti) e best-effort (niente CFLAGS = niente da fare).
inject_cflags() {
  local mk="$1"
  [ -f "$mk" ] || return 0
  [ -n "$COMPAT_CFLAGS" ] || return 0
  grep -q -- '-std=gnu17' "$mk" && return 0
  sed -i "0,/^CFLAGS[[:space:]]*=/s//& ${COMPAT_CFLAGS} /" "$mk"
  info "Compatibilita' compilatore applicata a $(basename "$(dirname "$mk")")/$(basename "$mk")"
}

# telive_receiver.h usa 'time_t' ma non include <time.h>: sulle glibc recenti
# la build fallisce con "unknown type name 'time_t'". Aggiungiamo l'include
# suggerito dallo stesso GCC. Idempotente e best-effort.
patch_telive_includes() {
  local h="$TELIVE_DIR/telive_receiver.h"
  [ -f "$h" ] || return 0
  grep -q '#include <time.h>' "$h" && return 0
  if grep -q '#include <stdint.h>' "$h"; then
    sed -i 's|#include <stdint.h>|#include <stdint.h>\n#include <time.h>|' "$h"
  else
    sed -i '1i #include <time.h>' "$h"
  fi
  info "Aggiunto #include <time.h> a telive_receiver.h"
}

# ---------------------------------------------------------------------------
# 0) Controlli preliminari
# ---------------------------------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
  echo "ERRORE: non lanciarmi con sudo/root. Eseguimi come utente normale:"
  echo "        bash install_telive2.sh"
  exit 1
fi

step "0) Controllo sistema"
if ! grep -qiE 'ubuntu|debian' /etc/os-release 2>/dev/null; then
  echo "ATTENZIONE: distribuzione non Ubuntu/Debian: proseguo ma apt potrebbe non funzionare."
fi
info "Utente: $(id -un)   Core: $JOBS   Arch: $(uname -m)"
log_system_info

# ---------------------------------------------------------------------------
# 1) Dipendenze di sistema (Ubuntu 24.04 / 25.10, x86 e ARM64)
# ---------------------------------------------------------------------------
step "1) Installazione dipendenze (apt)"
sudo apt-get update
sudo apt-get install -y \
  build-essential gcc make git pkg-config patch unzip wget ca-certificates \
  libosmocore-dev \
  libncurses-dev libxml2-dev \
  librtlsdr-dev rtl-sdr libusb-1.0-0-dev \
  socat alsa-utils sox vorbis-tools \
  gnuradio gr-osmosdr
info "Dipendenze installate."

if ! pkg-config --exists libosmocore; then
  echo "ATTENZIONE: pkg-config non trova libosmocore: la build dell'osmo receiver potrebbe fallire."
fi

# Ora che gcc c'e', rileviamo i flag di compatibilita' del compilatore locale.
COMPAT_CFLAGS="$(detect_compat_cflags)"
[ -n "$COMPAT_CFLAGS" ] && info "Flag compat compilatore: $COMPAT_CFLAGS"

# ---------------------------------------------------------------------------
# 2) Clone dei sorgenti
# ---------------------------------------------------------------------------
step "2) Download sorgenti (osmo-tetra-sq5bpf-2 e telive-2)"
clone_or_update() {
  local url="$1" dir="$2"
  if [ -d "$dir/.git" ]; then
    info "Aggiorno $dir"; git -C "$dir" pull --ff-only || true
  else
    info "Clono $url"; git clone --depth 1 "$url" "$dir"
  fi
}
clone_or_update "$OSMO_REPO" "$OSMO_DIR"
clone_or_update "$TELIVE_REPO" "$TELIVE_DIR"

# ---------------------------------------------------------------------------
# 3) Build dell'osmo receiver (tetra-rx, float_to_bits, ...)
# ---------------------------------------------------------------------------
step "3) Compilo l'osmo receiver (tetra-rx)"
inject_cflags "$OSMO_DIR/src/Makefile"
make -C "$OSMO_DIR/src" -j"$JOBS"
[ -x "$OSMO_DIR/src/tetra-rx" ] && info "OK: tetra-rx compilato" || { echo "ERRORE: tetra-rx non compilato"; exit 1; }

# ---------------------------------------------------------------------------
# 4) Codec vocale ETSI (cdecoder / sdecoder) -- con fix del 403
# ---------------------------------------------------------------------------
step "4) Scarico e compilo il codec vocale ETSI"
PATCHDIR="$OSMO_DIR/etsi_codec-patches"
ZIP="$PATCHDIR/etsi_tetra_codec.zip"

got=0
check_md5() { [ "$(md5sum "$1" | awk '{print $1}')" = "$ETSI_MD5" ]; }

info "Scarico il codec da ETSI (User-Agent browser)..."
if wget -q -U "$UA" -O "$ZIP" "$ETSI_URL" && check_md5 "$ZIP"; then
  got=1
else
  info "Sito ETSI non raggiungibile o file errato: provo il mirror archive.org..."
  if wget -q -U "$UA" -O "$ZIP" "https://web.archive.org/web/2id_/$ETSI_URL" && check_md5 "$ZIP"; then
    got=1
  fi
fi

if [ "$got" -eq 1 ]; then
  info "Zip ETSI pronto e verificato: lo script salta il download."
  sed -i 's/\[ ! -f $LOCAL_FILE \]/false/g; s/print "MD5sum/echo "MD5sum/g' "$PATCHDIR/download_and_patch.sh"
else
  info "Pre-download non riuscito: lo script scarichera' con User-Agent browser."
  sed -i 's/\[ ! -f $LOCAL_FILE \]/true/g; s/wget -O/wget -U "Mozilla\/5.0" -O/g; s/print "MD5sum/echo "MD5sum/g' "$PATCHDIR/download_and_patch.sh"
fi

( cd "$PATCHDIR" && sh ./download_and_patch.sh )
inject_cflags "$OSMO_DIR/codec/c-code/Makefile"
make -C "$OSMO_DIR/codec/c-code" -j"$JOBS"
[ -x "$OSMO_DIR/codec/c-code/cdecoder" ] && [ -x "$OSMO_DIR/codec/c-code/sdecoder" ] \
  && info "OK: cdecoder e sdecoder compilati" \
  || { echo "ERRORE: codec non compilato"; exit 1; }

# ---------------------------------------------------------------------------
# 5) Build di telive
# ---------------------------------------------------------------------------
step "5) Compilo telive"
inject_cflags "$TELIVE_DIR/Makefile"
patch_telive_includes
make -C "$TELIVE_DIR" -j"$JOBS"
[ -x "$TELIVE_DIR/telive" ] && info "OK: telive compilato" || { echo "ERRORE: telive non compilato"; exit 1; }

# ---------------------------------------------------------------------------
# 6) Cartella di lavoro /tetra e collegamento dei binari
# ---------------------------------------------------------------------------
step "6) Preparo /tetra e copio i binari"
sudo mkdir -p /tetra
sudo chown "$(id -un):$(id -gn)" /tetra
mkdir -p /tetra/in /tetra/out /tetra/log /tetra/tmp /tetra/bin
touch /tetra/log/telive.log

cp -v "$TELIVE_DIR"/bin/* /tetra/bin/ 2>/dev/null || true
cp -v "$OSMO_DIR/codec/c-code/cdecoder" "$OSMO_DIR/codec/c-code/sdecoder" /tetra/bin/
cp -v "$TELIVE_DIR/telive" /tetra/bin/
chmod +x /tetra/bin/* || true

# ---------------------------------------------------------------------------
# 7) PATH
# ---------------------------------------------------------------------------
step "7) Aggiungo /tetra/bin al PATH"
if ! grep -q '/tetra/bin' "$HOME/.bashrc" 2>/dev/null; then
  printf '\n# TELIVE-2: decoder vocali TETRA\nexport PATH="$PATH:/tetra/bin"\n' >> "$HOME/.bashrc"
  info "Aggiunto a ~/.bashrc (riapri il terminale o esegui: source ~/.bashrc)"
else
  info "/tetra/bin gia' nel PATH."
fi

# ---------------------------------------------------------------------------
# 8) Log di runtime (uso del programma)
# ---------------------------------------------------------------------------
# Oltre al log dell'installazione, raccogliamo in un solo posto anche i log
# dell'USO: telive scrive gia' in /tetra/log/telive.log (lo colleghiamo nella
# cartella logs/), e creiamo un launcher del ricevitore che salva tutto il suo
# output in logs/receiver.log (dove compaiono gli errori di gnuradio/tetra-rx).
step "8) Log di runtime (uso del programma)"
mkdir -p "$LOG_DIR"

# link del log runtime di telive dentro la cartella logs/ comune
ln -sf /tetra/log/telive.log "$LOG_DIR/telive-runtime.log" 2>/dev/null || true

# launcher del ricevitore con log su file (tee: a schermo e in logs/receiver.log)
RECV_LAUNCHER="$OSMO_DIR/src/run_receiver.sh"
cat > "$RECV_LAUNCHER" <<RUNEOF
#!/usr/bin/env bash
# Avvia il ricevitore osmo registrando TUTTO l'output in:
#   $LOG_DIR/receiver.log
# Uso:  ./run_receiver.sh [RXID]   (RXID predefinito: 1)
cd "$OSMO_DIR/src"
echo "==== receiver \$(date '+%Y-%m-%d %H:%M:%S') ====" >> "$LOG_DIR/receiver.log"
exec ./receiver1udp "\${1:-1}" 2>&1 | tee -a "$LOG_DIR/receiver.log"
RUNEOF
chmod +x "$RECV_LAUNCHER"

# launcher di GNU Radio con log su file (cattura i messaggi della GUI/flowgraph)
GRC="$TELIVE_DIR/gnuradio-companion/python3_based_gnuradio/telive_1ch_simple_gr310_udp_xmlrpc.grc"
GR_LAUNCHER="$TELIVE_DIR/run_gnuradio.sh"
cat > "$GR_LAUNCHER" <<GREOF
#!/usr/bin/env bash
# Avvia GNU Radio col flowgraph di telive, registrando TUTTO l'output in:
#   $LOG_DIR/gnuradio.log
# Uso:  ./run_gnuradio.sh [file.grc]   (predefinito: il flowgraph 1ch di telive)
GRCFILE="\${1:-$GRC}"
echo "==== gnuradio \$(date '+%Y-%m-%d %H:%M:%S')  ->  \$GRCFILE ====" >> "$LOG_DIR/gnuradio.log"
exec gnuradio-companion "\$GRCFILE" 2>&1 | tee -a "$LOG_DIR/gnuradio.log"
GREOF
chmod +x "$GR_LAUNCHER"

info "Log installazione : $INSTALL_LOG"
info "Traccia comandi   : $DEBUG_LOG"
info "Log telive (uso)  : /tetra/log/telive.log  (link: $LOG_DIR/telive-runtime.log)"
info "Log ricevitore    : $LOG_DIR/receiver.log  (via $RECV_LAUNCHER)"
info "Log GNU Radio     : $LOG_DIR/gnuradio.log  (via $GR_LAUNCHER)"

# ---------------------------------------------------------------------------
# Fine
# ---------------------------------------------------------------------------
cat <<EOF

============================================================
 Installazione TELIVE-2 completata!
============================================================

COME USARLO (tre terminali) -- ogni comando registra tutto nei log:

 1) GNU Radio (sorgente dalla chiavetta -> UDP verso telive):
      "$TELIVE_DIR/run_gnuradio.sh"
    (equivale a: gnuradio-companion "$GRC")

 2) Ricevitore osmo:
      "$OSMO_DIR/src/run_receiver.sh" 1
    (equivale a: cd "$OSMO_DIR/src" && ./receiver1udp 1)

 3) Interfaccia telive:
      cd "$TELIVE_DIR" && ./telive

 Ascolto voce: i file .out finiscono in /tetra/out
      tplay /tetra/out/<file>.out

TUTTI I LOG (per monitorare gli errori) sono nella cartella:
      $LOG_DIR
   - install_telive2.log         (installazione: output completo)
   - install_telive2.debug.log   (installazione: traccia di ogni comando)
   - gnuradio.log                (GNU Radio, via run_gnuradio.sh)
   - receiver.log                (ricevitore osmo / tetra-rx, via run_receiver.sh)
   - telive-runtime.log          (link a /tetra/log/telive.log)

DECIFRATURA a chiave NOTA (TEA1, anche chiave 32-bit):
      ./tetra-rx -r -k <keyfile> -s /dev/stdin
  receiver1udp usa gia' '-k sample_keyfile' (in $OSMO_DIR/src): mettici la tua chiave.
  Esempio (chiave TEA-1 accorciata a 32 bit -> key_type 16, padding a 80 bit):
      network mcc 0123 mnc 1337 ksg_type 1 security_class 2
      key mcc 0123 mnc 1337 addr 00000000 key_type 16 key_num 0 key 12345678000000000000

  Decifrare != craccare: si decifra solo con chiave gia' nota.
============================================================
EOF
