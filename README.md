# Guida all'installazione di TetraEar

Questa guida ti accompagna passo passo nell'installazione **automatica** di
[TetraEar](https://github.com/syrex1013/TetraEar) — un decoder TETRA per
chiavette RTL-SDR — **prima su Ubuntu/Debian, poi su Windows**.

Gli installer sono pensati per essere avviati con un solo comando (o un
doppio clic su Windows): scaricano da soli il codice di TetraEar,
installano tutte le dipendenze di sistema e Python, e compilano il codec
vocale. Non serve fare `git clone` a mano.

> **Prima di iniziare, leggi il [Disclaimer legale](DISCLAIMER.md).**
> L'uso di questo software è consentito solo per scopi didattici e di
> ricerca e nel rispetto delle leggi locali.

---

## Cosa ti serve (entrambi i sistemi)

- Una connessione a Internet.
- Una chiavetta **RTL-SDR** (chip RTL2832U) con la sua antenna — necessaria
  solo al momento di *usare* TetraEar, non per installarlo.
- I permessi di amministratore (su Ubuntu ti verrà chiesta la password
  `sudo`; su Windows la finestra si eleva da sola).

Cosa fanno gli installer, in sintesi:

1. controllano Python e il sistema operativo;
2. installano le dipendenze di sistema (compilatore, librerie RTL-SDR, Qt, audio);
3. scaricano il codice sorgente di TetraEar;
4. creano un ambiente virtuale Python (`.venv`) e installano i pacchetti `pip`;
5. **configurano la chiavetta RTL-SDR** (su Linux in automatico: blacklist del
   driver DVB-T, regole udev, permessi utente — vedi sotto);
6. scaricano e compilano il codec vocale ETSI TETRA;
7. verificano che tutto sia a posto.

## Il file di log `install.log` (leggimi)

Ogni cosa che accade durante l'installazione — **ogni comando, ogni output e
ogni errore, anche quelli imprevisti con il traceback completo** — viene
salvato nel file **`install.log`**, creato nella stessa cartella
dell'installer.

Se qualcosa va storto:

- **Non serve copiare la schermata**: apri (o allega) direttamente `install.log`.
- Il file è in modalità "aggiunta": conserva anche i tentativi precedenti, così
  la cronologia non si perde tra un `--repair` e l'altro.
- Per trovarlo: è accanto a `install_linux.py` / `install_windows.py`. Se hai
  lanciato l'installer da `~/tetraear-setup`, sarà `~/tetraear-setup/install.log`.

Puoi prendere quel file e sottopormelo così com'è: contiene tutto il necessario
per diagnosticare il problema.

```bash
# Linux: vedere le ultime righe / gli errori
tail -n 50 install.log
grep -i -E "errore|error|fallit|traceback" install.log
```

---

# Parte 1 — Ubuntu / Debian

Testato su **Ubuntu 24.04** e **Debian 12** (dovrebbe funzionare anche su
derivate recenti come Linux Mint e Pop!_OS).

## 1.1 Scarica l'installer

Ti basta il file `install_linux.py`. Puoi ottenerlo così:

```bash
# opzione A: scarica solo l'installer in una cartella nuova
mkdir -p ~/tetraear-setup && cd ~/tetraear-setup
wget https://raw.githubusercontent.com/chiaraberti13/TetraEarUbuntu/main/install_linux.py

# opzione B: se hai già clonato questa repo, entra nella sua cartella
cd /percorso/della/repo
```

## 1.2 Avvia l'installazione

```bash
python3 install_linux.py
```

Durante l'esecuzione ti verrà chiesta la password di `sudo` (serve per
installare i pacchetti di sistema con `apt`). Il processo può richiedere
diversi minuti: sta scaricando pacchetti e compilando il codec.

Al termine vedrai un messaggio di riepilogo. L'installer crea, accanto a sé,
una cartella `TetraEar/` con il codice sorgente, l'ambiente virtuale `.venv`
e il codec compilato.

### La chiavetta RTL-SDR su Linux è configurata in automatico

Su Ubuntu/Debian non devi fare nulla a mano: l'installer si occupa già di
tutto quello che serve per **usare davvero** la chiavetta (chip RTL2832U):

- mette in **blacklist** i driver DVB-T del kernel (`dvb_usb_rtl28xxu` ecc.)
  che altrimenti "occupano" la chiavetta e impediscono l'uso come SDR;
- installa/ricarica le **regole udev** per accedere al dongle senza `sudo`;
- aggiunge il tuo utente al gruppo **`plugdev`**.

> ⚠️ **Passaggio finale obbligatorio**: dopo l'installazione **scollega e
> ricollega** la chiavetta (oppure riavvia). Serve perché la blacklist del
> driver e le nuove regole udev abbiano effetto. Se avevi già collegato la
> chiavetta prima di lanciare l'installer, questo passaggio è indispensabile.

Verifica che il sistema la veda (senza sudo):

```bash
rtl_test -t
```

Se compare l'elenco del dispositivo (es. "Found 1 device(s)") sei a posto. Se
dice "usb_claim_interface error -6" significa che il driver DVB-T è ancora
caricato: scollega/ricollega la chiavetta o riavvia.

## 1.3 Avvia TetraEar

```bash
cd TetraEar
source .venv/bin/activate
python -m tetraear -f 392.225          # interfaccia grafica
# oppure, senza GUI:
python -m tetraear --no-gui -f 392.225 --auto-start
```

(sostituisci `392.225` con la frequenza in MHz che ti interessa).

## 1.4 Comandi utili

| Comando | Cosa fa |
| --- | --- |
| `python3 install_linux.py` | Installazione completa |
| `python3 install_linux.py --repair` | Ricompila **solo** il codec vocale |
| `python3 install_linux.py --uninstall` | Rimuove `.venv` e il codec (lascia il codice sorgente) |

## 1.5 Problemi comuni su Linux

- **La GUI non parte, errore "could not load the Qt platform plugin xcb"**:
  l'installer già installa le librerie Qt necessarie; se persiste, assicurati
  di essere in una sessione grafica (non solo SSH senza display).
- **La chiavetta RTL-SDR non viene rilevata / `usb_claim_interface error -6`**:
  è il driver DVB-T ancora caricato. Scollega e ricollega la chiavetta (o
  riavvia) — l'installer ha già messo il driver in blacklist, ma serve un
  ricollegamento perché il kernel lo rilasci. Poi riprova con `rtl_test -t`.
  In casi ostinati: `sudo modprobe -r dvb_usb_rtl28xxu` e ricollega.
- **`rtl_test` chiede i permessi / funziona solo con sudo**: fai
  logout/login una volta (serve ad attivare l'appartenenza al gruppo
  `plugdev` aggiunta dall'installer).
- **Il download del codec da ETSI fallisce**: riprova più tardi (a volte il
  sito ETSI è temporaneamente irraggiungibile), poi esegui
  `python3 install_linux.py --repair`.
- **All'avvio: `undefined symbol: rtlsdr_set_dithering`**: è un'incompatibilità
  tra `pyrtlsdr` e la `librtlsdr` di sistema (la versione di Ubuntu non ha
  quella funzione). L'installer la risolve compilando il fork **rtl-sdr-blog**;
  se hai aggiornato lo script, rilancia `python3 install_linux.py` (o
  `--repair`). Dopo, chiudi e riapri il terminale. Non dipende dalla chiavetta:
  l'errore compare all'`import`, prima di usare l'hardware.

---

# Parte 2 — Windows

Testato su **Windows 10** e **Windows 11** (64 bit).

## 2.1 Scarica l'installer

Ti servono due file, nella stessa cartella:

- `install_windows.bat`
- `install_windows.py`

Scaricali entrambi (per esempio nella cartella `Download`) dalla repo:
<https://github.com/chiaraberti13/TetraEarUbuntu>.

## 2.2 Avvia l'installazione

**Fai doppio clic su `install_windows.bat`.**

- Windows ti chiederà di **consentire le modifiche** (permessi di
  amministratore): accetta.
- Se Python non è installato, l'installer lo scarica e lo installa da solo
  (tramite `winget`). In questo caso, quando te lo chiede, **chiudi la
  finestra e rifai doppio clic** su `install_windows.bat`: alla seconda
  esecuzione troverà Python nel PATH e proseguirà.
- Il `.bat` avvia poi `install_windows.py`, che installa **Git** e **MSYS2**
  (il compilatore C serve per il codec vocale), scarica TetraEar, crea
  l'ambiente virtuale, installa i pacchetti Python e compila il codec.

Il processo può richiedere parecchi minuti (MSYS2 e la toolchain sono
diversi centinaia di MB). Al termine vedrai il messaggio di riepilogo.

## 2.3 RTL-SDR su Windows (passaggio semi-manuale)

A differenza di Linux, su Windows la chiavetta RTL-SDR ha bisogno di due
passaggi che vanno fatti a mano **una volta sola**:

1. **Driver WinUSB con Zadig**
   - Scarica Zadig da <https://zadig.akeo.ie/> e avvialo.
   - Collega la chiavetta RTL-SDR.
   - In Zadig: menu *Options → List All Devices*, seleziona **"Bulk-In,
     Interface (Interface 0)"** (o "RTL2832U"), scegli il driver **WinUSB**
     e premi *Replace Driver*.
2. **Libreria `rtlsdr.dll`**
   - Scarica i binari Windows di `librtlsdr` (ad es. dai rilasci di
     [librtlsdr / rtl-sdr per Windows](https://github.com/librtlsdr/librtlsdr/releases)).
   - Copia `rtlsdr.dll` (e le DLL di `libusb` incluse) nella cartella
     `TetraEar` creata dall'installer, oppure in una cartella presente nel
     `PATH` di sistema.

> Senza questi due passaggi TetraEar si avvia comunque, ma non riesce a
> comunicare con la chiavetta.

## 2.4 Avvia TetraEar

Apri il **Prompt dei comandi** nella cartella `TetraEar` creata
dall'installer:

```bat
cd TetraEar
.venv\Scripts\activate
python -m tetraear -f 392.225
```

## 2.5 Comandi utili

| Comando | Cosa fa |
| --- | --- |
| doppio clic su `install_windows.bat` | Installazione completa |
| `python install_windows.py --repair` | Ricompila **solo** il codec vocale |
| `python install_windows.py --uninstall` | Rimuove `.venv` e il codec |

## 2.6 Problemi comuni su Windows

- **"winget non è disponibile"**: aggiorna l'app *Programma di installazione
  app* dal Microsoft Store, oppure installa Python, Git e MSYS2 a mano e
  rilancia `install_windows.py`.
- **MSYS2 installato ma non trovato**: riavvia il PC e rilancia l'installer.
- **Il codec non si compila**: esegui `python install_windows.py --repair`;
  se il problema persiste, controlla `install.log`.
- **La GUI non parte**: assicurati che l'installazione dei pacchetti `pip`
  (in particolare PyQt6) sia andata a buon fine — lo vedi in `install.log`.

---

## In caso di problemi (entrambi i sistemi)

1. Apri (o allega) il file **`install.log`** creato accanto all'installer:
   contiene la cronologia completa, i messaggi di errore dettagliati e anche
   il traceback degli errori imprevisti. **È il file da inviare per chiedere
   supporto** — da solo basta a capire cos'è andato storto.
2. Riprova con l'opzione `--repair` se il problema riguarda solo il codec.
3. Se serve ripartire da zero, usa `--uninstall` e poi reinstalla.

---

Ricorda: usa TetraEar **solo** nel rispetto delle leggi vigenti e per
scopi consentiti. Vedi il [Disclaimer legale](DISCLAIMER.md).
