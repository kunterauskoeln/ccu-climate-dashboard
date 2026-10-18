# 7 API-Referenz

Das Backend bietet eine JSON-API. Im Betrieb erreichst du sie über den nginx-Proxy unter
**`http://<server>:3000/api/…`**. (Direkt am Backend, Port 8000, ohne das Präfix `/api`, ist
sie nur im Docker-Netz erreichbar.)

Eine **interaktive Dokumentation** (Swagger UI) mit allen Endpunkten und Modellen liefert die
Anwendung selbst:

- `http://<server>:3000/api/docs`: ausprobierbare Oberfläche
- `http://<server>:3000/api/openapi.json`: maschinenlesbare Beschreibung

**Es gibt keine Anmeldung.** Alle Endpunkte sind für jeden im Netz erreichbar.

Alle Beispiele setzen `BASE=http://localhost:3000/api` voraus:
```bash
BASE=http://localhost:3000/api
```

## 7.1 Übersicht

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/system/health` | Zustand der CCU-Verbindung und der Hintergrundaufgaben |
| GET | `/system/climate` | Aktuelle Betriebsart (Heizen/Kühlen) |
| PATCH | `/system/climate` | Betriebsart umschalten, startet die Übertragung |
| GET | `/system/climate/transfer` | Fortschritt der Hintergrundübertragung |
| POST | `/system/climate/transfer` | Aufgeschobene Tage nachziehen |
| GET | `/system/dew-point` | Taupunktüberwachung (Schnappschuss, jede Minute neu) |
| GET | `/system/device-health` | Gerätezustand und Funkauslastung (alle 5 Minuten neu) |
| GET | `/system/valve-history` | Ventilstellungen der letzten Stunden (`?hours=48`, höchstens 72) |
| GET | `/system/absence` | Geplante oder laufende Abwesenheit |
| PUT | `/system/absence` | Abwesenheit planen oder ändern |
| DELETE | `/system/absence` | Geplante verwerfen bzw. laufende sofort beenden |
| GET | `/system/climate/schedule` | Zeitplan für das automatische Umschalten |
| PUT | `/system/climate/schedule` | Zeitplan speichern |
| POST | `/system/active-profile` | Alle Räume auf ein Profil umschalten („Wohnung“) |
| GET | `/rooms` | Alle Räume (Kurzstatus mit Ventilstellung) |
| GET | `/rooms/{raum}` | Ein Raum mit vollem Status |
| PATCH | `/rooms/{raum}` | Solltemperatur, Modus, aktives Profil, Boost |
| GET | `/rooms/{raum}/profiles` | Alle 6 Profile eines Raumes |
| GET | `/rooms/{raum}/profiles/{profil}` | Ein Profil (Woche) |
| POST | `/rooms/{raum}/profiles/{profil}/days/{tag}/blocks` | Zeitabschnitt setzen |
| DELETE | `/rooms/{raum}/profiles/{profil}/days/{tag}/blocks` | Zeitabschnitt löschen |
| POST | `/rooms/{raum}/profiles/{profil}/copy` | Profil, Tag oder Tage kopieren |
| GET | `/profile-names` | Profilnamen |
| PUT | `/profile-names/{profil}` | Profil umbenennen |
| GET | `/history` | Änderungshistorie |
| POST | `/history/{id}/restore` | Bis zu diesem Eintrag zurücksetzen |
| GET | `/devices` | Geräteliste |
| GET | `/export` | Alle Daten der App als Datei |
| GET | `/backups` | Gespeicherte Sicherungen (täglich und vor Importen) |
| POST | `/backups` | Sicherung des heutigen Tages sofort anlegen |
| GET | `/backups/{name}` | Eine gespeicherte Sicherung herunterladen |
| POST | `/import` | Export-Datei prüfen (`?apply=true`: einspielen) |
| GET | `/` | Lebenszeichen des Backends |

`{raum}` ist der Raumname (URL-kodiert, z. B. `Wohnzimmer`), `{profil}` eine Zahl 1 bis 6,
`{tag}` ein Wochentag (`MONDAY` … `SUNDAY`, Groß-/Kleinschreibung egal).

Der Live-Ereignisstrom `/events/heating` ist im Code vorbereitet, aber **nicht
eingebunden** und nicht verfügbar.

## 7.2 Fehlerformat

Fehler der CCU-Schicht haben immer diese Form:
```json
{ "error": { "type": "ccu_error", "message": "profile P3 was not confirmed active" } }
```

| HTTP | `type` | Bedeutung |
|---|---|---|
| 404 | `room_not_found` | Unbekannter Raum |
| 409 | `busy` | Eine Übertragung läuft schon |
| 422 | `validation_error` | Ungültiger Wert oder Zeitplan |
| 503 | `ccu_unreachable` | CCU nicht erreichbar |
| 502 | `ccu_error` | CCU hat abgelehnt oder nicht bestätigt |

Schemafehler (fehlendes Feld, falscher Typ) liefert FastAPI als 422 mit
`{"detail": [{"loc": [...], "msg": "..."}]}`.

## 7.3 System

### `GET /system/health`
```bash
curl -s $BASE/system/health
```
```json
{
  "status": "ok", "ccu": "ok", "uptime": 86400, "ccu_host": "192.168.1.10",
  "mqtt": "verbunden", "dew_point": "aus", "devices": "Alle Geräte in Ordnung.",
  "backup": "ccu-auto-2026-10-07.json", "backup_error": null
}
```
`ccu` ist `"ok"` oder `"unreachable"`. `status` ist `"degraded"`, wenn die CCU nicht
erreichbar ist; nur davon hängt der Healthcheck des Containers ab. Der HTTP-Status ist
immer 200. Die übrigen Felder sind zur Information: MQTT-Verbindung (oder
`nicht eingerichtet`), Taupunkt-Lage, Gerätezustand, letzte automatische Sicherung und
deren letzter Fehler.

### `GET /system/climate`
```json
{ "cooling": false, "actuator": "000BBBB0000001" }
```
`cooling` ist `true` bei Kühlen. `actuator` ist die Adresse des erkannten Aktors (oder `null`).

### `PATCH /system/climate`
```bash
curl -s -X PATCH $BASE/system/climate -H 'Content-Type: application/json' -d '{"cooling": true}'
```
Schaltet den Aktor um (wartet auf die Bestätigung, bis ca. 15 s), merkt das aktive Profil je
Raum und startet die **Hintergrundübertragung**. Die Antwort ist der neue `ClimateState`.
Ist die gewünschte Betriebsart schon aktiv, passiert nichts.

### `GET /system/climate/transfer`
```json
{
  "running": true,
  "mode": "cooling",
  "kind": "mode_switch",
  "label": null,
  "started_at": 1790330000.5,
  "total": 8,
  "done": 3,
  "written": ["Wohnzimmer P4 Montag", "Wohnzimmer P4 Dienstag"],
  "deferred": ["Bad P1 Freitag"],
  "errors": []
}
```
| Feld | Bedeutung |
|---|---|
| `running` | Ein Auftrag läuft |
| `mode` | `"heating"` oder `"cooling"` (Betriebsart des Auftrags) |
| `kind` | `"mode_switch"` (Wechsel der Betriebsart, „Jetzt übertragen"), `"profile_switch"` (Profilwechsel im Raum) `"restore"` (Zurücksetzen über die Änderungshistorie) oder `"apartment_switch"` (alle Räume auf ein Profil); `null`, wenn noch nie ein Auftrag lief |
| `label` | Bei `profile_switch`: `"Raum P3"`; bei `restore`: `"Änderungen zurücksetzen"` |
| `started_at` | Startzeit (Sekunden seit 1970), kennzeichnet den Lauf |
| `total`, `done` | Geplante und erledigte Tage |
| `written` | Erfolgreich geschriebene Tage (`"Raum Pn Tag"`) |
| `deferred` | Aufgeschobene Tage (über der Obergrenze oder nach Fehlerserie) |
| `errors` | Fehlermeldungen |

Der Zustand liegt im Speicher und bleibt bis zum nächsten Auftrag oder Neustart erhalten.

### `POST /system/climate/transfer`
Startet einen neuen Auftrag für die aktuelle Betriebsart (die nächsten abweichenden Tage
des aktiven Profils je Raum, höchstens 8). Antwort: der `TransferState`. **409**, wenn
schon ein Auftrag läuft.

### `GET /system/valve-history`
```json
{
  "times": [1791000000.0, 1791000300.0, 1791000600.0],
  "rooms": { "Bad": [40, null, 55], "Wohnzimmer": [62, null, 60] }
}
```
`times` in Sekunden seit 1970, ein Punkt alle 5 Minuten; je Raum die Öffnung in Prozent.
`null` markiert eine Pause der Aufzeichnung (die App lief nicht). **422** bei `hours`
außerhalb von 0 bis 72.

### `GET /system/absence`
```json
{
  "phase": "aktiv", "profile": 2, "profile_name": "Urlaub",
  "start": "2026-10-10T08:00+02:00", "end": "2026-10-18T16:00+02:00",
  "previous": { "Bad": 3, "Wohnzimmer": 1 },
  "applied": true, "message": "Abwesenheit: Urlaub: alle Räume umgeschaltet"
}
```
`phase`: `aus`, `geplant`, `aktiv`, `rueckkehr`, `beendet`, `abgebrochen`. `previous`:
das Profil je Raum vor der Abwesenheit (gefüllt ab Beginn). `applied`: die Umschaltung der
aktuellen Phase ist erledigt.

### `PUT /system/absence`
```bash
curl -s -X PUT -H 'Content-Type: application/json' $BASE/system/absence \
  -d '{"profile": 2, "start": "2026-10-10T08:00", "end": "2026-10-18T16:00"}'
```
`start` weglassen oder `null`: sofort. Zeiten ohne Zeitzone gelten als Ortszeit
(`SCHEDULE_TZ`). Bei einer laufenden Abwesenheit werden nur `end` und `profile`
übernommen. **422**: Ende nicht in der Zukunft, Ende vor dem Beginn, unlesbare Zeit, Rückkehr
läuft gerade. Antwort wie `GET`.

### `DELETE /system/absence`
Geplant → `abgebrochen`; laufend → Ende auf jetzt, die Räume gehen beim nächsten Durchlauf
(≤ 30 s) zurück. **422**, wenn nichts geplant ist oder läuft.

### `GET /system/device-health`
```json
{
  "at": 1790950000.0, "ccu_duty_cycle": 12, "level": "warnung",
  "message": "Geräte: Bad: Batterie schwach (2,2 V)",
  "problems": ["Bad: Batterie schwach (2,2 V)"],
  "devices": [
    { "name": "Bad", "address": "0039…", "kind": "thermostat", "reachable": true,
      "low_battery": true, "voltage": 2.2, "rssi": -60, "duty_cycle": false, "config_pending": false },
    { "name": "Aktor", "address": "000BBBB0000001", "kind": "aktor", "reachable": true,
      "low_battery": null, "voltage": null, "rssi": -43, "duty_cycle": false, "config_pending": false }
  ]
}
```
`ccu_duty_cycle` kommt aus `Interface.listBidcosInterfaces` (`null`, wenn nicht lesbar),
die Gerätewerte vom Wartungskanal `:0`. `reachable: null` heißt: nicht lesbar.
`low_battery: null`: Gerät ohne Batterie.

### `GET /system/dew-point`
```json
{
  "at": 1790880300.2, "cooling": true, "level": "knapp",
  "message": "Taupunkt knapp: Bad (+1,9 K)",
  "warn_margin": 3.0, "alarm_margin": 1.0,
  "flow": { "configured": true, "connection": "verbunden", "topic": "…/state",
            "value": 18.0, "received_at": 1790880120.0, "stale": false,
            "effective": 18.0, "source": "live",
            "last_valid": 18.0, "last_valid_at": 1790880120.0, "flowing_since": 1790876700.0 },
  "rooms": [
    { "room": "Bad", "temperature": 24.1, "humidity": 60, "dew_point": 16.1,
      "valve": 1.0, "margin": 1.9, "status": "knapp" }
  ]
}
```
- `level`: `aus` (Heizbetrieb), `ok`, `unbekannt`, `knapp`, `gefahr` (schlechtester Raum
  mit offenem Ventil).
- `rooms[].status`: zusätzlich `ventil_zu`. `margin` = Vorlauf − Taupunkt in K.
- `flow.source`: `live` (gemessen nach `FLOW_SETTLE_MINUTES` Durchfluss), `last_valid`
  (letzter solcher Wert) oder `null`. Zeitangaben in Sekunden seit 1970.

### `GET /system/climate/schedule`
```json
{
  "heating": { "day": 15, "month": 9, "time": "08:00", "enabled": false },
  "cooling": { "day": 15, "month": 5, "time": "07:30", "enabled": true },
  "next": { "at": "2027-05-15T07:30+02:00", "cooling": true },
  "last_run": { "at": "2026-09-15T08:00:12+02:00", "due": "2026-09-15T08:00+02:00",
                "cooling": false, "result": "switched", "message": "Auf Heizen umgeschaltet." },
  "timezone": "Europe/Berlin"
}
```
Die Zeitpunkte wiederholen sich jährlich (Ortszeit von `SCHEDULE_TZ`); `enabled` je
Zeitpunkt schaltet das automatische Umschalten in diese Richtung ein. `heating`/`cooling`
sind `null`, solange nie gespeichert. `next` ist der nächste eingeschaltete Zeitpunkt,
`null`, wenn beide aus sind. `last_run.result`: `switched`, `already` (stand schon so) oder
`error` (wird alle 30 s wiederholt).

### `PUT /system/climate/schedule`
```bash
curl -s -X PUT -H 'Content-Type: application/json' $BASE/system/climate/schedule \
  -d '{"heating": {"day": 15, "month": 9, "time": "08:00", "enabled": false},
       "cooling": {"day": 15, "month": 5, "time": "07:30", "enabled": true}}'
```
Antwort wie `GET`. **422** bei unmöglichen Daten (31.04., 24:00) oder zwei gleichen
Zeitpunkten. Zeitpunkte bis zum Speichern gelten als erledigt; es wird also nicht sofort
umgeschaltet.

### `POST /system/active-profile`
Schaltet alle Räume auf denselben Profilplatz („Wohnung“):
```bash
curl -s -X POST $BASE/system/active-profile -H 'Content-Type: application/json' -d '{"profile": 3}'
```
```json
{ "rooms": 6, "skipped": 1, "deferred": 0, "background": true }
```
| Feld | Bedeutung |
|---|---|
| `rooms` | Räume, die in diesem Lauf umgeschaltet werden |
| `skipped` | Räume, die schon auf dem Profil stehen |
| `deferred` | Räume, deren abweichende Plan-Tage nicht mehr in die Obergrenze (14 je Lauf) passten; danach erneut aufrufen |
| `background` | `true`: Umschaltung läuft, Fortschritt über `GET /system/climate/transfer` (`kind: apartment_switch`, `label` z. B. `"Wohnung: Nacht"`) |

Je Raum wird erst der gespeicherte Plan übertragen, wo er vom Thermostat abweicht, dann das
Profil bestätigt umgeschaltet; scheitert der Plan, bleibt der Raum auf seinem Profil.
`profile` muss 1 bis 6 sein (sonst **422**); **409**, wenn schon eine Übertragung läuft.

## 7.4 Räume

### `RoomState`
```json
{
  "room": "Wohnzimmer",
  "actual_temperature": 22.3,
  "set_temperature": 21.0,
  "humidity": 48,
  "mode_code": 0,
  "mode": "AUTO",
  "active_profile": 1,
  "window_open": false,
  "boost": false,
  "cooling": false,
  "valve": 0.35,
  "battery_low": false,
  "voltage": 2.9,
  "rssi": -48,
  "reachable": true
}
```
| Feld | Bedeutung |
|---|---|
| `mode_code`, `mode` | 0 `AUTO`, 1 `MANU`, 2 `PARTY`, 3 `BOOST` |
| `active_profile` | 1 bis 6 |
| `valve` | Ventilöffnung als Bruchteil **0 bis 1** (Mittelwert der Aktorkanäle des Raumes); `null`, wenn unbekannt |
| `battery_low`, `voltage`, `rssi`, `reachable` | Nur im **Einzelabruf** (`/rooms/{raum}`) gefüllt; in der Liste sind es Standardwerte (`false`, `null`, `null`, `true`) |
| `null`-Werte | Bedeuten „nicht bekannt" (Gerät nicht erreichbar). Nie als 0 darstellen |

### `GET /rooms`
Liste aller Räume als `RoomState[]` (Kurzform mit `valve`, ohne Batterie/Funkdaten).
Momentan ausfallende Räume werden übersprungen.

### `GET /rooms/{raum}`
```bash
curl -s $BASE/rooms/Wohnzimmer
```
Ein `RoomState` mit allen Feldern. 404 bei unbekanntem Raum.

### `PATCH /rooms/{raum}`
Alle Felder optional, **mindestens eines** ist nötig (sonst 422):

| Feld | Werte | Wirkung |
|---|---|---|
| `setpoint` | 4,5 bis 30,5 (°C) | Solltemperatur setzen (schaltet den Raum in `MANU`) |
| `mode` | 0 bis 3 | Modus setzen |
| `active_profile` | 1 bis 6 | Aktives Profil (siehe unten) |
| `boost` | `true`/`false` | Boost |

```bash
curl -s -X PATCH $BASE/rooms/Wohnzimmer -H 'Content-Type: application/json' \
  -d '{"mode": 0, "active_profile": 2}'
```
Reihenfolge: erst `mode`, dann `active_profile`, `boost`, `setpoint` (ein Sollwert würde
sonst den Modus auf `MANU` zwingen). Die Antwort ist der Raumzustand **nach** den
Änderungen.

**`active_profile`:** Stimmt der gespeicherte Plan mit dem Thermostat überein (oder ist
keiner gespeichert), wird sofort umgeschaltet und **bestätigt** (sonst 502, nichts wird
gemerkt). Weicht er ab, startet ein **Hintergrundauftrag** (`kind: profile_switch`):
Tage schreiben, danach umschalten. Die Antwort zeigt dann noch das **alte** Profil; den
Fortschritt liefert `GET /system/climate/transfer`. Läuft schon ein Auftrag: **409**.

## 7.5 Profile

Profile sind **Wochen**: je Wochentag eine lückenlose Liste von Zeitabschnitten von 00:00
bis 24:00.

```json
{
  "profile": 1,
  "days": {
    "monday": [
      { "start": "00:00", "end": "06:00", "setpoint": 17.0 },
      { "start": "06:00", "end": "22:00", "setpoint": 21.5 },
      { "start": "22:00", "end": "24:00", "setpoint": 17.0 }
    ],
    "tuesday": [ ... ]
  }
}
```
Alle Endpunkte dieses Abschnitts akzeptieren den Abfrageparameter **`?mode=heating`** oder
**`?mode=cooling`**:
- **ohne** `mode` oder mit der **aktiven** Betriebsart: Arbeit am Thermostat (Lesen aus dem
  Gerät, Schreiben mit Bestätigung und Spiegeln in den Speicher);
- mit der **inaktiven** Betriebsart: nur der gespeicherte Satz, **ohne CCU-Zugriff**.

### `GET /rooms/{raum}/profiles`
```json
{ "active": 1, "profiles": { "1": { "profile": 1, "days": { ... } }, "2": { ... } } }
```
Alle 6 Profile und das aktive. Beim Thermostat: ein Lesezugriff auf den MASTER-Parametersatz.

### `GET /rooms/{raum}/profiles/{profil}`
Eine Woche (`WeekProfile`).

### `POST /rooms/{raum}/profiles/{profil}/days/{tag}/blocks`
Setzt einen Zeitabschnitt (**überschreibt** den Zeitraum, kürzt Nachbarn, fasst gleiche
zusammen). Körper:
```json
{ "start": "08:00", "end": "08:30", "setpoint": 23.5 }
```
`start`/`end` als `HH:MM` (`24:00` ist als Ende erlaubt), `setpoint` 4,5 bis 30,5.
Antwort: die aktualisierte Woche. Bei der aktiven Betriebsart dauert der Aufruf, bis der
Thermostat bestätigt hat (bis ca. 25 s).

```bash
curl -s -X POST "$BASE/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks" \
  -H 'Content-Type: application/json' -d '{"start":"08:00","end":"08:30","setpoint":23.5}'
```
422, wenn der Plan ungültig würde (zum Beispiel mehr als 13 Zeitabschnitte an einem Tag).

### `DELETE /rooms/{raum}/profiles/{profil}/days/{tag}/blocks`
Löscht den Zeitabschnitt `[start, end)`; die Lücke erbt die Temperatur des davor liegenden
Abschnitts (am Tagesanfang des folgenden). Körper: `{"start": "08:00", "end": "08:30"}`.

### `POST /rooms/{raum}/profiles/{profil}/copy`
Kopiert das Quellprofil aus der URL:

| Körper | Wirkung |
|---|---|
| `{"to_profile": 3}` | Ganze Woche in Profil 3 desselben Raumes |
| `{"to_room": "Bad", "to_profile": 1}` | Ganze Woche in Profil 1 des Raumes Bad |
| `{"to_profile": 1, "from_day": "MONDAY", "to_day": "TUESDAY"}` | Ein Tag auf einen anderen |
| `{"to_profile": 1, "from_day": "MONDAY", "to_days": ["TUESDAY", "WEDNESDAY"]}` | Ein Tag auf mehrere |

`to_room` ist optional (Standard: derselbe Raum). Antwort: die geschriebene Ziel-Woche.

## 7.6 Profilnamen

### `GET /profile-names`
```json
{ "1": "Standard", "2": "Urlaub", "3": "Nacht", "4": "Homeoffice", "5": "Wochenende", "6": "Individuell" }
```
Ein Name je Profilplatz, **für alle Räume gleich**.

### `PUT /profile-names/{profil}`
```bash
curl -s -X PUT $BASE/profile-names/2 -H 'Content-Type: application/json' -d '{"name":"Urlaub"}'
```
Körper `{"name": "..."}` (1 bis 64 Zeichen). Antwort: `{"profile": 2, "name": "Urlaub"}`.

## 7.7 Änderungshistorie

### `GET /history`
Die erfassten Änderungen, **neueste zuerst**:
```json
[
  { "id": "1868c2f0a3b1e400", "at": "2026-09-28T11:42:05+00:00", "kind": "name",
    "mode": null, "room": null, "profile": 2,
    "summary": "Name P2: „Urlaub“ → „Winterurlaub“" },
  { "id": "1868c2e8d7f02c00", "at": "2026-09-28T11:40:13+00:00", "kind": "profile",
    "mode": "heating", "room": "Wohnzimmer", "profile": 1,
    "summary": "Montag: 15:00–16:00 auf 19,0 °C" }
]
```
| Feld | Bedeutung |
|---|---|
| `id` | Kennung des Eintrags |
| `at` | Zeitpunkt (ISO 8601, UTC) |
| `kind` | `"profile"` (Profiländerung im aktiven Modus) oder `"name"` (Umbenennung) |
| `mode`, `room` | Nur bei `profile`: Modus und Raum |
| `profile` | Profilplatz 1 bis 6 |
| `summary` | Beschreibung der Änderung |

Der gespeicherte Vorher-Stand ist nicht Teil der Antwort.

### `POST /history/{id}/restore`
Nimmt den Eintrag `{id}` **und alle neueren** zurück.
```json
{ "names": 1, "profiles": 2, "days": 3, "deferred": 0, "background": true }
```
| Feld | Bedeutung |
|---|---|
| `names` | Sofort zurückgesetzte Profilnamen |
| `profiles` | Betroffene Raum-Profile |
| `days` | In diesem Lauf zu schreibende Profil-Tage |
| `deferred` | Tage über der Obergrenze (14 je Lauf); danach denselben Eintrag erneut zurücksetzen |
| `background` | `true`: Tage werden im Hintergrund geschrieben, Fortschritt über `GET /system/climate/transfer` (`kind: restore`) |

Die Einträge werden erst entfernt, wenn alles zurück ist. **409**, wenn schon eine
Übertragung läuft; **422**, wenn es den Eintrag nicht (mehr) gibt.

## 7.8 Geräte

### `GET /devices`
```json
[ { "id": "003924…", "name": "Wohnzimmer", "address": "003924…",
    "type": "HmIP-WTH-1", "interface": "HmIP-RF" } ]
```
Alle Geräte der CCU außer den virtuellen Heizgruppen (`HmIP-HEATING`).

## 7.9 Export

### `GET /export`
```bash
curl -s -OJ $BASE/export        # speichert ccu-export-<datum>.json
```
Antwort mit `Content-Disposition: attachment; filename="ccu-export-<datum>.json"`:
```json
{
  "format": "ccu-dashboard-export",
  "version": 1,
  "exported_at": "2026-09-28T14:05:11+00:00",
  "profile_sets": { "Wohnzimmer": { "heating": { … }, "cooling": { … }, "active_profile": { … } } },
  "profile_names": { "1": "Standard", "2": "Urlaub" },
  "valve_channels": { "Wohnzimmer": [2, 3, 4] },
  "climate_schedule": {
    "heating": { "day": 15, "month": 9, "time": "08:00", "enabled": false },
    "cooling": { "day": 15, "month": 5, "time": "07:30", "enabled": true }
  },
  "change_history": [ … ]
}
```
`profile_sets` entspricht `data/profile_sets.json`, `change_history` den Einträgen der
Änderungshistorie (älteste zuerst, mit Vorher-Stand). `climate_schedule` enthält nur die
beiden Zeitpunkte (beide `null`, solange nie gespeichert), nicht den letzten Lauf. Die CCU-Zugangsdaten sind nicht
enthalten.

### `POST /import`
```bash
# nur prüfen (ändert nichts)
curl -s -X POST -H 'Content-Type: application/json' --data @ccu-export-2026-09-28.json $BASE/import
# einspielen
curl -s -X POST -H 'Content-Type: application/json' --data @ccu-export-2026-09-28.json "$BASE/import?apply=true"
```
Körper: ein Export-Dokument wie oben (`change_history` wird ignoriert). Ohne `apply=true`
wird nur geprüft. Antwort (auch bei ungültiger Datei Status 200):
```json
{
  "valid": true, "applied": true,
  "errors": [],
  "warnings": ["Für „Keller“ enthält die Datei keine Profile – …"],
  "rooms": 7, "profiles": 12, "names": 6, "valve_rooms": 7, "schedule": "replace",
  "backup_file": "vor-import-2026-09-30-091502.json",
  "transfer_started": true
}
```
- `errors`: alle Fehler mit Fundstelle; ist die Liste nicht leer, ist `valid` false und
  es wurde nichts geschrieben, auch nicht mit `apply=true`.
- `schedule`: `replace` (Zeitplan aus der Datei wird übernommen; bis jetzt vergangene
  Zeitpunkte gelten als erledigt), `clear` (Datei hat keinen gesetzten Zeitplan, der
  bestehende wird entfernt), `keep` (älterer Export ohne `climate_schedule`, der bestehende
  bleibt).
- `backup_file`: Kopie des bisherigen Stands im Datenordner (nur bei `applied`).
- `transfer_started`: Übertragung der aktiven Betriebsart auf die Thermostate läuft,
  Fortschritt unter `GET /system/climate/transfer`.
- **409** `busy`, solange eine Profilübertragung läuft.

### `GET /backups`
```json
{
  "files": [
    { "name": "ccu-auto-2026-10-02.json", "kind": "auto", "size": 48213, "modified": 1790910000.0 },
    { "name": "vor-import-2026-10-01-201502.json", "kind": "vor-import", "size": 47110, "modified": 1790880902.0 }
  ],
  "hour": 3, "keep": 14, "last_error": null
}
```
Neueste zuerst. `kind`: `auto` (tägliche Sicherung) oder `vor-import`. `last_error`:
letzter Fehler der automatischen Sicherung, sonst `null`.

### `POST /backups`
Schreibt `ccu-auto-<heute>.json` sofort (eine vorhandene von heute wird ersetzt) und räumt
alte auf. Antwort wie `GET /backups`.

### `GET /backups/{name}`
```bash
curl -s -OJ $BASE/backups/ccu-auto-2026-10-02.json
```
Liefert nur Namen, die `GET /backups` auflistet; alles andere ergibt **404**. Der Inhalt
ist ein Export-Dokument und lässt sich mit `POST /import` wieder einspielen.
