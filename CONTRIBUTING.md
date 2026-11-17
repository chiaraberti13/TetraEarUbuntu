# Contributing to TetraEarUbuntu

This repository covers automation for installing and running TetraEar with RTL-SDR devices across Ubuntu/Debian and Windows.

## Workflow
1. Read `README.md`, `SECURITY.md` and relevant upstream/project documentation.
2. Search existing issues, use a dedicated branch and keep pull requests focused.
3. Never commit secrets, private captures, personal data, device identifiers or unauthorized material.
4. Use only devices, systems and signals you are legally entitled and explicitly authorized to work with.
5. Report vulnerabilities privately.

## Setup
```bash
git clone https://github.com/chiaraberti13/TetraEarUbuntu.git
cd TetraEarUbuntu
```

## Checks
```bash
bash -n install_ubuntu.sh
python -m compileall .
```
Test installer changes in a disposable environment where possible. Document packages, drivers, codec requirements, filesystem changes, supported OS versions and uninstall/repair behaviour.

## Engineering expectations
Keep platform/build changes explicit, validate external input, use least privilege, avoid destructive defaults, preserve rollback/uninstall paths where applicable, and document hardware/OS compatibility. Update tests or provide reproducible manual verification for behavioural changes. Write documentation in English and keep README.md and README.it.md semantically aligned.

## Pull requests
Describe what changed, why, affected platforms/hardware, tests performed, security/privacy impact, upstream relationship and rollback notes. Participation follows `CODE_OF_CONDUCT.md`.

## Reporting and contribution checks

Use the [issue templates](https://github.com/chiaraberti13/TetraEarUbuntu/issues/new/choose) and check for duplicates first. Useful context: Ubuntu, Debian or Windows version, Python version, RTL-SDR hardware and redacted logs.

Write community and technical documentation in English; maintain equivalent English and Italian READMEs. Preserve existing application translations. Fill in the pull request template with commands, results and checks not performed, including the reason. Use synthetic examples without secrets or personal data.

See [the code of conduct](CODE_OF_CONDUCT.md), [security policy](SECURITY.md) and [accessibility statement](ACCESSIBILITY.md). Report vulnerabilities only through the security policy process.
