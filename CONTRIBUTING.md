# Contributing / Mitmachen

Issues and pull requests are welcome in **German or English**. /
Issues und Pull Requests sind auf **Deutsch oder Englisch** willkommen.

## Reporting bugs / Fehler melden

- Use the issue templates. / Bitte die Vorlagen verwenden.
- **Remove passwords, tokens and IP addresses** from everything you paste; issues are
  public. / **Passwörter, Tokens und IP-Adressen entfernen**; Issues sind öffentlich.
- Security issues: report privately via the *Security* tab. / Sicherheitslücken
  vertraulich über den Reiter *Security* melden.

## Pull requests

- One topic per pull request, with a short description of what and why.
- The CI must pass: `pytest`, `ruff`, `mypy` (backend), `npm run lint` and `npm run build`
  (dashboard), `shellcheck` (scripts). How to run them locally:
  [docs/09-entwicklung.md](docs/09-entwicklung.md) (German).
- The app writes to real heating systems. Changes to anything that writes to the CCU
  (profiles, modes, heating/cooling switch) are tested on real hardware before a merge,
  so they may take a while.
- No personal data in code, tests or docs: no real IP addresses, serial numbers or
  household details.
- Contributions are licensed under the project's license, [GPL-3.0](LICENSE).

The user interface and the documentation in `docs/` are in German; please keep new
texts there in German (a rough translation is fine, it will be polished).
