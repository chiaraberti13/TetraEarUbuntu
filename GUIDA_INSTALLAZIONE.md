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
5. scaricano e compilano il codec vocale ETSI TETRA;
6. verificano che tutto sia a posto.

Tutto ciò che accade viene registrato nel file **`install.log`**, utile per
il supporto in caso di problemi.

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
- **La chiavetta RTL-SDR non viene rilevata**: scollegala e ricollegala dopo
  l'installazione (le regole udev vengono aggiunte da `apt`), oppure riavvia.
  Verifica con `rtl_test`.
- **Il download del codec da ETSI fallisce**: riprova più tardi (a volte il
  sito ETSI è temporaneamente irraggiungibile), poi esegui
  `python3 install_linux.py --repair`.

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

1. Apri il file **`install.log`** creato accanto all'installer: contiene la
   cronologia completa e i messaggi di errore dettagliati.
2. Riprova con l'opzione `--repair` se il problema riguarda solo il codec.
3. Se serve ripartire da zero, usa `--uninstall` e poi reinstalla.

---

Ricorda: usa TetraEar **solo** nel rispetto delle leggi vigenti e per
scopi consentiti. Vedi il [Disclaimer legale](DISCLAIMER.md).
