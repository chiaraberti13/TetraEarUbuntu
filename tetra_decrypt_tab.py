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
    QPlainTextEdit, QLineEdit, QGroupBox, QMessageBox, QCheckBox,
)

from tetraear.ui.tetra_gui_common import (
    open_terminal, receiver_launcher, gnuradio_launcher, grc_file,
    telive_dir, keyfile_default, voice_out_dir, find_bin, repo_root,
    set_app_status, shell_quote, validate_keyfile_text, mask_keyfile_text,
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
        # Le chiavi sono mascherate di default; il testo reale vive in _real_text.
        self._real_text = ""
        self._revealed = False
        self.keyfile_edit = QPlainTextEdit()
        self.keyfile_edit.setPlaceholderText(_KEYFILE_TEMPLATE)
        kf_layout.addWidget(self.keyfile_edit)
        btn_row = QHBoxLayout()
        self.reveal_check = QCheckBox("👁 Mostra/Modifica chiavi")
        self.reveal_check.toggled.connect(self._toggle_reveal)
        load_btn = QPushButton("Carica")
        load_btn.clicked.connect(self.load_keyfile)
        save_btn = QPushButton("Salva")
        save_btn.clicked.connect(self.save_keyfile)
        tea_btn = QPushButton("+ Chiave TEA-1 32-bit")
        tea_btn.clicked.connect(self._add_tea1_key)
        btn_row.addWidget(self.reveal_check)
        for b in (load_btn, save_btn, tea_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        kf_layout.addLayout(btn_row)
        root.addWidget(kf_box, 1)

        # --- Avvio catena ----------------------------------------------------
        run_box = QGroupBox("Avvio catena (in terminale)")
        run_row = QHBoxLayout(run_box)
        self.gr_btn = QPushButton("1) GNU Radio")
        self.gr_btn.clicked.connect(self.launch_gnuradio)
        self.rx_btn = QPushButton("2) Ricevitore (con keyfile)")
        self.rx_btn.clicked.connect(self.launch_receiver)
        self.tl_btn = QPushButton("3) telive")
        self.tl_btn.clicked.connect(self.launch_telive)
        out_btn = QPushButton("🔊 Voce decifrata (/tetra/out)")
        out_btn.clicked.connect(self.open_voice_dir)
        for b in (self.gr_btn, self.rx_btn, self.tl_btn, out_btn):
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
        missing = []
        for name, lbl in self.status_labels.items():
            found = find_bin(name)
            if found:
                lbl.setText("✅")
                lbl.setToolTip(str(found))
            else:
                lbl.setText("❌")
                lbl.setToolTip("non trovato")
                missing.append(name)

        # Abilita i pulsanti solo se il relativo componente c'e' (diagnostica).
        gr_ok = bool(gnuradio_launcher() or grc_file() or find_bin("gnuradio-companion"))
        rx_ok = receiver_launcher() is not None
        tl_ok = bool((telive_dir() and (telive_dir() / "telive").is_file()) or find_bin("telive"))
        self._gate(self.gr_btn, gr_ok, "GNU Radio", "gnuradio-companion / flowgraph")
        self._gate(self.rx_btn, rx_ok, "Ricevitore", "tetra-rx / receiver1udp")
        self._gate(self.tl_btn, tl_ok, "telive", "telive")

        if missing:
            self.install_hint.setText(
                "Mancano: <b>" + ", ".join(missing) + "</b>. Compila la catena con "
                "<code>python3 install_telive2.py</code> "
                "(su Windows: <code>python install_telive2_windows.py</code>)."
            )
        else:
            self.install_hint.setText("Catena TELIVE-2 pronta.")

    @staticmethod
    def _gate(btn, ok: bool, label: str, needs: str) -> None:
        btn.setEnabled(ok)
        btn.setToolTip("" if ok else f"{label} non disponibile: manca {needs}. Esegui install_telive2.py")

    # -- Keyfile -------------------------------------------------------------
    def _keyfile_path(self) -> Path:
        return Path(self.keyfile_path.text().strip() or "sample_keyfile")

    # -- masking chiavi ------------------------------------------------------
    def _render_keyfile(self) -> None:
        """Mostra il testo reale (se rivelato, editabile) o mascherato (read-only)."""
        if self._revealed:
            self.keyfile_edit.setReadOnly(False)
            self.keyfile_edit.setPlainText(self._real_text)
        else:
            self.keyfile_edit.setReadOnly(True)
            self.keyfile_edit.setPlainText(mask_keyfile_text(self._real_text))

    def _sync_real(self) -> None:
        """Se l'editor e' in modalita' modifica, aggiorna il testo reale."""
        if self._revealed:
            self._real_text = self.keyfile_edit.toPlainText()

    def _toggle_reveal(self, checked: bool) -> None:
        if not checked:
            self._sync_real()  # salva le modifiche prima di rimascherare
        self._revealed = checked
        self._render_keyfile()

    def _add_tea1_key(self) -> None:
        self._sync_real()
        if self._real_text and not self._real_text.endswith("\n"):
            self._real_text += "\n"
        self._real_text += _TEA1_32_LINE.strip() + "\n"
        # Rivela per far vedere cosa e' stato aggiunto.
        self.reveal_check.setChecked(True)
        self._revealed = True
        self._render_keyfile()

    def load_keyfile(self) -> None:
        p = self._keyfile_path()
        try:
            if p.is_file():
                self._real_text = p.read_text(encoding="utf-8", errors="ignore")
            else:
                self._real_text = _KEYFILE_TEMPLATE
        except OSError as exc:
            self._real_text = _KEYFILE_TEMPLATE
            QMessageBox.warning(self, "Keyfile", f"Non ho potuto leggere {p}: {exc}")
        self._render_keyfile()

    def save_keyfile(self) -> None:
        p = self._keyfile_path()
        self._sync_real()
        text = self._real_text
        ok, msg = validate_keyfile_text(text)
        if not ok:
            reply = QMessageBox.question(
                self, "Keyfile — possibili problemi",
                f"Il keyfile sembra malformato:\n{msg}\n\nSalvare comunque?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            QMessageBox.information(self, "Keyfile", f"Salvato in {p}")
        except OSError as exc:
            QMessageBox.warning(self, "Keyfile", f"Non ho potuto salvare {p}: {exc}")

    # -- Avvio ---------------------------------------------------------------
    def _run(self, command: str, cwd=None) -> None:
        ok, msg = open_terminal(command, cwd=cwd)
        set_app_status(self.main_window, "TELIVE-2: " + msg)
        if not ok:
            QMessageBox.information(self, "Avvio", msg)

    def launch_gnuradio(self) -> None:
        launcher = gnuradio_launcher()
        if launcher:
            self._run(shell_quote(launcher), cwd=launcher.parent)
            return
        grc = grc_file()
        if grc:
            self._run(f"gnuradio-companion {shell_quote(grc)}", cwd=grc.parent)
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
            self._run(f"{shell_quote(launcher)} 1", cwd=launcher.parent)
        else:  # tetra-rx diretto con keyfile
            kf = self._keyfile_path()
            if not kf.is_file():
                QMessageBox.warning(
                    self, "Keyfile",
                    f"Il keyfile non esiste o non e' un file regolare:\n{kf}\n"
                    "Salvalo prima con il pulsante 'Salva'.",
                )
                return
            self._run(
                f"{shell_quote(launcher)} -r -k {shell_quote(kf)} -s /dev/stdin",
                cwd=launcher.parent,
            )

    def launch_telive(self) -> None:
        td = telive_dir()
        telive = find_bin("telive")
        if td and (td / "telive").is_file():
            self._run("./telive", cwd=td)
        elif telive:
            self._run(shell_quote(telive), cwd=telive.parent)
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
