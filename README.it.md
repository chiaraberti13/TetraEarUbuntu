<p align="center"><img src="assets/banner.svg" alt="TetraEar" width="100%"></p>

<p align="center"><a href="README.md">🇬🇧 English</a> · <a href="README.it.md">🇮🇹 Italiano</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/status-active-F2C94C?style=flat-square" alt="Active">
  <img src="https://img.shields.io/badge/category-SDR%20%26%20RADIO-22D3EE?style=flat-square" alt="SDR and radio">
  <img src="https://img.shields.io/badge/stack-Python-8B949E?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/licence-MIT-2EA043?style=flat-square" alt="MIT">
</p>

> Ambiente automatizzato per installare e utilizzare TetraEar con dispositivi RTL-SDR su Ubuntu, Debian e Windows.

<p align="center"><a href="docs/manual.it.md"><strong>Manuale completo</strong></a> · <a href="SECURITY.md">Sicurezza</a> · <a href="LICENSE">Licenza</a></p>

---

## Perché esiste

Il progetto riduce a un flusso guidato l’installazione delle dipendenze, del codec vocale ETSI e della configurazione RTL-SDR necessaria per TetraEar.

## Funzionalità principali

- installazione automatizzata e riparazione dell’ambiente;
- supporto Ubuntu/Debian e Windows;
- configurazione RTL-SDR e codec ETSI;
- log diagnostici e procedure di disinstallazione;
- strumenti aggiuntivi di analisi radio documentati nel manuale.

## Avvio rapido

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

## Documentazione

- [Manuale completo in italiano](docs/manual.it.md)
- [Manuale completo in inglese](docs/manual.en.md)
- [Policy di sicurezza](SECURITY.md)
- [Disclaimer](DISCLAIMER.md)

## Uso responsabile

Utilizza il software esclusivamente nel rispetto della normativa applicabile e su segnali, sistemi e dispositivi per i quali possiedi le autorizzazioni necessarie.
