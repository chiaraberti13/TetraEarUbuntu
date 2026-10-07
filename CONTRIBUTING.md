# Contributing to TetraEarUbuntu

<p align="center"><a href="#english">🇬🇧 English</a> · <a href="#italiano">🇮🇹 Italiano</a></p>

## English
This repository covers automation for installing and running TetraEar with RTL-SDR devices across Ubuntu/Debian and Windows.

### Workflow
1. Read `README.md`, `SECURITY.md` and relevant upstream/project documentation.
2. Search existing issues, use a dedicated branch and keep pull requests focused.
3. Never commit secrets, private captures, personal data, device identifiers or unauthorized material.
4. Use only devices, systems and signals you are legally entitled and explicitly authorized to work with.
5. Report vulnerabilities privately.

### Setup
```bash
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git\ncd TetraEarUbuntu
```

### Checks
```bash
bash -n install_ubuntu.sh\npython -m compileall .
```
Test installer changes in a disposable environment where possible. Document packages, drivers, codec requirements, filesystem changes, supported OS versions and uninstall/repair behaviour.

### Engineering expectations
Keep platform/build changes explicit, validate external input, use least privilege, avoid destructive defaults, preserve rollback/uninstall paths where applicable, and document hardware/OS compatibility. Update tests or provide reproducible manual verification for behavioural changes. Update English documentation first and keep Italian documentation semantically aligned.

### Pull requests
Describe what changed, why, affected platforms/hardware, tests performed, security/privacy impact, upstream relationship and rollback notes. Participation follows `CODE_OF_CONDUCT.md`.

## Italiano
Questo repository riguarda automation for installing and running TetraEar with RTL-SDR devices across Ubuntu/Debian and Windows.

### Flusso
1. Leggi `README.md`, `SECURITY.md` e la documentazione upstream/di progetto pertinente.
2. Controlla le issue esistenti, usa un branch dedicato e mantieni le pull request focalizzate.
3. Non committare segreti, acquisizioni private, dati personali, identificativi di dispositivi o materiale non autorizzato.
4. Usa solo dispositivi, sistemi e segnali per cui hai diritto legale e autorizzazione esplicita.
5. Segnala privatamente le vulnerabilità.

### Setup
```bash
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git\ncd TetraEarUbuntu
```

### Controlli
```bash
bash -n install_ubuntu.sh\npython -m compileall .
```
Test installer changes in a disposable environment where possible. Document packages, drivers, codec requirements, filesystem changes, supported OS versions and uninstall/repair behaviour.

### Aspettative tecniche
Rendi esplicite le modifiche di piattaforma/build, valida gli input esterni, usa privilegi minimi, evita default distruttivi, conserva rollback/uninstall quando applicabile e documenta compatibilità hardware/OS. Aggiorna i test o fornisci verifiche manuali riproducibili. Aggiorna prima la documentazione inglese e mantieni quella italiana equivalente.

### Pull request
Descrivi cosa cambia, perché, piattaforme/hardware interessati, test, impatto sicurezza/privacy, relazione con upstream e rollback. Si applica `CODE_OF_CONDUCT.md`.
