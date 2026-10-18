# Security

## Design assumptions

- The app has **no authentication**. Anyone who can reach port 3000 can change your
  heating. Run it only in a trusted home network; use a VPN for remote access and never
  forward the port on your router.
- Credentials (CCU, optional MQTT) are kept only in `backend/.env` on the server
  (`chmod 600`; `deploy.sh` enforces it). Exports and backups never contain them.

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private vulnerability reporting
("Security" tab → "Report a vulnerability") with a description and, if possible, steps to
reproduce. This is a hobby project; responses may take a few days.
