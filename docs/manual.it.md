<p align="center"><img src="../assets/banner.svg" alt="TetraEar" width="100%"></p>

<p align="center"><a href="manual.en.md">🇬🇧 English</a> · <a href="manual.it.md">🇮🇹 Italiano</a></p>

<p align="center"><a href="../README.md">Panoramica del progetto</a> · <a href="../SECURITY.md">Sicurezza</a> · <a href="../LICENSE">Licenza</a></p>

---

## 🇮🇹 Italiano

### Panoramica

**TetraEar** è un decoder TETRA (Terrestrial Trunked Radio) per chiavette
RTL-SDR (chip RTL2832U). Questa repository contiene degli **installer
completamente automatizzati** che, con un solo comando, preparano tutto ciò
che serve a TetraEar: pacchetti di sistema, ambiente Python, codec vocale
ETSI e configurazione della chiavetta RTL-SDR.

Non devi clonare tu TetraEar: l'installer ne scarica il codice sorgente
automaticamente.

> ⚠️ **Leggi il [disclaimer legale](DISCLAIMER.md) prima di usare questo
> software.** TetraEar è destinato solo a scopi didattici e di ricerca, e
> solo dove consentito dalle leggi della tua giurisdizione.

### Cosa fanno gli installer

1. Controllano Python e il sistema operativo.
2. Installano le dipendenze di sistema (compilatore, librerie RTL-SDR, Qt, audio).
3. Scaricano il codice sorgente di TetraEar.
4. Creano un ambiente virtuale Python (`.venv`) e installano i pacchetti `pip`.
5. Configurano la chiavetta RTL-SDR (su Linux in automatico).
6. Scaricano e compilano il codec vocale ETSI TETRA.
7. Verificano che tutto sia a posto.

Tutto ciò che accade viene registrato in **`logs/install.log`** (tutti i log,
compresi quelli dell'app, stanno nella cartella `logs/` accanto all'installer)
— allega quel file se hai bisogno di supporto.

### Cosa ti serve

- Una connessione a Internet.
- Una chiavetta **RTL-SDR** (chip RTL2832U) con antenna — serve solo quando
  *usi* TetraEar, non per installarlo.
- I permessi di amministratore (su Linux la password `sudo`; su Windows la
  finestra si eleva da sola).

---

### 🐧 Ubuntu / Debian

Testato su **Ubuntu 24.04** e **Debian 12** (dovrebbe funzionare anche su
derivate recenti come Linux Mint e Pop!_OS).

**1. Installazione**

```bash
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
python3 install_linux.py
```

Ti verrà chiesta la password di `sudo` (per installare i pacchetti di
sistema). Il processo richiede qualche minuto. Al termine l'installer avrà
creato accanto a sé una cartella `TetraEar/` con il codice sorgente,
l'ambiente `.venv` e il codec compilato.

**2. La chiavetta RTL-SDR è configurata in automatico**

Su Linux non devi fare nulla a mano: l'installer mette in blacklist i driver
DVB-T del kernel che altrimenti "occupano" la chiavetta, installa/ricarica le
regole udev e aggiunge il tuo utente al gruppo `plugdev`.

> ⚠️ **Passaggio finale obbligatorio:** dopo l'installazione **scollega e
> ricollega** la chiavetta (oppure riavvia), così la blacklist del driver e
> le regole udev hanno effetto. Poi verifica con:
>
> ```bash
> rtl_test -t
> ```
>
> Se compare "Found 1 device(s)" sei a posto. `usb_claim_interface error -6`
> significa che il driver DVB-T è ancora caricato → ricollega o riavvia.

**3. Avvia TetraEar**

```bash
cd TetraEar
source .venv/bin/activate
python -m tetraear -f 392.225          # interfaccia grafica
# oppure senza GUI:
python -m tetraear --no-gui -f 392.225 --auto-start
```

(sostituisci `392.225` con la frequenza in MHz che ti interessa).

**Senza terminale:** l'installer crea anche una voce **TetraEar** nel menu
applicazioni e un'icona **`TetraEar.desktop`** sul Desktop — doppio clic per
avviare, senza terminale. L'icona avvia già la cattura in automatico con log
dettagliato, quindi scrive gli stessi file in `TetraEar/logs/` (più un
`console_*.log`) del comando da terminale — comodo se la voce non si
decodifica e devi inviare i log.

**Riavviare l'app (dopo logout o riavvio)** — bastano tre righe:

```bash
cd ~/TetraEarUbuntu/TetraEar
source .venv/bin/activate
python -m tetraear -f 392.225
```

Per avviarla con una sola parola, crea un alias una volta sola:

```bash
echo "alias tetraear='cd ~/TetraEarUbuntu/TetraEar && source .venv/bin/activate && python -m tetraear -f 392.225'" >> ~/.bashrc && source ~/.bashrc
```

Da allora basta digitare `tetraear`. C'è anche uno script pronto: dalla
cartella `TetraEarUbuntu` esegui `./avvia_tetraear.sh 392.225`.

**Decodifica vocale e log.** A ogni avvio l'app scrive log dettagliati in
`TetraEar/logs/`: `codec_<id>.log`, `decoder_<id>.log`, `audio_<id>.log`,
`tetraear_<id>.log`. Avvia con `-v --auto-start` (aggiungi `-m` per sentire
l'audio) per esercitare la decodifica, poi inviami quei file se la voce non
esce — lo script `avvia_tetraear.sh` fa esattamente questo.

> ℹ️ **Perché la voce può non decodificarsi.** Nelle reti TETRA
> professionali la voce è quasi sempre **cifrata** (TEA1–4): le chiamate
> cifrate non sono decodificabili senza le chiavi e compaiono come 🔐 nella
> tabella dei frame. Inoltre devi essere sintonizzato su una frequenza con
> una chiamata vocale **in chiaro** realmente attiva, con guadagno/segnale
> sufficienti. Se i frame arrivano ma l'audio è muto, guarda
> `codec_<id>.log`: un codec funzionante scrive `cdecoder exited 0` /
> `sdecoder exited 0`.
>
> **Lo stato dice "Signal Detected (Decoding…)" ma la tabella dei frame è
> vuota?** Di solito sono i filtri: imposta **Filter** su **All/Tutti** e
> **deseleziona "Decrypted/Text Only"** — altrimenti vedi solo le righe
> audio/testo già decifrate. Se poi i frame compaiono tutti con 🔐 il
> traffico è cifrato e il contatore del lucchetto (es. `0/0` = nessuna
> chiave caricata) conferma che non hai chiavi, quindi la voce non è
> recuperabile. Ricorda inoltre che un portante continuo è spesso un
> **canale di controllo** (segnalazione): la voce compare solo durante una
> chiamata reale.

**4. Comandi utili**

| Comando | Cosa fa |
| --- | --- |
| `python3 install_linux.py` | Installazione completa |
| `python3 install_linux.py --repair` | Ricompila solo il codec vocale + riapplica le correzioni |
| `python3 install_linux.py --uninstall` | Rimuove `.venv` e il codec (lascia il sorgente) |
| `python3 install_linux.py --check` | Verifica l'installazione (venv, codec, pyrtlsdr) senza modificare nulla |
| `python3 install_linux.py --ref <commit\|tag\|branch>` | Installa una versione specifica di TetraEar |

> ℹ️ **Installazioni riproducibili.** L'installer fissa TetraEar a una release
> nota e testata (attualmente `v2.3`) invece di prendere sempre l'ultimo
> `master`, così un cambiamento a monte non può rompere di nascosto le patch
> applicate. Il commit esatto installato è registrato in
> `TetraEar/.tetraear_version`. Per installare una versione diversa usa
> `--ref` (o la variabile d'ambiente `TETRAEAR_REF`). Il codec vocale ETSI
> viene scaricato da ETSI con fallback automatico su archive.org se il sito
> ETSI è irraggiungibile; il download è sempre verificato con MD5.

**5. Problemi comuni (Linux)**

- **`Could not get lock /var/lib/dpkg/lock-frontend` (occupato da
  `unattended-upgr`)**: gli aggiornamenti automatici di Ubuntu partono subito
  dopo l'avvio e tengono occupato il lock dei pacchetti. L'installer ora
  attende in automatico; se dovesse arrendersi, aspetta 2-3 minuti che gli
  aggiornamenti finiscano e rilancia `python3 install_linux.py`.
- **`dpkg was interrupted, you must manually run 'sudo dpkg --configure -a'`**:
  una precedente operazione sui pacchetti è rimasta a metà (un aggiornamento
  interrotto, uno spegnimento forzato…), così `apt` si rifiuta di proseguire.
  L'installer ora rileva questa situazione ed esegue automaticamente
  `sudo dpkg --configure -a` al posto tuo, poi riprova. Se la riparazione
  automatica fallisce a sua volta, esegui a mano `sudo dpkg --configure -a`,
  leggi gli errori che riporta e poi rilancia `python3 install_linux.py`.
- **La GUI non parte, "could not load the Qt platform plugin xcb"**:
  l'installer installa già le librerie Qt necessarie; assicurati di essere in
  una sessione grafica (non SSH senza display).
- **Chiavetta non rilevata / `usb_claim_interface error -6`**: il driver
  DVB-T è ancora caricato. Scollega/ricollega la chiavetta (o riavvia), poi
  `rtl_test -t`.
- **`rtl_test` funziona solo con sudo**: fai logout/login una volta (per
  attivare l'appartenenza al gruppo `plugdev`).
- **All'avvio: `undefined symbol: rtlsdr_set_dithering` (o simile)**: è
  un'incompatibilità tra `pyrtlsdr` e la `librtlsdr` di Ubuntu (che non ha
  alcune funzioni presenti solo nel fork *keenerd*). L'installer applica una
  patch a `pyrtlsdr` che tollera i simboli mancanti; se hai aggiornato lo
  script, rilancia `python3 install_linux.py` (o `--repair`). **Non dipende**
  dalla chiavetta: l'errore compare all'`import`.
- **Il download del codec da ETSI fallisce**: riprova più tardi (a volte il
  sito ETSI è irraggiungibile), poi `python3 install_linux.py --repair`.
- **Non decodifica nulla, `decoder.log`/`app.log` pieni di `Decode error:
  'CaptureThread' object has no attribute 'signal_processor'`**: è un bug del
  sorgente TetraEar a monte (nome di attributo errato nel thread di cattura).
  L'installer lo corregge in automatico; se hai aggiornato lo script, rilancia
  `python3 install_linux.py` (o `--repair`).
- **La voce è a scatti / si decodifica solo in parte su una macchina lenta**:
  ogni frame vocale esegue il codec ETSI come processo esterno. Su un sistema
  carico o "a freddo" (es. alle prime chiamate, mentre l'antivirus analizza il
  codec appena compilato) l'esecuzione può superare il timeout per-frame del
  codec, così i frame altrimenti decodificabili vengono scartati. L'installer
  alza il timeout predefinito da 5 s a 15 s; puoi regolarlo con la variabile
  d'ambiente `TETRAEAR_CODEC_TIMEOUT` (in secondi). Rilancia
  `python3 install_linux.py` (o `--repair`) per applicare la patch. Dipende dal
  progetto a monte e dal tuo segnale, non dall'installer.

---

### 📡 Decoder aggiuntivi (DMR, P25, ADS-B, cercapersone) — Linux

TetraEar decodifica il TETRA. Ma una chiavetta RTL-SDR riceve molti altri modi
— gli stessi che programmi chiusi come OpenEar coprivano, qui però con
strumenti **open source**:

| Strumento | Cosa decodifica |
| --- | --- |
| **multimon-ng** | cercapersone POCSAG / FLEX e altri modi FSK/AFSK |
| **dump1090** | ADS-B 1090 MHz (posizione aerei, mappa web) |
| **dsd-fme** | DMR / P25 / NXDN / dPMR (voce digitale **in chiaro**) |

**Vengono installati in automatico** al termine di `python3 install_linux.py`
(log in `logs/install_extra.log`, ogni decoder indipendente). Usa `--no-extra`
per saltarli, oppure rilancia lo script complementare da solo più tardi:

```bash
python3 install_extra_decoders.py                 # (re)installa tutti e tre
python3 install_extra_decoders.py --only dump1090 # solo uno (o un sottoinsieme)
python3 install_extra_decoders.py --check         # vedi cosa è installato
```

Dopo l'installazione, uso tipico (con la chiavetta collegata):

```bash
# Cercapersone (POCSAG), es. 439.9875 MHz
rtl_fm -f 439.9875M -s 22050 -g 42 - | \
  multimon-ng -t raw -a POCSAG1200 -f alpha /dev/stdin
# Aerei (ADS-B), mappa web su http://localhost:8080
dump1090 --interactive --net
# Voce DMR/P25 in chiaro, es. 446.09375 MHz
rtl_fm -f 446.09375M -s 48000 -g 42 - | dsd-fme -i - -o /dev/null
```

> ℹ️ Come sempre: vedi traffico solo se sei sulla frequenza giusta con segnale
> sufficiente, e la voce/dati **cifrati** non sono decodificabili senza le
> chiavi — da nessun software. Usa solo dove consentito dalla legge (vedi
> [DISCLAIMER](DISCLAIMER.md)).

📖 La guida d'uso completa (frequenze, comandi, note per Windows) è nelle
sezioni seguenti. Su Windows usa `install_extra_decoders_windows.py`.

---

### 🔓 Decifratura vocale a chiave nota — TELIVE-2 (Linux e Windows via WSL)

TetraEar decodifica la voce TETRA **in chiaro**. Se possiedi *già* la chiave
di cifratura, la catena **TELIVE-2** (osmo-tetra-sq5bpf-2 + codec ETSI +
telive) di Jacek Lipkowski (SQ5BPF) sa anche **decifrare** la voce — inclusa
la **chiave TEA-1 accorciata a 32 bit** (il backdoor documentato da Team
Midnight Blue nel 2023).

> ✅ **Viene installata in automatico** alla fine di `install_linux.py` — non
> serve un passo separato. Per saltarla, passa `--no-telive2` all'installer
> principale. La build è pesante (GNU Radio, `libosmocore`, codec ETSI),
> quindi aggiunge qualche minuto.

Puoi comunque eseguire (o rieseguire) l'installer complementare da solo:

```bash
python3 install_telive2.py            # compila e collega tutta la catena
python3 install_telive2.py --check    # controlla soltanto cosa è presente
python3 install_telive2.py --no-gnuradio   # salta GNU Radio (se ce l'hai già)
```

Preferisci un semplice script di shell? `install_telive2.sh` fa lo stesso, in
modo autonomo (lancialo da utente normale, **non** con sudo). È portabile fra
**Ubuntu 24.04 (x86)** e **25.10 (ARM64)** — rileva da solo i flag del
compilatore necessari a compilare i vecchi sorgenti C di SQ5BPF su GCC 15:

```bash
bash install_telive2.sh
```

Clona e compila `osmo-tetra-sq5bpf-2` (il ricevitore `tetra-rx` con la crypto
TEA1/2/3 **reale** e il flag `-k keyfile`), scarica e patcha il **codec vocale
ETSI** (`cdecoder`/`sdecoder`, con lo stesso trucco dello User-Agent «da
browser» usato da `install_linux.py`, così il `403 Forbidden` di ETSI non si
presenta), compila `telive` e prepara la cartella di lavoro `/tetra` più il
flowgraph GNU Radio incluso. Le istruzioni d'uso (ricevitore → telive →
riproduzione) vengono stampate alla fine.

**Come si fornisce la chiave nota** — si passa un keyfile al ricevitore
(`./tetra-rx -r -k <keyfile> -s`; `receiver1udp` lo fa già). Una riga per
chiave, ad esempio:

```
network mcc 0123 mnc 1337 ksg_type 1 security_class 2
key mcc 0123 mnc 1337 addr 00000000 key_type 1  key_num 0 key 11111111111111111111
# chiave TEA-1 accorciata a 32 bit (padding a 80 bit): key_type 16
key mcc 0123 mnc 1337 addr 00000000 key_type 16 key_num 0 key 12345678000000000000
```

> ℹ️ **Perché non il caricatore chiavi di TetraEar?** La GUI di TetraEar *ha*
> un pulsante «🔑 Load Keys» e un loader di keyfile, ma i suoi TEA1–4 in
> `core/crypto.py` sono implementazioni **segnaposto semplificate** (lo dicono
> i suoi stessi docstring: gli algoritmi reali sono proprietari), quindi lì
> una chiave reale non decifra correttamente il traffico reale. Il percorso a
> chiave nota **funzionante** è `tetra-rx -k` di TELIVE-2.

> ⚠️ **Decifrare ≠ craccare.** Questi strumenti decifrano solo con chiave
> **già nota**: nessuno di essi recupera una chiave. Usa solo dove consentito
> dalla legge (vedi [DISCLAIMER](DISCLAIMER.md)).

**Su Windows** la catena TELIVE-2 gira tramite **WSL2** (Ubuntu dentro
Windows), perché è profondamente POSIX (`libosmocore`, GNU Radio, script di
shell, la cartella fissa `/tetra`) e non ha una build Windows nativa
affidabile. L'installer complementare rileva WSL ed esegue al suo interno lo
*stesso* installer Linux:

```bat
python install_telive2_windows.py              REM rileva WSL e compila dentro Ubuntu
python install_telive2_windows.py --check      REM verifica solo lo stato WSL / build
python install_telive2_windows.py --guide-only REM stampa solo i passi per abilitare WSL
```

Se WSL non è ancora attivo, stampa la configurazione iniziale (`wsl --install
-d Ubuntu`, riavvio, creazione utente) e poi lo rilanci. La GUI di GNU Radio
compare automaticamente via WSLg su Windows 11 (su Windows 10 serve un server X).

---

### 📶 TETRA Network Scanner — pannello passivo di rete

Ispirato all'articolo *"Interception of TETRA radio"*, la cui funzione
distintiva (nel plugin per SDR#) è un **pannello passivo dei metadati di rete**
trasmessi nel broadcast TETRA. TetraEar decodifica la voce/testo ma **non**
mostra quei campi; questo strumento complementare li aggiunge leggendo l'output
del ricevitore TELIVE-2 (`tetra-rx`, compilato da `install_telive2.py`).

Mostra in tempo reale: **MCC / MNC / MNI**, **Location Area**, **Colour Code**,
modo operativo, **portante principale** (+ celle vicine viste), lo stato
**🔓/🔐 Air Interface Encryption (AIE)**, la **Security Class**, il **Cipher Key
ID / tipo TEA**, il flag **autenticazione richiesta sulla cella**, più un
**calcolatore della lunghezza d'antenna** (il consiglio sull'ANT-500 citato
nell'articolo). Usa gli stessi token `KEY:VALUE` (`MCC:`,
`MNC:`, `LA:`, `CCODE:`, `CRYPT:`, `ENC:`…) che analizza `telive`, così resta
robusto.

**Due modi per vederlo:**

- **Dentro la GUI di TetraEar** — l'installer principale (`install_linux.py` /
  `install_windows.py`) aggiunge un set di tab alla finestra di TetraEar,
  accanto a *Decoded Frames · Calls · … · Statistics*:
  - **📶 Network Info** — il pannello passivo dei metadati (MCC/MNC/LA/Colour
    Code/AIE/Security Class/…); scegli la sorgente (default: il log del
    ricevitore) e premi **▶ Avvia**.
  - **🔓 Decrypt (TELIVE-2)** — stato della catena, editor del keyfile (inclusa
    la chiave TEA-1 a 32 bit) e pulsanti per avviare GNU Radio → ricevitore →
    telive e aprire la cartella della voce decifrata. Solo a chiave nota,
    nessun cracking.
  - **📡 Decoders** — avvia multimon-ng (POCSAG), dump1090 (ADS-B + mappa web) e
    dsd-fme (DMR/P25) con le frequenze documentate.
  - **📻 Antenna/Freq** — calcolatore della lunghezza d'antenna + un piano
    frequenze TETRA i cui preset **sintonizzano TetraEar** con un clic.
  - **📚 Reference** — TETRA vs TETRA2, le suite TEA/TAA, le cinque CVE
    TETRA:BURST e tutti i link delle fonti.

  Le azioni del toolkit (sintonia, avvio di una catena/decoder) compaiono anche
  nel pannello **Status** in alto dell'app (una riga "🧰 Toolkit"). Già
  installato? Ottieni i tab rilanciando `python3 install_linux.py --repair` (su
  Windows rilancia l'installer). Ogni tab è avvolto in un `try/except`, quindi
  non può mai impedire l'avvio dell'app.
- **Come tool standalone** (`tetra_netscanner.py` / `avvia_netscanner.sh`),
  documentato qui sotto — è il motore condiviso che il tab della GUI riusa.

> ⚠️ **Una sola chiavetta per volta.** I dati *live* del tab arrivano dal
> ricevitore TELIVE-2, che ha bisogno della chiavetta: non può girare nello
> stesso istante della cattura interna di TetraEar su un'unica chiavetta. La
> sorgente predefinita *Log file* (segue `logs/receiver.log`) è ciò che li fa
> convivere: avvia la catena TELIVE-2 (o usa una seconda chiavetta) e osserva
> il tab.

> ✅ Viene **preparato in automatico** alla fine di `install_telive2.py` (per
> saltarlo: `--no-netscanner`). Puoi comunque collegarlo da solo — non compila
> nulla di pesante, è Python puro:
>
> ```bash
> python3 install_tetra_netscanner.py            # verifica + crea il launcher
> python3 install_tetra_netscanner.py --check    # controlla soltanto cosa c'è
> ```

Uso:

```bash
# Automatico: segue logs/receiver.log se presente (convive con telive), altrimenti avvia il ricevitore
./avvia_netscanner.sh 392.225
# Avvia direttamente il ricevitore:
python3 tetra_netscanner.py --run -f 392.225
# Convivi con una sessione telive già attiva (segue il suo log del ricevitore):
python3 tetra_netscanner.py --attach-file logs/receiver.log --follow
# Senza chiavetta:
python3 tetra_netscanner.py --antenna 392.225     # calcolo della lunghezza d'antenna
python3 tetra_netscanner.py --self-test           # prova il parser
```

**Su Windows** il pannello *live* gira dentro **WSL2**, esattamente come la
catena TELIVE-2: `install_telive2_windows.py` compila `tetra-rx` in WSL e ci
collega il pannello in automatico. Crea inoltre sull'host Windows un launcher
nativo **`Avvia NetScanner.bat`** (doppio clic, o passagli una frequenza) che
avvia il pannello live via WSL, oppure mostra il calcolo antenna offline se WSL
non c'è. Le funzioni senza chiavetta girano anche su Windows nativo:

```bat
python install_tetra_netscanner_windows.py        REM verifica + crea il launcher .bat
python tetra_netscanner.py --antenna 392.225       REM calcolo antenna (senza hardware)
python tetra_netscanner.py --self-test             REM prova il parser
```

> ⚠️ **Passivo e in sola lettura.** Il pannello si limita a *mostrare* i metadati
> di broadcast e se la cifratura è attiva — **non decifra nulla e non recupera
> chiavi** (la decifratura a chiave nota resta compito di TELIVE-2). Mostra
> valori reali solo dove il ricevitore li decodifica davvero, su un canale con
> segnale sufficiente. Usa solo dove consentito dalla legge (vedi
> [DISCLAIMER](DISCLAIMER.md)).

---

### 🪟 Windows

Testato su **Windows 10** e **Windows 11** (64 bit).

> ✅ **Per default TetraEar ora si installa e si avvia DENTRO WSL2** (Ubuntu in
> Windows), esattamente come la catena TELIVE-2. Così **l'intera suite — l'app,
> tutti e cinque i tab, TELIVE-2 e i decoder extra — gira in un unico ambiente
> Linux e funziona come su Ubuntu**; la finestra Qt appare via WSLg (Windows 11)
> o un server X (Windows 10). `install_windows.bat` rileva WSL, esegue dentro di
> esso `install_linux.py` e crea un launcher **`Avvia TetraEar (WSL).vbs`** sul
> Desktop.
>
> - Se WSL non è ancora configurato, l'installer stampa i passi una-tantum
>   (`wsl --install -d Ubuntu`, riavvio) e lo rilanci.
> - Per usare la **chiavetta RTL-SDR dentro WSL** la attacchi una volta per
>   sessione con **usbipd-win** (`winget install usbipd`, poi
>   `usbipd bind/attach --wsl`) — l'installer stampa i comandi esatti. Le
>   funzioni senza hardware (antenna, Reference, editor keyfile) funzionano
>   comunque.
> - Preferisci la **vecchia build nativa Windows**? Esegui
>   `install_windows.bat --native` (in modalità nativa i tab Decrypt/Decoders
>   potrebbero non vedere i tool installati in WSL).

**1. Scarica gli installer**

Con **Git per Windows** la via più semplice è clonare la repository (Prompt
dei comandi o PowerShell):

```bat
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
```

Senza Git: apri <https://github.com/chiaraberti13/TetraEarUbuntu>, premi
**Code → Download ZIP**, estrai e apri la cartella. In entrambi i casi ti
servono `install_windows.bat` e `install_windows.py` nella stessa cartella.

**2. Installazione**

**Fai doppio clic su `install_windows.bat`.**

- Windows chiederà di **consentire le modifiche** (permessi di
  amministratore): accetta.
- Se Python non è installato, l'installer lo installa tramite `winget`.
  Quando te lo chiede, **chiudi la finestra e rifai doppio clic** su
  `install_windows.bat`: alla seconda esecuzione trova Python nel PATH e
  prosegue.
- Il `.bat` avvia poi `install_windows.py`, che installa **Git** e **MSYS2**
  (il compilatore C per il codec), scarica TetraEar, crea l'ambiente,
  installa i pacchetti Python e compila il codec.
- Alla fine prepara **in automatico** anche i **decoder aggiuntivi**
  (`install_extra_decoders_windows.py`): scarica la build Windows ufficiale di
  **dsd-fme** e stampa i passi guidati per **dump1090** e **multimon-ng** (che
  su Windows non hanno un binario ufficiale unico). Usa `--no-extra` per
  saltarli. Tutti i log finiscono in `logs/`.

**3. RTL-SDR su Windows (un passaggio, una volta sola)**

`rtlsdr.dll` (con `libusb`) viene **installata automaticamente** dall'installer:
non devi più scaricarla a mano. Resta manuale solo il driver, **una volta sola**:

- **Driver WinUSB con Zadig** — scarica [Zadig](https://zadig.akeo.ie/),
  collega la chiavetta, poi *Options → List All Devices*, seleziona
  **"Bulk-In, Interface (Interface 0)"** (o "RTL2832U"), scegli il driver
  **WinUSB** e premi *Replace Driver*.

**4. Avvia TetraEar**

**Senza terminale:** fai doppio clic su **`Avvia TetraEar.vbs`** — l'installer
lo crea nella cartella `TetraEar` e ne mette una copia sul **Desktop**. Avvia
l'app senza finestra del terminale.

Oppure dal **Prompt dei comandi**, nella cartella `TetraEar` creata
dall'installer:

```bat
cd TetraEar
.venv\Scripts\activate
python -m tetraear -f 392.225
```

**5. Comandi utili**

| Comando | Cosa fa |
| --- | --- |
| doppio clic su `install_windows.bat` | Installazione completa |
| `python install_windows.py --repair` | Ricompila solo il codec vocale + riapplica le correzioni |
| `python install_windows.py --uninstall` | Rimuove `.venv` e il codec (lascia il sorgente) |
| `python install_windows.py --check` | Verifica l'installazione (venv, codec, rtlsdr.dll) senza modificare nulla |
| `python install_windows.py --ref <commit\|tag\|branch>` | Installa una versione specifica di TetraEar |

> ℹ️ **Installazioni riproducibili.** Come su Linux: TetraEar è fissato a una
> release nota e testata (attualmente `v2.3`), il commit installato è
> registrato in `TetraEar\.tetraear_version`, e il download del codec ETSI ha
> un fallback su archive.org ed è verificato con MD5. Usa `--ref` o la
> variabile d'ambiente `TETRAEAR_REF` per installare una versione diversa.

**6. Problemi comuni (Windows)**

- **"winget non disponibile"**: aggiorna *Programma di installazione app* dal
  Microsoft Store, oppure installa Python, Git e MSYS2 a mano e rilancia
  `install_windows.py`.
- **MSYS2 installato ma non trovato**: riavvia e rilancia l'installer.
- **Il codec non compila**: esegui `python install_windows.py --repair`; se
  persiste, controlla `logs/install.log`.
- **All'avvio: `undefined symbol: rtlsdr_set_dithering`**: stessa soluzione di
  Linux — l'installer applica la patch a `pyrtlsdr`. Rilancia l'installer (o
  `--repair`).
- **Non decodifica nulla, log pieni di `'CaptureThread' object has no attribute
  'signal_processor'`**: stesso bug a monte di Linux — l'installer corregge in
  automatico il sorgente di TetraEar. Rilancia l'installer (o `--repair`).
- **Ad ogni decodifica compare/lampeggia una finestra nera**: il launcher senza
  console (`pythonw`) fa aprire una finestra a ogni chiamata del codec
  (`cdecoder.exe`/`sdecoder.exe`), una per frame. L'installer ora corregge
  `voice.py` per eseguire il codec nascosto (`CREATE_NO_WINDOW`). Rilancia
  l'installer (o `python install_windows.py --repair`) per applicare la modifica.
- **La voce è a scatti / si decodifica solo in parte su una macchina lenta**:
  ogni frame vocale esegue il codec ETSI (`cdecoder.exe`/`sdecoder.exe`) come
  processo esterno. Su un sistema carico o "a freddo" — tipicamente alle prime
  chiamate, mentre Windows Defender analizza il codec appena compilato —
  l'esecuzione può superare il timeout per-frame del codec, così i frame
  altrimenti decodificabili vengono scartati. L'installer alza il timeout
  predefinito da 5 s a 15 s; puoi regolarlo con la variabile d'ambiente
  `TETRAEAR_CODEC_TIMEOUT` (in secondi). Rilancia l'installer (o
  `python install_windows.py --repair`) per applicare la patch. Dipende dal
  progetto a monte e dal tuo segnale, non dall'installer.

---

### In caso di problemi (entrambi i sistemi)

1. Apri (o allega) **`logs/install.log`** (nella cartella `logs/`): contiene
   la cronologia completa e i dettagli degli errori, compresi i traceback
   degli errori imprevisti. **È il file da inviare per chiedere supporto.**
2. Usa `--repair` se il problema riguarda solo il codec o la compatibilità
   RTL-SDR.
3. Per ripartire da zero, usa `--uninstall` e poi reinstalla.

---

<p align="center">
  <sub>Usa TetraEar solo nel rispetto delle leggi vigenti · Use TetraEar only in compliance with applicable laws — <a href="DISCLAIMER.md">DISCLAIMER</a></sub>
</p>
