# 2 Installation der Anwendung auf Debian – Schritt für Schritt

Diese Anleitung installiert die **CCU-Anwendung** auf einem **bereits laufenden Debian 12
(„Bookworm") oder Debian 13 („Trixie")**. Die Einrichtung von Debian selbst (Installation,
Netzwerk, Benutzer, Updates) wird nicht beschrieben. Es werden keine Docker-Kenntnisse
vorausgesetzt.

> **Schreibweise:** Zeilen in den grauen Kästen sind Befehle für das Terminal des
> Linux-Servers. `<...>` steht für Werte, die du selbst einsetzt. Ein `#` in einer
> Zeile leitet eine Erklärung ein und gehört nicht zum Befehl.

> **Abkürzung:** Die Schritte 2 bis 8 erledigt auch das Installationsskript
> `scripts/install.sh` mit Rückfragen ([Abschnitt 2.14](#214-installationsskript)).
> Schritt 1 (Vorbereitung an der CCU) bleibt Handarbeit; die Abschnitte ab 2.9 gelten
> für beide Wege.

---

## 2.0 Was du brauchst

| Voraussetzung | Details |
|---|---|
| **Server** | Laufendes Debian 12 oder 13, 64 Bit (amd64 oder arm64), mindestens 1 GB RAM (2 GB empfohlen für den ersten Bauvorgang), 4 GB freier Speicher, Internetzugang |
| **Netzwerk** | Server und CCU im selben LAN; der Server hat eine **feste IP-Adresse** (oder eine DHCP-Reservierung im Router) |
| **CCU** | CCU3 oder OpenCCU mit HomematicIP-Wandthermostaten (HmIP-WTH-1) und Fußbodenheizungsaktor (HmIP-FALMOT-C12), im LAN erreichbar |
| **CCU-Zugang** | Benutzername und Passwort eines CCU-Benutzers (am einfachsten ein Administrator-Konto) |
| **Zugriff auf den Server** | Terminal (direkt oder per SSH) mit einem Benutzer, der `sudo` verwenden darf |

**Arbeite als normaler Benutzer, nicht als root.** Falls du bisher nur `root` hast, lege
einmalig (als root) einen eigenen Benutzer an und melde dich danach mit ihm an:
```bash
apt-get install -y sudo
adduser <name>                  # fragt nach einem Passwort
usermod -aG sudo <name>         # darf Verwaltungsbefehle mit sudo ausführen
```
Die Gruppe `docker` kommt in Schritt 3 dazu. Tippe das Passwort bei `adduser` im selben
Programm (zum Beispiel PuTTY) wie später beim Anmelden: Bei unterschiedlichem
Tastaturlayout passt es sonst nicht. Wie du danach die root-Anmeldung per SSH sperrst,
steht in [Betrieb, Abschnitt 4.9](04-betrieb-und-wartung.md#49-root-anmeldung-per-ssh-sperren).

---

## 2.1 Schritt 1: An der CCU vorbereiten

Diese Schritte erledigst du in der Weboberfläche der CCU (`http://<ccu-ip>`). Die
Bezeichnungen der Menüs können je nach CCU-/OpenCCU-Version leicht abweichen.

1. **Feste IP für die CCU:** Notiere die IP-Adresse der CCU (im Router oder unter
   *Einstellungen → Systemsteuerung → Netzwerkeinstellungen*). Sie soll sich nicht
   ändern. Im Folgenden heißt sie `<ccu-ip>`.
2. **Zugang für die Anwendung:** Lege einen Benutzer an oder verwende einen
   vorhandenen (*Einstellungen → Systemsteuerung → Benutzerverwaltung*). Er muss sich
   anmelden und Geräte bedienen dürfen. Notiere Benutzername und Passwort.
3. **Zugriff auf die XML-RPC-Schnittstelle freigeben:** Die Anwendung liest Zustände
   über Port **2010** (HmIP-Server). Prüfe unter *Einstellungen → Systemsteuerung →
   Sicherheit* (Bereich *Firewall*), dass der Zugriff auf die **XML-RPC-API** für den
   Server erlaubt ist (Vollzugriff, oder eingeschränkt auf die IP deines Servers).
   Ob es klappt, prüfst du in Abschnitt 2.5.
4. **Namen der Geräte:** Die Anwendung erkennt Räume an den Gerätenamen.
   - Jeder **Wandthermostat** (HmIP-WTH-1) heißt genau wie der Raum, zum Beispiel
     `Wohnzimmer`.
   - Die zugehörige **Heizgruppe** heißt `<Raum> INT<nummer>`, zum Beispiel
     `Wohnzimmer INT0000003`. Die CCU legt diese Namen beim Anlegen der Gruppen
     selbst so an.

   Ändere die Namen nur, wenn sie davon abweichen (*Status und Bedienung → Geräte*).
5. **Zuordnung Aktor-Kanal → Raum notieren** (für Abschnitt 2.7): Öffne *Status und
   Bedienung → Geräte* und klicke beim **HmIP-FALMOT-C12** die Kanäle 1, 2, 3 … auf.
   Bei jedem Kanal steht unter *Verknüpfungspartner* der zugehörige Raumthermostat.
   Notiere dir zum Beispiel „Kanal 1 = Arbeitszimmer, Kanal 2 bis 4 = Wohnzimmer, …".
   Ein Raum kann mehrere Kanäle (Heizkreise) haben.

---

## 2.2 Schritt 2: Benötigte Pakete installieren

Die Anwendung braucht nur `git` (Projekt herunterladen), `curl` (Tests) und
`ca-certificates` (verschlüsselte Downloads). `nano` dient als einfacher Editor.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git nano
```

---

## 2.3 Schritt 3: Docker installieren

Debian liefert Docker in eigenen Paketen mit, die oft veraltet sind. Die Anwendung
benötigt **Docker Engine** und das **Compose-Plugin (Version 2)**. Sie werden hier aus
dem offiziellen Docker-Paketarchiv installiert.

**3.1 Paketarchiv einrichten**
```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
```

**3.2 Docker installieren**
```bash
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

**3.3 Prüfen**
```bash
sudo systemctl status docker --no-pager | head -5      # muss "active (running)" zeigen
docker --version
docker compose version                                  # muss "Docker Compose version v2..." zeigen
sudo docker run --rm hello-world                        # muss "Hello from Docker!" ausgeben
```
Der Dienst startet nach jedem Neustart automatisch. Falls nicht:
`sudo systemctl enable --now docker`.

**3.4 Eigenen Benutzer für Docker berechtigen** (damit du nicht bei jedem Befehl
`sudo` brauchst):
```bash
sudo usermod -aG docker $USER
```
**Danach einmal abmelden und wieder anmelden** (bei SSH: Verbindung neu aufbauen).
Prüfen: `docker ps` muss ohne `sudo` und ohne Fehler laufen.

> **Hinweis:** Mitglieder der Gruppe `docker` haben faktisch Root-Rechte auf dem
> Server. Nimm nur Benutzer auf, denen du vertraust.

---

## 2.4 Schritt 4: Projekt herunterladen

Das Projekt ist öffentlich auf GitHub (https://github.com/kunterauskoeln/ccu-climate-dashboard) und wird per HTTPS
geklont; ein Schlüssel ist dafür nicht nötig.

```bash
sudo mkdir -p /opt/ccu
sudo chown $USER:$USER /opt/ccu
git clone https://github.com/kunterauskoeln/ccu-climate-dashboard.git /opt/ccu
cd /opt/ccu
git log -1 --oneline            # zeigt den aktuellen Stand
git tag --list                  # alle Versionen
```
Die Anleitung geht durchgehend von `/opt/ccu` aus. Ohne Angabe verwendet `deploy.sh`
(Schritt 8) den neuesten Stand des Zweigs `main`; eine bestimmte Version installierst du
mit `./deploy.sh <tag>`.

**Eigener privater Fork:** Wer eine private Kopie auf GitHub verwendet, braucht auf dem
Server einen **Deploy-Key** (gilt nur für dieses eine Repository und nur zum Lesen):

```bash
ssh-keygen -t ed25519 -C "$(whoami)@$(hostname) ccu" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub        # bei GitHub: Settings -> Deploy keys -> Add deploy key,
                                 # "Allow write access" NICHT ankreuzen
ssh -T git@github.com            # Fingerabdruck SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU
git clone git@github.com:<konto>/<repository>.git /opt/ccu
```
Weitergeben darf man nur die `.pub`-Datei; der private Schlüssel bleibt auf dem Server.
`install.sh` erledigt das mit `CCU_REPO=git@github.com:<konto>/<repository>.git` selbst.

---

## 2.5 Schritt 5: Verbindung zur CCU testen

Ersetze `<ccu-ip>` durch die IP der CCU. Beide Tests brauchen **kein Passwort**.

**Weboberfläche/JSON-RPC (Port 80) erreichbar?**
```bash
curl -sS -m 5 -o /dev/null -w "HTTP %{http_code}\n" http://<ccu-ip>/
```
Erwartet: `HTTP 200` (oder `301`/`302`).

**XML-RPC/HmIP-Server (Port 2010) erreichbar?**
```bash
curl -sS -m 5 -X POST -H "Content-Type: text/xml" \
  -d '<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>' \
  http://<ccu-ip>:2010/ | head -c 300; echo
```
Erwartet: eine XML-Antwort mit `<methodResponse>` und Methodennamen wie `getValue`.

| Ausgabe | Bedeutung und Lösung |
|---|---|
| `Connection refused` oder Zeitüberschreitung bei Port 80 | Falsche IP, CCU aus, anderes Netz. Prüfe Router und Kabel |
| `Connection refused` oder Zeitüberschreitung bei **Port 2010** | Die XML-RPC-API ist in der CCU-Firewall gesperrt (Abschnitt 2.1, Punkt 3) |
| `Empty reply` bei Port 2010 | Zugriff auf die XML-RPC-API nur für andere IP-Adressen erlaubt; die IP des Servers eintragen |

---

## 2.6 Schritt 6: Zugangsdaten eintragen (`backend/.env`)

```bash
cd /opt/ccu
cp backend/.env.example backend/.env
nano backend/.env
```

Inhalt anpassen (Erklärung aller Werte in [Konfiguration](03-konfiguration.md)):
```ini
CCU_HOST=<ccu-ip>              # nur die IP oder der Name, ohne http://
CCU_USERNAME=<ccu-benutzer>
CCU_PASSWORD=<ccu-passwort>
```
Speichern: `Strg+O`, `Enter`, dann `Strg+X`.

Rechte einschränken, damit nur du das Passwort lesen kannst:
```bash
chmod 600 backend/.env
```

> **Sonderzeichen im Passwort** (`$`, `#`, Leerzeichen): Setze das Passwort in
> **einfache Anführungszeichen**, zum Beispiel `CCU_PASSWORD='ab$c #1'`. Ohne sie ersetzt
> Docker Compose `$name` durch eine (leere) Variable, und ` #` beginnt einen Kommentar.
> Innerhalb einfacher Anführungszeichen gilt jedes Zeichen wörtlich; nur ein `'` im
> Passwort selbst geht so nicht. Wenn die Anmeldung später mit „invalid credentials"
> scheitert, prüfe zuerst dies. Das Installationsskript schreibt das Passwort
> automatisch so. Die Datei `backend/.env` steht in `.gitignore` und wird nie hochgeladen.

---

## 2.7 Schritt 7: Ventil-Zuordnung anpassen (`data/valve_channels.json`)

Die Ventilstellung liest die Anwendung von den Kanälen des Aktors. Welcher Kanal zu
welchem Raum gehört, verrät die CCU der Anwendung nicht, deshalb steht die Zuordnung
in einer Datei. Alle Daten der Anwendung liegen im Ordner `/opt/ccu/data/`, den Updates
nie anfassen. Lege die Datei aus der mitgelieferten Vorlage an und trage die Notizen aus
Abschnitt 2.1, Punkt 5 ein:

```bash
cd /opt/ccu
mkdir -p data
cp backend/src/app/valve_channels.json data/valve_channels.json
nano data/valve_channels.json
```
```json
{
  "Arbeitszimmer": [1],
  "Wohnzimmer": [2, 3, 4],
  "Bad": [5],
  "WC": [6],
  "Schlafzimmer": [7],
  "Ankleide": [8],
  "Flur": [9]
}
```
- Die **Schlüssel** sind die Raumnamen (genau wie die Thermostatnamen in der CCU).
- Die **Zahlen** sind die Kanalnummern des Aktors (`:1` bis `:12`). Bei mehreren Kanälen
  zeigt die Anwendung den Mittelwert.
- Ein Raum ohne Eintrag zeigt „–" statt einer Ventilstellung; alles andere funktioniert.

Überspringst du diesen Schritt, legt `deploy.sh` die Datei beim ersten Start aus der
Vorlage an. Du kannst sie jederzeit später anpassen; danach genügt
`docker compose restart backend`.

---

## 2.8 Schritt 8: Erster Start

```bash
cd /opt/ccu
./deploy.sh
```

Was `deploy.sh` tut:
1. lädt den neuesten Stand (`git fetch`) und wechselt auf `origin/main`; danach startet
   es sich einmal selbst neu, damit der Rest garantiert aus der neuen Version läuft;
2. legt im Ordner `data/` fehlende Dateien an: `profile_names.json` und
   `valve_channels.json` aus den Vorlagen, `profile_sets.json` und
   `profile_sets.backup.json` leer. Vorhandene Dateien bleiben unverändert;
3. baut die Images und startet die zwei Container `ccu-backend` und `ccu-dashboard`
   (`docker compose up -d --build`);
4. wartet bis zu 60 Sekunden auf `http://localhost:3000/api/system/health`.

Der **erste Bauvorgang dauert einige Minuten** (Abhängigkeiten werden geladen, das
Frontend wird gebaut). Spätere Starts sind deutlich schneller.

Bei Erfolg endet die Ausgabe so:
```
==> OK
{"status":"ok","ccu":"ok","uptime":...,"ccu_host":"<ccu-ip>"}
```

Endet `deploy.sh` mit `!! Health check failed`, stehen darunter die letzten Logzeilen
des Backends. Häufige Ursachen: [Abschnitt 2.13](#213-fehlersuche-bei-der-installation).

> **Deine Daten sind vor Updates sicher:** `deploy.sh` wechselt mit `git checkout -f`
> auf den gewünschten Stand. Das betrifft nur die Dateien des Projekts, nicht den Ordner
> `data/`; der ist von Git ausgenommen. Eigene Anpassungen an `docker-compose.yml`
> gehören in eine eigene Datei, siehe
> [Betrieb, „Eigene Anpassungen"](04-betrieb-und-wartung.md#eigene-anpassungen).

---

## 2.9 Schritt 9: Prüfen, ob alles läuft

```bash
docker compose ps
```
Beide Container (`ccu-backend`, `ccu-dashboard`) sollen laufen und nach spätestens
einer Minute `healthy` zeigen.

```bash
curl -s http://localhost:3000/api/system/health
curl -s http://localhost:3000/api/rooms | head -c 400; echo
```
Der zweite Befehl muss Räume mit Temperaturen liefern.

**Im Browser** (auf einem beliebigen Gerät im LAN): `http://<server-ip>:3000`.
Du siehst eine Kachel je Raum. Öffne einen Raum: Der Drehregler und die
Ventilstellung erscheinen.

**CCU-Daten im Detail prüfen** (nur lesend, ändert nichts):
```bash
docker compose exec backend python scripts/dump_ccu.py
```
Das Skript listet die erkannten Wandthermostate. Mit einem Raumnamen als Argument
(`... dump_ccu.py Wohnzimmer`) zeigt es zusätzlich die Datenpunkte dieses Raumes.

---

## 2.10 Schritt 10: Automatischer Start nach einem Neustart

Die Container sind mit `restart: always` konfiguriert, und der Docker-Dienst startet
beim Booten. `always` ist hier bewusst gewählt: Beim Herunterfahren stoppt Debian den
Docker-Dienst und damit jeden Container geordnet. Für Docker ist das nicht von einem
manuellen `docker stop` zu unterscheiden, und mit der Einstellung `unless-stopped` blieben
die Container nach dem Neustart deshalb aus. Teste das einmal:
```bash
sudo reboot
# ... nach dem Neustart, neu anmelden:
docker compose -f /opt/ccu/docker-compose.yml ps
curl -s http://localhost:3000/api/system/health
```

---

## 2.11 Schritt 11: Hinweise zur Sicherheit

Die Anwendung hat **keine Anmeldung**. Für das Heimnetz ist das üblich, beachte aber:

1. **Nicht ins Internet stellen.** Leite den Port 3000 nie am Router ins Internet
   weiter. Für Zugriff von unterwegs nutze ein VPN (zum Beispiel WireGuard).
2. **Docker und Firewalls:** Docker umgeht `ufw`-Regeln für veröffentlichte Ports.
   Beschränke den Zugriff auf den Port 3000 deshalb am Router oder mit der
   Docker-Kette `DOCKER-USER`.

**Anderer Port statt 3000?** Das gehört in eine eigene Datei
`docker-compose.override.yml` (siehe
[Betrieb, „Eigene Anpassungen"](04-betrieb-und-wartung.md#eigene-anpassungen)). Beachte,
dass der Health-Check in `deploy.sh` Port 3000 abfragt; mit einem anderen Port meldet er
am Ende einen Fehler, obwohl die Anwendung läuft.

---

## 2.12 Schritt 12: Erste Einrichtung in der Anwendung

1. **Betriebsart prüfen:** *Einstellungen → Betriebsart*. Sie zeigt den aktuellen
   Zustand des Aktors (Heizen oder Kühlen). Schalte nichts um, bevor du die Punkte 2 bis 4
   gelesen hast.
2. **Profile:** Beim ersten Bearbeiten eines Raumes liest die Anwendung dessen
   aktuelle Profile vom Thermostat und legt daraus **beide** Sätze (Heizen und
   Kühlen) an. Danach sind sie voneinander unabhängig.
3. **Profilnamen** vergibst du unter *Einstellungen → Heizprofile → Raum → Profil →
   Profil umbenennen* (sie gelten für alle Räume).
4. **Beim ersten Wechsel der Betriebsart** schreibt die Anwendung die gespeicherten
   Pläne der neuen Betriebsart auf die Thermostate. Das geschieht im Hintergrund und
   funkschonend (ein Tag alle 4 Sekunden, höchstens 8 Tage je Wechsel, der Rest folgt
   über den Knopf „Jetzt übertragen"). Setze **vor dem ersten Wechsel** die
   Solltemperaturen der neuen Betriebsart so, dass Heizung oder Kühlung nicht
   unerwünscht anläuft (zum Beispiel beim Wechsel auf Kühlen an einem kühlen Tag),
   und beobachte den Vorgang. Details in [Bedienung](05-bedienung.md).
5. **Fertige Zeitpläne einlesen** (optional): Dafür gibt es das Skript
   `scripts/import_heating_schedule.py` (Beschreibung in
   [Betrieb](04-betrieb-und-wartung.md#45-diagnose--und-hilfsskripte)).

---

## 2.13 Fehlersuche bei der Installation

| Symptom | Ursache und Lösung |
|---|---|
| `docker: permission denied` | Benutzer nicht in der Gruppe `docker` oder nicht neu angemeldet (Abschnitt 2.3, Punkt 3.4) |
| `git clone` oder `deploy.sh` meldet `Permission denied (publickey)` | Nur bei einem privaten Fork über `git@…`: Dieser Benutzer hat keinen Deploy-Key bei GitHub (Abschnitt 2.4). Jeder Benutzer, der `deploy.sh` ausführt, braucht seinen eigenen Schlüssel |
| `deploy.sh` bricht bei `git checkout` ab | Lokale Änderung an einer Datei des Projekts. `git status` zeigt welche; eigene Anpassungen gehören nach `data/` oder in `docker-compose.override.yml` (siehe [Eigene Anpassungen](04-betrieb-und-wartung.md#eigene-anpassungen)) |
| Health zeigt `"ccu":"unreachable"` | Backend erreicht die CCU nicht oder das Login schlägt fehl. `docker compose logs --tail 50 backend` ansehen. Meldung `Session.login ... invalid credentials or too many sessions`: Benutzername und Passwort in `backend/.env` prüfen, danach `docker compose up -d --force-recreate backend`. Bei „too many sessions" etwa 10 Minuten warten (die CCU begrenzt gleichzeitige Anmeldungen) |
| Räume erscheinen nicht / Liste leer | Gerätenamen stimmen nicht (Abschnitt 2.1, Punkt 4) oder Port 2010 ist gesperrt (Abschnitt 2.5). `docker compose exec backend python scripts/dump_ccu.py` zeigt, was erkannt wird |
| Ventilstellung zeigt überall „–" | `data/valve_channels.json` fehlt, ist fehlerhaft oder die Raumnamen stimmen nicht (Abschnitt 2.7). Bei defekter Datei steht im Backend-Log eine Warnung |
| Ventilstellung bleibt 0 %, obwohl die CCU mehr zeigt | Falscher Kanal in `data/valve_channels.json`; Zuordnung in der CCU nochmals prüfen, danach `docker compose restart backend` |
| Seite lädt nicht (`ERR_CONNECTION_REFUSED`) | Container läuft nicht (`docker compose ps`) oder Firewall/Port. Auf dem Server `curl -I http://localhost:3000` versuchen |
| Beim ersten Start „no space left on device" | Zu wenig Speicher; `docker system df`, dann `docker image prune` |
| Sehr langsamer Bau auf einem Raspberry Pi | Normal beim ersten Mal (Frontend-Build), 10 bis 20 Minuten sind möglich; ausreichend RAM/Swap bereitstellen |
| `.env` geändert, aber nichts passiert | Änderungen werden erst nach `docker compose up -d --force-recreate backend` gelesen |
| `docker compose ps` zeigt nach einem Neustart keine laufenden Container | Nur bei Installationen vor v0.17.0 (damals `restart: unless-stopped`). `./deploy.sh` bringt die aktuelle Einstellung `restart: always` |
| Umlaute und Häkchen erscheinen in PuTTY als `â`, `Ã¤` o. ä. | Anzeigeproblem von PuTTY: *Window → Translation → Remote character set* auf **UTF-8** stellen und die Sitzung speichern |

Weitere Hilfe: [Betrieb und Wartung](04-betrieb-und-wartung.md).

---

## 2.14 Installationsskript

`scripts/install.sh` führt die Schritte 2 bis 8 dieser Anleitung aus. Jeder Schritt prüft
zuerst, ob er schon erledigt ist; das Skript kann also gefahrlos erneut laufen, zum
Beispiel nach einem Abbruch oder auf einem Server, auf dem schon Teile eingerichtet sind.

| Schritt | Was das Skript tut |
|---|---|
| Grundlagen | Bricht ab, wenn es als root läuft (eigener Benutzer mit sudo, siehe 2.0); prüft Debian-Version und Architektur |
| Pakete | Installiert fehlende Pakete: `ca-certificates curl git nano openssh-client` |
| Docker | Richtet das offizielle Docker-Archiv ein, installiert Docker mit Compose-Plugin, startet den Dienst beim Booten, nimmt dich in die Gruppe `docker` auf. Ist das Debian-Paket `docker.io` installiert, bricht es mit einem Hinweis ab |
| GitHub | Prüft, ob das Repository erreichbar ist. Nur bei einer `git@…`-Adresse (privater Fork, `CCU_REPO`): erzeugt den Deploy-Key, trägt `github.com` nach Prüfung des Fingerabdrucks als bekannten Server ein, zeigt den öffentlichen Schlüssel und **wartet**, bis du ihn eingetragen hast |
| Projekt | Klont nach `/opt/ccu` |
| CCU | Fragt IP, Benutzer und Passwort (verdeckt) ab, prüft Port 80, Port 2010 und die **Anmeldung** an der CCU (und meldet sich sofort wieder ab), schreibt `backend/.env` mit Rechten 600 |
| Ventil-Zuordnung | Legt `data/valve_channels.json` aus der Vorlage an und bietet an, sie gleich mit nano zu bearbeiten |
| Start | Ruft `./deploy.sh` auf und zeigt am Ende die Adresse der Anwendung |

Das Passwort wird nirgends angezeigt oder protokolliert und steht danach nur in
`backend/.env`.

**Skript auf den Server bringen** (als dein Benutzer):
```bash
curl -fsSLO https://raw.githubusercontent.com/kunterauskoeln/ccu-climate-dashboard/main/scripts/install.sh
```

**Ausführen** (als dein Benutzer, nicht als root):
```bash
bash install.sh                  # installieren
bash install.sh --ref v0.24.0    # eine bestimmte Version starten
bash install.sh --check          # nur prüfen, nichts verändern
```
Läuft die Anwendung schon, liegt das Skript unter `/opt/ccu/scripts/install.sh`.
`--check` zeigt für jeden Punkt `[ok]` oder `[fehlt]` und am Ende, ob die Anwendung
läuft und mit der CCU verbunden ist; es eignet sich auch später zur schnellen Kontrolle.

Andere Ziele über Umgebungsvariablen: `CCU_DIR=/srv/ccu bash install.sh` (Zielordner),
`CCU_REPO=…` (Adresse des Repositorys).

Nach dem ersten Lauf einmal ab- und wieder anmelden, damit `docker` ohne `sudo`
funktioniert. Weiter geht es mit [Abschnitt 2.9](#29-schritt-9-prüfen-ob-alles-läuft).
