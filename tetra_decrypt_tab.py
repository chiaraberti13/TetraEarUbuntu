"""
tetra_decrypt_tab.py -- Tab "Decrypt (TELIVE-2)" per la GUI di TetraEar (PyQt6)
==============================================================================

Porta dentro la GUI la catena TELIVE-2 (osmo-tetra-sq5bpf-2 + codec ETSI +
telive) che aggiunge a TetraEar la DECIFRATURA vocale a CHIAVE NOTA, inclusa la
chiave TEA-1 accorciata a 32 bit. NON cracca nulla: decifra solo se la chiave e'
GIA' nota. Il tab:

  * mostra lo stato dei componenti (tetra-rx, telive, cdecoder/sdecoder, GNU Radio);
  * permette di modificare il keyfile (network/key, incluso key_type 16 = TEA1 32-bit);
  * lancia in terminale i tre passi della catena (GNU Radio -> ricevitore -> telive);
  * apre la cartella della voce decifrata (/tetra/out).

Viene COPIATO nell'app come tetraear/ui/tetra_decrypt_tab.py dall'installer.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QPlainTextEdit, QLineEdit, QGroupBox, QMessageBox,
)

from tetraear.ui.tetra_gui_common import (
    open_terminal, receiver_launcher, gnuradio_launcher, grc_file,
    telive_dir, keyfile_default, voice_out_dir, find_bin, repo_root,
)

_KEYFILE_TEMPLATE = (
    "# Keyfile TELIVE-2 (tetra-rx -k). Una riga per chiave. La DECIFRATURA\n"
    "# funziona SOLO con chiave GIA' nota: questi strumenti non craccano il TETRA.\n"
    "network mcc 0123 mnc 1337 ksg_type 1 security_class 2\n"
    "key mcc 0123 mnc 1337 addr 00000000 key_type 1  key_num 0 key 11111111111111111111\n"
    "# Chiave TEA-1 accorciata a 32 bit (backdoor Midnight Blue): key_type 16, pad a 80 bit\n"
    "key mcc 0123 mnc 1337 addr 00000000 key_type 16 key_num 0 key 12345678000000000000\n"
)

_TEA1_32_LINE = (
    "key mcc 0123 mnc 1337 addr 00000000 key_type 16 key_num 0 key 12345678000000000000\n"
)


class DecryptTab(QWidget):
    def __init__(self, main_window=None) -> None:
        super().__init__()
        self.main_window = main_window
        self._build_ui()
        self.refresh_status()
        self.load_keyfile()

    # -- UI ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        intro = QLabel(
            "<b>Decifratura vocale a CHIAVE NOTA (TELIVE-2).</b> "
            "Decifra solo se possiedi gia' la chiave — nessun cracking. "
            "Include la chiave TEA-1 accorciata a 32 bit (key_type 16)."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        # --- Stato componenti -------------------------------------------------
        st_box = QGroupBox("Stato catena TELIVE-2")
        st_grid = QGridLayout(st_box)
        self.status_labels = {}
        comps = ["tetra-rx", "telive", "cdecoder", "sdecoder", "gnuradio-companion", "socat"]
        for i, name in enumerate(comps):
            st_grid.addWidget(QLabel(f"<b>{name}</b>"), i // 3, (i % 3) * 2)
            lbl = QLabel("?")
            self.status_labels[name] = lbl
            st_grid.addWidget(lbl, i // 3, (i % 3) * 2 + 1)
        refresh_btn = QPushButton("↻ Ricontrolla")
        refresh_btn.clicked.connect(self.refresh_status)
        st_grid.addWidget(refresh_btn, 2, 0, 1, 2)
        self.install_hint = QLabel("")
        self.install_hint.setWordWrap(True)
        st_grid.addWidget(self.install_hint, 2, 2, 1, 4)
        root.addWidget(st_box)

        # --- Keyfile ---------------------------------------------------------
        kf_box = QGroupBox("Keyfile (chiavi note)")
        kf_layout = QVBoxLayout(kf_box)
        path_row = QHBoxLayout()
        default_kf = keyfile_default()
        self.keyfile_path = QLineEdit(str(default_kf) if default_kf else "sample_keyfile")
        path_row.addWidget(QLabel("File:"))
        path_row.addWidget(self.keyfile_path, 1)
        kf_layout.addLayout(path_row)
        self.keyfile_edit = QPlainTextEdit()
        self.keyfile_edit.setPlaceholderText(_KEYFILE_TEMPLATE)
        kf_layout.addWidget(self.keyfile_edit)
        btn_row = QHBoxLayout()
        load_btn = QPushButton("Carica")
        load_btn.clicked.connect(self.load_keyfile)
        save_btn = QPushButton("Salva")
        save_btn.clicked.connect(self.save_keyfile)
        tea_btn = QPushButton("+ Chiave TEA-1 32-bit")
        tea_btn.clicked.connect(lambda: self.keyfile_edit.appendPlainText(_TEA1_32_LINE.strip()))
        for b in (load_btn, save_btn, tea_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        kf_layout.addLayout(btn_row)
        root.addWidget(kf_box, 1)

        # --- Avvio catena ----------------------------------------------------
        run_box = QGroupBox("Avvio catena (in terminale)")
        run_row = QHBoxLayout(run_box)
        gr_btn = QPushButton("1) GNU Radio")
        gr_btn.clicked.connect(self.launch_gnuradio)
        rx_btn = QPushButton("2) Ricevitore (con keyfile)")
        rx_btn.clicked.connect(self.launch_receiver)
        tl_btn = QPushButton("3) telive")
        tl_btn.clicked.connect(self.launch_telive)
        out_btn = QPushButton("🔊 Voce decifrata (/tetra/out)")
        out_btn.clicked.connect(self.open_voice_dir)
        for b in (gr_btn, rx_btn, tl_btn, out_btn):
            run_row.addWidget(b)
        root.addWidget(run_box)

        warn = QLabel(
            "⚠️ Una sola chiavetta per volta: GNU Radio usa la RTL-SDR, quindi ferma "
            "la cattura di TetraEar prima di avviare la catena. Ordine: 1 → 2 → 3. "
            "Uso consentito solo dove permesso dalla legge (vedi DISCLAIMER)."
        )
        warn.setWordWrap(True)
        root.addWidget(warn)

    # -- Stato ---------------------------------------------------------------
    def refresh_status(self) -> None:
        missing = False
        for name, lbl in self.status_labels.items():
            found = find_bin(name)
            if found:
                lbl.setText("✅")
                lbl.setToolTip(str(found))
            else:
                lbl.setText("❌")
                lbl.setToolTip("non trovato")
                missing = True
        if missing:
            self.install_hint.setText(
                "Manca qualcosa: compila la catena con "
                "<code>python3 install_telive2.py</code> "
                "(su Windows: <code>python install_telive2_windows.py</code>)."
            )
        else:
            self.install_hint.setText("Catena TELIVE-2 pronta.")

    # -- Keyfile -------------------------------------------------------------
    def _keyfile_path(self) -> Path:
        return Path(self.keyfile_path.text().strip() or "sample_keyfile")

    def load_keyfile(self) -> None:
        p = self._keyfile_path()
        try:
            if p.is_file():
                self.keyfile_edit.setPlainText(p.read_text(encoding="utf-8", errors="ignore"))
            else:
                self.keyfile_edit.setPlainText(_KEYFILE_TEMPLATE)
        except OSError as exc:
            self.keyfile_edit.setPlainText(_KEYFILE_TEMPLATE)
            QMessageBox.warning(self, "Keyfile", f"Non ho potuto leggere {p}: {exc}")

    def save_keyfile(self) -> None:
        p = self._keyfile_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(self.keyfile_edit.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "Keyfile", f"Salvato in {p}")
        except OSError as exc:
            QMessageBox.warning(self, "Keyfile", f"Non ho potuto salvare {p}: {exc}")

    # -- Avvio ---------------------------------------------------------------
    def _run(self, command: str, cwd=None) -> None:
        ok, msg = open_terminal(command, cwd=cwd)
        if not ok:
            QMessageBox.information(self, "Avvio", msg)

    def launch_gnuradio(self) -> None:
        launcher = gnuradio_launcher()
        if launcher:
            self._run(f'"{launcher}"', cwd=launcher.parent)
            return
        grc = grc_file()
        if grc:
            self._run(f'gnuradio-companion "{grc}"', cwd=grc.parent)
        else:
            QMessageBox.information(
                self, "GNU Radio",
                "Flowgraph non trovato. Compila la catena: python3 install_telive2.py",
            )

    def launch_receiver(self) -> None:
        launcher = receiver_launcher()
        if not launcher:
            QMessageBox.information(
                self, "Ricevitore",
                "tetra-rx non trovato. Compila la catena: python3 install_telive2.py",
            )
            return
        if launcher.name in ("run_receiver.sh", "receiver1udp"):
            self._run(f'"{launcher}" 1', cwd=launcher.parent)
        else:  # tetra-rx diretto con keyfile
            kf = self._keyfile_path()
            self._run(f'"{launcher}" -r -k "{kf}" -s /dev/stdin', cwd=launcher.parent)

    def launch_telive(self) -> None:
        td = telive_dir()
        telive = find_bin("telive")
        if td and (td / "telive").is_file():
            self._run("./telive", cwd=td)
        elif telive:
            self._run(f'"{telive}"', cwd=telive.parent)
        else:
            QMessageBox.information(
                self, "telive",
                "telive non trovato. Compila la catena: python3 install_telive2.py",
            )

    def open_voice_dir(self) -> None:
        d = voice_out_dir()
        if not d.is_dir():
            QMessageBox.information(
                self, "Voce",
                f"{d} non esiste ancora. I file .out compaiono qui durante le chiamate; "
                "riproducili con: tplay /tetra/out/<file>.out",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))
