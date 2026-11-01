# CCU Dashboard – Dokumentation

Webanwendung zur Steuerung einer **Fußbodenheizung/-kühlung über eine HomematicIP
CCU3** (bzw. OpenCCU): Raumübersicht mit Ist-/Soll-Temperatur und Ventilstellung,
Wochenprofile je Raum, getrennte Heiz- und Kühlprofile, mehrere Designs.

Diese Dokumentation beschreibt Aufbau, Installation, Betrieb und Entwicklung des
Projekts. Sie gilt für den Stand **v0.35.1** (siehe [Versionen](10-versionen.md)).

## Inhaltsverzeichnis

| Datei | Für wen / wofür |
|---|---|
| [01 – Überblick](01-ueberblick.md) | Was kann die Anwendung, wie ist sie aufgebaut? |
| [02 – Installation auf Debian](02-installation-debian.md) | **Schritt für Schritt** von einem leeren Debian-System bis zur laufenden Anwendung |
| [03 – Konfiguration](03-konfiguration.md) | `.env`, Raum- und Ventilzuordnung, Datendateien, Ports |
| [04 – Betrieb und Wartung](04-betrieb-und-wartung.md) | Update, Rollback, Datensicherung, Logs, Fehlersuche, Deinstallation |
| [05 – Bedienung](05-bedienung.md) | Anleitung für Benutzer: alle Bildschirme und Funktionen |
| [06 – Architektur](06-architektur.md) | Aufbau von Backend und Frontend, Datenflüsse, Entwurfsentscheidungen |
| [07 – API-Referenz](07-api-referenz.md) | Alle HTTP-Endpunkte mit Beispielen |
| [08 – CCU-Hintergrund](08-ccu-hintergrund.md) | Wie die CCU/HmIP-Geräte sich verhalten, Datenpunkte, Fallstricke |
| [09 – Entwicklung](09-entwicklung.md) | Entwicklungsumgebung, Tests, Qualitätswerkzeuge, CI, Git-Ablauf |
| [10 – Versionen](10-versionen.md) | Änderungsverlauf je Release |

## Schnellstart (wenn alles vorbereitet ist)

Voraussetzung: Docker ist installiert (siehe [Installation](02-installation-debian.md);
das Installationsskript `scripts/install.sh` erledigt auch das).

```bash
git clone https://github.com/kunterauskoeln/ccu-climate-dashboard.git /opt/ccu
cd /opt/ccu
cp backend/.env.example backend/.env && nano backend/.env   # CCU-Zugangsdaten eintragen
mkdir -p data && cp backend/src/app/valve_channels.json data/
nano data/valve_channels.json                               # Ventil-Zuordnung anpassen
./deploy.sh
# danach im Browser: http://<server>:3000
```

Wenn du noch keinen Server eingerichtet hast: **[Installation auf Debian](02-installation-debian.md)**.
