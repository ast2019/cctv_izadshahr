#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Server-side deployment for the Frigate GitOps repo.
#
# Order of operations (fail-fast):
#   1. Render configs from the inventory.
#   2. Back up all current config.yml + frigate.db files (timestamped).
#   3. Validate the generated compose file.
#   4. For each instance, sequentially:
#        - update ONLY runtime-config/<instance>/config.yml
#        - (re)create the container
#        - health-check the UI port before moving on.
#
# It NEVER deletes or overwrites frigate.db and NEVER touches media.
# Expected to run from /home/rootuser/frigate_new/repo on the Ubuntu server.
# -----------------------------------------------------------------------------
set -euo pipefail

REPO_DIR="${FRIGATE_REPO_DIR:-/home/rootuser/frigate_new/repo}"
BASE="${FRIGATE_BASE:-/home/rootuser/frigate_new}"
RUNTIME="$BASE/runtime-config"
MEDIA="$BASE/media"
COMPOSE_FILE="$REPO_DIR/generated/compose.generated.yaml"

# Make base paths available to docker compose variable substitution.
export FRIGATE_BASE="$BASE"

cd "$REPO_DIR"

echo "==> [1/4] Rendering configs from inventory/"
python3 scripts/render.py

echo "==> [2/4] Backing up current config.yml and frigate.db files"
bash scripts/backup-config.sh

echo "==> [3/4] Validating generated compose"
docker compose -f "$COMPOSE_FILE" config -q

echo "==> [4/4] Deploying instances sequentially"
while IFS=$'\t' read -r name ui_port _rtsp _webrtc; do
  [ -z "$name" ] && continue
  echo "--> instance: $name (UI :$ui_port)"

  mkdir -p "$RUNTIME/$name" "$MEDIA/$name"

  # Update ONLY config.yml. frigate.db and media are left untouched.
  install -m 0644 "generated/config/$name/config.yml" "$RUNTIME/$name/config.yml"

  # Recreate just this service; --no-deps keeps siblings running.
  docker compose -f "$COMPOSE_FILE" up -d --no-deps "frigate-$name"

  # Health check: the UI answering (any HTTP status, incl. 401) means it is up.
  echo "    health-checking frigate-$name ..."
  healthy=0
  for _ in $(seq 1 30); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$ui_port/api/version" || true)"
    if [ -n "$code" ] && [ "$code" != "000" ]; then
      healthy=1
      break
    fi
    sleep 2
  done

  if [ "$healthy" -ne 1 ]; then
    echo "ERROR: health check failed for frigate-$name" >&2
    echo "Recent logs:" >&2
    docker logs --tail 50 "frigate-$name" >&2 || true
    exit 1
  fi
  echo "    frigate-$name healthy (HTTP $code)"
done < generated/instances.tsv

echo "==> Deployment complete"
