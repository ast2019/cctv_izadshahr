#!/usr/bin/env bash
# Diagnose camera problems across the RECORDING Frigate instances (NOT temp).
# Surfaces: auth failures, wrong codec, connection errors, ffmpeg restart loops
# (wasted CPU), and per-container CPU/RAM. Run on the server and send output.
#
#   ./scripts/diag-cameras.sh
#
set -uo pipefail
cd "$(dirname "$0")/.."

compose() {
  if [[ "${EUID}" -eq 0 ]]; then
    docker compose "$@"
  else
    sudo docker compose "$@"
  fi
}

# Recording instances only — temp is intentionally excluded.
INSTANCES=(cafe center11 center22 restaurant sahel villa mahoote tasisat entezamat anbar)

# Error patterns that indicate misconfig / wrong codec / dead stream / thrash.
PAT='wrong user|wrong pass|401|Unauthor|Unable to read frames|not running. exiting|No frames received|Connection refused|Connection timed out|timed out|No route to host|does not appear|not a supported|Unsupported|Could not find|codec|hwaccel|Invalid data|moov atom|Non-monotonous|corrupt|failed'

LINES="${DIAG_LOG_LINES:-4000}"      # how far back to scan each log
SHOW="${DIAG_SHOW:-25}"              # matching lines to show per instance

echo "############################################################"
echo "# CPU / MEM per Frigate container (snapshot)"
echo "############################################################"
names=$(compose ps --format '{{.Name}}' 2>/dev/null | grep -E 'frigate-' || true)
if [[ -n "$names" ]]; then
  # shellcheck disable=SC2086
  docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' $names
else
  echo "(could not list containers)"
fi

for s in "${INSTANCES[@]}"; do
  echo ""
  echo "############################################################"
  echo "# frigate-$s — error/warn lines (last $SHOW of ~$LINES scanned)"
  echo "############################################################"
  out=$(compose logs --tail="$LINES" "frigate-$s" 2>&1 | grep -iE "$PAT" | tail -"$SHOW")
  if [[ -n "$out" ]]; then
    echo "$out"
    echo "--- cameras mentioned in errors above ---"
    echo "$out" | grep -oiE 'cam_[0-9a-z]+|dvr_[0-9a-z_]+|restoran_[a-z]+|paziresh_[a-z_]+|sahel_[a-z0-9_]+|villa_[a-z_]+|view_cafe_[a-z]+|vorodi_[a-z]+|generator|parking_villa' \
      | sort | uniq -c | sort -rn
  else
    echo "OK — no error/warn matches."
  fi
done

echo ""
echo "Done. Send this whole output back for debugging."
