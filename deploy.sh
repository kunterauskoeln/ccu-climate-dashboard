#!/usr/bin/env bash
#
# Deploy / rollback the CCU stack on the Linux target.
#
#   ./deploy.sh              → latest origin/main
#   ./deploy.sh v0.2.0       → roll back to a tag
#   ./deploy.sh <sha>        → pin to a commit
#
set -euo pipefail
cd "$(dirname "$0")"

REF="${1:-origin/main}"

if [ "${_CCU_DEPLOY_STAGE2:-}" != "1" ]; then
  # Stage 1 only: fetch + checkout, then hand off to a FRESH copy of this
  # script. `git checkout -f` can rewrite deploy.sh itself -- bash keeps
  # reading the OLD file content from its already-open handle for anything
  # after this point, so continuing in-process would silently run stale
  # logic (observed: after restructuring this script, the tail kept running
  # with pre-checkout code and paths). The rescue block below deliberately
  # stays in this stage, before checkout, since checkout is exactly what
  # would otherwise discard a still-tracked file's local state.
  mkdir -p data
  for pair in \
    "backend/profile_names.json:data/profile_names.json" \
    "backend/profile_sets.json:data/profile_sets.json" \
    "backend/profile_sets.backup.json:data/profile_sets.backup.json" \
    "backend/src/app/valve_channels.json:data/valve_channels.json"
  do
    old="${pair%%:*}"; new="${pair##*:}"
    if [ -e "$old" ] && [ ! -e "$new" ]; then
      echo "==> Übernehme bestehende $old nach $new"
      cp "$old" "$new"
    fi
  done

  echo "==> Fetching…"
  git fetch --all --tags --prune

  echo "==> Checking out ${REF}"
  git checkout -f "${REF}"
  git --no-pager log -1 --oneline

  _CCU_DEPLOY_STAGE2=1 exec bash "$0" "${REF}"
fi

# --- Everything below runs from the freshly checked-out script (stage 2). ---

# Fills in anything still missing after the rescue above -- a genuinely new
# install, or a file that never existed in the old layout either.
# profile_names.json and valve_channels.json get a real starting point (the
# shipped templates); the profile sets start empty.
[ -e data/profile_names.json ]       || { echo "==> Seeding data/profile_names.json"; cp backend/profile_names.example.json data/profile_names.json; }
[ -e data/valve_channels.json ]      || { echo "==> Seeding data/valve_channels.json"; cp backend/src/app/valve_channels.json data/valve_channels.json; }
[ -e data/profile_sets.json ]        || { echo "==> Creating data/profile_sets.json"; echo '{}' > data/profile_sets.json; }
[ -e data/profile_sets.backup.json ] || { echo "==> Creating data/profile_sets.backup.json"; echo '{}' > data/profile_sets.backup.json; }

# backend/.env holds the CCU (and MQTT) password: only its owner may read it.
if [ -f backend/.env ]; then
  perms="$(stat -c %a backend/.env)"
  if [ "$perms" != "600" ]; then
    if [ -O backend/.env ]; then
      chmod 600 backend/.env
      echo "==> backend/.env: Rechte von $perms auf 600 gesetzt (enthält Passwörter)"
    else
      echo "!! backend/.env hat Rechte $perms und gehört nicht $(id -un). Bitte:"
      echo "   sudo chown $(id -un) backend/.env && chmod 600 backend/.env"
    fi
  fi
fi

echo "==> Building & starting containers"
docker compose up -d --build --remove-orphans
docker compose ps

echo "==> Waiting for health (via the nginx /api proxy)…"
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:3000/api/system/health >/dev/null 2>&1; then
    echo "==> OK"
    curl -fsS http://localhost:3000/api/system/health
    echo
    exit 0
  fi
  sleep 2
done

echo "!! Health check failed — last backend logs:"
docker compose logs --tail=50 backend
exit 1
