#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Render everything from the inventory and validate the generated compose file.
# Safe to run locally and in CI — it never touches the server or any secrets.
# -----------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Rendering configs from inventory/"
python3 scripts/render.py

COMPOSE_FILE="generated/compose.generated.yaml"

echo "==> Validating $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" config -q

echo "==> Validating generated Frigate YAML syntax"
for cfg in generated/config/*/config.yml; do
  python3 -c "import sys, yaml; yaml.safe_load(open(sys.argv[1]))" "$cfg"
  echo "    ok: $cfg"
done

echo "==> Validation successful"
