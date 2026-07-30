"""
network_info_tab.py -- Tab "Network Info" per la GUI di TetraEar (PyQt6)
=======================================================================

NON fa parte del pacchetto originale di TetraEar: viene COPIATO dentro l'app
scaricata (in tetraear/ui/network_info_tab.py) dall'installer
(install_linux.py / install_windows.py), che inietta anche una riga in
tetraear/ui/modern.py per aggiungere il tab alla finestra principale.

Il tab mostra, in modo PASSIVO, i parametri di rete trasmessi in chiaro nel
broadcast TETRA (MCC/MNC/MNI, Location Area, Colour Code, modo operativo,
portante principale + celle vicine, stato AIE, Security Class, Cipher Key ID,
autenticazione richiesta) piu' il calcolo della lunghezza d'antenna -- gli
stessi campi del pannello descritto nell'articolo "Interception of TETRA
radio". NON decifra nulla e NON recupera chiavi.

I dati arrivano dal ricevitore osmo-tetra 'tetra-rx' della catena TELIVE-2
(che decodifica il SYSINFO): il tab legge le sue righe da un log
(logs/receiver.log, default), dal ricevitore avviato direttamente, o da UDP.
Il parsing riusa esattamente lo stesso motore del tool standalone
tetra_netscanner.py, qui importato come tetra_netinfo_backend.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

# Motore di parsing condiviso col tool standalone (copiato accanto a questo
# file dall'installer). Import assoluto, come il resto del pacchetto tetraear.
from tetraear.ui.tetra_netinfo_backend import (
    NetInfoParser, antenna_length, _find_receiver,
)


# ============================================================
# THREAD DI LETTURA (una sorgente -> parser -> snapshot)
# ============================================================

def _snapshot(info) -> dict:
    """Copia 'piatta' dello stato, sicura da passare al thread GUI."""
    cells = []
    for (la, cc, dl), cell in list(info.cells.items()):
        cells.append((la, cc, dl, getattr(cell, "ul_freq_hz", None)))
    return {
        "mcc": info.mcc, "mnc": info.mnc, "mni": info.mni,
        "location_area": info.location_area, "colour_code": info.colour_code,
        "operating_mode": info.operating_mode,
        "main_carrier_hz": info.main_carrier_hz, "ul_carrier_hz": info.ul_carrier_hz,
        "aie_enabled": info.aie_enabled,
        "tea_label": info.tea_label(),
        "security_class_label": info.security_class_label(),
        "cipher_key_id": info.cipher_key_id,
        "authentication_required": info.authentication_required,
        "total_messages": info.total_messages,
        "encrypted_events": info.encrypted_events, "clear_events": info.clear_events,
        "last_ssi": info.last_ssi,
        "cells": cells,
    }


class NetInfoReader(QThread):
    """Legge le righe della sorgente scelta, le da' in pasto a NetInfoParser
    ed emette periodicamente uno snapshot. Fermabile in modo pulito."""

    updated = pyqtSignal(object)     # dict snapshot
    failed = pyqtSignal(str)
    info_msg = pyqtSignal(str)

    def __init__(self, kind: str, arg: str, parent=None) -> None:
        super().__init__(parent)
        self.kind = kind            # "file" | "receiver" | "udp"
        self.arg = arg
        self._running = True
        self._proc = None

    def stop(self) -> None:
        self._running = False
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass

    # -- sorgenti ------------------------------------------------------------
    def _iter_file(self):
        path = Path(self.arg)
        if not path.is_file():
            self.failed.emit(f"File non trovato: {path}")
            return
        self.info_msg.emit(f"Seguo {path}")
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(0, os.SEEK_END)
            while self._running:
                line = f.readline()
                if line:
                    yield line
                else:
                    self.msleep(200)

    def _iter_receiver(self):
        receiver = _find_receiver(self.arg or None)
        if receiver is None:
            self.failed.emit(
                "Ricevitore 'tetra-rx' non trovato. Compila la catena TELIVE-2 "
                "(python3 install_telive2.py) oppure indica il percorso."
            )
            return
        cmd = [str(receiver)]
        if receiver.name in ("run_receiver.sh", "receiver1udp"):
            cmd.append("1")
        self.info_msg.emit("Avvio ricevitore: " + " ".join(cmd))
        try:
            self._proc = subprocess.Popen(
                cmd, cwd=str(receiver.parent),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
        except OSError as exc:
            self.failed.emit(f"Impossibile avviare il ricevitore: {exc}")
            return
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if not self._running:
                break
            yield line

    def _iter_udp(self):
        try:
            port = int(self.arg)
        except (ValueError, TypeError):
            self.failed.emit(f"Porta UDP non valida: {self.arg}")
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as exc:
            self.failed.emit(f"Impossibile ascoltare su UDP {port}: {exc}")
            return
        sock.settimeout(0.5)
        self.info_msg.emit(f"In ascolto su UDP :{port}")
        while self._running:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            for line in data.decode("utf-8", errors="ignore").splitlines():
                yield line
        sock.close()

    # -- loop principale -----------------------------------------------------
    def run(self) -> None:
        sources = {"file": self._iter_file, "receiver": self._iter_receiver, "udp": self._iter_udp}
        it = sources.get(self.kind, self._iter_file)()
        parser = NetInfoParser()
        last_emit = 0.0
        try:
            for line in it:
                parser.feed_line(line)
                now = time.time()
                if now - last_emit >= 0.5:
                    last_emit = now
                    self.updated.emit(_snapshot(parser.info))
        except Exception as exc:  # difensivo: mai far crashare la GUI
            self.failed.emit(f"Errore di lettura: {exc}")
        finally:
            self.updated.emit(_snapshot(parser.info))
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                except OSError:
                    pass


# ============================================================
# IL TAB
# ============================================================

def _fmt(v) -> str:
    return "-" if v is None else str(v)


def _fmt_hz(hz) -> str:
    return "-" if not hz else f"{hz/1e6:.4f} MHz"


def _fmt_bool(v) -> str:
    return "-" if v is None else ("si'" if v else "no")


class NetworkInfoTab(QWidget):
    """Pannello passivo dei metadati di rete TETRA (SYSINFO), via TELIVE-2."""

    def __init__(self, main_window=None) -> None:
        super().__init__()
        self.main_window = main_window
        self.reader = None
        self._default_log = self._guess_receiver_log()
        self._build_ui()

    # -- costruzione UI ------------------------------------------------------
    def _guess_receiver_log(self) -> str:
        """Percorso probabile del log del ricevitore (scritto dalla catena
        TELIVE-2). Cerca in posizioni note accanto all'app/installer."""
        candidates = []
        try:
            here = Path(__file__).resolve()
            # .../TetraEar/tetraear/ui/network_info_tab.py -> risali fino a TetraEar
            for up in (here.parents[2], here.parents[3] if len(here.parents) > 3 else here.parents[2]):
                candidates.append(up / "logs" / "receiver.log")
        except Exception:
            pass
        candidates.append(Path.home() / "TetraEarUbuntu" / "logs" / "receiver.log")
        for c in candidates:
            if c.is_file():
                return str(c)
        return str(candidates[0]) if candidates else "logs/receiver.log"

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- Barra sorgente ---------------------------------------------------
        src_box = QGroupBox("Sorgente dati (ricevitore TELIVE-2 tetra-rx)")
        src_row = QHBoxLayout(src_box)
        self.source_combo = QComboBox()
        self.source_combo.addItems([
            "Log file (receiver.log)",
            "Ricevitore (live, usa la chiavetta)",
            "UDP (messaggi TETMON)",
        ])
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.arg_edit = QLineEdit(self._default_log)
        self.start_btn = QPushButton("▶ Avvia")
        self.start_btn.clicked.connect(self._toggle)
        src_row.addWidget(QLabel("Modo:"))
        src_row.addWidget(self.source_combo)
        src_row.addWidget(self.arg_edit, 1)
        src_row.addWidget(self.start_btn)
        root.addWidget(src_box)

        # --- Griglia identita' + sicurezza -----------------------------------
        grid_box = QGroupBox("Parametri di rete (broadcast, in chiaro)")
        grid = QGridLayout(grid_box)
        self.labels = {}

        def add(col, row, key, caption):
            grid.addWidget(QLabel(f"<b>{caption}</b>"), row, col * 2)
            lbl = QLabel("-")
            self.labels[key] = lbl
            grid.addWidget(lbl, row, col * 2 + 1)

        add(0, 0, "mni", "MCC / MNC (MNI)")
        add(1, 0, "location_area", "Location Area")
        add(0, 1, "colour_code", "Colour Code")
        add(1, 1, "operating_mode", "Operating mode")
        add(0, 2, "main_carrier", "Main carrier")
        add(1, 2, "ul_carrier", "Uplink")
        add(0, 3, "security_class_label", "Security class")
        add(1, 3, "cipher_key_id", "Cipher Key ID")
        add(0, 4, "tea_label", "Algoritmo (TEA)")
        add(1, 4, "authentication_required", "Auth. su cella")
        root.addWidget(grid_box)

        # --- Indicatore cifratura (AIE) --------------------------------------
        self.aie_label = QLabel("AIE: ?")
        self.aie_label.setStyleSheet("font-size:16px; font-weight:bold; padding:6px;")
        root.addWidget(self.aie_label)

        # --- Celle vicine -----------------------------------------------------
        cells_box = QGroupBox("Celle osservate (corrente + vicine)")
        cells_layout = QVBoxLayout(cells_box)
        self.cells_table = QTableWidget(0, 4)
        self.cells_table.setHorizontalHeaderLabels(["Location Area", "Colour Code", "Downlink", "Uplink"])
        try:
            self.cells_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        except Exception:
            pass
        self.cells_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        cells_layout.addWidget(self.cells_table)
        root.addWidget(cells_box, 1)

        # --- Antenna ----------------------------------------------------------
        ant_box = QGroupBox("Calcolatore antenna (come nell'articolo)")
        ant_row = QHBoxLayout(ant_box)
        self.ant_edit = QLineEdit("392.225")
        self.ant_edit.setMaximumWidth(120)
        ant_btn = QPushButton("Calcola")
        ant_btn.clicked.connect(self._calc_antenna)
        self.ant_label = QLabel("-")
        ant_row.addWidget(QLabel("Frequenza (MHz):"))
        ant_row.addWidget(self.ant_edit)
        ant_row.addWidget(ant_btn)
        ant_row.addWidget(self.ant_label, 1)
        root.addWidget(ant_box)
        self._calc_antenna()

        # --- Stato ------------------------------------------------------------
        self.status_label = QLabel(
            "Passivo / sola lettura: mostra i metadati e se c'e' cifratura, "
            "non decifra nulla. Avvia una sorgente per popolare i campi."
        )
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self._on_source_changed(0)

    # -- interazioni ---------------------------------------------------------
    def _on_source_changed(self, idx: int) -> None:
        if idx == 0:
            self.arg_edit.setText(self._default_log)
            self.arg_edit.setToolTip("Percorso del log del ricevitore (receiver.log)")
        elif idx == 1:
            self.arg_edit.setText("")
            self.arg_edit.setToolTip("Percorso del ricevitore (vuoto = autorileva). "
                                     "ATTENZIONE: usa la chiavetta, ferma la cattura di TetraEar.")
        else:
            self.arg_edit.setText("7379")
            self.arg_edit.setToolTip("Porta UDP dei messaggi TETMON")

    def _toggle(self) -> None:
        if self.reader is not None and self.reader.isRunning():
            self.stop_reader()
        else:
            self.start_reader()

    def start_reader(self) -> None:
        kind = {0: "file", 1: "receiver", 2: "udp"}.get(self.source_combo.currentIndex(), "file")
        arg = self.arg_edit.text().strip()
        self.reader = NetInfoReader(kind, arg)
        self.reader.updated.connect(self._on_updated)
        self.reader.failed.connect(self._on_failed)
        self.reader.info_msg.connect(lambda m: self.status_label.setText(m))
        self.reader.finished.connect(self._on_finished)
        self.reader.start()
        self.start_btn.setText("■ Ferma")

    def stop_reader(self) -> None:
        if self.reader is not None:
            self.reader.stop()
            self.reader.wait(3000)
        self.start_btn.setText("▶ Avvia")

    def _on_finished(self) -> None:
        self.start_btn.setText("▶ Avvia")

    def _on_failed(self, msg: str) -> None:
        self.status_label.setText("[errore] " + msg)
        self.start_btn.setText("▶ Avvia")

    def _calc_antenna(self) -> None:
        try:
            freq = float(self.ant_edit.text().strip())
            a = antenna_length(freq)
            self.ant_label.setText(
                f"lambda/4 pratico ~= {a['quarter_wave_practical_mm']/10:.1f} cm "
                f"({a['quarter_wave_practical_mm']:.0f} mm) - ANT-500 ~{a['ant500_segments']} segmenti"
            )
        except (ValueError, Exception) as exc:  # noqa: B014
            self.ant_label.setText(f"(frequenza non valida: {exc})")

    # -- aggiornamento display ----------------------------------------------
    def _on_updated(self, snap: dict) -> None:
        L = self.labels
        L["mni"].setText(f"{_fmt(snap['mcc'])} / {_fmt(snap['mnc'])}   (MNI {_fmt(snap['mni'])})")
        L["location_area"].setText(_fmt(snap["location_area"]))
        L["colour_code"].setText(_fmt(snap["colour_code"]))
        L["operating_mode"].setText(_fmt(snap["operating_mode"]))
        L["main_carrier"].setText(_fmt_hz(snap["main_carrier_hz"]))
        L["ul_carrier"].setText(_fmt_hz(snap["ul_carrier_hz"]))
        L["security_class_label"].setText(snap["security_class_label"])
        L["cipher_key_id"].setText(_fmt(snap["cipher_key_id"]))
        L["tea_label"].setText(snap["tea_label"])
        L["authentication_required"].setText(_fmt_bool(snap["authentication_required"]))

        aie = snap["aie_enabled"]
        if aie is True:
            self.aie_label.setText("\U0001f512 ENCRYPTED (AIE attiva)")
            self.aie_label.setStyleSheet("font-size:16px; font-weight:bold; padding:6px; color:#e05555;")
        elif aie is False:
            self.aie_label.setText("\U0001f513 CLEAR (nessuna AIE)")
            self.aie_label.setStyleSheet("font-size:16px; font-weight:bold; padding:6px; color:#4caf50;")
        else:
            self.aie_label.setText("AIE: ?")
            self.aie_label.setStyleSheet("font-size:16px; font-weight:bold; padding:6px;")

        cells = snap["cells"]
        self.cells_table.setRowCount(len(cells))
        for r, (la, cc, dl, ul) in enumerate(cells):
            self.cells_table.setItem(r, 0, QTableWidgetItem(_fmt(la)))
            self.cells_table.setItem(r, 1, QTableWidgetItem(_fmt(cc)))
            self.cells_table.setItem(r, 2, QTableWidgetItem(_fmt_hz(dl)))
            self.cells_table.setItem(r, 3, QTableWidgetItem(_fmt_hz(ul)))

        self.status_label.setText(
            f"Messaggi: {snap['total_messages']}  "
            f"(cifrati {snap['encrypted_events']} / chiari {snap['clear_events']})   "
            f"ultimo SSI: {_fmt(snap['last_ssi'])}   -   passivo, nessuna decifratura"
        )

    # -- pulizia -------------------------------------------------------------
    def closeEvent(self, event):  # noqa: N802 (override Qt)
        self.stop_reader()
        super().closeEvent(event)
