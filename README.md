# CCU Climate Dashboard

A self-hosted web app to run **HomematicIP underfloor heating and cooling** through a
**CCU3 / OpenCCU**: room overview with valve positions, weekly schedules per room,
**separate heating and cooling schedules**, scheduled heating/cooling switch-over,
absence mode, dew point monitoring for floor cooling, Home Assistant integration (MQTT
discovery), automatic backups. It runs with Docker on a small Linux server in your home
network.

> **The user interface and the detailed documentation are in German.** This page gives an
> English overview; everything else is in [`docs/`](docs/README.md).

## Features

- Room tiles with actual/target temperature, humidity and valve position; room detail with
  a setpoint dial, mode and profile selection
- Six weekly profiles per room, editable day by day (graph + time blocks), copy days,
  profiles and rooms; profile names
- Heating and cooling as **two independent sets** of profiles; the inactive set can be
  edited any time, switching writes it to the thermostats in the background (paced to
  respect the CCU's radio duty cycle)
- Scheduled heating/cooling switch per year, whole-apartment profile switch, absence mode
  (all rooms on one profile, then back to each room's previous one)
- Change history with "reset to here", export/import with strict validation, nightly
  backups
- Dew point monitoring for floor cooling (flow temperature via MQTT), device health
  (batteries, reachability, CCU duty cycle), valve history chart (up to 72 h)
- Home Assistant entities via MQTT discovery (e.g. for push notifications)
- Seven themes, works on phone, tablet and desktop

## Hardware

Tested with **HmIP-WTH-1** wall thermostats (one per room, the device name is the room
name) and the **HmIP-FALMOT-C12** floor heating actuator on a CCU3 running OpenCCU. Other
HomematicIP climate devices may need adjustments.

## Quick start

On a Debian 12/13 server with a user that may use `sudo`:

```bash
curl -fsSLO https://raw.githubusercontent.com/kunterauskoeln/ccu-climate-dashboard/main/scripts/install.sh
bash install.sh            # installs Docker, clones to /opt/ccu, asks for the CCU login, starts
bash install.sh --check    # later: check everything without changing anything
```

or by hand:

```bash
git clone https://github.com/kunterauskoeln/ccu-climate-dashboard.git /opt/ccu && cd /opt/ccu
cp backend/.env.example backend/.env && nano backend/.env    # CCU address and login
./deploy.sh                                                  # builds and starts both containers
# open http://<server>:3000
```

Step-by-step guide (German): [docs/02-installation-debian.md](docs/02-installation-debian.md).

- **Backend:** Python 3.11, FastAPI · **Frontend:** React 18, TypeScript, Vite, nginx
- **Operation:** Docker Compose (`backend`, `dashboard`), all data in `data/`

## Security

The app has **no login**. Run it only inside a trusted home network and never expose
port 3000 to the internet; use a VPN for remote access. The CCU password lives only in
`backend/.env` on the server. See [SECURITY.md](SECURITY.md).

## Disclaimer

This is an independent hobby project. It is **not affiliated with or endorsed by eQ-3**;
Homematic and HomematicIP are trademarks of eQ-3 AG. The app writes schedules and
settings to your heating system: use it at your own risk and check its behaviour,
especially before switching between heating and cooling.

## License

[GNU General Public License v3.0](LICENSE). You may use, study, change and share it;
modified versions you distribute must be released under the same license.

---

### Deutsch

Webanwendung zur Steuerung einer HomematicIP-Fußbodenheizung/-kühlung über eine CCU3
(OpenCCU). Die vollständige Dokumentation liegt im Ordner **[`docs/`](docs/README.md)**:
Installation auf Debian, Konfiguration, Betrieb, Bedienung, Architektur, API,
CCU-Hintergrund und Entwicklung.
