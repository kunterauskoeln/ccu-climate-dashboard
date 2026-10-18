# 8 CCU-Hintergrund

Dieses Kapitel sammelt, was über das Verhalten der CCU und der HomematicIP-Geräte
**gemessen** wurde und warum die Anwendung so arbeitet, wie sie arbeitet. Es ist vor allem
für Entwickler und für die Fehlersuche gedacht. Die Werte wurden an einer CCU3
(später OpenCCU 3.89) mit HmIP-WTH-1 und HmIP-FALMOT-C12 ermittelt.

## 8.1 Die Anlage

| Gerät | Anzahl | Adresse (Muster) | Rolle |
|---|---|---|---|
| HmIP-WTH-1 (Wandthermostat) | 1 je Raum | `<Seriennummer>` | Misst, regelt, speichert die Wochenprofile |
| HmIP-HEATING (Heizgruppe, virtuell) | 1 je Raum | `INT000000x` auf der Schnittstelle `VirtualDevices` | Gruppierung in der CCU; ihr `LEVEL` bleibt hier bei 0 |
| HmIP-FALMOT-C12 (Fußbodenheizungsaktor) | 1 | `<Seriennummer>` | Steuert die Ventile (Kanäle 1–12) und schaltet **systemweit** Heizen/Kühlen |
| CCU3 / OpenCCU | 1 | – | Zentrale mit den Schnittstellen unten |

Die Thermostate haben Kanäle `:0` (Wartung: Batterie, Funkqualität, Erreichbarkeit) bis `:7`;
Status und Profile liegen auf **`:1`**.

## 8.2 Zwei Schnittstellen, beide nötig

| | JSON-RPC (ReGaHss) | XML-RPC (HmIP-Server) |
|---|---|---|
| Adresse | `http://<ccu>/api/homematic.cgi` | `http://<ccu>:2010` |
| Anmeldung | Sitzung (`Session.login`, Benutzer/Passwort) | keine (Zugriff über die CCU-Firewall) |
| Werte | als **Zeichenketten** (`"25.300000"`, `"0"`) | **typisiert** (`25.3`, `False`, `1`) |
| Stärken | Geräteliste, Räume, **Schreiben der Profile** | Zustände, Sollwert, Modus, Profile lesen |
| Schwächen | Sitzungen begrenzt; kennt HmIP-Profile nur über `Interface.putParamset` | Kann HmIP-**MASTER-Parameter nicht schreiben** |

Folge: Die Anwendung liest Zustände per XML-RPC und schreibt Profile per JSON-RPC.
Die Zuordnung steht in [Architektur 6.3](06-architektur.md#63-backend-im-detail).

## 8.3 Datenpunkte des Wandthermostats (HmIP-WTH-1)

**Status lesen** (Kanal `:1`, `VALUES`, XML-RPC):

| Wert | Schlüssel | Typ / Bereich |
|---|---|---|
| Ist-Temperatur | `ACTUAL_TEMPERATURE` | Kommazahl |
| Solltemperatur | `SET_POINT_TEMPERATURE` | 4,5 bis 30,5 °C |
| Luftfeuchte | `HUMIDITY` | ganze Zahl (%) |
| Modus lesen | `SET_POINT_MODE` | 0 Auto, 1 Manuell, 2 Party, 3 Boost |
| Aktives Profil | `ACTIVE_PROFILE` | 1 bis 6 |
| Fenster offen | `WINDOW_STATE` | Aufzählung |
| Boost | `BOOST_MODE` | Wahrheitswert |
| Heizen/Kühlen | `HEATING_COOLING` | 0 Heizen, 1 Kühlen (Spiegel des Aktors) |

**Wartung** (Kanal `:0`): `LOW_BAT`, `OPERATING_VOLTAGE`, `RSSI_DEVICE`, `UNREACH`.

**Schreiben:**

| Aktion | Wie |
|---|---|
| Solltemperatur | `setValue(":1", "SET_POINT_TEMPERATURE", x)` |
| **Modus** | `putParamset(":1", "VALUES", {"CONTROL_MODE": n})`. **Nicht** `SET_POINT_MODE`: Lesen und Schreiben des Modus laufen über **verschiedene** Datenpunkte. Andere Wege bleiben wirkungslos, ohne Fehler zu melden |
| Aktives Profil | `setValue(":1", "ACTIVE_PROFILE", n)`, danach **Bestätigung** durch Zurücklesen |
| Boost | `setValue(":1", "BOOST_MODE", bool)` |

`CONTROL_MODE` lässt sich nicht zurücklesen (`getValue` wirft einen Fehler, der Wert bleibt 0).

## 8.4 Wochenprofile

- Ablage im **MASTER-Parametersatz** von Kanal `:1`, Schlüssel **ohne** Vorsatz:
  `P{1..6}_ENDTIME_{TAG}_{1..13}` (ganze Zahl, Minuten seit Mitternacht, 0 bis 1440) und
  `P{1..6}_TEMPERATURE_{TAG}_{1..13}` (Kommazahl, °C). `TAG` = `MONDAY` … `SUNDAY`.
- **6 Profile, 7 Tage, 13 Slots je Tag.** Slots werden von 1 an gefüllt; der erste Slot mit
  Endzeit 1440 schließt den Tag. Weitere Slots sind Füllung (Endzeit 1440, Temperatur des
  letzten Abschnitts).
- **Es gibt nur eine Tabelle**, obwohl das Gerät Heizen und Kühlen kann: keine Schlüssel
  `HEATING_Px_`/`COOLING_Px_`. Deshalb führt die Anwendung beide Sätze selbst
  ([Architektur 6.4](06-architektur.md#64-heizen-und-kühlen-die-zwei-profilsätze)).
- Es gibt **keine eigene Basistemperatur**; sie ist die Temperatur des ersten bzw. letzten
  Abschnitts.
- Insgesamt rund 1100 Schlüssel im MASTER-Satz.

### Profile schreiben

Nur dieser Weg funktioniert:
`Interface.putParamset` (JSON-RPC) mit `set: [{name, type, value}, …]`:

```json
{ "interface": "HmIP-RF", "address": "<Seriennummer>:1", "paramsetKey": "MASTER",
  "set": [ {"name": "P1_TEMPERATURE_MONDAY_1", "type": "double", "value": "21.5"},
           {"name": "P1_ENDTIME_MONDAY_1",     "type": "int",    "value": "540"} ] }
```
- `type` muss ein gültiger XML-RPC-Typ sein: `"double"` für Temperaturen, `"int"` für Endzeiten.
  Ungültige Typen (`"DOUBLE"`, `"float"`) speichert die CCU als Text (`"DOUBLE 28.0"`) und
  verdirbt den Wert.
- `set` muss eine **Liste** aus `{name,type,value}` sein (kein `{schlüssel: wert}`-Objekt).
- Die CCU antwortet **auch bei Erfolg** mit dem Scheinfehler `505 "XML-RPC: unknown argument
  or value"`. Das Backend ignoriert ihn und **prüft durch Zurücklesen**.
- Roher XML-RPC-`putParamset` auf MASTER schlägt immer mit `Fault -5` fehl.
- **Ein Aufruf je Tag** (26 Schlüssel). Große Sammelaufrufe verträgt die CCU schlecht.
- Danach **Warten und Polling** (1,5 s Pause, dann alle 2 s bis 25 s): Funkübertragungen
  brauchen Zeit; ein einmaliges Lesen nach 1,5 s meldete fälschlich „nicht bestätigt".

## 8.5 Aktivprofil-Zeiger

Der Thermostat hat **einen** Zeiger `ACTIVE_PROFILE`, den Heizen und Kühlen teilen. Die
Anwendung merkt sich deshalb je Betriebsart und Raum, welches Profil zuletzt aktiv war, und
stellt es beim Wechsel wieder ein (bestätigt). Ein unbestätigtes Schreiben des Zeigers
führte einmal dazu, dass der Speicher ein Profil für aktiv hielt, das der Thermostat nie
übernommen hatte.

## 8.6 Heizen/Kühlen am Aktor

- Datenpunkt: `HEATING_COOLING` am **Kanal `:0`** des Aktors (Aufzählung, 0 Heizen, 1
  Kühlen, les- und schreibbar).
- Die Werte am Thermostat (`:1`) und in der Heizgruppe sind **Spiegel** davon.
- Die Anwendung sendet den Wert auf **beiden Wegen** (`setValue` und `putParamset VALUES`)
  und wartet mit Polling bis ca. 15 s. Der Aktor gibt die Änderung per Funk nach mehreren
  Sekunden weiter, ein Schnelltest nach 1 s meldete fälschlich „nicht bestätigt".
- Die Umschaltung gilt für die **ganze Anlage** (ein Aktor für alle Räume).

## 8.7 Ventilstellung

- Die **Heizgruppe** (`INTxxxx:1`, `LEVEL` 0 bis 1, `VALVE_STATE`) meldete auf dieser Anlage
  **dauerhaft 0**, auch bei offenem Ventil.
- Die echte Stellung steht an den **Aktorkanälen** `:1` bis `:12` (`LEVEL` 0 bis 1,
  `VALVE_STATE`). Ungenutzte Kanäle liefern einen leeren Wert.
- Welcher Kanal zu welchem Raum gehört, verrät die Geräteliste **nicht**; Aufrufe wie
  `Interface.getLinkPeers` scheitern mit `TCL error` (Code 601). In der CCU-Oberfläche
  erscheint die Zuordnung unter *Verknüpfungspartner* je Kanal. Daher `valve_channels.json`
  ([Konfiguration 3.3](03-konfiguration.md#33-ventil-zuordnung-datavalve_channelsjson)).
- Ein Raum kann mehrere Kanäle haben (mehrere Heizkreise); die Anwendung mittelt sie.

## 8.8 Duty Cycle

HomematicIP-Funk unterliegt einer **Sendezeitbegrenzung** (Duty Cycle, etwa 1 % der Zeit).
Ist sie erreicht, lehnt die CCU weitere Funkbefehle ab oder verzögert sie, teils über
Stunden. Ein Profiltag zu schreiben ist ein größerer Funkvorgang.

Aus einem Vorfall (Wechsel der Betriebsart schrieb synchron viele Tage, die Anwendung hing,
Geräte verweigerten Befehle) folgen die Regeln der Anwendung:
- Schreibvorgänge an Profilen **nie im Anfrage-Thread**, sondern im Hintergrund;
- **ein Tag pro Schreibvorgang**, 4 Sekunden Pause;
- **höchstens 8 Tage je Wechsel**, Rest „aufgeschoben";
- **Abbruch nach 3 Fehlern in Folge**;
- nur das **aktive** Profil je Raum beim Wechsel der Betriebsart.

Die Auslastung zeigt die CCU-Oberfläche an (Anzeige „Duty Cycle", zum Beispiel bei der
Zentrale in der Geräteliste). Vor größeren Übertragungen sollte sie möglichst niedrig sein.

## 8.9 Sitzungen der CCU

Die JSON-RPC-Schnittstelle erlaubt nur **wenige gleichzeitige Sitzungen**. Wird die Zahl
erreicht, antwortet `Session.login` mit `invalid credentials or too many sessions`
(irreführend: auch bei richtigem Passwort). Offene Sitzungen laufen nach etwa 10 Minuten ab.
Daraus folgt:
- Jede Komponente, die sich anmeldet, **meldet sich wieder ab** (Skripte, Hintergrundauftrag,
  Verwerfen einer Sitzung nach einem Fehler).
- Nach einer Serie fehlgeschlagener Aufrufe etwa 10 Minuten abwarten.
- Diagnose-Skripte melden sich in einem `finally`-Block ab.

## 8.10 CCU-Updates und Wiederanlauf

Nach einem CCU-Firmware-Update melden sich Geräte (Aktor, einzelne Thermostate) erst nach
einigen Minuten wieder mit Messwerten. Die Anwendung zeigt bis dahin „–" (nie „0"). Ein
Neustart der Anwendung ist nicht nötig.

## 8.11 Diagnose

Alle Abfragen ohne Schreibzugriff:

```bash
docker compose exec backend python scripts/dump_ccu.py                 # Thermostate
docker compose exec backend python scripts/dump_ccu.py Wohnzimmer      # Datenpunkte eines Raums
```
Für eigene Abfragen (Vorsicht: Fehlerfälle belegen CCU-Sitzungen, Abschnitt 8.8):
```bash
docker compose exec -T backend python - <<'PY'
from app.deps import get_jsonrpc, get_xmlrpc
j, x = get_jsonrpc(), get_xmlrpc()
try:
    print(x.get_paramset("<Seriennummer>:1", "VALUES"))
finally:
    j.logout()
PY
```
