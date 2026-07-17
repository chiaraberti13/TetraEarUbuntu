# Guida all'uso e alle impostazioni

Come **usare e configurare** TetraEar (e cosa ascoltare nella zona di Latina).
L'interfaccia è **identica** su Ubuntu e Windows, quindi qui c'è **una sola
descrizione** valida per entrambi.

> Per **installare** e **avviare** il programma, e per scaricare i decoder
> aggiuntivi, vedi il **[README](README.md)**. Questa guida parte dal
> presupposto che il programma sia già installato e aperto.

> ⚠️ **Nota legale (Italia).** È legale possedere un ricevitore RTL-SDR e
> ascoltare le emissioni **pubbliche** (radio FM/DAB, segnali meteo dei
> satelliti, ADS-B degli aerei, radioamatori). **NON è consentito** ascoltare
> le comunicazioni di polizia, carabinieri, 112/118, forze armate e in
> generale le comunicazioni **non destinate al pubblico** (art. 617 del Codice
> Penale). Quelle reti sono comunque **cifrate** e non decodificabili. Usa
> questi strumenti solo nel rispetto della legge — vedi
> [DISCLAIMER](DISCLAIMER.md).

---

## 1. Come settare il programma (TetraEar)

Quando il programma è aperto vedi tre zone: in alto lo **spettro/waterfall** (la
"cascata" colorata del segnale), al centro la **tabella dei frame** decodificati,
in basso la **barra di stato**. Ecco i controlli che contano.

### a) Frequenza
È l'impostazione principale: dove ti sintonizzi. La imposti nella casella
**Frequency** (in MHz) e premi Invio, oppure la passi all'avvio. Una frequenza
sbagliata = nessun dato: prima verifica che lì ci sia davvero traffico (vedi
§3).

### b) Guadagno (Gain)
È la "sensibilità" del ricevitore. Parti da **Auto**; se il segnale è debole o
la sincronizzazione è bassa, passa a **manuale** e alza il guadagno poco per
volta (es. 30 → 40 dB). Troppo guadagno però "satura" e peggiora: cerca il
punto in cui lo spettro è pulito e la sincronizzazione è più alta.

### c) Avvio/arresto della cattura
Il pulsante **Start/Stop** avvia o ferma la ricezione. Quando è attiva, la
barra di stato mostra qualcosa tipo *"Signal Detected (Decoding…)"*.

### d) I filtri della tabella (il motivo #1 di "non vedo niente")
Se lo stato dice che sta decodificando ma la **tabella è vuota**, quasi sempre
sono i filtri:
- imposta **Filter = All / Tutti**;
- **togli la spunta** a **"Decrypted/Text Only"**.
Altrimenti vedi solo le righe già decifrate. Se poi i frame compaiono ma sono
tutti con il lucchetto 🔐, il traffico è **cifrato**.

### e) Ascolto audio
Attiva il **monitor audio** (l'opzione "monitor"/altoparlante) per sentire la
voce delle chiamate **in chiaro**. Se i frame arrivano ma non senti nulla,
guarda il log del codec (vedi sotto): un codec che funziona scrive
`cdecoder exited 0` / `sdecoder exited 0`.

### f) Dove finiscono i log
Tutti i log (app **e** installazione) sono nella cartella **`logs/`**. Se
qualcosa non va, è lì che guardare (o che mi mandi): `codec_*.log`,
`decoder_*.log`, `audio_*.log`, `tetraear_*.log`.

---

## 2. Perché a volte "non funziona al 100%"

Non manca nessuna libreria: l'installer mette tutto. I limiti sono **fisici e
crittografici**:
- 🔐 **cifratura**: le reti professionali cifrano la voce; senza chiave non è
  decodificabile da **nessun** software;
- 📻 **frequenza**: un portante continuo è spesso un *canale di controllo*, non
  una voce; la voce c'è solo durante una chiamata reale;
- 📶 **segnale**: antenna/guadagno insufficienti → frame persi.

Il "100%" si ottiene sul traffico **in chiaro**, sulla frequenza giusta, con
buon segnale.

---

## 3. Cosa ascoltare nella zona di Latina e provincia

Queste sono emissioni **pubbliche e legali**, ricevibili con una chiavetta
RTL-SDR e l'antenna in dotazione (per alcune serve un'antenna migliore). Le
frequenze "fisse" valgono ovunque, Latina compresa; per quelle **locali** ti
indico dove trovarle, perché cambiano da zona a zona e non vanno inventate.

| Cosa | Frequenza | Programma | Note |
| --- | --- | --- | --- |
| **Aerei (ADS-B)** | **1090 MHz** (fissa) | `dump1090` | Posizione/quota degli aerei su mappa. Latina è sotto le rotte di Roma/Fiumicino-Ciampino: ne vedi molti. |
| **Satelliti meteo NOAA** | 137.100 / 137.620 / 137.9125 MHz | SDR + wxtoimg/satdump | Immagini meteo dai satelliti in transito. Serve antenna adatta (V-dipolo/QFH). |
| **Stazione Spaziale (ISS)** | 145.800 MHz (voce/SSTV) · 145.825 (APRS) | qualsiasi SDR FM | Quando passa sopra di te. |
| **Radioamatori 2 m** | 144–146 MHz (chiamata FM 145.500) | qualsiasi SDR FM | Banda amatoriale, aperta all'ascolto. |
| **Radioamatori 70 cm** | 430–440 MHz | qualsiasi SDR FM | Include ripetitori locali. |
| **PMR446 (walkie-talkie liberi)** | 446.00625–446.19375 MHz (canali 1–16) | qualsiasi SDR FM | Ricetrasmittenti senza licenza. |
| **Radio FM commerciali** | 87.5–108 MHz | qualsiasi SDR WFM | Le emittenti locali di Latina. |
| **DAB+ (radio digitale)** | ~174–230 MHz (Banda III) | welle.io / SDR DAB | Multiplex nazionali/regionali. |

**Frequenze locali (FM, ripetitori radioamatoriali di Latina):** non le elenco a
memoria per non darti numeri sbagliati. Le trovi qui:
- **[RadioReference](https://www.radioreference.com/)** — database mondiale per
  zona.
- **Lista ripetitori ARI** (Associazione Radioamatori Italiani) per il Lazio.
- Un programma a **spettro** (`gqrx` su Linux, **SDR#**/**SDR++** su Windows) per
  "vedere" dove c'è portante e capire il modo prima di puntarci un decoder.

> ❌ **Fuori lista (per legge):** polizia, carabinieri, 112/118, vigili del
> fuoco, forze armate, TETRA SATER. Sono cifrate e l'ascolto è vietato in
> Italia. Non vanno inserite.

---

## 4. I decoder aggiuntivi (cosa fanno)

Insieme a TetraEar l'installer prepara **in automatico** anche questi decoder
per gli altri modi (vedi README per install e dettagli):

| Decoder | Modi | Frequenze tipiche |
| --- | --- | --- |
| **dsd-fme** | DMR / P25 / NXDN / dPMR (voce digitale **in chiaro**) | 430–440 MHz (amatoriale), 446 MHz |
| **dump1090** | ADS-B aerei | 1090 MHz |
| **multimon-ng** | POCSAG/FLEX (cercapersone) e altri FSK | dove ancora in uso e consentito |

I comandi d'uso pratici di ciascuno sono nel **[README](README.md)** (sezione
"decoder aggiuntivi").

---

<p align="center"><sub>Ascolta solo emissioni pubbliche e nel rispetto della legge — vedi <a href="DISCLAIMER.md">DISCLAIMER</a>.</sub></p>
