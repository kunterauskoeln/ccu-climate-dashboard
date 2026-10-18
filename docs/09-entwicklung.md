# 9 Entwicklung

Dieses Kapitel richtet sich an alle, die am Projekt weiterarbeiten.

## 9.1 Entwicklungsumgebung

| Werkzeug | Version | Wozu |
|---|---|---|
| Python | 3.11 oder neuer (Docker und CI nutzen 3.11) | Backend |
| Node.js | 20 | Frontend |
| Git | – | Versionsverwaltung |
| Docker + Compose v2 | – | nur zum Ausprobieren der Container; nicht für die tägliche Arbeit nötig |

Entwickelt wird auf einem beliebigen Rechner (im Projekt: Windows), **gegen die echte CCU**
im Heimnetz. Getestet und betrieben wird auf dem Linux-Zielsystem.

### Backend lokal starten

```bash
cd backend
python -m venv venv                       # einmalig
source venv/bin/activate                  # Windows PowerShell: venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

cd src
export CCU_HOST=<ccu-ip> CCU_USERNAME=<benutzer> CCU_PASSWORD=<passwort>
uvicorn app.main:app --reload --port 8000
```
Unter Windows/PowerShell statt `export`: `$env:CCU_HOST="<ccu-ip>"` usw.

Die Datendateien liegen dann standardmäßig unter `/app/app/data/` (Container-Pfad). Lokal
überschreibst du sie mit Umgebungsvariablen:
```bash
export PROFILE_SETS_FILE=$PWD/../dev-profile_sets.json
export PROFILE_SETS_BACKUP_FILE=$PWD/../dev-profile_sets.backup.json
export PROFILE_NAMES_FILE=$PWD/../dev-profile_names.json
export CHANGE_HISTORY_FILE=$PWD/../dev-change_history.json
```
Ohne `VALVE_CHANNELS_FILE` gilt die Vorlage `backend/src/app/valve_channels.json`.

### Frontend lokal starten

```bash
cd dashboard
npm ci                                              # einmalig (exakt nach package-lock.json)
echo "VITE_API_URL=http://localhost:8000" > .env.local
npm start                                           # Vite-Entwicklungsserver auf Port 3000
```
`VITE_API_URL` zeigt auf das lokal laufende Backend (das erlaubt `http://localhost:3000`
standardmäßig per CORS). Ohne die Variable verwendet das Frontend `/api`.

## 9.2 Qualitätswerkzeuge und Tests

Alles Folgende läuft auch automatisch in der CI (9.3). **Vor jedem Push lokal ausführen.**

### Backend (in `backend/`)

```bash
python -m pytest -q          # 328 Tests, ohne Netzwerk und ohne CCU
ruff check src scripts tests # Lint
mypy                         # Typprüfung (Konfiguration in pyproject.toml)
```

| Werkzeug | Konfiguration |
|---|---|
| **pytest** | `pytest.ini`: `pythonpath = src`, Tests in `tests/` |
| **ruff** | `pyproject.toml`: Zeilenlänge 100, Regeln `E W F I UP B RUF` plus `S110 S112` (kein stilles `except: pass/continue`). Bewusst aus: `E501` (Zeilenlänge, Formatierer-Sache), `RUF001-003` (typografische Zeichen in deutschen Kommentaren). In `scripts/` ist `E402` und `S110` erlaubt |
| **mypy** | `pyproject.toml`: Paket `app`, `mypy_path = src`, fehlende Stubs ignoriert |

Versionen von `ruff` und `mypy` sind in `requirements-dev.txt` **festgelegt**, damit
Ergebnisse nicht mit jedem Update wandern.

### Frontend (in `dashboard/`)

```bash
npm run lint                 # ESLint (typescript-eslint, react-hooks)
npx tsc --noEmit             # Typprüfung
npm run build                # Produktionsbau (Vite)
```
`tsconfig.json` arbeitet mit `strict: false`, im Code sind aber keine `any`-Typen erlaubt
oder vorhanden. `react-hooks/set-state-in-effect` ist bewusst abgeschaltet (Formulare und
das Theme werden aus Server- bzw. Speicherdaten befüllt).

### Aufbau der Backend-Tests

| Datei | Prüft |
|---|---|
| `test_schedule.py` | Reine Zeitplan-Rechnung (Überschreiben, Löschen, Umwandlung in Slots) |
| `test_profiles.py`, `test_state.py`, `test_climate.py`, `test_mapping.py`, `test_jsonrpc.py` | CCU-Schicht mit **Attrappen** |
| `test_profile_sets.py`, `test_profile_names.py` | JSON-Persistenz inkl. Backup und Sonderfälle |
| `test_climate_profiles.py`, `test_profile_transfer.py` | Speicher ↔ Gerät, Hintergrundübertragung |
| `test_change_history.py` | Änderungshistorie: Einträge, Ziele beim Zurücksetzen, Löschen beim Moduswechsel |
| `test_api_routes.py` | Alle HTTP-Endpunkte über `TestClient`, inklusive Protokollieren und Zurücksetzen |

**Datendateien:** Ein automatischer Fixture in `tests/conftest.py` leitet für **jeden** Test
alle Datendateien (`profile_sets`, Sicherungskopie, `profile_names`, `change_history`) in
ein eigenes Temp-Verzeichnis um. Ohne das schrieben Tests in den Container-Pfad
`/app/app/data`, auf einem Entwicklungsrechner ein echter Ordner. Neue Datendateien dort
ebenfalls eintragen.

**Attrappen** (`tests/conftest.py`): `FakeXmlRpc` und `FakeJsonRpc` ersetzen die Clients und
halten Parametersätze im Speicher; `_LiveXmlRpc` in `test_api_routes.py` übernimmt `setValue`
direkt, damit bestätigte Schreibvorgänge ihr Ergebnis zurücklesen können. Der
`client`-Fixture verdrahtet die Attrappen und setzt die Wartezeiten auf fast null. Für
Protokolle prüfen Tests mit `caplog`, dass Warnungen geschrieben werden.

Ein neuer Test für einen Endpunkt: Fixture `client` verwenden, Speicher mit
`profile_sets.put_mode(...)` vorbereiten, Aufruf per `client.get/post/patch`, Ergebnis und
Nebenwirkungen (`client.xmlrpc.set_calls`, `profile_sets.get_...`) prüfen.

## 9.3 Kontinuierliche Integration (GitHub Actions)

`.github/workflows/ci.yml` läuft bei jedem Push und jedem Pull Request:

| Job | Schritte |
|---|---|
| `backend` | Python 3.11, `pip install -r requirements-dev.txt`, Byte-Kompilierung, `pytest`, `ruff check`, `mypy` |
| `frontend` | Node 26, `npm ci`, `npm run lint`, `tsc --noEmit`, `npm run build` |
| `compose` | `docker compose config` (Prüft die Compose-Datei mit der Vorlage `.env.example`) |
| `shell` | `shellcheck` für `deploy.sh` und `scripts/*.sh` |

Alle Schritte sind **verbindlich** (ein Fehler lässt den Lauf scheitern). Ergebnis mit der
GitHub-CLI: `gh run list --branch <zweig>`.

**Dependabot** (`.github/dependabot.yml`) schlägt Updates als Pull Requests vor: Python-
und npm-Pakete jeden Montag (kleine Updates je Ökosystem gebündelt, große einzeln),
GitHub-Actions und Docker-Basisimages monatlich. Jeder Vorschlag durchläuft die CI; erst
danach entscheidet man über das Übernehmen. Große Updates (neue Hauptversion) können
Codeänderungen brauchen und gehören in einen eigenen Zweig mit Test auf dem Server.

**Tests und Datenordner:** `tests/conftest.py` leitet alle Datendateien in ein
Temp-Verzeichnis um. In Tests deshalb nie `monkeypatch.undo()` verwenden: es hebt auch
diese Umleitung auf, und der Test schreibt dann in den Container-Pfad `/app/app/data`
(auf dem Entwicklungsrechner entsteht ein Ordner `app` im Laufwerkswurzelverzeichnis).
Stattdessen das Original gezielt wieder einsetzen.

## 9.4 Arbeitsweise im Projekt

Bewährter Ablauf für jede Änderung:

1. **Zweig anlegen** (nie direkt auf `main` arbeiten): `git checkout -b feature/<thema>`.
   Vor jedem Commit `git branch --show-current` prüfen.
2. Änderung umsetzen, **Tests mitschreiben**, lokal `pytest`/`ruff`/`mypy` bzw.
   `lint`/`tsc`/`build` ausführen.
3. Committen (Deutsch, kurze Zusammenfassung plus Begründung), Zweig pushen, CI abwarten.
4. **Auf dem Zielsystem testen:** `./deploy.sh origin/<zweig>`, Änderung durchklicken,
   Backend-Log auf Warnungen prüfen.
   **Änderungen an `deploy.sh` selbst** vorher lokal so testen, wie sie am Ziel ablaufen:
   einen frischen Klon auf dem **alten** Stand auschecken und von dort
   `bash deploy.sh <neuer-stand>` starten. Das alte Skript läuft zuerst (siehe
   [Architektur 6.8](06-architektur.md#68-betrieb-container-und-deploysh)).
5. Nach dem Test **zusammenführen** ohne Merge-Commit (`git merge --ff-only <zweig>` in
   `main`), **taggen** (`git tag -a v0.N.0 -m "…"`), `git push origin main --tags`,
   Zweig löschen (`git push origin --delete <zweig>`).
6. Auf dem Zielsystem `./deploy.sh` (ohne Argument) bringt es auf `main`.

**Versionierung:** `v0.N.0`, aufsteigend je abgeschlossener Änderung (siehe
[Versionen](10-versionen.md)). Rollback = `./deploy.sh <tag>`.

## 9.5 Regeln für Änderungen am Code

**Backend**

- **Jeder Schreibvorgang an die CCU wird zurückgelesen und bestätigt.** Keine „fire and
  forget"-Schreibvorgänge für Zustände, deren Erfolg der Speicher voraussetzt.
- **Funk schonen:** Alles, was Profile schreibt, läuft im Hintergrund, mit Pause und
  Obergrenze. Nie viele Tage in einer Anfrage schreiben.
- **Bestehende Fehlerarten verwenden** (`CcuError`, `CcuUnreachable`, `CcuValidationError`,
  `CcuBusy`, `RoomNotFound`); sie werden automatisch in HTTP-Antworten übersetzt.
- **Best-Effort-Stellen loggen** (`log.warning(..., exc_info=True)`). Ein stummes
  `except: pass` lehnt der Linter ab.
- **CCU-Sitzungen freigeben:** jedes Skript, das `get_jsonrpc()` benutzt, ruft am Ende
  `logout()` auf (im `finally`).
- Neue Routen gehören in `routers/`, die Logik in `services/`. Zeitplan-Mathematik ohne
  Netzwerk gehört nach `services/ccu/schedule.py` und ist dort leicht testbar.

**Frontend**

- Serverdaten **nur über Hooks** (`src/hooks/`, react-query), nicht mit eigenem
  `useEffect`+`fetch`.
- Typen der API stehen in `services/types.ts` und spiegeln die Backend-Modelle.
- **Fehlende Werte nie als 0 anzeigen:** `lib/format.ts` liefert „–".
- Neue Bildschirme brauchen eine Route in `App.tsx` unter `/settings/...` (für alles im
  Einstellungsbereich) und nutzen die Kopfleiste (`back-card`).
- Farben und Abstände nur über die **CSS-Variablen** (`var(--color-…)`), damit alle Themen
  funktionieren.
- Layout-Anpassungen für breite Bildschirme in `styles.css` mit `@media (min-width: …)`;
  das Handy-Layout bleibt die Grundlage.

## 9.6 Häufige Erweiterungen

### Neues Thema

1. In `dashboard/src/styles/styles.css` einen Block `.theme-<name> { … }` anlegen (Kopiervorlage:
   ein vorhandenes Thema; **alle** Variablen setzen, inklusive `--chart-*` und `--bg-image`).
2. In `dashboard/src/theme/ThemeContext.tsx` den Typ `ThemeMode` und die Liste
   `AVAILABLE_THEMES` erweitern.
3. Build und Sichtprüfung. Hintergrundbild oder Farbverlauf über `--bg-image`.

### Anderer Raum, anderer Aktor

- Neue Thermostate erscheinen automatisch (Name = Raumname).
- Ventilzuordnung: `data/valve_channels.json` auf dem Server (Vorlage im Projekt:
  `backend/src/app/valve_channels.json`).
- Anderer Aktor-Typ: `_ACTUATOR_HINTS` in `services/ccu/mapping.py` erweitern und die
  Datenpunkte in `services/ccu/climate.py` prüfen.

### Neuer Endpunkt

Router in `routers/…` ergänzen; Anfragemodelle in `schemas.py`; Test in
`tests/test_api_routes.py`; Typ in `dashboard/src/services/types.ts` und Funktion in
`services/api.ts`, Hook in `src/hooks/`. Die OpenAPI-Beschreibung (`/api/docs`) entsteht
automatisch.

## 9.7 Layout lokal prüfen

Für Änderungen am Aussehen genügt ein statischer Test ohne Backend: `npm run build`, dann ein
kleiner Server, der `build/` ausliefert und `/api/...` mit Beispiel-JSON beantwortet, und
ein Screenshot mit Headless-Chrome:

```bash
chrome --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=12000 \
       --window-size=1280,800 --screenshot=seite.png "http://localhost:4174/settings/theme"
```
Mit `--window-size` prüfst du Handy (400), Tablet (900–1280) und PC (2200). (Ein Fenster
unter ca. 500 px Breite rendert Chrome trotzdem mit Mindestbreite.) Testserver danach über
ihren Port beenden.

## 9.8 Bekannte Einschränkungen und mögliche Verbesserungen

| Thema | Stand |
|---|---|
| Beim Moduswechsel wird nur das aktive Profil je Raum übertragen (andere beim Profilwechsel) | gewollt (Funklast) |
| Kein Login | gewollt für das Heimnetz |
| Live-Ereignisse (`/events/heating`) sind nur vorbereitet | ungenutzt |
