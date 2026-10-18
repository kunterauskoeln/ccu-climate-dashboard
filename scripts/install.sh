#!/usr/bin/env bash
#
# Installiert die CCU-Anwendung auf einem laufenden Debian 12/13 -- dieselben
# Schritte wie docs/02-installation-debian.md, nur automatisch und mit
# Rückfragen, wo eine Entscheidung nötig ist.
#
#   bash install.sh            installieren / fehlende Teile ergänzen
#   bash install.sh --check    nur prüfen, nichts verändern
#   bash install.sh --ref v0.23.0   eine bestimmte Version starten (Standard: origin/main)
#
# Jeder Schritt prüft zuerst, ob er schon erledigt ist; das Skript kann also
# gefahrlos mehrfach laufen (zum Beispiel nach einem Abbruch).
#
# Auf einem neuen Server zuerst nur dieses Skript holen:
#   curl -fsSLO https://raw.githubusercontent.com/kunterauskoeln/ccu-climate-dashboard/main/scripts/install.sh
# oder es aus einer vorhandenen Kopie unter /opt/ccu/scripts/ ausführen.
#
# Einstellbar über Umgebungsvariablen:
#   CCU_DIR   Zielordner                (Standard: /opt/ccu)
#   CCU_REPO  Adresse des Repositorys   (Standard: https://github.com/kunterauskoeln/ccu-climate-dashboard.git)
#             Eine git@…-Adresse (eigener privater Fork) richtet einen Deploy-Key ein.
#
# Das CCU-Passwort wird verdeckt abgefragt, nur in backend/.env (Rechte 600)
# geschrieben und nie angezeigt oder protokolliert.

set -euo pipefail

DIR="${CCU_DIR:-/opt/ccu}"
REPO="${CCU_REPO:-https://github.com/kunterauskoeln/ccu-climate-dashboard.git}"
REF="origin/main"
MODE="install"
# Fingerabdruck des ED25519-Host-Schlüssels von github.com (veröffentlicht von GitHub)
GITHUB_FP="SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
PACKAGES=(ca-certificates curl git nano openssh-client)
DOCKER_PACKAGES=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin)

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --ref) shift; REF="${1:?--ref braucht einen Wert, z. B. v0.23.0}" ;;
    -h|--help) sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unbekannte Option: $1 (siehe --help)" >&2; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------- Ausgabe
if [ -t 1 ]; then
  C_OK=$'\e[32m'; C_WARN=$'\e[33m'; C_ERR=$'\e[31m'; C_HEAD=$'\e[1m'; C_OFF=$'\e[0m'
else
  C_OK=""; C_WARN=""; C_ERR=""; C_HEAD=""; C_OFF=""
fi
PROBLEMS=0
step() { printf '\n%s== %s%s\n' "$C_HEAD" "$*" "$C_OFF"; }
ok()   { printf '  %s[ok]%s %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '  %s[!!]%s %s\n' "$C_WARN" "$C_OFF" "$*"; }
miss() { printf '  %s[fehlt]%s %s\n' "$C_ERR" "$C_OFF" "$*"; PROBLEMS=$((PROBLEMS + 1)); }
info() { printf '       %s\n' "$*"; }
die()  { printf '\n%sAbbruch:%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; exit 1; }

# Rückfragen lesen immer vom Terminal, auch wenn das Skript per Pipe kam. Ohne
# Terminal (oder bei Strg+D) wird abgebrochen statt mit leeren Antworten weiterzulaufen.
tty_read() {  # tty_read <read-Optionen…> <Variable>  (immer mit -r)
  { : </dev/tty; } 2>/dev/null || die "Keine Eingabe möglich: kein Terminal. Bitte direkt in einer Sitzung (z. B. PuTTY) starten."
  read -r "$@" </dev/tty || die "Eingabe beendet (Strg+D)."
}
ask() {  # ask "Frage" "Vorgabe" -> Antwort auf stdout
  local answer
  tty_read -p "  $1 [$2]: " answer
  printf '%s' "${answer:-$2}"
}
confirm() {  # confirm "Frage" j|n
  local answer
  answer=$(ask "$1 (j/n)" "$2")
  case "$answer" in j|J|ja|Ja|y|Y|yes) return 0 ;; *) return 1 ;; esac
}
pause() { local _answer; tty_read -p "  $1" _answer; }

checking() { [ "$MODE" = "check" ]; }

# ---------------------------------------------------------------- 0. Grundlagen
step "Grundlagen"

if [ "$(id -u)" -eq 0 ]; then
  if checking; then
    warn "Läuft als root. Für die Installation einen normalen Benutzer mit sudo verwenden."
  else
    die "Bitte nicht als root ausführen. Lege einen eigenen Benutzer an und melde dich mit ihm an:
    apt-get install -y sudo
    adduser <name>
    usermod -aG sudo <name>
(Details: docs/02-installation-debian.md, Abschnitt 2.0)"
  fi
else
  ok "Benutzer: $(id -un)"
fi

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [ "${ID:-}" = "debian" ] && { [ "${VERSION_CODENAME:-}" = "bookworm" ] || [ "${VERSION_CODENAME:-}" = "trixie" ]; }; then
    ok "System: ${PRETTY_NAME:-Debian}"
  else
    warn "System: ${PRETTY_NAME:-unbekannt}. Getestet ist nur Debian 12 (bookworm) und 13 (trixie)."
    if ! checking && ! confirm "Trotzdem fortfahren?" n; then die "Abgebrochen."; fi
  fi
else
  warn "/etc/os-release fehlt, System unbekannt."
fi
CODENAME="${VERSION_CODENAME:-bookworm}"

ARCH="$(dpkg --print-architecture 2>/dev/null || echo unbekannt)"
case "$ARCH" in
  amd64|arm64) ok "Architektur: $ARCH" ;;
  *) warn "Architektur: $ARCH (getestet sind amd64 und arm64)" ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  if ! command -v sudo >/dev/null 2>&1; then
    if checking; then
      miss "sudo ist nicht installiert"
    else
      die "sudo fehlt. Als root: apt-get install -y sudo && usermod -aG sudo $(id -un)"
    fi
  elif ! checking; then
    info "Für die Installation werden Verwaltungsrechte gebraucht (sudo-Passwort):"
    sudo -v || die "sudo ist für $(id -un) nicht erlaubt (Gruppe sudo?)."
    ok "sudo erlaubt"
  else
    ok "sudo vorhanden"
  fi
fi
SUDO="sudo"; [ "$(id -u)" -eq 0 ] && SUDO=""

# ---------------------------------------------------------------- 1. Pakete
step "Pakete (${PACKAGES[*]})"
missing=()
for pkg in "${PACKAGES[@]}"; do
  if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
    ok "$pkg"
  else
    missing+=("$pkg")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  if checking; then
    for pkg in "${missing[@]}"; do miss "$pkg"; done
  else
    info "Installiere: ${missing[*]}"
    $SUDO apt-get update
    $SUDO apt-get install -y "${missing[@]}"
    ok "Pakete installiert"
  fi
fi

# ---------------------------------------------------------------- 2. Docker
step "Docker"
have_docker() { command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; }
if dpkg-query -W -f='${Status}' docker.io 2>/dev/null | grep -q "install ok installed"; then
  warn "Das Debian-Paket docker.io ist installiert (oft veraltet, ohne Compose v2)."
  info "Die Anwendung braucht Docker aus dem offiziellen Docker-Archiv. Entfernen mit:"
  info "  sudo apt-get remove docker.io docker-compose docker-doc podman-docker"
  info "und dieses Skript erneut starten."
  if checking; then PROBLEMS=$((PROBLEMS + 1)); else die "Bitte zuerst docker.io entfernen."; fi
elif have_docker; then
  ok "$(docker --version)"
  ok "$(docker compose version)"
elif checking; then
  miss "Docker Engine mit Compose-Plugin (v2)"
else
  info "Richte das offizielle Docker-Paketarchiv ein und installiere Docker…"
  $SUDO install -m 0755 -d /etc/apt/keyrings
  $SUDO curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  $SUDO chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $CODENAME stable" \
    | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  $SUDO apt-get update
  $SUDO apt-get install -y "${DOCKER_PACKAGES[@]}"
  ok "$(docker --version)"
fi

if command -v systemctl >/dev/null 2>&1 && command -v docker >/dev/null 2>&1; then
  if systemctl is-enabled --quiet docker 2>/dev/null && systemctl is-active --quiet docker 2>/dev/null; then
    ok "Docker-Dienst läuft und startet beim Booten"
  elif checking; then
    miss "Docker-Dienst läuft nicht oder startet nicht beim Booten (sudo systemctl enable --now docker)"
  else
    $SUDO systemctl enable --now docker
    ok "Docker-Dienst gestartet und für den Systemstart aktiviert"
  fi
fi

# Gruppe docker: ohne sie braucht jeder docker-Befehl sudo. Frisch hinzugefügt
# gilt sie erst nach neuer Anmeldung -- bis dahin läuft deploy.sh über `sg docker`.
DOCKER_VIA_SG=0
if [ "$(id -u)" -ne 0 ]; then
  if id -nG | tr ' ' '\n' | grep -qx docker; then
    ok "$(id -un) ist in der Gruppe docker"
  elif getent group docker | cut -d: -f4 | tr ',' '\n' | grep -qx "$(id -un)"; then
    ok "$(id -un) ist in der Gruppe docker (gilt ab der nächsten Anmeldung)"
    DOCKER_VIA_SG=1
  elif checking; then
    miss "$(id -un) ist nicht in der Gruppe docker (sudo usermod -aG docker $(id -un), danach neu anmelden)"
  elif getent group docker >/dev/null; then
    $SUDO usermod -aG docker "$(id -un)"
    ok "$(id -un) zur Gruppe docker hinzugefügt (gilt ab der nächsten Anmeldung)"
    DOCKER_VIA_SG=1
  fi
fi

# ---------------------------------------------------------------- 3. Zugang zu GitHub
step "Zugang zum Repository ($REPO)"
KEY="$HOME/.ssh/id_ed25519"
KNOWN="$HOME/.ssh/known_hosts"
can_read_repo() { GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10" git ls-remote "$REPO" HEAD >/dev/null 2>&1; }

if [[ "$REPO" != git@* ]]; then
  # öffentliches Repository (HTTPS): kein Schlüssel nötig
  if can_read_repo; then
    ok "Repository erreichbar"
  elif checking; then
    miss "Repository nicht erreichbar: $REPO (Internetverbindung? Adresse?)"
  else
    die "Repository nicht erreichbar: $REPO. Internetverbindung und Adresse prüfen."
  fi
else
  if [ -f "$KEY" ]; then
    ok "Schlüssel vorhanden: $KEY"
  elif checking; then
    miss "Kein SSH-Schlüssel $KEY (Deploy-Key, docs/02 Abschnitt 2.4)"
  else
    mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
    ssh-keygen -q -t ed25519 -C "$(id -un)@$(hostname) ccu" -f "$KEY" -N ""
    ok "Schlüssel erzeugt: $KEY"
  fi

  if [[ "$REPO" == git@github.com:* ]]; then
    if [ -f "$KNOWN" ] && ssh-keygen -F github.com -f "$KNOWN" >/dev/null 2>&1; then
      ok "github.com ist als bekannter Server eingetragen"
    elif checking; then
      miss "github.com ist noch nicht als bekannter Server eingetragen"
    else
      scanned="$(ssh-keyscan -t ed25519 github.com 2>/dev/null || true)"
      fp="$(printf '%s\n' "$scanned" | ssh-keygen -lf - 2>/dev/null | awk '{print $2}')"
      if [ -n "$scanned" ] && [ "$fp" = "$GITHUB_FP" ]; then
        mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
        printf '%s\n' "$scanned" >>"$KNOWN"
        ok "github.com eingetragen (Fingerabdruck $GITHUB_FP geprüft)"
      else
        die "Der Schlüssel von github.com passt nicht zum erwarteten Fingerabdruck ($GITHUB_FP), erhalten: '${fp:-nichts}'. Netzwerk prüfen; nicht fortfahren."
      fi
    fi
  fi

  if [ -f "$KEY" ] && can_read_repo; then
    ok "Lesezugriff auf das Repository funktioniert"
  elif checking; then
    miss "Kein Lesezugriff auf das Repository (Deploy-Key bei GitHub eingetragen?)"
  else
    printf '\n  Trage diesen öffentlichen Schlüssel bei GitHub als Deploy-Key ein:\n'
    printf '  dein Repository auf GitHub -> Settings -> Deploy keys -> Add deploy key\n'
    printf '  Titel: %s, "Allow write access" NICHT ankreuzen.\n\n' "$(hostname)"
    printf '%s\n\n' "$(cat "$KEY.pub")"
    printf '  (Nur diese .pub-Zeile weitergeben; der private Schlüssel bleibt auf dem Server.)\n'
    until can_read_repo; do
      pause "Enter drücken, sobald der Schlüssel eingetragen ist (Strg+C bricht ab) "
      can_read_repo || warn "Noch kein Zugriff. Schlüssel richtig eingetragen? Repository-Adresse: $REPO"
    done
    ok "Lesezugriff auf das Repository funktioniert"
  fi
fi

# ---------------------------------------------------------------- 4. Projekt
step "Projekt in $DIR"
if [ -d "$DIR/.git" ]; then
  ok "Vorhanden ($(git -C "$DIR" log -1 --format='%h %s' 2>/dev/null || echo '?'))"
elif checking; then
  miss "$DIR ist noch nicht eingerichtet"
else
  if [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
    die "$DIR existiert und ist nicht leer, aber kein Git-Projekt. Bitte prüfen oder CCU_DIR=<anderer Ordner> setzen."
  fi
  $SUDO mkdir -p "$DIR"
  $SUDO chown "$(id -un):$(id -gn)" "$DIR"
  git clone "$REPO" "$DIR"
  ok "Geklont: $(git -C "$DIR" log -1 --format='%h %s')"
fi

# ---------------------------------------------------------------- 5. CCU und Zugangsdaten
step "CCU-Verbindung und Zugangsdaten (backend/.env)"
ENV_FILE="$DIR/backend/.env"

json_escape() {
  local s=$1
  s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

test_ports() {  # test_ports <host> -> 0 wenn beide Schnittstellen antworten
  local host=$1 code body good=0
  code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "http://$host/" 2>/dev/null || true)"
  case "$code" in
    200|301|302|303|307|308) ok "CCU-Weboberfläche/JSON-RPC (Port 80) erreichbar" ;;
    *) miss "CCU auf Port 80 nicht erreichbar (HTTP '${code:-keine Antwort}'): IP richtig, CCU an?"; good=1 ;;
  esac
  body="$(curl -sS -m 5 -X POST -H 'Content-Type: text/xml' \
    -d '<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>' \
    "http://$host:2010/" 2>/dev/null || true)"
  if printf '%s' "$body" | grep -q "methodResponse"; then
    ok "XML-RPC (Port 2010) erreichbar"
  else
    miss "XML-RPC (Port 2010) antwortet nicht: in der CCU-Firewall die XML-RPC-API für diesen Server freigeben (docs/02 Abschnitt 2.1, Punkt 3)"
    good=1
  fi
  return $good
}

test_login() {  # test_login <host> <user> <password> -> 0 bei Erfolg; nichts davon wird angezeigt
  local host=$1 user=$2 pw=$3 resp sid
  resp="$(printf '{"method":"Session.login","params":{"username":"%s","password":"%s"}}' \
      "$(json_escape "$user")" "$(json_escape "$pw")" \
    | curl -sS -m 10 -H 'Content-Type: application/json' --data-binary @- \
      "http://$host/api/homematic.cgi" 2>/dev/null || true)"
  sid="$(printf '%s' "$resp" | sed -n 's/.*"result" *: *"\([^"]*\)".*/\1/p')"
  [ -n "$sid" ] || return 1
  # sofort wieder abmelden: die CCU erlaubt nur wenige gleichzeitige Sitzungen
  printf '{"method":"Session.logout","params":{"_session_id_":"%s"}}' "$sid" \
    | curl -sS -m 10 -H 'Content-Type: application/json' --data-binary @- \
      "http://$host/api/homematic.cgi" >/dev/null 2>&1 || true
  return 0
}

env_value() { sed -n "s/^$1=//p" "$ENV_FILE" 2>/dev/null | head -1 | sed "s/^['\"]//; s/['\"]\$//"; }

write_env() {  # write_env <host> <user> <password>
  local host=$1 user=$2 pw=$3 quoted
  # Docker Compose setzt in .env-Werten ohne Anführungszeichen $VARIABLEN ein und
  # liest " #" als Kommentar. In einfachen Anführungszeichen gilt alles wörtlich.
  if [[ "$pw" != *"'"* ]]; then
    quoted="'$pw'"
  else
    local d=${pw//\\/\\\\}; d=${d//\"/\\\"}; d=${d//\$/\$\$}
    quoted="\"$d\""  # mit ': doppelte Anführungszeichen, \ " escapen, $ als $$
  fi
  (
    umask 077
    {
      echo "# CCU3-Verbindung (angelegt von scripts/install.sh am $(date +%F))"
      echo "CCU_HOST=$host"
      echo "CCU_USERNAME=$user"
      printf 'CCU_PASSWORD=%s\n' "$quoted"
      echo
      echo "# Nur nötig, wenn das Dashboard NICHT same-origin über den nginx-Proxy läuft"
      echo "# (z. B. lokaler Dev-Server). Kommagetrennte Liste erlaubter Origins."
      echo "# CORS_ALLOW_ORIGINS=http://localhost:3000"
    } >"$ENV_FILE"
  )
  chmod 600 "$ENV_FILE"
}

if [ ! -d "$DIR/backend" ]; then
  miss "Projekt fehlt, Zugangsdaten werden übersprungen"
elif [ -f "$ENV_FILE" ]; then
  ok "backend/.env vorhanden"
  perms="$(stat -c '%a' "$ENV_FILE")"
  if [ "$perms" = "600" ]; then
    ok "Rechte 600 (nur du kannst das Passwort lesen)"
  elif checking; then
    miss "backend/.env hat Rechte $perms statt 600 (chmod 600 $ENV_FILE)"
  else
    chmod 600 "$ENV_FILE"; ok "Rechte auf 600 gesetzt"
  fi
  host="$(env_value CCU_HOST)"
  if [ -n "$host" ]; then
    info "CCU: $host"
    test_ports "$host" || true
  else
    miss "CCU_HOST fehlt in backend/.env"
  fi
  info "Die Anmeldung mit dem gespeicherten Passwort prüft der Start (Health-Check)."
elif checking; then
  miss "backend/.env fehlt (CCU-Zugangsdaten)"
else
  info "Die Angaben stehen in der CCU (docs/02 Abschnitt 2.1)."
  while :; do
    host="$(ask "IP-Adresse der CCU (ohne http://)" "")"
    host="${host#http://}"; host="${host#https://}"; host="${host%%/*}"
    [ -n "$host" ] || { warn "Bitte eine Adresse eingeben."; continue; }
    if test_ports "$host"; then break; fi
    confirm "Trotzdem mit $host weitermachen?" n && break
  done
  while :; do
    user="$(ask "CCU-Benutzername" "Admin")"
    tty_read -s -p "  CCU-Passwort (wird nicht angezeigt): " pw; echo
    if [[ "$pw" =~ ^[[:space:]] || "$pw" =~ [[:space:]]$ ]]; then
      warn "Das Passwort beginnt oder endet mit einem Leerzeichen -- bitte prüfen."
    fi
    if test_login "$host" "$user" "$pw"; then
      ok "Anmeldung an der CCU erfolgreich (und wieder abgemeldet)"
      break
    fi
    warn "Anmeldung fehlgeschlagen: Benutzer/Passwort falsch, oder zu viele offene Sitzungen (dann ~10 Minuten warten)."
    confirm "Erneut eingeben?" j || { confirm "Trotzdem so speichern?" n && break; die "Abgebrochen, backend/.env wurde nicht angelegt."; }
  done
  write_env "$host" "$user" "$pw"
  unset pw
  ok "backend/.env geschrieben (Rechte 600)"
fi

# ---------------------------------------------------------------- 6. Ventil-Zuordnung
step "Ventil-Zuordnung (data/valve_channels.json)"
VALVES="$DIR/data/valve_channels.json"
if [ ! -d "$DIR/backend" ]; then
  miss "Projekt fehlt, wird übersprungen"
elif [ -f "$VALVES" ]; then
  ok "Vorhanden: $(tr -d '\n' <"$VALVES" | tr -s ' ' | cut -c1-110)"
elif checking; then
  info "Fehlt noch; der erste Start legt sie aus der Vorlage an."
else
  mkdir -p "$DIR/data"
  cp "$DIR/backend/src/app/valve_channels.json" "$VALVES"
  ok "Aus der Vorlage angelegt"
  info "Raumname -> Kanäle des Aktors HmIP-FALMOT-C12, zum Beispiel  \"Wohnzimmer\": [2, 3, 4]"
  info "(in der CCU: Geräte -> HmIP-FALMOT-C12 -> Kanal -> Verknüpfungspartner)"
  if confirm "Jetzt mit nano bearbeiten? (später geht auch: nano $VALVES)" j; then
    nano "$VALVES" </dev/tty >/dev/tty
  fi
fi

# ---------------------------------------------------------------- 7. Start
step "Start der Anwendung"
if checking; then
  if [ -f "$DIR/docker-compose.yml" ] && command -v docker >/dev/null 2>&1 && docker ps >/dev/null 2>&1; then
    (cd "$DIR" && docker compose ps)
    health="$(curl -fsS -m 5 http://localhost:3000/api/system/health 2>/dev/null || true)"
    field() { printf '%s' "$health" | sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p"; }
    if printf '%s' "$health" | grep -q '"ccu":"ok"'; then
      ok "Anwendung läuft, CCU verbunden ($(field ccu_host))"
    elif [ -n "$health" ]; then
      miss "Anwendung läuft, aber die CCU ist nicht erreichbar: $health"
    else
      miss "Anwendung antwortet nicht auf http://localhost:3000"
    fi
    if [ -n "$health" ]; then
      case "$(field mqtt)" in
        verbunden) ok "MQTT verbunden" ;;
        "nicht eingerichtet"|"") info "MQTT nicht eingerichtet (optional, für Taupunkt und Home Assistant)" ;;
        *) miss "MQTT: $(field mqtt)" ;;
      esac
      devices="$(field devices)"
      case "$devices" in
        "Alle Geräte in Ordnung.") ok "$devices" ;;
        "noch nicht geprüft"|"") info "Gerätezustand: noch nicht geprüft (erste Prüfung kurz nach dem Start)" ;;
        *) warn "$devices" ;;
      esac
      backup="$(field backup)"
      backup_day="$(printf '%s' "$backup" | sed -n 's/^ccu-auto-\([0-9-]*\)\.json$/\1/p')"
      if [ -n "$backup_day" ] && [ "$backup_day" \> "$(date -d '2 days ago' +%F)" ]; then
        ok "Letzte automatische Sicherung: $backup_day"
      elif [ -n "$backup_day" ]; then
        miss "Letzte automatische Sicherung ist alt: $backup_day"
      else
        info "Noch keine automatische Sicherung (entsteht jede Nacht ab 03:00)"
      fi
      if [ -n "$(field backup_error)" ]; then
        miss "Automatische Sicherung fehlgeschlagen: $(field backup_error)"
      fi
    fi
  else
    info "Nicht geprüft (Projekt oder Docker-Zugriff fehlt)."
  fi
  echo
  if [ "$PROBLEMS" -eq 0 ]; then
    printf '%sAlles vorhanden.%s\n' "$C_OK" "$C_OFF"
  else
    printf '%s%d Punkt(e) fehlen.%s Zum Einrichten: bash %s\n' "$C_ERR" "$PROBLEMS" "$C_OFF" "$0"
  fi
  exit $((PROBLEMS > 0))
fi

[ -f "$ENV_FILE" ] || die "backend/.env fehlt."
info "Erster Bau dauert einige Minuten (auf einem Raspberry Pi auch 10–20)."
if [ "$DOCKER_VIA_SG" -eq 1 ]; then
  sg docker -c "cd '$DIR' && ./deploy.sh '$REF'"
else
  (cd "$DIR" && ./deploy.sh "$REF")
fi

ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
step "Fertig"
ok "Die Anwendung läuft: http://${ip:-<server-ip>}:3000"
info "Nächste Schritte (docs/02 ab Abschnitt 2.9):"
info "- Einmal 'sudo reboot' und prüfen, dass sie danach von selbst wieder läuft."
info "- Nur im Heimnetz verwenden, Port 3000 nie ins Internet weiterleiten."
info "- Vor dem ersten Wechsel Heizen/Kühlen die Profile der anderen Betriebsart prüfen."
if [ "$DOCKER_VIA_SG" -eq 1 ]; then
  info "- Einmal ab- und wieder anmelden, damit docker ohne sudo funktioniert."
fi
info "Prüfen geht jederzeit mit: bash $DIR/scripts/install.sh --check"
