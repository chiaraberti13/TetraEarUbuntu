"""
tetra_antenna_tab.py -- Tab "Antenna & Frequenze" per la GUI di TetraEar (PyQt6)
===============================================================================

Riunisce in un tab:
  * il calcolatore della lunghezza d'antenna (come nell'articolo: ANT-500 sui
    390 MHz) -- lambda intera / mezz'onda / quarto d'onda + stima segmenti;
  * un piano delle frequenze TETRA (banda 380-430 MHz) con pulsante per
    SINTONIZZARE direttamente TetraEar sulla frequenza scelta;
  * un promemoria delle frequenze usate dagli altri decoder (POCSAG/ADS-B/DMR).

Viene COPIATO nell'app come tetraear/ui/tetra_antenna_tab.py dall'installer.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)

from tetraear.ui.tetra_netinfo_backend import antenna_length
from tetraear.ui.tetra_gui_common import tune_main_window, set_app_status

# Piano frequenze TETRA (indicativo): (MHz, descrizione).
_TETRA_PRESETS = [
    (390.000, "TETRA — comune in EU"),
    (392.225, "Esempio articolo / README"),
    (395.000, "TETRA — banda bassa"),
    (410.000, "TETRA — uso commerciale/PMR"),
    (415.000, "TETRA — uso commerciale/PMR"),
    (425.000, "TETRA — uso commerciale/PMR"),
]

# Frequenze tipiche degli altri decoder (tab Decoders).
_OTHER_PRESETS = [
    ("POCSAG (cercapersone)", "439.9875 MHz", "multimon-ng"),
    ("ADS-B (aerei)", "1090 MHz", "dump1090"),
    ("DMR / P25 (voce chiara)", "446.09375 MHz", "dsd-fme"),
]


class AntennaTab(QWidget):
    def __init__(self, main_window=None) -> None:
        super().__init__()
        self.main_window = main_window
        self._build_ui()
        self._calc()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- Calcolatore antenna --------------------------------------------
        ant_box = QGroupBox("Calcolatore antenna")
        ant_l = QVBoxLayout(ant_box)
        row = QHBoxLayout()
        self.freq_edit = QLineEdit("392.225")
        self.freq_edit.setMaximumWidth(140)
        self.freq_edit.returnPressed.connect(self._calc)
        calc_btn = QPushButton("Calcola")
        calc_btn.clicked.connect(self._calc)
        tune_btn = QPushButton("📡 Sintonizza TetraEar")
        tune_btn.clicked.connect(lambda: self._tune(self.freq_edit.text()))
        row.addWidget(QLabel("Frequenza (MHz):"))
        row.addWidget(self.freq_edit)
        row.addWidget(calc_btn)
        row.addWidget(tune_btn)
        row.addStretch(1)
        ant_l.addLayout(row)

        self.result_grid = QGridLayout()
        self.res = {}
        for i, (key, cap) in enumerate((
            ("wave", "Lunghezza d'onda (λ)"),
            ("half", "Mezz'onda (λ/2)"),
            ("quarter", "Quarto d'onda (λ/4)"),
            ("stub", "Stilo consigliato (~0.95)"),
            ("ant500", "ANT-500 (segmenti)"),
        )):
            self.result_grid.addWidget(QLabel(f"<b>{cap}</b>"), i, 0)
            lbl = QLabel("-")
            self.res[key] = lbl
            self.result_grid.addWidget(lbl, i, 1)
        ant_l.addLayout(self.result_grid)
        root.addWidget(ant_box)

        # --- Piano frequenze TETRA ------------------------------------------
        band_box = QGroupBox("Piano frequenze TETRA (380–430 MHz)")
        band_l = QVBoxLayout(band_box)
        self.band_table = QTableWidget(len(_TETRA_PRESETS), 3)
        self.band_table.setHorizontalHeaderLabels(["Frequenza", "Descrizione", ""])
        try:
            self.band_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.band_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.band_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        except Exception:
            pass
        self.band_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for r, (mhz, desc) in enumerate(_TETRA_PRESETS):
            self.band_table.setItem(r, 0, QTableWidgetItem(f"{mhz:.3f} MHz"))
            self.band_table.setItem(r, 1, QTableWidgetItem(desc))
            btn = QPushButton("Sintonizza")
            btn.clicked.connect(lambda _=False, f=mhz: self._tune(f))
            self.band_table.setCellWidget(r, 2, btn)
        band_l.addWidget(self.band_table)
        note = QLabel(
            "Doppio uso: il pulsante <b>Sintonizza</b> imposta la frequenza di "
            "TetraEar e ri-sintonizza. Le frequenze sono indicative: la voce "
            "compare solo durante una chiamata reale, in chiaro."
        )
        note.setWordWrap(True)
        band_l.addWidget(note)
        root.addWidget(band_box, 1)

        # --- Frequenze altri decoder ----------------------------------------
        other_box = QGroupBox("Frequenze tipiche altri decoder (tab Decoders)")
        og = QGridLayout(other_box)
        for r, (name, freq, tool) in enumerate(_OTHER_PRESETS):
            og.addWidget(QLabel(f"<b>{name}</b>"), r, 0)
            og.addWidget(QLabel(freq), r, 1)
            og.addWidget(QLabel(f"<i>{tool}</i>"), r, 2)
        root.addWidget(other_box)

    # -- logica --------------------------------------------------------------
    def _calc(self) -> None:
        try:
            a = antenna_length(float(self.freq_edit.text().strip()))
        except (ValueError, Exception):  # noqa: B014
            for lbl in self.res.values():
                lbl.setText("(frequenza non valida)")
            return
        self.res["wave"].setText(f"{a['wavelength_m']*100:.1f} cm")
        self.res["half"].setText(f"{a['half_wave_m']*100:.1f} cm")
        self.res["quarter"].setText(f"{a['quarter_wave_m']*100:.1f} cm (teorico)")
        self.res["stub"].setText(
            f"{a['quarter_wave_practical_mm']/10:.1f} cm ({a['quarter_wave_practical_mm']:.0f} mm)")
        self.res["ant500"].setText(
            f"~{a['ant500_segments']} segmenti (~{a['ant500_segment_mm']:.0f} mm/seg)")

    def _tune(self, freq) -> None:
        ok, msg = tune_main_window(self.main_window, freq)
        set_app_status(self.main_window, msg)
