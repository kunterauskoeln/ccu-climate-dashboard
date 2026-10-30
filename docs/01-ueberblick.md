# 1 Überblick

## 1.1 Zweck

Die Anwendung ist ein Web-Frontend (mit eigenem Backend) für eine
**HomematicIP-Fußbodenheizung**. Sie ersetzt die Bedienung über die CCU-Oberfläche
durch eine schlanke, für Handy, Tablet und PC gedachte Oberfläche und ergänzt
Funktionen, die die CCU nicht bietet – vor allem **unabhängige Heiz- und
Kühlprofile** je Raum.

Die Heizungsregelung selbst bleibt bei den Geräten (Wandthermostate,
Fußbodenheizungsaktor). Die Anwendung liest Zustände, schreibt Sollwerte, Modi und
Wochenprofile und überträgt bei Bedarf gespeicherte Pläne auf die Thermostate.
**Fällt die Anwendung aus, heizen bzw. kühlen die Geräte mit ihren zuletzt
gespeicherten Plänen weiter.**

## 1.2 Funktionen

| Bereich | Funktion |
|---|---|
| Übersicht | Kachel je Raum: Modus, aktives Profil, Soll- und Ist-Temperatur, Luftfeuchte, **Ventilstellung** als Balken |
| Raumdetail | Solltemperatur per Drehregler, Modus (Automatik/Manuell/Party/Boost), Profilauswahl, Ventilstellung |
| Wochenprofile | 6 Profile je Raum, je Wochentag beliebig viele Zeitabschnitte (bis 13), Grafik je Tag, Zeitabschnitte hinzufügen/ändern/löschen, Tag oder ganzes Profil kopieren (auch in andere Räume), Profile umbenennen |
| Heizen und Kühlen | Systemweite **Betriebsart** (Heizen/Kühlen). Heiz- und Kühlprofile sind **getrennte, dauerhaft gespeicherte Datensätze**; der jeweils inaktive lässt sich ohne Umschalten bearbeiten |
| Übertragung | Beim Umschalten und beim Profilwechsel schreibt ein Hintergrundauftrag die gespeicherten Pläne auf die Thermostate (funkschonend, mit Fortschrittsanzeige) |
| Änderungshistorie | Profiländerungen im aktiven Modus und Umbenennungen werden mit Zeitpunkt protokolliert; „bis hierhin zurücksetzen" nimmt einen Eintrag und alle neueren zurück, auch auf den Thermostaten |
| Taupunkt | Im Kühlbetrieb Taupunkt je Raum gegen die Vorlauftemperatur (MQTT-Sensor), Ampel und Warnbalken bei Kondensgefahr |
| Home Assistant | Zustand per MQTT-Discovery als Gerät „CCU Dashboard“, z. B. für Push-Nachrichten bei Kondensgefahr |
| Geräte | Liste aller angelernten Geräte (Adresse, Typ, Schnittstelle) |
| Design | 8 Themen (Hellblau, Weiß, Dunkel, Sepia, Wald, Sonnenuntergang, Graphit, Ozean), **Erhaben-Effekt** (Aus/Leicht/Stark) und **Glanz** (Aus/An) |
| Betrieb | Health-Endpunkt, automatischer Neustart, eigener Datenordner (von Updates unberührt), Sicherungskopie der Profildaten, Logging |

## 1.3 Systemlandschaft

```
   Handy / Tablet / PC (Browser)
              │  HTTP :3000
              ▼
  ┌────────────────────────── Docker Compose (ein Linux-Server) ────────────────────────┐
  │                                                                                     │
  │   dashboard  (nginx)                                                                │
  │     ├─ /        → statisches React-Frontend                                         │
  │     └─ /api/*   → Reverse-Proxy ──►  backend  (FastAPI/uvicorn, nur intern :8000)   │
  │                                         │   └─ liest/schreibt JSON-Dateien in data/ │
  └─────────────────────────────────────────┼───────────────────────────────────────────┘
                                            │ im LAN
                          ┌─────────────────┴──────────────────┐
                          ▼                                    ▼
             CCU3 / OpenCCU  ReGaHss                CCU3 / OpenCCU  HmIP-Server
             JSON-RPC  http://<ccu>/api/homematic.cgi     XML-RPC  http://<ccu>:2010
             (Login, Geräteliste, Schreiben               (Status lesen, Sollwert,
              der Profile, ...)                             Modus, Profile lesen)
                          └────────────► Funk ◄────────────────┘
                     Wandthermostate HmIP-WTH-1  ·  Aktor HmIP-FALMOT-C12
```

Die CCU läuft auf eigener Hardware. Die Anwendung läuft auf einem **separaten
Linux-Rechner im selben Netz** (Server, Mini-PC, Raspberry Pi o. Ä.).

## 1.4 Komponenten

| Komponente | Technik | Aufgabe |
|---|---|---|
| `dashboard` | React 18, TypeScript, Vite, react-query, nginx | Oberfläche; nginx liefert sie aus und leitet `/api` ans Backend |
| `backend` | Python 3.11, FastAPI, uvicorn | HTTP-API, CCU-Zugriff, Profil-Speicher, Hintergrundübertragung |
| Datenordner `data/` | JSON-Dateien auf dem Host | Heiz-/Kühlprofile mit Sicherungskopie, Profilnamen, Ventil-Zuordnung, Änderungshistorie |

## 1.5 Wichtige Eigenschaften und Grenzen

- **Ein Server, eine CCU, eine Anlage.** Die Raum- und Ventilzuordnung ist auf die
  eigene Installation zugeschnitten (siehe [Konfiguration](03-konfiguration.md)).
- **Kein Login in der Anwendung.** Sie ist für das vertrauenswürdige Heimnetz
  gedacht und **nicht** für den Zugriff aus dem Internet. Wer das Dashboard
  erreicht, kann die Heizung bedienen. Zugriff aus dem Internet nur über VPN.
- **Ein Thermostat speichert nur eine Profiltabelle** (6 Profile), die Heizen und
  Kühlen sich teilen. Die Anwendung hält deshalb beide Sätze selbst und schreibt
  den jeweils benötigten auf die Geräte (siehe [Architektur](06-architektur.md)).
- **Funk ist knapp.** HomematicIP darf nur etwa 1 % der Zeit senden (Duty Cycle).
  Alle Schreibvorgänge an Profilen sind deshalb gebremst und begrenzt.
- Getestete Hardware: Wandthermostat **HmIP-WTH-1**, Aktor **HmIP-FALMOT-C12**
  (Fußbodenheizung). Andere Geräte sind nicht getestet.
