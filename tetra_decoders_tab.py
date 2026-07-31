"""
tetra_decoders_tab.py -- Tab "Decoders" per la GUI di TetraEar (PyQt6)
=====================================================================

Porta dentro la GUI i decoder radio OPEN SOURCE aggiuntivi installati da
install_extra_decoders.py (gli stessi modi che coprono programmi chiusi come
OpenEar, ma liberi):

  * multimon-ng -> cercapersone POCSAG / FLEX (FSK/AFSK)
  * dump1090    -> ADS-B 1090 MHz (posizione aerei, mappa web)
  * dsd-fme     -> DMR / P25 / NXDN / dPMR (voce digitale IN CHIARO)

Ogni decoder si avvia in un terminale con il comando documentato nel README.
La voce/dati cifrati non sono decodificabili senza le chiavi, da nessun
software. Viene COPIATO nell'app come tetraear/ui/tetra_decoders_tab.py.
"""

from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QMessageBox,
)

from tetraear.ui.tetra_gui_common import open_terminal, find_bin


class DecodersTab(QWidget):
    def __init__(self, main_window=None) -> None:
        super().__init__()
        self.main_window = main_window
        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        intro = QLabel(
            "<b>Decoder radio aggiuntivi (open source).</b> Una RTL-SDR riceve molti "
            "modi oltre al TETRA. Mostrano traffico solo se sei sulla frequenza giusta, "
            "con segnale sufficiente e <b>in chiaro</b> (il cifrato non si decodifica)."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        # Stato
        st_box = QGroupBox("Stato decoder")
        st = QGridLayout(st_box)
        self.status_labels = {}
        for i, name in enumerate(("multimon-ng", "dump1090", "dsd-fme", "rtl_fm")):
            st.addWidget(QLabel(f"<b>{name}</b>"), 0, i * 2)
            lbl = QLabel("?")
            self.status_labels[name] = lbl
            st.addWidget(lbl, 0, i * 2 + 1)
        btn = QPushButton("↻ Ricontrolla")
        btn.clicked.connect(self.refresh_status)
        st.addWidget(btn, 1, 0, 1, 2)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        st.addWidget(self.hint, 1, 2, 1, 6)
        root.addWidget(st_box)

        # Pager (POCSAG)
        pg = QGroupBox("Cercapersone POCSAG (multimon-ng)")
        pr = QHBoxLayout(pg)
        self.pager_freq = QLineEdit("439.9875")
        self.pager_freq.setMaximumWidth(120)
        pbtn = QPushButton("▶ Avvia")
        pbtn.clicked.connect(self.launch_pager)
        pr.addWidget(QLabel("Frequenza (MHz):"))
        pr.addWidget(self.pager_freq)
        pr.addWidget(pbtn)
        pr.addStretch(1)
        root.addWidget(pg)

        # ADS-B
        ag = QGroupBox("Aerei ADS-B 1090 MHz (dump1090)")
        ar = QHBoxLayout(ag)
        abtn = QPushButton("▶ Avvia")
        abtn.clicked.connect(self.launch_adsb)
        mapbtn = QPushButton("🌍 Mappa web (localhost:8080)")
        mapbtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("http://localhost:8080")))
        ar.addWidget(QLabel("Frequenza fissa 1090 MHz"))
        ar.addWidget(abtn)
        ar.addWidget(mapbtn)
        ar.addStretch(1)
        root.addWidget(ag)

        # DMR/P25
        dg = QGroupBox("Voce digitale DMR / P25 in chiaro (dsd-fme)")
        dr = QHBoxLayout(dg)
        self.dmr_freq = QLineEdit("446.09375")
        self.dmr_freq.setMaximumWidth(120)
        dbtn = QPushButton("▶ Avvia")
        dbtn.clicked.connect(self.launch_dmr)
        dr.addWidget(QLabel("Frequenza (MHz):"))
        dr.addWidget(self.dmr_freq)
        dr.addWidget(dbtn)
        dr.addStretch(1)
        root.addWidget(dg)

        warn = QLabel(
            "⚠️ Usano la RTL-SDR: ferma la cattura di TetraEar prima di avviarli. "
            "Solo dove consentito dalla legge (vedi DISCLAIMER)."
        )
        warn.setWordWrap(True)
        root.addWidget(warn)
        root.addStretch(1)

    def refresh_status(self) -> None:
        missing = False
        for name, lbl in self.status_labels.items():
            if find_bin(name):
                lbl.setText("✅")
            else:
                lbl.setText("❌")
                missing = True
        self.hint.setText(
            "Manca qualcosa: installa con <code>python3 install_extra_decoders.py</code>."
            if missing else "Decoder pronti."
        )

    def _freq(self, edit: QLineEdit) -> str:
        return (edit.text().strip() or "0").replace(",", ".")

    def _run(self, command: str) -> None:
        ok, msg = open_terminal(command)
        if not ok:
            QMessageBox.information(self, "Avvio", msg)

    def launch_pager(self) -> None:
        f = self._freq(self.pager_freq)
        self._run(
            f"rtl_fm -f {f}M -s 22050 -g 42 - | "
            "multimon-ng -t raw -a POCSAG1200 -f alpha /dev/stdin"
        )

    def launch_adsb(self) -> None:
        self._run("dump1090 --interactive --net")

    def launch_dmr(self) -> None:
        f = self._freq(self.dmr_freq)
        self._run(f"rtl_fm -f {f}M -s 48000 -g 42 - | dsd-fme -i - -o /dev/null")
