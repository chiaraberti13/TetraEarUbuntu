# Guida all'uso — TetraEar e decoder aggiuntivi

Guida pratica: quale file lanciare, e come usare ogni decoder con la chiavetta
RTL-SDR. Per l'installazione dettagliata vedi il [README](README.md); per gli
aspetti legali vedi il [DISCLAIMER](DISCLAIMER.md).

> ⚠️ **Usa questi strumenti solo dove consentito dalle leggi della tua
> giurisdizione.** Ascoltare certe comunicazioni può essere illegale nel tuo
> Paese anche se tecnicamente possibile.

---

## 1. Prima cosa: capire i vari file `install_*`

Ogni installer fa **un solo lavoro**. Si dividono per **scopo × sistema**:

| File | Cosa installa | Sistema |
| --- | --- | --- |
| `install_linux.py` | **TetraEar** (decoder TETRA) | Linux |
| `install_windows.py` | **TetraEar** (decoder TETRA) | Windows |
| `install_extra_decoders.py` | **decoder extra** (DMR/P25, ADS-B, cercapersone) | Linux |
| `install_extra_decoders_windows.py` | **decoder extra** | Windows |

Non sono doppioni: TetraEar decodifica **solo il TETRA**; gli "extra decoders"
coprono **altri modi radio**. Installa quello che ti serve.

> 💡 Una regola sola non basta per "sentire tutto": ogni modo radio (TETRA,
> DMR, ADS-B, cercapersone) usa frequenze e formati diversi, quindi serve il
> decoder giusto per ciascuno.

---

## 2. La verità sul "funziona al 100%"

Non manca nessuna libreria: gli installer mettono tutto il necessario. I limiti
sono **fisici e crittografici**, non di software:

- 🔐 **Cifratura.** Molte reti (TETRA TEA1–4, DMR/P25 con chiavi) cifrano la
  voce. **Senza la chiave non è decodificabile da nessun software.** La vedi
  come traffico presente ma muto.
- 📻 **Frequenza giusta e chiamata reale.** Un portante continuo di solito è un
  *canale di controllo*: la voce compare solo durante una chiamata vera.
- 📶 **Segnale.** Guadagno/antenna insufficienti → poca sincronizzazione →
  frame persi.

Quindi il "100%" si raggiunge sul traffico **in chiaro**, sulla frequenza
giusta, con buon segnale.

---

## 3. TETRA — con TetraEar

**Linux**

```bash
cd ~/TetraEarUbuntu/TetraEar
source .venv/bin/activate
python -m tetraear -f 392.225          # sostituisci con la tua frequenza in MHz
```

**Windows**

```bat
cd TetraEar
.venv\Scripts\activate
python -m tetraear -f 392.225
```

Oppure doppio clic su **`Avvia TetraEar.vbs`** (Windows) o sull'icona
**TetraEar** (Linux).

**Se la tabella dei frame è vuota:** metti **Filter = All** e togli la spunta a
**"Decrypted/Text Only"**. Se poi i frame compaiono tutti con 🔐, il traffico è
cifrato (contatore chiavi `0/0` = nessuna chiave) e la voce non è recuperabile.

---

## 4. Decoder aggiuntivi

Prima di tutto: la chiavetta va **libera dai driver DVB-T** (su Linux
l'installer lo fa; su Windows serve il driver **WinUSB** installato una volta
con [Zadig](https://zadig.akeo.ie/)).

Su Linux i comandi usano `rtl_fm` (incluso nel pacchetto `rtl-sdr`) che manda
l'audio "in pipe" al decoder. Cambia **frequenza** (`-f`) e **guadagno** (`-g`)
in base alla tua zona.

### 4.1 DMR / P25 / NXDN / dPMR — `dsd-fme`

Voce digitale professionale/amatoriale **in chiaro**.

**Linux**
```bash
rtl_fm -f 446.09375M -s 48000 -g 42 - | dsd-fme -i - -o /dev/null
```

**Windows** — usa l'eseguibile scaricato in `decoders\dsd-fme\`:
```bat
rtl_fm -f 446.09375M -s 48000 -g 42 - | dsd-fme.exe -i - -o NUL
```

> `dsd-fme` mostra a schermo tipo di rete, talkgroup e ID. Le chiamate cifrate
> restano mute (te lo segnala).

### 4.2 ADS-B (aerei) — `dump1090`

Posizione, quota e codice degli aerei a **1090 MHz** (frequenza fissa).

**Linux / Windows**
```bash
dump1090 --interactive --net
```
Poi apri il browser su **http://localhost:8080** per la mappa. Non serve
antenna speciale: anche quella in dotazione vede gli aerei vicini.

### 4.3 Cercapersone POCSAG / FLEX — `multimon-ng`

Messaggi di testo dei sistemi di paging (dove ancora in uso e consentito).

**Linux**
```bash
rtl_fm -f 439.9875M -s 22050 -g 42 - | \
  multimon-ng -t raw -a POCSAG512 -a POCSAG1200 -a POCSAG2400 -f alpha /dev/stdin
```

**Windows** (multimon-ng compilato con MSYS2, vedi README) oppure il programma
**PDW**:
```bat
rtl_fm -f 439.9875M -s 22050 -g 42 - | multimon-ng.exe -t raw -a POCSAG1200 -f alpha -
```

---

## 5. Come trovare le frequenze giuste

I comandi sopra usano frequenze **di esempio**: non è detto che nella tua zona
ci sia traffico lì. Per trovare le frequenze attive:

- Un database pubblico come [RadioReference](https://www.radioreference.com/) o
  siti/forum locali.
- Uno **spettro** (es. l'app `gqrx` su Linux, o SDR#/SDR++ su Windows) per
  "vedere" dove c'è portante e capire il modo.

---

## 6. Riepilogo comandi di verifica

| Vuoi sapere se… | Comando |
| --- | --- |
| TetraEar è installato bene | `python3 install_linux.py --check` |
| i decoder extra ci sono (Linux) | `python3 install_extra_decoders.py --check` |
| i decoder extra ci sono (Windows) | `python install_extra_decoders_windows.py --check` |
| la chiavetta è vista (Linux) | `rtl_test -t` |

---

<p align="center"><sub>Usa questi strumenti solo nel rispetto delle leggi vigenti — vedi <a href="DISCLAIMER.md">DISCLAIMER</a>.</sub></p>
