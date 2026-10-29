# 6 Architektur

## 6.1 Verzeichnisstruktur

```
ccu/
├── docker-compose.yml          Zwei Dienste: backend, dashboard (nginx); Datenordner ./data
├── deploy.sh                   Update/Rollback auf dem Server (zweistufig, siehe 6.8)
├── scripts/install.sh          Erstinstallation auf Debian und Zustandsprüfung (--check)
├── data/                       Laufzeitdaten (nur auf dem Server, nicht im Git)
├── DEVELOPMENT.md              Kurzverweis auf die Entwicklungsdokumentation
├── .github/workflows/ci.yml    Automatische Prüfung bei jedem Push
├── backend/
│   ├── Dockerfile              Python 3.11 (slim), uvicorn
│   ├── pyproject.toml          ruff- und mypy-Konfiguration
│   ├── pytest.ini              Testkonfiguration (pythonpath=src)
│   ├── requirements(-dev).txt  Abhängigkeiten (dev: pytest, httpx, ruff, mypy)
│   ├── scripts/                Diagnose- und Hilfsskripte (laufen im Container)
│   ├── src/app/
│   │   ├── main.py             FastAPI-App, CORS, Logging, Router einbinden
│   │   ├── deps.py             Singletons: CCU-Clients, Gerätezuordnung
│   │   ├── schemas.py          Pydantic-Anfrage-Modelle, Antwort-DTOs
│   │   ├── http_errors.py      Abbildung der Fehler auf HTTP-Status/JSON
│   │   ├── valve_channels.json Vorlage der Zuordnung Raum → Aktorkanäle
│   │   ├── routers/            HTTP-Endpunkte (rooms, profiles, system, devices, meta, history, backup, events)
│   │   └── services/
│   │       ├── ccu/            Zugriff auf die CCU (siehe 6.3)
│   │       ├── climate_profiles.py   Brücke zwischen Speicher und Geräten
│   │       ├── profile_sets.py       Persistenz Heiz-/Kühlprofile (JSON)
│   │       ├── profile_names.py      Persistenz Profilnamen (JSON)
│   │       ├── profile_transfer.py   Hintergrundübertragung auf die Thermostate
│   │       ├── change_history.py     Änderungshistorie (Protokoll + Zurücksetzen)
│   │       ├── backup_data.py        Export, Prüfung und Einspielen einer Export-Datei
│   │       ├── auto_backup.py        Tägliche Sicherung in data/backups (Hintergrund-Thread)
│   │       ├── climate_switch.py     Umschalten Heizen/Kühlen (von Hand und automatisch)
│   │       ├── climate_schedule.py   Zeitplan und Hintergrund-Timer für das automatische Umschalten
│   │       ├── flow_sensor.py        Vorlauftemperatur per MQTT (paho, eigener Netzwerk-Thread)
│   │       ├── dew_point.py          Taupunktüberwachung (Hintergrund-Runde jede Minute)
│   │       ├── ha_publish.py         Zustand per MQTT-Discovery an Home Assistant
│   │       ├── device_health.py      Batterie, Erreichbarkeit, Duty Cycle (alle 5 Minuten)
│   │       ├── apartment.py          Mehrere Räume auf Profile umschalten (Wohnung, Abwesenheit)
│   │       ├── absence.py            Abwesenheit: Phasen, gemerkte Profile, Hintergrund-Timer
│   │       ├── valve_history.py      Ventilstellungen alle 5 Minuten, 72 h (Ventilverlauf)
│   │       └── event_bus.py          Vorbereitet für Live-Ereignisse (nicht aktiv)
│   └── tests/                  Automatische Tests (pytest)
└── dashboard/
    ├── Dockerfile              Mehrstufig: Node-Build, dann nginx
    ├── nginx.conf              Auslieferung + /api-Reverse-Proxy
    ├── vite.config.ts          Build-Konfiguration
    ├── eslint.config.mjs       Lint-Regeln
    └── src/
        ├── App.tsx             Routen, QueryClient, Übertragungsbalken
        ├── components/         Bildschirme und Bausteine
        ├── hooks/              Datenzugriff mit react-query
        ├── services/           HTTP-Client und Typen
        ├── theme/              Themen und Effekt-Stufen
        ├── lib/                Kleine Hilfsfunktionen
        └── styles/styles.css   Alle Stile (CSS-Variablen je Thema)
```

## 6.2 Laufzeitarchitektur

```
Browser ──► nginx :3000
             ├─ /              statische Dateien (React-Build)
             └─ /api/…  ──►  backend :8000   (Präfix /api wird entfernt)
                               │
                               ├─ CCU JSON-RPC  (requests, Sitzung, Wiederholungen)
                               ├─ CCU XML-RPC   (xmlrpc.client, Port 2010)
                               └─ JSON-Dateien  (Ordner data/: Profile, Namen,
                                                 Ventil-Zuordnung, Änderungshistorie)
```

- **Ein Uvicorn-Worker**, synchrone Handler (FastAPI führt sie im Thread-Pool aus).
- Das Frontend spricht **nur relative Pfade** (`/api/...`) an. Dadurch braucht es kein CORS,
  keine eingebaute Server-Adresse, und dasselbe Image läuft überall.
- Der nginx-Proxy nutzt Dockers DNS (`127.0.0.11`) über eine Variable: nginx startet auch,
  wenn das Backend kurz fehlt, und findet es nach einem Neustart wieder.
- `index.html` wird nie gecacht, `/static/` (Dateien mit Hash im Namen) ein Jahr lang.

## 6.3 Backend im Detail

### Schichten

| Schicht | Module | Aufgabe |
|---|---|---|
| HTTP | `routers/*`, `schemas.py`, `http_errors.py` | Anfragen prüfen, Fehler in JSON/Statuscodes übersetzen |
| Anwendungslogik | `climate_profiles.py`, `profile_transfer.py` | Heiz-/Kühl-Speicher, Wechsel der Betriebsart, Profilwechsel |
| Persistenz | `profile_sets.py`, `profile_names.py` | JSON-Dateien, gesperrt und atomar |
| CCU-Zugriff | `services/ccu/*` | Alles, was die CCU direkt anspricht |

### Das CCU-Modul (`services/ccu/`)

| Datei | Inhalt |
|---|---|
| `jsonrpc.py` | Client für die ReGaHss-Schnittstelle (`/api/homematic.cgi`): Sitzung mit Anmeldung/Abmeldung, Wiederholungen, `Device.listAllDetail`, `Interface.getParamset`/`putParamset` |
| `xmlrpc.py` | Client für den HmIP-Server (Port 2010): `getValue`/`setValue`/`getParamset`/`putParamset` |
| `mapping.py` | Baut aus der Geräteliste die Zuordnung Raum → Thermostat/Gruppe/Aktorkanäle, mit 5 Minuten Zwischenspeicher |
| `state.py` | Liest den Raumzustand (`RoomState`): Temperaturen, Modus, Profil, Ventil, Batterie, Funkqualität |
| `profiles.py` | Profile lesen/schreiben, aktives Profil, Modus, Sollwert, Boost |
| `schedule.py` | Reine Rechenfunktionen für Zeitpläne (kein Netzwerk): Zeitabschnitte ↔ die 13 Slots der CCU, Überschreiben, Löschen, Validierung |
| `climate.py` | Heizen/Kühlen am Aktor lesen und schreiben (mit Bestätigung) |
| `errors.py` | Fehlerarten (siehe 6.6) |

**Regel der Zugriffswege** (beide sind Pflicht, siehe [CCU-Hintergrund](08-ccu-hintergrund.md)):

| Aufgabe | Weg |
|---|---|
| Geräteliste, Anmeldung | JSON-RPC |
| **Schreiben der Profile** | JSON-RPC `Interface.putParamset` (nur dieser Weg funktioniert für HmIP-Profile) |
| Zustände lesen (Temperatur, Modus, Ventil, Batterie …) | XML-RPC |
| Sollwert, Modus, Boost, aktives Profil, Heizen/Kühlen | XML-RPC |
| Profile lesen | XML-RPC (MASTER-Parameter) |

**Immer den Gerätekanal adressieren** (Thermostat `:1` für Zustände/Profile, `:0` für
Batterie und Empfang), nie die Heizgruppe. Einzige Ausnahme war früher die Ventilstellung,
sie kommt jetzt von den Aktorkanälen.

### Sitzungen und Wiederholungen

- JSON-RPC-Sitzungen leben ca. 10 Minuten (die Anwendung erneuert sie nach 550 s).
- Fehlgeschlagene Aufrufe werden bis zu 2× wiederholt. Vor dem Verwerfen einer Sitzung
  wird sie **abgemeldet**, denn die CCU erlaubt nur wenige gleichzeitige Sitzungen.
  Deterministische Fehler der CCU (Code 601) werden **nicht** wiederholt.
- Der Hintergrundauftrag verwendet **eigene** Clients (nicht die der Anfragen, sie sind nicht
  thread-sicher) und meldet sich nach jedem Lauf ab.

### Schreibvorgänge und Bestätigung

**Jeder Schreibvorgang an die CCU wird zurückgelesen und bestätigt** (Polling), denn die
CCU meldet bei Profil-Schreibvorgängen sogar Scheinfehler, und Funkbefehle kommen mit
Verzögerung an:

| Vorgang | Bestätigung |
|---|---|
| Profiltag schreiben | 1,5 s warten, dann alle 2 s lesen, bis 25 s; ein Tag pro Schreibvorgang |
| Heizen/Kühlen am Aktor | Lesen alle 1 s bis 15 s |
| Aktives Profil | Lesen alle 1 s bis 8 s; bei fehlender Bestätigung Fehler (502) statt stillem Erfolg |

## 6.4 Heizen und Kühlen: die zwei Profilsätze

**Ausgangslage:** Ein HmIP-WTH-1 speichert nur **eine** Tabelle mit 6 Profilen (kein
getrennter Heiz- und Kühlsatz), und einen Zeiger `ACTIVE_PROFILE`. Beides teilen sich die
Betriebsarten.

**Lösung:** Die Anwendung hält in `profile_sets.json` je Raum **zwei vollständige Sätze**
(`heating`, `cooling`) plus das zuletzt aktive Profil je Betriebsart. Die Thermostate
enthalten den Satz der **gerade aktiven** Betriebsart. Nach einem Wechsel der Betriebsart
ist das zunächst nur für das **aktive Profil** jedes Raums der Fall; die übrigen fünf Profile
werden erst beim Profilwechsel im Raum nachgezogen (siehe unten).

```
                 profile_sets.json  (Wahrheit für BEIDE Sätze, dauerhaft)
                  ├─ heating: P1..P6
                  └─ cooling: P1..P6
                        ▲                    │
   Bearbeiten (aktive   │ spiegeln           │ übertragen (Hintergrund,
   Betriebsart)         │                    ▼ funkschonend)
 Browser ──► Thermostat (aktive Betriebsart, eine physische Tabelle)
 Bearbeiten (inaktive Betriebsart) ─────────► nur profile_sets.json
```

**Bearbeiten (`?mode=`):**
- Ohne `?mode` oder mit der aktiven Betriebsart: schreibt in den Thermostat (bestätigt)
  **und** spiegelt das Ergebnis in `profile_sets.json`.
- Mit der **inaktiven** Betriebsart: liest und schreibt **nur** `profile_sets.json`. Kein
  CCU-Zugriff, sofort.
- Beim ersten Bearbeiten eines Raumes werden beide Sätze aus dem Thermostat gefüllt
  („Seeding", vor dem Schreiben, damit die Änderung nicht in beide Sätze gelangt).

**Wechsel der Betriebsart (`PATCH /system/climate`):**
1. Aktor schalten (bestätigt, ca. bis 15 s).
2. Das **aktive Profil** jedes Raums unter der **alten** Betriebsart merken (nur Lesen).
3. Hintergrundauftrag starten (`profile_transfer`):
   a. aktives Profil jedes Raums für die **neue** Betriebsart wiederherstellen (bestätigt);
   b. Plan bilden: je Raum nur das aktive Profil, nur Tage, die vom Thermostat abweichen;
   c. Tage einzeln schreiben (4 s Pause, höchstens 8 Tage, Abbruch nach 3 Fehlern in
      Folge; der Rest gilt als „aufgeschoben").

**Profilwechsel im Raum (`PATCH /rooms/{raum}` mit `active_profile`):** Vergleicht den
gespeicherten Plan des Ziel-Profils mit dem Thermostat. Ohne Unterschied: sofort
umschalten (bestätigt). Mit Unterschied: Hintergrundauftrag schreibt **zuerst** die Tage
und schaltet **danach** um; bei einem Fehler bleibt das alte Profil aktiv.

### Hintergrundübertragung (`profile_transfer.py`)

- **Ein Thread**, ein Auftrag zur Zeit; Zustand in einem Modul-Singleton (`TransferState`:
  `running`, `kind`, `label`, `total`, `done`, `written`, `deferred`, `errors`,
  `started_at`), abrufbar über `GET /system/climate/transfer`.
- Vier Arten (`kind`): `mode_switch` (Wechsel der Betriebsart, „Jetzt übertragen"),
  `profile_switch` (Profilwechsel im Raum), `restore` (Zurücksetzen über die
  Änderungshistorie, höchstens 14 Tage je Lauf) und `apartment_switch` (alle Räume auf ein
  Profil: je Raum erst die abweichenden Plan-Tage, dann `ACTIVE_PROFILE` bestätigt; Räume
  nacheinander mit 4 s Pause; höchstens 14 Plan-Tage je Lauf; Abbruch nach drei
  fehlgeschlagenen Räumen in Folge).
- Ein Betriebsartwechsel bricht einen laufenden Auftrag ab; ein Profilwechsel,
  „Jetzt übertragen", ein Zurücksetzen oder die Umschaltung der Wohnung wird bei
  laufendem Auftrag mit **409** abgelehnt.
- **Warum im Hintergrund und begrenzt?** Ein früher, synchroner Ansatz blockierte die
  Anwendung minutenlang und überflutete den Funk (Duty Cycle), bis die CCU Schreibvorgänge
  verweigerte. Deshalb: nie im Request-Thread, ein Tag je Schreibvorgang, Pausen,
  Obergrenze, Abbruch bei Fehlerserien.

### Persistenz

Alle Daten liegen im Ordner `data/`, der als Ganzes nach `/app/app/data` eingebunden wird.
`profile_sets.json`, `profile_names.json` und `change_history.json` werden mit einer Sperre
und an Ort und Stelle geschrieben. `profile_sets.py` legt vor **jedem** Schreiben eine Kopie
des vorherigen Stands als `profile_sets.backup.json` an (eine Generation). Eine fehlende oder
beschädigte Datei wird als „noch keine Daten" behandelt, statt eine Anfrage scheitern zu
lassen.

### Änderungshistorie (`change_history.py`, `routers/history.py`)

- **Live oder Speicher:** `routers/profiles.py` liest und schreibt nur das Profil auf dem
  Gerät, das in der laufenden Betriebsart gerade aktiv ist (`ACTIVE_PROFILE`; nicht
  lesbar = wie früher Gerät). Alle anderen Profile kommen aus dem Speicher und werden dort
  geändert. Beim Kopieren in das laufende Profil aus einem gespeicherten wird der
  gespeicherte Plan geschrieben (nicht der Geräteinhalt des Quellplatzes); beim Kopieren
  des laufenden Profils in einen anderen Platz wird erst dessen Speicherkopie vom Gerät
  aufgefrischt. Grund: Der WTH-1 teilt eine Profiltabelle zwischen Heizen und Kühlen, nicht
  benutzte Plätze können beliebigen Inhalt haben.
- **Protokollieren:** `_with_mirror` in `routers/profiles.py` liest vor jeder Änderung am
  laufenden Profil den Stand des betroffenen Profils vom Thermostat und legt nach dem
  Schreiben einen Eintrag mit diesem Vorher-Stand an (nicht bei wirkungslosen Änderungen).
  `PUT /profile-names/{n}` protokolliert den alten Namen. Beides ist best-effort mit
  Warnung im Log.
- **Zurücksetzen** (`POST /history/{id}/restore`): nimmt den Eintrag und alle neueren. Je
  Profil gilt der Vorher-Stand des **ältesten** betroffenen Eintrags. Namen werden sofort
  zurückgeschrieben; für Profile wird der Unterschied zum Thermostat berechnet und über
  `profile_transfer` (`kind: restore`) geschrieben. Danach wird der Speicher aus den
  Thermostaten neu gespiegelt, auch nach einem Teilerfolg. Die Einträge werden erst bei
  vollem Erfolg entfernt; ein erneutes Zurücksetzen schreibt nur, was noch abweicht.
- **Moduswechsel** löscht alle Profil-Einträge (sie beschreiben die Pläne des anderen
  Modus); Namens-Einträge bleiben. Die gespeicherten Heiz-/Kühlsätze sind davon nicht
  betroffen.

### Abwesenheit (`absence.py`, `apartment.py`)

- `apartment.plan` entscheidet je Raum: nichts zu tun, oder abweichende Plantage plus
  Umschalten, im Schreibbudget; jeder Raum kann ein eigenes Zielprofil haben
  (`RoomSwitch.profile`). „Wohnung“ und Abwesenheit nutzen denselben Weg über
  `profile_transfer.start_apartment_switch`.
- `absence.tick` (eigener Thread, alle 30 s) wartet, solange eine Übertragung läuft. Beim
  Beginn werden die aktiven Profile gemerkt (`previous`), dann wird „sichergestellt“:
  planen, Räume am Ziel überspringen, den Rest umschalten; im nächsten Durchlauf prüfen.
  Sind alle am Ziel oder `MAX_ATTEMPTS` (3) verbraucht, gilt die Phase als erledigt und
  die App greift nicht mehr ein (Handänderungen bleiben). Ab dem Ende dasselbe mit den
  gemerkten Profilen, danach `beendet`.

### Gerätezustand und Funkauslastung (`device_health.py`)

- Läuft in der Hintergrund-Runde der Taupunktüberwachung, jede 5. Runde: Wartungskanal
  `:0` jedes Thermostats und des Aktors (XML-RPC, lokal) und `dutyCycle` der
  Standard-Schnittstelle aus `Interface.listBidcosInterfaces` (JSON-RPC).
- `profile_transfer._execute_plan` liest den Duty Cycle vor jedem 4. Schreibvorgang mit
  dem eigenen Client. Ab `DUTY_CYCLE_LIMIT` hält es an, schiebt den Rest auf und meldet den
  Grund; ist der Wert nicht lesbar, wird nicht gebremst (der Fehlerschutz nach drei
  Fehlern bleibt).

### Taupunktüberwachung (`dew_point.py`, `flow_sensor.py`)

- `flow_sensor` abonniert `MQTT_FLOW_TOPIC` (nur wenn `MQTT_HOST` gesetzt ist) und hält
  den letzten Wert mit Empfangszeit; paho verbindet sich bei Abbrüchen selbst neu.
- Ein Hintergrund-Thread liest jede Minute Betriebsart, Temperatur, Feuchte und
  Ventilstellung aller Räume (nur XML-RPC, kein Funk; Gerätezuordnung alle 10 Minuten
  neu) und legt einen **Schnappschuss** ab, den `GET /system/dew-point` ausliefert.
- Taupunkt nach Magnus (Konstanten 17,62 / 243,12 °C). Vergleichswert ist der Vorlauf,
  aber nur, wenn er **nach** mindestens `FLOW_SETTLE_MINUTES` Durchfluss (ein Ventil
  ≥ 10 %) gemessen wurde; sonst der letzte solche Wert (höchstens 48 h alt). Räume mit
  geschlossenem Ventil zählen nicht zur Gesamtlage. Gültige Vorlaufwerte werden nur im
  Kühlbetrieb gemerkt und beim Wechsel auf Heizen verworfen (warmes Heizwasser darf nach
  dem Umschalten nicht als Vergleichswert dienen).
- Reine Anzeige: es wird nichts geschaltet.
- Nach jeder Runde sendet `ha_publish` den Schnappschuss als ein JSON-Dokument
  (retained) an `ccu-dashboard/state`; die Discovery-Anmeldungen (retained) gehen nach
  jedem Verbindungsaufbau und bei geänderter Raumliste. `flow_sensor` setzt dafür einen
  Last Will (`ccu-dashboard/status` = `offline`) und meldet nach dem Verbinden `online`.

### Automatisches Umschalten (`climate_schedule.py`, `climate_switch.py`)

- `climate_switch.switch` ist der eine Weg zum Umschalten (Aktivprofile merken, Aktor
  umschalten, Übertragung starten, Profil-Historie leeren), mit Sperre; genutzt von
  `PATCH /system/climate` und vom Zeitplan.
- Ein Hintergrund-Thread (gestartet im `lifespan` von `main.py`) ruft alle 30 s `tick`
  auf. Fällig ist der **letzte vergangene** Zeitpunkt, eingeschaltet oder nicht; ist er
  neuer als `last_handled`, wird er einmal behandelt und `last_handled` gesetzt: ist er
  eingeschaltet, wird umgeschaltet (oder festgestellt, dass es schon so steht), sonst
  nichts (ein ausgeschalteter Zeitpunkt beendet nur die Saison des anderen). Dadurch werden verpasste Zeitpunkte nach einem Neustart
  nachgeholt, und ein Handwechsel danach bleibt bestehen. Speichern des Plans setzt
  `last_handled` auf „jetzt“. Bei CCU-Fehlern bleibt `last_handled` stehen (neuer
  Versuch beim nächsten Tick).
- Der Thread holt sich eigene CCU-Clients und eine frische Gerätezuordnung, statt die
  Singletons der Anfragen mitzubenutzen. Zeitrechnung mit `zoneinfo` (`SCHEDULE_TZ`,
  Zeitzonendaten aus dem Python-Paket `tzdata`), unabhängig von der Container-Zeitzone.

### Tägliche Sicherung (`auto_backup.py`)

- Ein Hintergrund-Thread prüft alle 5 Minuten: Ist `AUTO_BACKUP_HOUR` (Ortszeit von
  `SCHEDULE_TZ`) vorbei und fehlt `backups/ccu-auto-<heute>.json`, wird sie geschrieben
  (erst in eine `.tmp`-Datei, dann umbenannt) und alles über `AUTO_BACKUP_KEEP` gelöscht.
  Dadurch wird eine verpasste Nacht beim Start nachgeholt.
- `GET /backups/{name}` löst nur Namen nach den festen Mustern `ccu-auto-…` und
  `vor-import-…` auf, keine Pfade.

### Export und Import (`backup_data.py`, `routers/backup.py`)

- **Prüfen** (`check`) läuft immer vollständig durch und sammelt alle Fehler mit
  Fundstelle, mit denselben Regeln wie beim Bearbeiten (`schedule.validate_blocks`,
  höchstens 13 Abschnitte, Sollwertgrenzen, Profile 1–6). Unbekannte Schlüssel sind Fehler.
  Der Abgleich mit den Räumen der CCU erzeugt nur Hinweise.
- **Einspielen** nur bei fehlerfreier Datei und ohne laufende Übertragung: erst
  `vor-import-….json` schreiben, dann `profile_sets.replace_all` (mit der üblichen
  Backup-Generation), `profile_names.replace_all`, Ventil-Zuordnung speichern und in der
  `CachedDeviceMap` ersetzen, `change_history.clear()`, zuletzt
  `profile_transfer.start` für die aktive Betriebsart.

### Ventilstellung

Kommt aus den Aktorkanälen (Zuordnung in `data/valve_channels.json`, Pfad über
`VALVE_CHANNELS_FILE`), Mittelwert je Raum, gelesen per XML-RPC (lokal, kein Funk). Die
Raumliste liest sie mit (`valve=True`), ohne den Wartungskanal.

### Best-Effort-Regeln und Logging

An Stellen, an denen ein Fehler eine erfolgreiche Schreiboperation nicht scheitern lassen
soll (Spiegeln in den Speicher, Erstbefüllung, Merken des aktiven Profils), fängt der
Code den Fehler ab **und protokolliert ihn als `WARNING`** (siehe
[Betrieb 4.4](04-betrieb-und-wartung.md#44-logs-und-überwachung)). Stilles Verschlucken ist
per Lint-Regel (`S110`/`S112`) untersagt.

## 6.5 Frontend im Detail

**Technik:** React 18, TypeScript 4.9, Vite, react-router-dom 7, @tanstack/react-query 5,
axios, Chart.js (react-chartjs-2), Iconify.

### Routen

| Pfad | Bildschirm |
|---|---|
| `/` | Raumübersicht |
| `/room/:raum` | Raumdetail |
| `/settings` | Einstellungen |
| `/settings/devices`, `/settings/devices/:id` | Geräteliste, Gerätedetail |
| `/settings/theme` | Design |
| `/settings/history` | Änderungshistorie |
| `/settings/backup` | Datensicherung: Export und Import |
| `/settings/dew-point` | Taupunktüberwachung |
| `/settings/valves` | Ventilverlauf |
| `/settings/heating-profiles` | Heizprofile: alle Räume |
| `/settings/heating-profiles/:raum/:profil` | Profilseite (z. B. `P1`), mit `?mode=heating\|cooling` |
| `…/:tag` | Tag eines Profils |
| `…/:tag/:index`, `…/:tag/add` | Zeitabschnitt ändern bzw. hinzufügen |

Der Parameter `mode` wird durch die ganze Kette bis zu den API-Aufrufen gereicht, damit die
Bearbeitung im gewählten Modus bleibt.

### Datenzugriff (react-query)

Alle Serverdaten laufen über Hooks in `src/hooks/`. Standardwerte: `staleTime` 10 s,
Neuladen beim Fokussieren des Fensters, 1 Wiederholung.

| Hook | Schlüssel | Besonderheit |
|---|---|---|
| `useRooms` | `["rooms"]` | Abfrage alle 15 s |
| `useRoom`, `usePatchRoom` | `["rooms", name]` | Nach dem Schreiben wird der Cache direkt aktualisiert; bei Profilwechsel wird die Übertragung beobachtet |
| `useProfiles`, `useProfile` | `["profiles", raum, (profil,) modus]` | Modus ist Teil des Schlüssels |
| `useAddBlock`, `useClearBlock`, `useCopyProfile` | – | Die Antwort (aktualisierte Woche) wird direkt in den Cache geschrieben |
| `useProfileNames`, `useSetProfileName` | `["profileNames"]` | 5 Minuten aktuell |
| `useClimate`, `useSetClimate` | `["climate"]` | – |
| `useClimateTransfer` | `["climateTransfer"]` | Abfrage alle 2 s **nur während** eine Übertragung läuft |
| `useContinueTransfer` | – | „Jetzt übertragen" |
| `useDevices` | `["devices"]` | – |
| `useHistory`, `useRestoreHistory` | `["history"]` | Beim Öffnen der Seite immer neu geladen; nach einem Zurücksetzen werden Historie, Profile, Profilnamen und Übertragung neu geladen |

### Komponenten (Auswahl)

| Komponente | Aufgabe |
|---|---|
| `RoomOverview`, `RoomDetail` | Übersicht und Raumdetail (mit `TemperatureDial`, `ValveBar`) |
| `Settings`, `Devices`, `DeviceDetail`, `ThemeSettings` | Einstellungsbereich |
| `HeatingProfiles`, `HeatingProfileDetail`, `HeatingProfileDayDetail` | Profilübersicht, Profilseite, Tagesseite |
| `TimeBlockAdd`, `TimeBlockDetail` | Zeitabschnitt hinzufügen bzw. ändern (Zeiträder) |
| `ProfileDayChart` | Tagesgrafik im 5-Minuten-Raster |
| `TransferBanner` | Hinweisbalken der Hintergrundübertragung (App-weit) |
| `ChangeHistory` | Änderungshistorie mit Zurücksetzen |
| `BusyOverlay`, `ConfirmRow` | Wartesperre beim Speichern; Zurück/Haken-Zeile |
| `TemperatureDial` | Eigener Drehregler (SVG), 270°-Bogen |

### Themen und Stile

- Ein einziges Stylesheet (`styles/styles.css`); jedes Thema ist eine CSS-Klasse
  (`theme-dark`, `theme-wald`, …) auf `<html>`, die **CSS-Variablen** setzt (Farben,
  Diagrammfarben, Hintergrund).
- Der Erhaben-Effekt ist eine zweite Klasse (`elev-light`, `elev-strong`), die Schatten- und
  Verlaufsvariablen überschreibt. Der Glanz ist eine dritte, unabhängige Klasse
  (`gloss-on`), die einen Reflex über den Erhaben-Verlauf legt.
- **Breite Bildschirme:** Ab 600 px mehrspaltiges Raster; Inhalt maximal 1200 px und
  zentriert; Kopfleiste über alle Spalten; Zusatzklassen `equal-height` und `center-cards`
  für gleich hohe Kacheln.
- Im Browser gespeichert (`localStorage`, pro Gerät): `theme`, `elevation`, `gloss`,
  `transferBannerDismissed`.

## 6.6 Fehlerbehandlung

Das Backend übersetzt Fehler der CCU-Schicht in einheitliches JSON
`{"error": {"type": "<kürzel>", "message": "<text>"}}`:

| Ausnahme | HTTP | `type` | Bedeutung |
|---|---|---|---|
| `RoomNotFound` | 404 | `room_not_found` | Kein Thermostat mit diesem Raumnamen |
| `CcuBusy` | 409 | `busy` | Eine Übertragung läuft |
| `CcuValidationError` | 422 | `validation_error` | Ungültiger Wert (Solltemperatur, Profil, Zeitplan …) |
| `CcuUnreachable` | 503 | `ccu_unreachable` | CCU nicht erreichbar (Netz, Zeitüberschreitung) |
| `CcuError` (sonst) | 502 | `ccu_error` | CCU hat abgelehnt, ungültig geantwortet oder nicht bestätigt |

Schema-Fehler von FastAPI (falsche Typen im Anfragekörper) liefern 422 mit dem Feld
`detail`. Das Frontend zeigt die Meldung an (`apiErrorMessage`) und protokolliert Einzelheiten
in der Browser-Konsole (`logApiError`).

## 6.7 Wichtige Entwurfsentscheidungen

1. **Beide CCU-Schnittstellen sind nötig**, weil keine allein alles kann.
2. **Gerät ist die Wahrheit für die aktive Betriebsart**, der Speicher für die inaktive.
3. **Jeder Schreibvorgang wird bestätigt.** Ein unbestätigtes Schreiben führte bereits zu
   einem stillen Abweichen von Speicher und Gerät.
4. **Funk ist ein knappes Gut.** Alles, was Pläne schreibt, ist gebremst, begrenzt und im
   Hintergrund.
5. **Keine Datenbank.** Wenige, kleine JSON-Dateien genügen für eine Anlage und bleiben von
   Hand les- und reparierbar.
6. **Kein Login.** Bewusst einfach gehalten für das Heimnetz.
7. **Die Heizungsregelung bleibt bei den Geräten.** Die Anwendung ist nur Bedienoberfläche
   und Datenverwaltung; ihr Ausfall stoppt die Heizung nicht.

## 6.8 Betrieb: Container und `deploy.sh`

- **Neustart-Verhalten:** Beide Container haben `restart: always`. Beim Herunterfahren
  stoppt systemd den Docker-Dienst und damit jeden Container per SIGTERM; Docker wertet das
  wie ein bewusstes `docker stop`. Mit `unless-stopped` blieben die Container nach einem
  Neustart des Servers deshalb aus (so geschehen vor v0.17.0).
- **Healthchecks:** Das Backend prüft `http://localhost:8000/system/health`, das Dashboard
  `http://127.0.0.1/`. `localhost` löst im Dashboard-Container zuerst nach IPv6 auf, nginx
  lauscht aber nur auf IPv4.
- **`deploy.sh` ist zweistufig.** Stufe 1 holt den Stand (`git fetch`, `git checkout -f`)
  und startet das Skript dann per `exec` neu. Grund: `git checkout -f` kann `deploy.sh`
  selbst ersetzen, bash liest aber aus dem bereits geöffneten, alten Dateiinhalt weiter.
  Ohne Neustart liefe der Rest mit veraltetem Code. Stufe 2 legt fehlende Dateien in
  `data/` an, baut und startet die Container und wartet auf den Health-Check.
- **Datenordner statt Einzeldateien:** Früher waren drei Dateien einzeln eingebunden;
  fehlte eine, legte Docker sie als Verzeichnis an. Ein eingebundener Ordner hat dieses
  Problem nicht und liegt außerhalb dessen, was Git verwaltet.
