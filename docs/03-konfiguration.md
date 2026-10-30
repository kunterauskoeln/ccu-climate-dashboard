# 3 Konfiguration

Alle Einstellungen der Anwendung liegen an vier Stellen:

| Stelle | Zweck | Wo |
|---|---|---|
| `backend/.env` | CCU-Zugangsdaten und Verbindungsangaben | nur auf dem Server, **nicht** im Git |
| `docker-compose.yml` | Container, Ports, Datenordner | im Git |
| `docker-compose.override.yml` | Eigene Anpassungen daran (optional, z. B. anderer Port) | nur auf dem Server, **nicht** im Git |
| Datenordner `/opt/ccu/data/` | Profile, Profilnamen, Ventil-Zuordnung, Änderungshistorie | nur auf dem Server, **nicht** im Git |

## 3.1 `backend/.env`

Vorlage: `backend/.env.example`. Die Datei wird vom Backend-Container beim Start
gelesen (`env_file` in `docker-compose.yml`). Nach jeder Änderung:
```bash
docker compose up -d --force-recreate backend
```

| Variable | Pflicht | Bedeutung | Beispiel |
|---|---|---|---|
| `CCU_HOST` | ja | IP-Adresse oder Name der CCU, **ohne** `http://` | `192.168.1.10` |
| `CCU_USERNAME` | ja | CCU-Benutzer für die JSON-RPC-Anmeldung | `admin` |
| `CCU_PASSWORD` | ja | Passwort dieses Benutzers. In **einfachen Anführungszeichen**, sobald es `$`, `#` oder Leerzeichen enthält (Docker Compose ersetzt sonst `$name` und schneidet ab ` #` ab) | `'ge$heim #1'` |
| `CORS_ALLOW_ORIGINS` | nein | Kommagetrennte Liste erlaubter Herkunfts-Adressen. Nur nötig, wenn das Dashboard **nicht** über den nginx-Proxy läuft (lokaler Entwicklungsserver). Standard: `http://localhost:3000` | `http://localhost:3000` |
| `MQTT_HOST` | nein | MQTT-Broker für die Vorlauftemperatur (Taupunktüberwachung). Ohne ihn ist die Überwachung ohne Vergleichswert | `192.168.1.20` |
| `MQTT_PORT` | nein | Port des Brokers, Standard `1883` | `1883` |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | nein | Anmeldung am Broker. Am besten ein eigener Benutzer, der nur das Vorlauf-Thema lesen darf. Passwort wie oben in einfachen Anführungszeichen | – |
| `MQTT_FLOW_TOPIC` | mit `MQTT_HOST` | Thema mit der Vorlauftemperatur (Zahl oder JSON mit `state`/`value`/`temperature`; ein mitgesendeter `timestamp` gilt als Messzeitpunkt) | `heizung/vorlauf/temperatur` |
| `DEW_WARN_MARGIN`, `DEW_ALARM_MARGIN` | nein | Abstand Vorlauf − Taupunkt in K, unter dem „knapp“ bzw. „Kondensgefahr“ gilt. Standard `3` und `1` | `3` |
| `FLOW_SETTLE_MINUTES` | nein | So lange muss ein Ventil offen sein, bis der Vorlauf-Messwert gilt. Standard `10` | `10` |
| `FLOW_STALE_MINUTES` | nein | Ohne neue MQTT-Nachricht gilt der Messwert danach als veraltet. Standard `120` | `120` |
| `AUTO_BACKUP_HOUR` | nein | Ab dieser Stunde (Ortszeit) entsteht die tägliche Sicherung. Standard `3` | `3` |
| `AUTO_BACKUP_KEEP` | nein | So viele tägliche Sicherungen bleiben erhalten. Standard `14` | `14` |
| `DUTY_CYCLE_WARN` | nein | Funkauslastung der CCU (%), ab der die App einen Hinweis zeigt. Standard `60` | `60` |
| `DUTY_CYCLE_LIMIT` | nein | Funkauslastung (%), ab der Profilübertragungen anhalten. Standard `70` | `70` |
| `CONFIG_PENDING_WARN_MINUTES` | nein | So viele Minuten darf „Konfiguration ausstehend“ an einem Gerät bestehen, bevor die App warnt. Standard `30` | `30` |
| `HA_DISCOVERY` | nein | `0` schaltet die Veröffentlichung für Home Assistant ab (3.7). Standard an, sobald MQTT eingerichtet ist | `1` |
| `HA_DISCOVERY_PREFIX` | nein | Discovery-Präfix von Home Assistant. Standard `homeassistant` | `homeassistant` |
| `MQTT_BASE_TOPIC` | nein | Themen, unter denen die App veröffentlicht (`…/state`, `…/status`). Standard `ccu-dashboard` | `ccu-dashboard` |

Weitere Umgebungsvariablen (werden in `docker-compose.yml` bzw. im Code gesetzt, normalerweise
nicht anzufassen):

| Variable | Standard | Bedeutung |
|---|---|---|
| `ROOT_PATH` | `/api` (Compose) | Pfadpräfix, unter dem das Backend hinter nginx erreichbar ist. Beeinflusst die Adressen der API-Dokumentation |
| `PROFILE_NAMES_FILE` | `/app/app/data/profile_names.json` | Pfad der Profilnamen-Datei im Container |
| `PROFILE_SETS_FILE` | `/app/app/data/profile_sets.json` | Pfad der Heiz-/Kühlprofile im Container |
| `PROFILE_SETS_BACKUP_FILE` | `/app/app/data/profile_sets.backup.json` | Pfad der automatischen Sicherung dazu |
| `CHANGE_HISTORY_FILE` | `/app/app/data/change_history.json` | Pfad der Änderungshistorie im Container |
| `CLIMATE_SCHEDULE_FILE` | `/app/app/data/climate_schedule.json` | Pfad des Zeitplans für das automatische Umschalten |
| `SCHEDULE_TZ` | `Europe/Berlin` | Zeitzone, in der die Zeitpunkte des automatischen Umschaltens gelten |
| `VALVE_CHANNELS_FILE` | `/app/app/data/valve_channels.json` (Compose) | Pfad der Ventil-Zuordnung. Ohne diese Variable (lokale Entwicklung) gilt die Vorlage `backend/src/app/valve_channels.json` |

**Sicherheit:** `backend/.env` enthält das CCU-Passwort. Setze `chmod 600 backend/.env`,
gib die Datei nicht weiter und schreibe das Passwort nie in Chats, Tickets oder
Commit-Nachrichten. Ist es doch einmal irgendwo gelandet, ändere es in der CCU und in
der `.env`.

## 3.2 Räume und Geräte: Namensregeln

Das Backend baut seine Raumliste aus der Geräteliste der CCU (`Device.listAllDetail`,
wird 5 Minuten zwischengespeichert):

| Gerät in der CCU | Erkennung | Verwendung |
|---|---|---|
| Wandthermostat | Gerätetyp beginnt mit `HmIP-WTH` | **Name des Geräts = Raumname**; die Räume der Anwendung sind genau diese Thermostate |
| Heizgruppe | Typ `HmIP-HEATING` auf der Schnittstelle `VirtualDevices` | Name `<Raum> INTxxxxxxx`; der Teil vor ` INT` ist der Raumname (wird zugeordnet, aber nicht mehr für die Ventilstellung benutzt) |
| Aktor | Gerätetyp enthält `FALMOT`, `FAL230`, `FAL24` oder `HEATING_ACTUATOR` | Schaltet Heizen/Kühlen für die ganze Anlage; seine Kanäle liefern die Ventilstellungen |

Ein neuer Raum erscheint automatisch, sobald der Thermostat in der CCU angelernt und
benannt ist. Nach einer Umbenennung in der CCU dauert es bis zu 5 Minuten, bis die
Anwendung den neuen Namen kennt (oder du startest das Backend neu:
`docker compose restart backend`).

## 3.3 Ventil-Zuordnung (`data/valve_channels.json`)

```json
{
  "Arbeitszimmer": [1],
  "Wohnzimmer": [2, 3, 4],
  "Bad": [5]
}
```

- **Schlüssel:** Raumname, exakt wie der Thermostatname in der CCU (Groß-/Kleinschreibung
  beachten).
- **Werte:** Liste der Kanalnummern des Aktors (`1` bis `12`), die zu diesem Raum gehören.
  Hat ein Raum mehrere Heizkreise, zeigt die Anwendung den **Mittelwert** der Kanäle.
- **Warum eine Datei?** Die CCU gibt die Zuordnung von Aktorkanal zu Raum nicht über die
  Schnittstelle her. In der CCU-Oberfläche sieht man sie unter *Status und Bedienung →
  Geräte → HmIP-FALMOT-C12 → Kanal → Verknüpfungspartner*.
- **Warum nicht die Heizgruppe?** Deren Wert `LEVEL` bleibt bei dieser Anlage dauerhaft
  0, auch wenn das Ventil offen ist. Siehe [CCU-Hintergrund](08-ccu-hintergrund.md).
- Fehlt die Datei oder ist sie fehlerhaft (kein gültiges JSON), schreibt das Backend eine
  Warnung ins Log, und die Ventilanzeige bleibt leer („–"). Alles andere funktioniert.
- **Ort:** `/opt/ccu/data/valve_channels.json`. `deploy.sh` legt sie beim ersten Start aus
  der Vorlage `backend/src/app/valve_channels.json` an, falls sie fehlt; danach bleibt sie
  unangetastet, auch bei Updates.
- Nach einer Änderung: `docker compose restart backend`. Ein Neubau ist nicht nötig.

## 3.4 `docker-compose.yml`

Zwei Dienste:

| Dienst | Image / Build | Port | Aufgabe |
|---|---|---|---|
| `backend` | Build aus `./backend` (Python 3.11) | 8000, **nur intern** | API und CCU-Zugriff |
| `dashboard` | Build aus `./dashboard` (Node 20 zum Bauen, nginx zum Ausliefern) | **3000** (Host) → 80 (Container) | Oberfläche und `/api`-Proxy |

Wichtige Punkte:
- Beide Container haben `restart: always`: Sie starten nach einem Absturz und nach jedem
  Neustart des Servers von selbst. `unless-stopped` wäre hier falsch, weil Docker das
  geordnete Stoppen beim Herunterfahren wie ein bewusstes `docker stop` wertet und die
  Container dann aus ließe.
- Jeder Dienst hat einen **Healthcheck**; `docker compose ps` zeigt `healthy`. Der Check
  des Dashboards fragt `http://127.0.0.1/` ab, nicht `localhost`: `localhost` löst im
  Container zuerst nach IPv6 auf, nginx lauscht aber nur auf IPv4.
- Das Backend bindet den Ordner `./data` (also `/opt/ccu/data`) als
  `/app/app/data` ein. Ein Ordner statt einzelner Dateien: Fehlt eine Datei, legt Docker
  sie so nicht versehentlich als Verzeichnis an.
- `ROOT_PATH: /api` weist FastAPI an, dass es hinter dem nginx-Pfad `/api` läuft.
- Eigene Anpassungen gehören in `docker-compose.override.yml`, nicht in diese Datei (siehe
  [Betrieb, „Eigene Anpassungen"](04-betrieb-und-wartung.md#eigene-anpassungen)).

## 3.5 Datendateien

Diese Dateien enthalten **deine Daten**. Sie liegen auf dem Host im Ordner
`/opt/ccu/data/`, der als Ganzes in den Backend-Container eingebunden wird. Der Ordner ist
von Git ausgenommen, Updates mit `deploy.sh` ändern ihn nicht. `deploy.sh` legt nur
fehlende Dateien an: `profile_names.json` und `valve_channels.json` aus Vorlagen im
Projekt, die Profilsätze leer.

| Datei | Inhalt | Geschrieben von |
|---|---|---|
| `profile_names.json` | Bezeichnungen der 6 Profile: `{"1": "Standard", "2": "Urlaub", ...}`, gilt für alle Räume | App (Profil umbenennen) |
| `profile_sets.json` | Je Raum die **Heiz- und die Kühlprofile** (6 Profile × 7 Tage × Zeitabschnitte) und das zuletzt aktive Profil je Betriebsart | App (Profil bearbeiten, Wechsel der Betriebsart) |
| `profile_sets.backup.json` | Sicherung des **vorherigen** Standes von `profile_sets.json` (eine Generation, wird vor jedem Schreiben angelegt) | App (automatisch) |
| `valve_channels.json` | Zuordnung Raum → Aktorkanäle (3.3) | du |
| `change_history.json` | Änderungshistorie: Profiländerungen im aktiven Modus und Umbenennungen, je mit dem Stand davor (höchstens 200 Einträge) | App |
| `climate_schedule.json` | Zeitplan für das automatische Umschalten Heizen/Kühlen und das Ergebnis des letzten Laufs (fehlt, solange nie gespeichert) | App |
| `backups/ccu-auto-<datum>.json` | Tägliche Sicherung im Export-Format, die letzten 14 | App (jede Nacht) |
| `valve_history.json` | Ventilstellungen aller Räume, alle 5 Minuten, die letzten 72 Stunden (für den Ventilverlauf) | App |
| `absence.json` | Geplante oder laufende Abwesenheit samt den gemerkten Profilen je Raum (fehlt, solange nie eine geplant wurde) | App |
| `vor-import-<datum-uhrzeit>.json` | Stand vor einem Import, im Export-Format | App (Import) |

Format von `profile_sets.json`:
```json
{
  "Wohnzimmer": {
    "heating": {
      "1": { "monday": [ {"start": "00:00", "end": "06:00", "setpoint": 17.0},
                         {"start": "06:00", "end": "22:00", "setpoint": 21.5},
                         {"start": "22:00", "end": "24:00", "setpoint": 17.0} ],
             "tuesday": [ ... ] },
      "2": { ... }
    },
    "cooling": { "1": { ... } },
    "active_profile": { "heating": 1, "cooling": 4 }
  }
}
```
Die Zeitabschnitte eines Tages müssen lückenlos 00:00 bis 24:00 abdecken (die App
erzwingt das). Tagesnamen sind kleingeschrieben und englisch (`monday` … `sunday`).

Diese Dateien gehören in jede **Datensicherung** (siehe
[Betrieb](04-betrieb-und-wartung.md#43-datensicherung)).

## 3.6 Ports und Netzwerk

| Port | Dienst | Erreichbar von | Zweck |
|---|---|---|---|
| 3000/TCP | nginx (Dashboard) | Clients im LAN | Weboberfläche und API unter `/api` |
| 80/TCP (zur CCU) | JSON-RPC | Server → CCU | Anmeldung, Geräteliste, Schreiben der Profile |
| 2010/TCP (zur CCU) | XML-RPC HmIP-Server | Server → CCU | Zustände lesen, Sollwerte und Modi schreiben |
| 1883/TCP (zum Broker) | MQTT | Server → Broker | Vorlauftemperatur lesen, Zustand für Home Assistant senden (nur mit `MQTT_HOST`) |

Die interne API-Dokumentation (Swagger) ist unter `http://<server>:3000/api/docs`
erreichbar.

## 3.7 Home Assistant

Ist MQTT eingerichtet (3.1), meldet sich die App bei Home Assistant über **MQTT
Discovery** an. Unter *Einstellungen → Geräte & Dienste → MQTT* erscheint dann ein Gerät
**CCU Dashboard**, ohne weitere Konfiguration in Home Assistant.

| Entität | Inhalt |
|---|---|
| `binary_sensor.ccu_dashboard_kondensgefahr` | An bei „Kondensgefahr“ |
| `binary_sensor.ccu_dashboard_taupunkt_warnung` | An bei „knapp“ oder „Kondensgefahr“ |
| `sensor.ccu_dashboard_taupunkt_lage` | `aus`, `ok`, `unbekannt`, `knapp`, `gefahr` |
| `sensor.ccu_dashboard_taupunkt_meldung` | Text wie in der App, z. B. „Kondensgefahr: Bad (+0,6 K)“ |
| `binary_sensor.ccu_dashboard_kuhlbetrieb` | An im Kühlbetrieb |
| `binary_sensor.ccu_dashboard_abwesenheit` | An während einer Abwesenheit (einschließlich Rückkehr) |
| `sensor.ccu_dashboard_abwesenheit_bis` | Ende der laufenden Abwesenheit (Zeitstempel) |
| `binary_sensor.ccu_dashboard_gerateproblem` | An bei einem Gerätehinweis (Batterie, nicht erreichbar, Funk-Limit, hohe Funkauslastung, Einstellungen nicht übertragen) |
| `sensor.ccu_dashboard_gerate_meldung` | Text der Hinweise wie in der App |
| `sensor.ccu_dashboard_ccu_funkauslastung` | Duty Cycle der CCU (%) |
| je Gerät `…_<name>_erreichbar`, `…_batterie_schwach`, `…_batteriespannung` | Erreichbarkeit, Batterie schwach, Spannung (V); Batterie nur bei den Thermostaten |
| `sensor.ccu_dashboard_vorlauf`, `…_vorlauf_sensor` | Vergleichswert bzw. letzter Messwert des Vorlaufs (°C) |
| je Raum `…_<raum>_taupunkt`, `…_abstand`, `…_taupunkt_bewertung`, `…_ventil` | Taupunkt (°C), Abstand zum Vorlauf (K), Bewertung, Ventilstellung (%) |

Die Entitäts-IDs bildet Home Assistant aus Geräte- und Entitätsnamen, Umlaute werden
dabei zu einfachen Buchstaben („Kühlbetrieb“ → `kuhlbetrieb`); die genauen IDs stehen in
Home Assistant beim Gerät. Die Werte kommen jede Minute. Ist die App nicht
erreichbar, zeigen alle Entitäten „nicht verfügbar“ (Status `ccu-dashboard/status` mit
Last Will).

**Rechte am Broker.** Der MQTT-Benutzer der App braucht zusätzlich zum Lesen des
Vorlauf-Themas Schreibrechte auf seine eigenen Themen und die Discovery-Anmeldungen.
Beispiel für Mosquitto, Block in der ACL-Datei (`/etc/mosquitto/acl`):
```
user ccu-dashboard
topic read heizung/vorlauf/temperatur
topic write ccu-dashboard/#
topic write homeassistant/+/ccu_dashboard/#
```
Danach `systemctl restart mosquitto`. Ohne diese Rechte verwirft der Broker die
Nachrichten stillschweigend; Home Assistant sieht dann einfach kein Gerät.

**Push-Nachricht bei Kondensgefahr** (Automation in Home Assistant, *Einstellungen →
Automationen → Neu → YAML bearbeiten*; `notify.mobile_app_…` durch dein Handy aus der
Companion-App ersetzen):
```yaml
alias: Kondensgefahr Fußbodenkühlung
mode: single
triggers:
  - trigger: state
    entity_id: binary_sensor.ccu_dashboard_kondensgefahr
    to: "on"
    for: "00:02:00"
actions:
  - action: notify.mobile_app_<dein_handy>
    data:
      title: Kondensgefahr
      message: "{{ states('sensor.ccu_dashboard_taupunkt_meldung') }}"
```
Die zwei Minuten Verzögerung vermeiden Meldungen bei kurzen Schwankungen. Für eine
frühere Warnung `binary_sensor.ccu_dashboard_taupunkt_warnung` verwenden.

**Meldung, wenn die App ausfällt:**
```yaml
alias: CCU Dashboard nicht erreichbar
mode: single
triggers:
  - trigger: state
    entity_id: sensor.ccu_dashboard_taupunkt_lage
    to: unavailable
    for: "00:10:00"
actions:
  - action: notify.mobile_app_<dein_handy>
    data:
      title: CCU Dashboard
      message: Die App meldet sich seit 10 Minuten nicht mehr.
```
