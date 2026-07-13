#!/bin/bash
# Delete Frigate recordings/clips older than today (run with sudo)
set -u
TODAY=$(date +%F)
echo "Keeping only >= $TODAY"

for base in /media/frigate/recordings /media/frigate22/recordings; do
  [ -d "$base" ] || continue
  for d in "$base"/*/; do
    name=$(basename "$d")
    if [[ "$name" < "$TODAY" ]]; then
      echo "DELETING $d"
      rm -rf "$d"
    fi
  done
done

# clips/previews/thumbs older than today
for base in /media/frigate/clips /media/frigate22/clips; do
  [ -d "$base" ] || continue
  find "$base" -type f ! -newermt "$TODAY" -delete 2>/dev/null
  find "$base" -type d -empty -delete 2>/dev/null
done

echo '=== AFTER ==='
df -h /
du -sh /media/frigate /media/frigate22 2>/dev/null
