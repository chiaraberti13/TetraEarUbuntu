# Roadmap — Installer Linux per TetraEar

Questo file traccia l'obiettivo e i passaggi concreti per portare TetraEar
da "funziona su Windows, rotto su Linux" a "installabile su Ubuntu/Debian
con un solo comando". Tienilo aggiornato man mano che spunti le voci.

## Obiettivo finale

```
git clone https://github.com/syrex1013/TetraEar.git
cd TetraEar
python3 install_linux.py
```

deve, da solo, su una macchina Ubuntu 24.04 o Debian 12 pulita:
- verificare Python e il sistema operativo;
- installare tutte le dipendenze (di sistema e Python);
- compilare e installare il codec vocale ETSI;
- verificare che tutto funzioni;
- dare messaggi chiari a ogni passaggio, non un traceback illeggibile.

---

## Fase 1 — Analisi (completata)

- [ ] Struttura del repository capita (`tetraear/`, `tests/`, `requirements.txt`, ecc.)
- [ ] Dipendenze individuate: pacchetti apt (compilatore, librerie RTL-SDR,
      Qt) + pacchetti Python (`requirements.txt`)
- [ ] Flusso del codec capito: download pacchetto ETSI → estrazione →
      (patch) → compilazione con `make`/`gcc` → binari `cdecoder`/`sdecoder`
      copiati in `tetraear/tetra_codec/bin/`

## Fase 2 — Sviluppo dell'installer (in corso)

- [ ] `install_linux.py` di base creato (vedi file consegnato in questa
      conversazione), che copre:
  - [ ] controllo versione Python e sistema operativo
  - [ ] installazione dipendenze di sistema via `apt`
  - [ ] creazione virtual environment (`.venv`) + `pip install -r requirements.txt`
  - [ ] compilazione codec con `CC=gcc` esplicito (corretto il typo `acc`)
  - [ ] cartella temporanea sicura con `tempfile.mkdtemp()` + pulizia garantita
  - [ ] ricerca file/cartelle case-insensitive (`find_path_ci`)
  - [ ] messaggi di errore con codice di uscita + stderr completo
  - [ ] logging su `install.log`
  - [ ] flag `--repair` (rifà solo il codec, metodo manuale di riserva)
  - [ ] flag `--uninstall` (rimuove venv e codec)
  - [ ] controllo "morbido" della presenza di un dongle RTL-SDR
- [ ] **Da fare:** testare `install_linux.py` su una macchina Ubuntu 24.04
      reale (o VM/container) e correggere quello che emerge
- [ ] **Da fare:** verificare se l'URL del pacchetto ETSI dentro lo script
      è ancora valido; se no, aggiornare la costante `ETSI_CODEC_URL`
- [ ] **Da fare:** verificare che `python -m tetraear.tools.install_tetra_codec`
      esista davvero con quel nome nella versione del progetto che stai
      usando (controllare dentro `tetraear/tools/`)

## Fase 3 — Pulizia del progetto

- [ ] Individuare ed eliminare codice specifico per Windows/MSYS2 non
      necessario quando si gira su Linux (es. riferimenti a `.exe`,
      percorsi con backslash, controlli case-insensitive superflui)
- [ ] Rivedere gli altri script (`continuous_capture.py`, `listen_clear.py`,
      ecc.) per messaggi di errore poco chiari simili a quelli già trovati
      nell'installer
- [ ] Aggiungere/verificare compatibilità esplicita con Debian 12
      (oltre a Ubuntu 24.04)

## Fase 4 — Test finale

- [ ] Installazione da zero su ambiente pulito (VM Ubuntu 24.04 consigliata)
- [ ] Verifica compilazione ed effettivo funzionamento del codec (audio
      udibile su un frame vocale non cifrato)
- [ ] Avvio e verifica dei programmi principali:
  - [ ] `python -m tetraear` (GUI)
  - [ ] `python -m tetraear --no-gui` (CLI)
  - [ ] `listen_clear.py`
  - [ ] `continuous_capture.py`
- [ ] Verifica che `--repair` e `--uninstall` funzionino davvero come
      previsto (provare a rompere volutamente l'installazione e ripararla)

## Consegna finale

- [x] Guida in italiano all'installazione: `GUIDA_INSTALLAZIONE.md`
      (prima Ubuntu/Debian, poi Windows)
- [x] Installer Windows automatizzato: `install_windows.bat`
      (bootstrap che installa Python se manca) + `install_windows.py`
      (winget per Git/MSYS2, clona TetraEar, venv, requirements, codec)
- [x] Installer Linux reso "da zero": ora clona da solo il repo TetraEar
      se non è già presente (non serve più `git clone` manuale)
- [x] Disclaimer ufficiale replicato in `DISCLAIMER.md` e richiamato nella guida
- [ ] `README_LINUX.md` (o sezione dedicata nel README principale) con la
      guida in italiano all'installazione
- [ ] `install.log` di esempio incluso/documentato per chi deve fare
      supporto
- [ ] Archivio ZIP del progetto con l'installer incluso, pronto da
      distribuire
- [ ] (Facoltativo, step successivo — non bloccante) valutare la
      trasformazione in pacchetto Python installabile con `pip install .`

---

## Come continuare da qui

1. Copia `install_linux.py` nella root del repository (se non l'hai già
   fatto).
2. Prova l'installazione su una macchina/VM Ubuntu pulita e annota ogni
   errore in questo file, sotto "Da fare" nella Fase 2/3.
3. Ogni volta che risolvi un problema, sposta la voce corrispondente da
   "Da fare" a completata (spunta `[ ]`) e, se utile, aggiungi una riga
   con la causa e la soluzione (come nella tabella dei 5 problemi già
   documentata in `istruzioni.md`).
4. Quando tutte le voci della Fase 4 sono spuntate, passa alla Consegna
   finale.
