"""
tetra_reference_tab.py -- Tab "Reference" per la GUI di TetraEar (PyQt6)
=======================================================================

Pannello di sola lettura con il materiale tecnico dell'articolo "Interception
of TETRA radio" e delle fonti collegate: cos'e' il TETRA, confronto TETRA vs
TETRA2, le suite crypto TEA/TAA1, le vulnerabilita' TETRA:BURST (CVE) e i link
di approfondimento. Nessuna azione, nessun dato: solo riferimento.

Viene COPIATO nell'app come tetraear/ui/tetra_reference_tab.py dall'installer.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser


_HTML = """
<h2>TETRA — riferimento rapido</h2>
<p><b>TETRA</b> (TErrestrial Trunked Radio), standard ETSI di meta' anni '90 per
servizi civili (polizia, vigili del fuoco, emergenze, trasporti, M2M). Banda
<b>380–430 MHz</b>, accesso <b>TDMA</b> con <b>4 canali duplex</b> per portante,
spaziatura <b>25 kHz</b>, modulazione <b>&pi;/4-DQPSK</b>. Modalita' di rete (TMO)
e diretta (DMO). Voce+dati fino a 7,2 kbps, dati fino a 36 kbps.</p>

<h3>TETRA vs TETRA2 (TEDS)</h3>
<table border="1" cellspacing="0" cellpadding="4">
<tr><th>Parametro</th><th>TETRA</th><th>TETRA2 (TEDS)</th></tr>
<tr><td>Banda</td><td>~380–430 MHz</td><td>~380–430 MHz</td></tr>
<tr><td>Larghezza canale</td><td>25 kHz</td><td>25 / 50 / 100 / 150 kHz</td></tr>
<tr><td>Accesso</td><td>TDMA, 4 slot/portante</td><td>TDMA, 4 slot/portante</td></tr>
<tr><td>Modulazione</td><td>&pi;/4-DQPSK</td><td>&pi;/4-DQPSK, &pi;/8-D8PSK, 4/16/64-QAM</td></tr>
<tr><td>Data rate RF</td><td>36 kbps (25 kHz)</td><td>fino a 691,2 kbps (64-QAM, 150 kHz)</td></tr>
<tr><td>Voce</td><td>7,2 kbps</td><td>invariata</td></tr>
</table>

<h3>Crypto: suite TEA (Air Interface Encryption)</h3>
<ul>
<li><b>TEA1</b> — uso commerciale, export ristretto. Cifrario a flusso a 80 bit ma
chiave <b>effettiva ridotta a 32 bit</b> (CVE-2022-24402): forzabile in minuti.</li>
<li><b>TEA2</b> — servizi civili/emergenza in Europa.</li>
<li><b>TEA3</b> — paesi extra-europei.</li>
<li><b>TEA4</b> — uso commerciale, export ristretto.</li>
<li><b>TEA5/6/7</b> — introdotti dal 2022 (anche protezione da attacchi quantistici).</li>
</ul>
<p><b>TAA1</b> — suite di autenticazione e distribuzione chiavi (negoziazione di
una chiave privata a 80 bit). Sopra all'AIE puo' esserci <b>E2EE</b>
(cifratura end-to-end).</p>

<h3>TETRA:BURST (Midnight Blue, 2023)</h3>
<ul>
<li><b>CVE-2022-24400</b> — la Derived Cipher Key (DCK) puo' essere posta a 0:
perdita di autenticita' e parziale di riservatezza.</li>
<li><b>CVE-2022-24401</b> — IV dell'AIE basato sul tempo di rete pubblico e non
autenticato: possibili attacchi oracle.</li>
<li><b>CVE-2022-24402</b> — TEA1: chiave 80&nbsp;bit ridotta a 32&nbsp;bit,
forzabile su hardware comune in minuti.</li>
<li><b>CVE-2022-24403</b> — funzione di cifratura dell'identita' debole:
cifratura/decifratura arbitraria di identita'.</li>
<li><b>CVE-2022-24404</b> — mancata autenticazione del ciphertext AIE: attacchi
di malleabilita'.</li>
</ul>
<p><i>Nota: questa suite (TetraEar/TELIVE-2) NON cracca il TETRA. La decifratura
avviene solo con chiave GIA' nota. Usa solo dove consentito dalla legge — vedi
DISCLAIMER.</i></p>

<h3>Approfondimenti (link)</h3>
<ul>
<li><a href="https://allthewriteups.gitbook.io/book/rf-hacking/sigint/interception-of-tetra-radio">Interception of TETRA radio (articolo)</a></li>
<li><a href="https://www.rfwireless-world.com/Terminology/TETRA-vs-TETRA2.html">TETRA vs TETRA2 (RF Wireless World)</a></li>
<li><a href="https://www.cryptomuseum.com/crypto/algo/tea/index.htm">Algoritmi TEA (Crypto Museum)</a></li>
<li><a href="https://www.cryptomuseum.com/crypto/algo/taa/index.htm">Algoritmi TAA (Crypto Museum)</a></li>
<li><a href="https://www.rtl-sdr.com/sdrsharp-plugins/">Plugin SDR# (RTL-SDR.com)</a></li>
<li><a href="https://archive.org/details/SDRSharp_Collection">SDRSharp Collection (Internet Archive)</a></li>
<li><a href="https://www.itu.int/rec/T-REC-E.212/en">ITU-T E.212 (MCC/MNC)</a></li>
<li><a href="https://www.etsi.org/deliver/etsi_en/300300_300399/30039202/03.08.01_60/en_30039202v030801p.pdf">ETSI EN 300 392-2 (Air Interface)</a></li>
<li><a href="https://www.etsi.org/deliver/etsi_en/300300_300399/30039207/03.05.01_60/en_30039207v030501p.pdf">ETSI EN 300 392-7 (Security)</a></li>
<li><a href="https://www.youtube.com/watch?v=1dVJCExTqQ0">Esempio audio TETRA cifrato (YouTube)</a></li>
<li><a href="https://drive.google.com/file/d/1IJsPDXn678yKm8GZs7u0MMTtX95zrPtx/edit">OpenEar 1.70 (Google Drive)</a></li>
<li><a href="https://cs.ru.nl/~cmeijer/publications/All_cops_are_broadcasting_TETRA_under_scrutiny.pdf">All Cops Are Broadcasting (paper Radboud)</a></li>
<li><a href="https://www.midnightblue.nl/research/tetraburst">TETRA:BURST (Midnight Blue)</a></li>
<li><a href="https://github.com/MidnightBlueLabs/TETRA_crypto">MidnightBlueLabs/TETRA_crypto (GitHub)</a></li>
</ul>
"""


class ReferenceTab(QWidget):
    def __init__(self, main_window=None) -> None:
        super().__init__()
        self.main_window = main_window
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(_HTML)
        layout.addWidget(browser)
