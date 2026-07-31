#!/usr/bin/env python3
"""
test_toolkit.py -- test a logica pura del toolkit TETRA (senza PyQt6/hardware)
=============================================================================

Verifica le parti testabili senza GUI ne' chiavetta:
  * validate_frequency_mhz  -> rifiuta injection / fuori range, accetta MHz validi
  * validate_keyfile_text   -> forma minima del keyfile TELIVE-2
  * NetInfoParser           -> parsing dei messaggi TETMON di esempio

Uso:  python3 test_toolkit.py   (exit 0 = tutto OK)

I moduli GUI (tab PyQt6) NON sono importabili qui perche' richiedono PyQt6; per
questo i validatori vivono in tetra_gui_common.py (solo stdlib) ed e' quello che
i tab riusano.
"""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_FAILS = []


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # serve a dataclasses per risolvere le annotazioni
    spec.loader.exec_module(mod)
    return mod


def check(cond, label):
    print(f"  [{'OK' if cond else 'FAIL'}] {label}")
    if not cond:
        _FAILS.append(label)


def test_frequency(gc):
    print("validate_frequency_mhz:")
    bad = ["", "abc", "433; rm -rf ~", "433 | nc x", "$(id)", "`id`", "1e999",
           "nan", "10", "23.9", "2000", "43 3", "0x1a", "--", ";reboot"]
    for b in bad:
        ok, _, _ = gc.validate_frequency_mhz(b)
        check(not ok, f"rifiuta {b!r}")
    good = [("392.225", 392.225), ("1090", 1090.0), ("446,09375", 446.09375),
            ("24", 24.0), ("1766", 1766.0), (" 415.0 ", 415.0)]
    for text, val in good:
        ok, v, _ = gc.validate_frequency_mhz(text)
        check(ok and v is not None and abs(v - val) < 1e-6, f"accetta {text!r} -> {val}")


def test_keyfile(gc):
    print("validate_keyfile_text:")
    valid = (
        "# commento\n"
        "network mcc 0123 mnc 1337 ksg_type 1 security_class 2\n"
        "key mcc 0123 mnc 1337 addr 00000000 key_type 16 key_num 0 key 12345678000000000000\n"
    )
    ok, _ = gc.validate_keyfile_text(valid)
    check(ok, "keyfile valido accettato")
    for bad in ("riga spazzatura", "network mcc 1", "key mcc 1 mnc 1 addr 0 key_type 1"):
        ok, _ = gc.validate_keyfile_text(bad)
        check(not ok, f"keyfile non valido rifiutato: {bad!r}")


def test_parser(ns):
    print("NetInfoParser (fixture):")
    p = ns.NetInfoParser()
    p.feed(ns._FIXTURE_LINES)
    info = p.info
    check(info.mcc == 222, "MCC=222")
    check(info.mnc == 1, "MNC=1")
    check(info.location_area == 1234, "LA=1234")
    check(info.colour_code == 12, "ColourCode=12")
    check(info.main_carrier_hz == 392_225_000, "MainCarrier=392.225MHz")
    check(info.aie_enabled is True, "AIE on")
    check(info.security_class == 3, "SecurityClass=3")
    check(info.authentication_required is True, "AuthRequired on")


def main():
    gc = _load("tetra_gui_common")
    ns = _load("tetra_netscanner")
    test_frequency(gc)
    test_keyfile(gc)
    test_parser(ns)
    print()
    if _FAILS:
        print(f"RESULT: FAIL ({len(_FAILS)} check falliti)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
