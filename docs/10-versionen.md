# 10 Versionen

Jede abgeschlossene Änderung wird als Git-Tag `v0.N.0` markiert. Den Stand eines Tags
installierst du mit `./deploy.sh <tag>`; die Liste der Tags mit Kurzbeschreibung zeigt
`git tag -n1`.

## v0.35.1: Icon fürs Esszimmer

- Ein Raum mit dem Namen `Esszimmer` zeigt ein Icon mit Messer und Gabel.

## v0.35.0: Thema Weiß, Glanz, Warnung bei nicht übertragenen Einstellungen

- Neues Thema **Weiß**: fast weiße Karten auf hellgrauem Grund, blaue Akzente.
- Neuer Effekt **Glanz** (*Einstellungen → Design*, Aus/An): Glasknopf-Reflex über Karten
  und Schaltflächen (helle obere Hälfte, Kante in der Mitte, Lichtkante oben), mit Erhaben
  kombinierbar, Stärke je Thema. Wird wie Thema und Erhaben pro Gerät im Browser
  gespeichert.
- **Seiten laden zuverlässig:** Lud eine Seite mehrere Daten gleichzeitig, scheiterten
  Anfragen oft mit Fehler 500 (bei Messungen ein Großteil) und die Seite musste neu
  angestoßen werden. Ursache: Alle Anfragen teilten sich eine XML-RPC-Verbindung zur CCU,
  die keine parallelen Zugriffe verträgt. Jetzt hat jeder Bearbeitungs-Thread seine eigene.
  Außerdem melden sich gleichzeitige Anfragen nur noch einmal per JSON-RPC an, und die
  Geräteliste wird nach Ablauf nur einmal neu geholt.
- **Einstellungen nicht übertragen:** Steht „Konfiguration ausstehend“ an einem Gerät länger
  als 30 Minuten (`CONFIG_PENDING_WARN_MINUTES`), wird es ein Gerätehinweis (Banner,
  Geräteseite, Home Assistant). Raumkachel und Profilseite warnen, dass der gezeigte Plan
  noch nicht am Thermostat angekommen ist. Anlass: Ein Thermostat hing fünf Wochen
  unbemerkt, weil zwei Einstellungen als Text gespeichert waren (CCU-Hintergrund 8.4).
- Skripte `compare_group_profiles.py` (nur lesen) und `sync_group_profiles.py`: Wochenprofile
  von Thermostat und Heizgruppe vergleichen bzw. vom Thermostat in die Gruppe kopieren.

## v0.34.1: Rund ums öffentliche Repository

- Bildschirmfotos im README (mit erfundenen Daten, `docs/screenshots/`).
- Vorlagen für Fehlermeldungen und Wünsche (zweisprachig, mit Hinweis, Passwörter und
  IP-Adressen zu entfernen), `CONTRIBUTING.md`; Issues auf Deutsch oder Englisch.
- Dependabot schlägt Updates nur noch monatlich vor; Sicherheitsupdates weiterhin sofort.
- Sicherheitswarnung im Bauwerkzeug behoben: `postcss-selector-parser` (unter Tailwind)
  per `overrides` auf 7.1.6; die gebaute Oberfläche ist byte-gleich.
- Die App selbst ist unverändert.

## v0.34.0: Vorbereitung als Open Source (GPL-3.0)

- Lizenz GPL-3.0 (`LICENSE`), englisches `README.md`, `SECURITY.md`, Haftungsausschluss.
- Installation aus dem öffentlichen Repository per HTTPS; Deploy-Key nur noch für private
  Forks (`install.sh` mit `CCU_REPO=git@…`).
- Haushaltsspezifisches entfernt: neutrale Beispieladressen und MQTT-Thema, allgemeine
  Vorlage `valve_channels.json`, erfundene Seriennummern in Tests, Einmal-Skript
  `set_heating_profiles_20c.sh` gelöscht.
- Hintergrundbilder ungeklärter Herkunft durch Farbverläufe ersetzt.

## v0.33.0: Ventilverlauf

- Neue Seite *Einstellungen → Ventilverlauf*: Ventilöffnung aller Räume als Grafik über
  12, 24, 48 oder 72 Stunden, eine Farbe je Raum, Räume über die Legende ein- und
  ausblendbar, Werte beim Überfahren.
- Aufzeichnung alle 5 Minuten in `data/valve_history.json` (72 Stunden), Lücken bei
  Pausen. Neuer Endpunkt `GET /system/valve-history`.

## v0.32.1: Abhängigkeiten

- Dependabot: kleine npm-Updates und `@types/node` 26 (passend zu Node 26). Keine
  Änderung an der Bedienung.

## v0.32.0: Profilseite zeigt gespeicherte Pläne

- **Fehler behoben:** Beim Heizen zeigte die Profilseite für alle Profile den Inhalt der
  Thermostate. Für Profile, die gerade nicht laufen, ist der veraltet (das Thermostat teilt
  eine Tabelle zwischen Heizen und Kühlen); nach einem Import sah man deshalb nicht die
  neuen Pläne, und eine Änderung darauf hätte den gespeicherten Plan überschrieben.
- Jetzt gilt: Nur das gerade laufende Profil wird auf dem Thermostat gelesen und
  bearbeitet, alle anderen im App-Speicher (ohne Funk); ein Hinweis auf der Seite sagt,
  wo das Profil liegt. Kopieren berücksichtigt das in beide Richtungen.

## v0.31.0: Abhängigkeiten aktualisiert

- Erste Runde der Dependabot-Vorschläge: GitHub-Actions auf v7, Node 26 im
  Dashboard-Image und in der CI, `@iconify/react` 6, kleinere npm- und Python-Updates
  (ruff 0.16.10, mypy 2.4.0, `paho-mqtt` ≥ 2.1).
- Zurückgestellt (brauchen Codeänderungen): TypeScript 7, React 19, Tailwind 4.

## v0.30.0: Abwesenheit

- *Einstellungen → Abwesenheit*: alle Räume ab sofort oder ab einem geplanten Zeitpunkt
  auf ein Profil, zum Ende automatisch zurück auf das vorherige Profil je Raum. Verpasste
  Zeitpunkte werden nachgeholt, Handänderungen während der Abwesenheit bleiben.
- „Wohnung“ und Abwesenheit nutzen einen gemeinsamen Planungsweg (`apartment.py`); jeder
  Raum kann ein eigenes Zielprofil haben.
- Neue Endpunkte `GET`/`PUT`/`DELETE /system/absence`; Home Assistant: Abwesenheit und
  Abwesenheit bis.

## v0.29.0: Wartung

- `/system/health` meldet zusätzlich MQTT, Taupunkt-Lage, Gerätezustand und die letzte
  automatische Sicherung; `install.sh --check` prüft diese Punkte mit.
- `deploy.sh` setzt die Rechte von `backend/.env` auf 600, wenn sie abweichen.
- Dependabot schlägt Updates der Abhängigkeiten wöchentlich bzw. monatlich vor.
- Testbibliothek auf `httpx2` umgestellt (Warnung behoben), Browser-Daten des Builds
  aktualisiert.

## v0.28.0: Gerätezustand und Funkauslastung

- Alle 5 Minuten: Erreichbarkeit, Batterie, Signal und Funk-Limit von Thermostaten und
  Aktor sowie die Funkauslastung (Duty Cycle) der CCU. Gelber Hinweisbalken bei
  Problemen, Details auf der Geräteseite, Zahl der Hinweise auf der Kachel *Geräte*.
- Profilübertragungen halten ab 70 % Funkauslastung an und schieben den Rest auf.
- Home Assistant: Geräteproblem, Geräte-Meldung, CCU-Funkauslastung und je Gerät
  Erreichbarkeit, Batterie schwach, Batteriespannung.
- Neuer Endpunkt `GET /system/device-health`.

## v0.27.0: Home Assistant

- Die App veröffentlicht ihren Zustand per MQTT-Discovery: Gerät „CCU Dashboard“ mit
  Kondensgefahr, Taupunkt-Warnung, Taupunkt-Lage und -Meldung, Kühlbetrieb, Vorlauf und je
  Raum Taupunkt, Abstand, Bewertung und Ventil. Verfügbarkeit über Last Will.
- Doku: nötige Broker-Rechte und Vorlagen für Push-Nachrichten (Konfiguration 3.7).

## v0.26.0: Tägliche Sicherung

- Die App legt jede Nacht ab 03:00 eine Sicherung im Export-Format in `data/backups/` an
  und behält die letzten 14; eine verpasste Nacht wird beim Start nachgeholt.
- *Datensicherung*: neue Kachel *Gespeicherte Sicherungen* mit Herunterladen, Einspielen
  (über die Import-Prüfung) und „Jetzt sichern“; die Kopien vor Importen erscheinen mit.
- Neue Endpunkte `GET`/`POST /backups`, `GET /backups/{name}`.

## v0.25.0: Taupunktüberwachung

- Neue Seite *Einstellungen → Taupunkt*: im Kühlbetrieb je Raum Taupunkt (aus Temperatur
  und Luftfeuchte des Thermostats) gegen die Vorlauftemperatur, Ampel ok / knapp /
  Kondensgefahr, Warnbalken auf jeder Seite, Taupunkt im Raumdetail.
- Vorlauftemperatur per MQTT (`MQTT_*` in `backend/.env`); der Messwert gilt erst nach
  10 Minuten Durchfluss, sonst der letzte gültige Wert.
- Nur Anzeige und Warnung, kein Eingriff. Neue Abhängigkeit `paho-mqtt`, neuer Endpunkt
  `GET /system/dew-point`.

## v0.24.0: Installationsskript

- `scripts/install.sh` richtet die Anwendung auf einem laufenden Debian 12/13 ein: Pakete,
  Docker, Deploy-Key (mit Prüfung des GitHub-Fingerabdrucks), Klonen, CCU-Zugangsdaten mit
  Verbindungs- und Anmeldetest, Ventil-Zuordnung, erster Start. Mehrfach ausführbar.
- `install.sh --check` prüft den Zustand, ohne etwas zu verändern.
- Doku: Passwörter mit `$` oder ` #` in `backend/.env` in einfache Anführungszeichen
  setzen (Docker Compose ersetzt sonst `$name`).

## v0.23.0: Automatisches Umschalten Heizen/Kühlen

- In der Kachel *Betriebsart*: **Automatisch umschalten** mit je einem Zeitpunkt (Tag,
  Monat, Uhrzeit) und eigenem Haken für Kühlen und für Heizen. Gilt jedes Jahr, bis es
  geändert oder abgehakt wird; verpasste Zeitpunkte (Server aus) werden nachgeholt.
- Neue Endpunkte `GET`/`PUT /system/climate/schedule`, neue Datei
  `data/climate_schedule.json`, neue Abhängigkeit `tzdata`.
- Der Zeitplan ist Teil der Datensicherung (Export `climate_schedule`, Import mit Prüfung;
  ein Import schaltet nie selbst um).

## v0.22.0: Datensicherung mit Import

- *Einstellungen → Datensicherung* ist eine eigene Seite mit **Export** und **Import**.
- Import einer Export-Datei: vollständige Prüfung mit Fehlerliste (Fundstelle je Fehler),
  Hinweise zu Räumen, die nicht zur CCU passen; erst nach Bestätigung übernommen. Vorher
  wird der bisherige Stand als `data/vor-import-….json` gesichert, die Änderungshistorie
  wird gelöscht, die aktive Betriebsart im Hintergrund übertragen.
- Neuer Endpunkt `POST /import` (ohne `apply=true` nur Prüfung).
- Geräteseite: Kopfleiste wie auf den anderen Seiten, auf Tablet und PC alle Kacheln
  gleich hoch.

## v0.21.0: „Wohnung": alle Räume auf ein Profil

- Neue Kachel **Wohnung** unter *Heizprofile*: schaltet nach Rückfrage alle Räume auf
  dasselbe Profil, nacheinander im Hintergrund. Weicht der gespeicherte Plan eines Raums
  ab, wird er zuerst übertragen; scheitert das, bleibt der Raum auf seinem Profil.
- Heizprofil-Seite: auf Tablet und PC alle Kacheln gleich hoch, Profil-Schaltflächen auf
  einer Höhe.

## v0.20.0: Rückfrage vor dem Umschalten, Export

- Umschalten Heizen/Kühlen nur noch nach ausdrücklicher Rückfrage („Wirklich auf Kühlen
  umschalten?").
- *Einstellungen → Datensicherung*: Export aller Daten der App als Datei (ohne
  CCU-Zugangsdaten).

## v0.19.0: Dokumentation

- Projektdokumentation im Ordner `docs/` (Installation auf Debian, Konfiguration, Betrieb,
  Bedienung, Architektur, API, CCU-Hintergrund, Entwicklung).

## v0.18.0: Änderungshistorie mit Zurücksetzen

- Profiländerungen im aktiven Modus und Umbenennungen von Profilen werden mit Zeitpunkt
  und Vorher-Stand protokolliert (*Einstellungen → Änderungshistorie*).
- „Bis hierhin zurücksetzen" nimmt einen Eintrag und alle neueren zurück: Namen sofort,
  Profile über den gebremsten Hintergrundweg auf die Thermostate.
- Ein Wechsel Heizen/Kühlen löscht die Profil-Änderungshistorie; die Historie der
  Umbenennungen bleibt. Die gespeicherten Heiz-/Kühlsätze bleiben unverändert.
- Tests schreiben ihre Daten nicht mehr in den Container-Pfad auf dem Entwicklungsrechner.

## v0.17.0: Automatischer Neustart, Datenordner, Redis entfernt

- **Fehler behoben:** Nach einem Neustart des Servers blieben die Container aus
  (`restart: unless-stopped` wertet das geordnete Stoppen beim Herunterfahren wie ein
  bewusstes `docker stop`). Jetzt `restart: always`.
- **Datenordner `data/`** statt einzeln eingebundener Dateien. Profile, Profilnamen und die
  Ventil-Zuordnung überstehen Updates; die Profilnamen wurden vorher bei jedem Deploy
  zurückgesetzt. Die Ventil-Zuordnung braucht nach Änderung keinen Neubau mehr.
- **Redis entfernt** (diente nur einer Statuszeile im Health-Check; `REDIS_HOST`/`REDIS_PORT`
  wirkten nie).
- **`deploy.sh`** startet sich nach dem Checkout selbst neu (bash las sonst den alten
  Skriptinhalt weiter) und übernimmt beim Umstieg alte Dateien nach `data/`.
- **Umstieg von älteren Versionen:** Auf dem Server läuft beim ersten Deploy noch das alte
  `deploy.sh`, das die neue Übernahme nicht kennt. Deshalb **vorher** von Hand kopieren:
  `mkdir -p data`, dann `backend/profile_names.json`, `backend/profile_sets.json`,
  `backend/profile_sets.backup.json` und `backend/src/app/valve_channels.json` nach `data/`.
- Dashboard-Healthcheck fragt `127.0.0.1` statt `localhost` ab (meldete sonst fälschlich
  `unhealthy`).

## v0.16.0: Layout für breite Bildschirme

- Kopfleiste (Zurück + Titel) spannt auf Tablet/PC über alle Spalten.
- Inhalt maximal 1200 px breit und zentriert; Kacheln nur so hoch wie ihr Inhalt.
- Profilseite: die sieben Tagesgrafiken als Raster (ab 1100 px vier je Zeile, dann drei).
- Gleich hohe Kacheln je Zeile auf der Startseite, in den Einstellungen und auf der
  Profilseite. Das Handy-Layout bleibt unverändert.
- Übertragungsbalken stürzt bei unerwarteten Daten nicht mehr die ganze App ab.

## v0.15.0: Profilwechsel mit Plan-Übertragung, Übertragungsbalken

- **Lücke geschlossen:** Nach einem Wechsel der Betriebsart wird nur das aktive Profil je
  Raum übertragen; die anderen fünf lagen mit dem Plan der alten Betriebsart auf dem
  Thermostat, und ein Profilwechsel schaltete nur den Zeiger um. Jetzt schreibt ein Wechsel
  auf ein solches Profil **zuerst den Plan und schaltet danach um** (bei Fehlern nicht).
- App-weiter **Übertragungsbalken** mit Fortschritt, offenen und fehlgeschlagenen Tagen,
  Knopf „Jetzt übertragen" und Ausblenden je Vorgang.
- Neuer Endpunkt `POST /system/climate/transfer`, Fehlercode 409 `busy`,
  `TransferState` mit `kind`, `label`, `started_at`.

## v0.14.0: Ventilanzeige, Erhaben-Stufen, neue Themen, Sitzungs-Leck

- **Ventil-Balken** auf Raumkachel und Raumdetail. Die Stellung kommt von den
  **Aktorkanälen** (Zuordnung in `valve_channels.json`), weil die Heizgruppen dauerhaft 0
  melden.
- **Erhaben** als Auswahl Aus / Leicht / Stark statt Schalter.
- Vier neue Themen: Wald, Sonnenuntergang, Graphit, Ozean. Die Themenwahl bleibt auf der
  Design-Seite.
- **Fehler behoben:** Bei einem fehlgeschlagenen JSON-RPC-Aufruf blieben bis zu drei
  CCU-Sitzungen offen („too many sessions"). Sitzungen werden jetzt vor dem Verwerfen
  abgemeldet; deterministische CCU-Fehler (601) werden nicht wiederholt.

## v0.13.0: Verschluckte Fehler werden protokolliert

- Erstes Logging der Anwendung (`docker compose logs backend`).
- Warnungen an allen Best-Effort-Stellen (Spiegeln in den Speicher, Erstbefüllung, Merken
  des aktiven Profils, Abmelden). Das Verhalten ist unverändert.
- Linter-Regeln `S110`/`S112`: kein stilles `except: pass/continue` mehr.

## v0.12.0: ESLint, Tagesgrafik im 5-Minuten-Raster

- ESLint mit TypeScript- und React-Hooks-Regeln als verbindlicher CI-Schritt.
- **Fehler behoben:** Die Tagesgrafik tastete nur volle Stunden ab; Abschnitte dazwischen
  (zum Beispiel 08:00–08:30) fehlten. Jetzt 5-Minuten-Raster mit Stunden-Beschriftung.
- Zeitrad-Werte in einem gemeinsamen Modul (die Effekte liefen bei jedem Rendern neu).

## v0.11.0: ruff und mypy

- Feste Konfiguration (`pyproject.toml`), gepinnte Versionen, beide als verbindliche
  CI-Schritte.
- Ein CCU-Login ohne Sitzungs-ID schlägt jetzt mit einem Fehler fehl statt stillschweigend
  fortzufahren.

## v0.10.0: Routing und Typen

- Alle Profilseiten unter `/settings/heating-profiles/…`; doppelte Route entfernt.
- Alle `any`-Typen entfernt (`unknown` mit Prüfung, generische Hilfsfunktionen).

## v0.9.0: react-query

- Alle Serverdaten laufen über Hooks mit gemeinsamem Cache (Übersicht alle 15 s, Übertragung
  alle 2 s nur bei laufendem Auftrag), statt handgeschriebener Abfrage- und Cache-Muster.

## v0.8.0: Vite statt Create React App

- Reiner Werkzeugwechsel: schnellerer Bau, deutlich weniger Abhängigkeiten (864 → 134),
  `npm ci` funktioniert wieder. Ausgabeverzeichnis und Dockerfile/nginx unverändert.
- Fehlende React-Typdefinitionen ergänzt; zwei bis dahin verdeckte Typfehler behoben.

## v0.7.0: Heiz-/Kühlprofile ohne Umschalten bearbeiten (Phase 2b.2)

- Umschalter Heizen/Kühlen im Profileditor. Der **inaktive** Modus wird nur in der Anwendung
  gespeichert (`?mode=` an allen Profil-Endpunkten), ohne CCU-Zugriff und ohne Umschalten.

## v0.6.0: Unabhängige Heiz-/Kühlprofile (Phase 2b.1)

- Zwei dauerhaft gespeicherte Profilsätze je Raum (`profile_sets.json`, mit Backup).
- **Hintergrundübertragung** beim Wechsel der Betriebsart: ein Tag je Schreibvorgang, 4 s
  Pause, höchstens 8 Tage, Abbruch nach drei Fehlern; Aktivprofil je Betriebsart gemerkt
  und **bestätigt** zurückgeschrieben (behob ein stilles Abweichen).
- Ausgelöst durch einen Vorfall: die erste, synchrone Fassung blockierte die Anwendung und
  überlastete den Funk.

## v0.5.0: Neue API, Profil-Editor, Betriebsart

- Ressourcenorientierte API (`/rooms`, `/rooms/{raum}/profiles/…`, `/system/climate` …)
  mit einheitlichem Fehlerformat.
- Profile bearbeiten (Zeitabschnitte setzen/löschen), kopieren (Tag, Profil, Räume),
  Profilnamen; Umschalten Heizen/Kühlen; eigener Drehregler; viel Oberflächenpflege.
- Profile schreiben über JSON-RPC `Interface.putParamset` mit Bestätigung durch Zurücklesen.

## v0.4.0: CCU-Zugriff sauber gekapselt

- Modul `services/ccu/` (JSON-RPC, XML-RPC, Zuordnung, Zustand, Profile, reine
  Zeitplan-Rechnung); Modus-Schreiben korrigiert; Profile 1–6 einheitlich.

## v0.3.0: Aufräumen und Betrieb

- Zugangsdaten aus dem Code in `backend/.env`; toter Code entfernt.
- nginx als `/api`-Proxy (kein CORS, keine eingebaute Server-Adresse), `deploy.sh`,
  Healthchecks, GitHub-Actions-CI.

## v0.2.0: Ausgangsstand

- Stand vor dem Umbau.
