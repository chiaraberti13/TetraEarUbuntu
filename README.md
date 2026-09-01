<p align="center"><img src="assets/banner.svg" alt="TetraEar" width="100%"></p>

<p align="center"><a href="README.md">🇬🇧 English</a> · <a href="README.it.md">🇮🇹 Italiano</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/status-active-F2C94C?style=flat-square" alt="Active">
  <img src="https://img.shields.io/badge/category-SDR%20%26%20RADIO-22D3EE?style=flat-square" alt="SDR and radio">
  <img src="https://img.shields.io/badge/stack-Python-8B949E?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/licence-MIT-2EA043?style=flat-square" alt="MIT">
</p>

> An automated environment for installing and running TetraEar with RTL-SDR devices on Ubuntu, Debian and Windows.

<p align="center"><a href="docs/manual.en.md"><strong>Complete guide</strong></a> · <a href="SECURITY.md">Security</a> · <a href="LICENSE">Licence</a></p>

---

## Why this project exists

The project turns the installation of system dependencies, the ETSI voice codec and RTL-SDR configuration required by TetraEar into a guided workflow.

## Key features

- automated installation and environment repair;
- Ubuntu/Debian and Windows support;
- RTL-SDR and ETSI codec configuration;
- diagnostic logs and uninstall procedures;
- additional radio-analysis tools documented in the guide.

## Quick start

### Ubuntu / Debian

```bash
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
chmod +x install_ubuntu.sh
./install_ubuntu.sh
```

### Windows

```powershell
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
python install_windows.py
```

## Documentation

- [Complete English guide](docs/manual.en.md)
- [Guida completa in italiano](docs/manual.it.md)
- [Security policy](SECURITY.md)
- [Disclaimer](DISCLAIMER.md)

## Responsible use

Use the software only in compliance with applicable law and with signals, systems and devices for which you hold the necessary authorization.
