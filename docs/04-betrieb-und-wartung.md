# 4 Betrieb und Wartung

Alle Befehle werden auf dem Server im Projektverzeichnis ausgeführt, als dein normaler
Benutzer (nicht als root, siehe 4.9):
```bash
cd /opt/ccu
```

## 4.1 Update und Rollback

`deploy.sh` ist das einzige Werkzeug für Updates und Rollbacks:

```bash
./deploy.sh              # neuester Stand von origin/main
./deploy.sh v0.18.0      # bestimmte Version (Tag) – auch für ein Rollback
./deploy.sh <commit>     # bestimmter Commit
./deploy.sh origin/<zweig>   # ein Zweig, z. B. zum Testen einer neuen Funktion
```

Ablauf:
1. `git fetch`, dann `git checkout -f <stand>`;
2. `deploy.sh` startet sich danach einmal selbst neu, damit der Rest garantiert aus der
   gerade ausgecheckten Version läuft;
3. fehlende Dateien im Datenordner `data/` anlegen (vorhandene bleiben unverändert);
4. die Rechte von `backend/.env` auf 600 setzen, falls sie davon abweichen (die Datei
   enthält Passwörter; gehört sie einem anderen Benutzer, gibt es nur einen Hinweis);
5. `docker compose up -d --build`, dann auf `/api/system/health` warten.

Die Anwendung ist während des Neubaus kurz (Sekunden) nicht erreichbar; die **Heizung
läuft weiter**, denn die Pläne liegen in den Thermostaten.

`deploy.sh` braucht Zugriff auf GitHub (öffentlich per HTTPS, ohne Anmeldung). Nur bei
einem eigenen privaten Fork braucht jeder Benutzer, der es ausführt, einen Deploy-Key
(siehe [Installation, Schritt 4](02-installation-debian.md#24-schritt-4-projekt-herunterladen)).

Welche Version läuft?
```bash
git log -1 --oneline
git describe --tags --always
```
Alle Versionen mit Beschreibung: `git tag -n1` und [Versionen](10-versionen.md).

**Vor einem Update** (empfohlen): Datensicherung (4.3) und einen Blick in
[Versionen](10-versionen.md), ob sich etwas Wichtiges geändert hat.

**Nach einem Update:**
```bash
docker compose ps
curl -s http://localhost:3000/api/system/health
docker compose logs --tail 30 backend | grep -i -E "warning|error"    # sollte leer sein
```

### Eigene Anpassungen

`deploy.sh` wechselt mit `git checkout -f` auf den gewünschten Stand. Das **verwirft
lokale Änderungen an Dateien des Projekts**. Deshalb gilt:

- **Deine Daten** (Profile, Profilnamen, Ventil-Zuordnung, Änderungshistorie) liegen in
  `data/`. Dieser Ordner ist von Git ausgenommen, Updates fassen ihn nie an.
- **Änderungen an `docker-compose.yml`** (zum Beispiel ein anderer Port) gehören in eine
  eigene Datei `docker-compose.override.yml` im Projektverzeichnis. Docker Compose liest
  sie automatisch zusätzlich ein, und Git ignoriert sie. Beispiel für Port 80 statt 3000:
  ```yaml
  services:
    dashboard:
      ports: !override
        - "80:80"
  ```
  Beachte, dass der Health-Check in `deploy.sh` Port 3000 abfragt; mit einem anderen Port
  meldet er am Ende einen Fehler, obwohl die Anwendung läuft.
- **Änderungen am Programmcode selbst** gehören ins Repository (über die Entwicklung,
  siehe [Entwicklung](09-entwicklung.md)), nicht direkt auf den Server.

`git status` im Projektverzeichnis sollte deshalb immer `working tree clean` zeigen.

## 4.2 Starten, Stoppen, Neustarten

```bash
docker compose ps                        # Zustand
docker compose stop                      # alles anhalten (Daten bleiben erhalten)
docker compose start                     # wieder starten
docker compose restart backend           # nur das Backend neu starten (z. B. nach Änderung
                                         # von data/valve_channels.json)
docker compose up -d --force-recreate backend    # nach Änderung der .env
docker compose down                      # Container entfernen (Daten bleiben)
```
Nach einem Neustart des Servers starten die Container von selbst (`restart: always`).
Auch nach `docker compose stop` kommen sie beim nächsten Neustart des Servers wieder. Wer
sie dauerhaft aus haben will, nimmt `docker compose down`.

## 4.3 Datensicherung

**Was sichern?**

| Datei | Warum |
|---|---|
| `backend/.env` | Zugangsdaten (enthält das CCU-Passwort, sicher aufbewahren!) |
| `data/profile_sets.json` | Deine **Heiz- und Kühlprofile**: der wichtigste Datenbestand |
| `data/profile_sets.backup.json` | Vorheriger Stand davon |
| `data/profile_names.json` | Profilnamen |
| `data/valve_channels.json` | Deine Ventil-Zuordnung |
| `data/change_history.json` | Änderungshistorie |
| `data/climate_schedule.json` | Zeitplan für das automatische Umschalten |

Kurz: `backend/.env` und der ganze Ordner `data/`. (Die Datendateien ohne `.env` lassen
sich auch in der App herunterladen und dort wieder einlesen: *Einstellungen →
Datensicherung*, siehe [Bedienung 5.12](05-bedienung.md#512-datensicherung).) Vor jedem
Import legt die App den bisherigen Stand als `data/vor-import-<datum-uhrzeit>.json` ab;
diese Dateien kann man gelegentlich aufräumen. Der Rest ist aus
dem Git-Repository
wiederherstellbar. Die Pläne stehen zusätzlich in den Thermostaten; für den **inaktiven**
Modus (zum Beispiel Kühlen im Winter) existiert aber nur die Kopie in
`data/profile_sets.json`.

**Sicherung anlegen:**
```bash
tar czf ~/ccu-backup-$(date +%F).tar.gz -C /opt/ccu backend/.env data
chmod 600 ~/ccu-backup-*.tar.gz
```

**Automatisch in der App:** Die Anwendung legt jede Nacht ab 03:00 selbst eine Sicherung
ihrer Daten in `data/backups/` an (`ccu-auto-<datum>.json`, Export-Format, die letzten 14
bleiben; siehe [Bedienung 5.12](05-bedienung.md#512-datensicherung)). Die CCU-Zugangsdaten
(`backend/.env`) sind darin nicht enthalten, und die Dateien liegen auf demselben Server.

**Kopie auf einen anderen Rechner,** zum Beispiel ein NAS, das per SSH erreichbar ist
(Benutzer-Crontab mit `crontab -e`, täglich 03:30):
```cron
30 3 * * * rsync -a /opt/ccu/data/backups/ <nas-benutzer>@<nas>:ccu-backups/
```

**Komplettsicherung per Cron** (mit `backend/.env`; Beispiel, bewahrt 30 Tage auf):
```cron
30 3 * * * tar czf $HOME/ccu-backup-$(date +\%F).tar.gz -C /opt/ccu backend/.env data && find $HOME -maxdepth 1 -name 'ccu-backup-*.tar.gz' -mtime +30 -delete
```
Kopiere die Sicherungen zusätzlich auf einen **anderen Rechner** (NAS, externer Datenträger).

**Wiederherstellen:**
```bash
cd /opt/ccu
docker compose down
sudo tar xzf ~/ccu-backup-<datum>.tar.gz -C /opt/ccu
./deploy.sh
```
`sudo` ist nötig, weil der Container Dateien in `data/` als root anlegt (zum Beispiel die
Änderungshistorie).

**Einzelne Änderungen zurücknehmen:** Dafür ist die **Änderungshistorie** in der App da
(*Einstellungen → Änderungshistorie*, siehe [Bedienung](05-bedienung.md)). Sie nimmt
Profiländerungen im aktiven Modus und Umbenennungen zurück, auch auf den Thermostaten.

**Nur die letzte Schreiboperation an der Profildatei zurücknehmen** (Notlösung, wenn die
Datei selbst beschädigt ist): Vor jedem Schreiben legt die Anwendung den vorherigen Stand
von `profile_sets.json` als `profile_sets.backup.json` ab.
```bash
docker compose stop backend
sudo cp data/profile_sets.backup.json data/profile_sets.json
docker compose start backend
```
Das ändert nur die gespeicherte Datei, nicht die Thermostate.

## 4.4 Logs und Überwachung

```bash
docker compose logs --tail 100 backend           # letzte Zeilen des Backends
docker compose logs -f backend                   # live mitlesen (Strg+C beendet)
docker compose logs backend | grep -i -E "warning|error"
docker compose logs --tail 50 dashboard          # nginx-Zugriffe und Fehler
```

Das Backend schreibt im normalen Betrieb wenig. Zeilen mit `WARNING` deuten auf ein
Problem hin, das die Anwendung abgefangen hat (die Anfrage selbst ist gelungen). Die
wichtigsten:

| Meldung enthält | Bedeutung |
|---|---|
| `device edit not mirrored into the profile store` | Eine Profiländerung kam am Thermostat an, wurde aber nicht in `profile_sets.json` gespeichert. **Nach dem nächsten Moduswechsel würde der alte Stand zurückkehren.** Datei- und Rechteproblem prüfen, Änderung wiederholen |
| `not recorded in the change history` | Eine Änderung ist gelungen, steht aber nicht in der Änderungshistorie (und lässt sich dort nicht zurücknehmen) |
| `could not remember active profile` | Das aktive Profil wurde gewechselt, aber nicht gemerkt |
| `seeding the profile store` / `read P… before an edit` | Erstbefüllung eines Raumes oder Lesen des Stands vor einer Änderung fehlgeschlagen (Funk/CCU) |
| `could not save the active profile before the mode switch` | Vor dem Moduswechsel konnte das aktive Profil eines Raumes nicht gelesen werden |
| `CCU JSON-RPC logout failed` | Eine CCU-Sitzung wurde nicht sauber beendet (die CCU erlaubt nur wenige gleichzeitig) |
| `valve channel map ... unreadable` | `data/valve_channels.json` fehlt oder ist kein gültiges JSON |

**Health-Endpunkt:** `GET /api/system/health` → `{"status":"ok","ccu":"ok",...}`.
`degraded` heißt, dass die CCU nicht erreichbar ist (der HTTP-Status bleibt 200).
`docker compose ps` zeigt zusätzlich den Zustand der Container (`healthy`).

**Speicherplatz:** Docker sammelt alte Images. Aufräumen bei Bedarf:
```bash
docker image prune -f
docker system df
```

## 4.5 Diagnose- und Hilfsskripte

Alle Skripte liegen in `backend/scripts/` und laufen **im Backend-Container** (dort sind
die CCU-Zugangsdaten gesetzt und `data/` eingebunden):
```bash
docker compose exec backend python scripts/<skript>.py [Argumente]
```
Alle schreibenden Skripte melden zuerst, was sie tun würden (**Trockenlauf**), und ändern
erst mit `--apply` etwas.

| Skript | Zweck | Schreibt? |
|---|---|---|
| `dump_ccu.py [Raum]` | Listet die erkannten Thermostate. Mit Raumname: Datenpunkte und Profil-Schlüssel dieses Raumes | nein (nur CCU lesen) |
| `import_heating_schedule.py [--apply] <Raum> <datei.json>` | Liest einen fertigen Wochenplan (deutsches JSON-Format, siehe Skriptkopf) in **alle 6 Heizprofile** eines Raumes | nur `data/profile_sets.json`, nie die Geräte |
| `prepare_heating_sets.py [--apply] [--temp 20] [Räume…]` | Sichert den Kühlsatz vom Gerät und setzt den Heizsatz auf einen Flachwert. Für einen gefahrlosen Test des Moduswechsels | nur `data/profile_sets.json` |
| `drain_profile_transfer.py [--apply] [--max-days N]` | Überträgt in einem Lauf alles, was ein Moduswechsel aufgeschoben hat (sonst „Jetzt übertragen" in der App, 8 Tage je Lauf) | **ja, Thermostate** (funkschonend) |

Die Skripte tragen nichts in die Änderungshistorie ein.

Regeln beim Umgang mit Schreib-Skripten:
- **Nie gleichzeitig** mit einem Moduswechsel oder einer laufenden Übertragung in der
  App ausführen; beide würden unabhängig voneinander an dieselben Geräte schreiben.
- Vorher **Datensicherung** (4.3).
- Wer viele Tage überträgt, belastet den Funk (siehe [CCU-Hintergrund](08-ccu-hintergrund.md#88-duty-cycle)).

**Zustand prüfen:** `bash /opt/ccu/scripts/install.sh --check` prüft ohne etwas zu
verändern Pakete, Docker, Gruppe `docker`, Zugriff auf GitHub, `backend/.env`
(Rechte 600), die Erreichbarkeit der CCU (Port 80 und 2010), ob die Anwendung läuft und
mit der CCU verbunden ist, die MQTT-Verbindung, den Gerätezustand und ob die letzte
automatische Sicherung höchstens zwei Tage alt ist (siehe
[Installation 2.14](02-installation-debian.md#214-installationsskript)).

## 4.6 Fehlersuche im Betrieb

| Symptom | Mögliche Ursache und Vorgehen |
|---|---|
| Seite lädt nicht | `docker compose ps`; `curl -I http://localhost:3000`; Container starten: `docker compose up -d` |
| Seite lädt, aber „Lade …" bleibt oder Werte fehlen | Backend/CCU nicht erreichbar: Health prüfen (`"ccu"`), Backend-Log ansehen |
| `ccu: unreachable`, Log: `invalid credentials or too many sessions` | Passwort falsch **oder** die CCU hat zu viele offene Sitzungen (sie erlaubt nur wenige). Passwort in `.env` prüfen; sonst ca. 10 Minuten warten, Sitzungen laufen ab. Keine Skripte gleichzeitig laufen lassen |
| Fehler 502/503 in der App | 503 = CCU nicht erreichbar (Netz, CCU-Neustart); 502 = CCU hat abgelehnt oder nicht bestätigt. Nach kurzer Zeit erneut versuchen |
| Nach einem CCU-Update fehlen Messwerte kurz | Geräte melden sich nach einem CCU-Update erst nach einigen Minuten wieder. Abwarten |
| Ventilstellung zeigt „–" oder falsche Werte | [Konfiguration 3.3](03-konfiguration.md#33-ventil-zuordnung-datavalve_channelsjson) |
| Hinweisbalken „Fehler bei der Übertragung" | Details im Balken und im Backend-Log; nach Beseitigung der Ursache „Jetzt übertragen" (nach einem Moduswechsel) bzw. denselben Eintrag der Änderungshistorie erneut zurücksetzen. Lässt sich mit × wegklicken |
| „Hinweis: N Profil-Tage stehen noch aus" | Nach einem Moduswechsel sind höchstens 8 Tage je Lauf übertragen worden; „Jetzt übertragen" schreibt die nächsten. Beim Zurücksetzen über die Änderungshistorie (höchstens 14 Tage je Lauf) denselben Eintrag erneut zurücksetzen |
| Profilwechsel im Raum „springt zurück" | Der Wechsel dauert, wenn der Plan des Profils vom Thermostat abweicht (Plan wird zuerst geschrieben). Balken oben beobachten; bei einem Fehler wird **nicht** umgeschaltet |
| Fehler „Eine Profilübertragung läuft noch" (409) | Es läuft schon eine Übertragung. Warten, bis der Balken verschwindet |
| `deploy.sh` meldet `Permission denied (publickey)` | Nur bei einem privaten Fork über `git@…`: Der angemeldete Benutzer hat keinen Deploy-Key bei GitHub ([Installation, Schritt 4](02-installation-debian.md#24-schritt-4-projekt-herunterladen)) |
| Container `unhealthy`, obwohl die App funktioniert | Bei Installationen vor v0.17.0 fragte der Dashboard-Check `localhost` über IPv6 ab. `./deploy.sh` bringt den korrigierten Check |
| Anwendung hängt nach vielen schnellen Umschaltungen | Vermutlich Funk-Duty-Cycle der CCU erreicht (Geräte lehnen Schreibvorgänge ab). Ein bis zwei Stunden nichts umschalten. Nicht wiederholt zwischen Heizen und Kühlen wechseln |

## 4.7 Regeln, die Ärger vermeiden

1. **Nicht wiederholt die Betriebsart wechseln.** Jeder Wechsel schreibt Pläne per Funk.
2. **Nicht mehrere Schreibvorgänge parallel starten** (App, Skripte, CCU-Oberfläche).
3. **Das CCU-Passwort nur in `backend/.env`** eintragen.
4. **Vor Updates und größeren Änderungen sichern.**
5. **Nichts direkt an Projektdateien auf dem Server ändern** – Daten liegen in `data/`,
   Compose-Anpassungen in `docker-compose.override.yml` (4.1).
6. **Als normaler Benutzer arbeiten**, nicht als root (4.9).

## 4.8 Deinstallation

```bash
cd /opt/ccu
docker compose down --rmi local        # Container und die gebauten Images entfernen
# Datensicherung (4.3) vorher nicht vergessen!
cd / && sudo rm -rf /opt/ccu           # Projektverzeichnis samt Daten
```
Docker selbst bleibt installiert. Zum Entfernen:
`sudo apt-get purge -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin`.
Bei einem privaten Fork den Deploy-Key des Servers danach bei GitHub unter *Settings →
Deploy keys* löschen. Die Heizung läuft ohne die Anwendung mit den zuletzt in den Thermostaten
gespeicherten Plänen weiter.

## 4.9 root-Anmeldung per SSH sperren

Wer bisher als root gearbeitet hat, stellt so auf einen eigenen Benutzer um. Die
Reihenfolge ist wichtig, damit du dich nicht aussperrst.

1. **Benutzer anlegen** (als root) und berechtigen:
   ```bash
   apt-get install -y sudo
   adduser <name>
   usermod -aG sudo,docker <name>
   chown -R <name>:<name> /opt/ccu
   ```
   Das Passwort bei `adduser` im selben Programm (zum Beispiel PuTTY) eintippen wie später
   beim Anmelden; bei anderem Tastaturlayout passt es sonst nicht.
2. Nur bei einem privaten Fork: **Deploy-Key für den neuen Benutzer** anlegen und bei
   GitHub eintragen ([Installation, Schritt 4](02-installation-debian.md#24-schritt-4-projekt-herunterladen)).
   Der Schlüssel von root gilt nicht für andere Benutzer.
3. **Testen** – die root-Sitzung dabei offen lassen und in einem **zweiten** Fenster als
   neuer Benutzer anmelden:
   ```bash
   sudo whoami          # muss "root" ausgeben
   docker ps            # muss ohne sudo funktionieren
   cd /opt/ccu && git status && ./deploy.sh
   ```
4. **Erst dann** die root-Anmeldung per SSH sperren:
   ```bash
   echo "PermitRootLogin no" | sudo tee /etc/ssh/sshd_config.d/10-kein-root.conf
   sudo sshd -t                      # prüft die Konfiguration, darf nichts ausgeben
   sudo systemctl restart ssh
   ```
   In einem neuen Fenster prüfen: `root` wird abgelehnt, der neue Benutzer kommt rein.

Läuft der Server als Container oder VM auf **Proxmox**, kommst du über die
Proxmox-Konsole weiterhin als root hinein; `PermitRootLogin` gilt nur für SSH.

Im Alltag: Befehle für die App (`./deploy.sh`, `docker compose …`, `git …`) ohne `sudo`,
Verwaltung mit `sudo <befehl>`, eine längere root-Shell mit `sudo -i`.
