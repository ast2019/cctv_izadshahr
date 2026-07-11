#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Back up every runtime config.yml and frigate.db* into a timestamped folder.
# This is COPY-ONLY: it never deletes or modifies anything under runtime-config.
# Intended to run on the server before each deployment.
# -----------------------------------------------------------------------------
set -euo pipefail

BASE="${FRIGATE_BASE:-/srv/frigate}"
RUNTIME="$BASE/runtime-config"
BACKUP_ROOT="$BASE/backups"
RETENTION="${FRIGATE_BACKUP_RETENTION:-30}"

STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_ROOT/$STAMP"
mkdir -p "$DEST"

if [ -d "$RUNTIME" ]; then
  # Preserve the per-instance directory layout inside the backup.
  while IFS= read -r -d '' file; do
    rel="${file#"$RUNTIME"/}"
    mkdir -p "$DEST/$(dirname "$rel")"
    cp -a "$file" "$DEST/$rel"
  done < <(find "$RUNTIME" -type f \( -name 'config.yml' -o -name 'frigate.db*' \) -print0)
fi

echo "Backup written to $DEST"

# Retention: keep only the newest N backup directories (never touches runtime).
if [ "$RETENTION" -gt 0 ]; then
  # shellcheck disable=SC2012
  ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | tail -n +"$((RETENTION + 1))" | while read -r old; do
    rm -rf "$old"
  done
fi
