---
inclusion: always
---

# cctv_izadshahr — Project Rules

## Instances

| Instance | Container | UI port | Config |
|----------|-----------|---------|--------|
| cafe | frigate-cafe | 8972 | config/cafe/config.yml |
| center11 | frigate-center11 | 8973 | config/center11/config.yml |
| center22 | frigate-center22 | 8974 | config/center22/config.yml |

Always use authenticated UI port mapping (`897x` → internal `8971`). Never expose port `5000`.

## Camera config rules

0. **Inventory**: Full camera list with IPs/passwords/status → `docs/CAMERAS.md`. Update it when adding/removing cameras.
1. **Naming**: IP cameras → `cam_<last_octet>` (e.g. `cam_5` for `192.168.51.5`). DVR channels → `dvr_<site>_ch<N>`.
2. **No duplicates**: A camera name must appear in only one instance. Before adding, grep all `config/*/config.yml` files.
3. **RTSP password**: Write inline in each instance config URL (`rtsp://admin:PASSWORD@IP:554/...`). Do NOT use `.env` or `{FRIGATE_RTSP_PASSWORD}`.
4. **go2rtc pattern**: One go2rtc stream per camera; recording reads from `rtsp://127.0.0.1:8554/<name>` with `preset-rtsp-restream`.
5. **Record-only**: `detect.enabled: false` unless explicitly requested.
6. **Audio is never used.** No instance uses audio. Cameras that expose an audio
   track (especially a `sendonly` PCMA/PCMU **backchannel**) can break go2rtc:
   it negotiates the audio track, receives no video, and the watchdog restarts
   ffmpeg every 20s producing corrupt segments. Fix: append `#media=video` to
   the go2rtc source URL.
   - Known affected: **ICAMRA** cameras (`a=tool:WWW.ICAMRA.COM` in SDP) —
     `.99`, `.100`, `.101` in `restaurant`. Details in `docs/CAMERAS.md`.
   - Changing the camera codec does **not** fix this; the audio track is
     independent of the video codec.
   - When a camera shows `i/o timeout` + `No frames received` while the camera
     itself is reachable, check its SDP for audio tracks **before** suspecting
     the codec. H265 alone is not a problem; several H265 cameras work fine.
7. **Verify which stream a path actually serves.** Don't assume
   `Streaming/Channels/102` is the substream. ICAMRA cameras serve the *main*
   stream on both `101` and `102`; their real substream lives at
   `Streaming/Channels/2`. Relying on `102` risks recordings silently dropping
   to VGA if camera behaviour changes. Write the intended channel explicitly and
   confirm with:
   `ffprobe -rtsp_transport tcp -select_streams v:0 -show_entries stream=codec_name,width,height -i <url>`
   (ffprobe lives at `/usr/lib/ffmpeg/7.0/bin/ffprobe` inside the container).
8. **Diagnose at the go2rtc level, not with direct ffmpeg.** Direct ffmpeg to a
   camera can succeed while go2rtc fails, which makes direct tests misleading.
   Inspect `docker exec <container> curl -s http://127.0.0.1:1984/api/streams`
   and compare `receivers[].bytes`: a healthy stream has non-zero, growing bytes.
9. **Wait ~90s after restart before judging a camera.** While the container is
   `health: starting`, go2rtc may not have finished RTSP negotiation, so streams
   can look stalled when they are actually fine.
10. After config change: `docker compose restart frigate-<instance>`.
11. **Hang recovery**: `frigate-watchdog` probes each instance `http://frigate-<id>:5000`
    (`/api/stats` + `latest.jpg`). Restart that container only after consecutive
    failures. Do not restart the whole stack. Skip mass-restart when most
    instances fail together (host/network outage). The `temp` instance is for
    broken/unidentified cameras — zero video there is **not** a hang. See
    `scripts/frigate_watchdog.py`.

## Portal frontend (portal/)

- **Semver** in `portal/js/changelog.js` → `PORTAL_VERSION`. Bump on every portal change:
  - `patch`: bugfix / style
  - `minor`: new feature
  - `major`: breaking redesign
- **Changelog** in same file → `CHANGELOG[]`. Each entry: `date`, `version`, `items[]`.
  - Shown at bottom of portal for **2 days** then auto-hidden.
  - Add a new entry (or extend today's) when shipping portal updates.

## UI auth (separate from camera RTSP)

- Portal login is a single HttpOnly cookie. nginx gates Frigate on port `5000`.
- Password check hits `8971` on every recording instance (cafe first if `FRIGATE_AUTH_URL` is set).
- Frigate UI users live in `config/<instance>/frigate.db` per instance.
- On first boot, admin password is random and printed in logs:
  `docker compose logs <service> 2>&1 | grep -i password`
- Reset admin: add `auth: { reset_admin_password: true }` to config, restart, read log, remove flag.
- Sync users across instances: `scripts/sync-frigate-users.sh` (requires running containers).
- **Frigate's REST API refuses short passwords** (min 12 chars, newer builds also
  want a special character) and the minimum cannot be configured. So a historic
  short password can never be re-applied through `/api/users/...`. Logging in has
  no such rule — only the stored hash is checked. To restore known-good
  credentials on every instance use `scripts/restore-frigate-passwords.sh <admin-pw> <ceo-pw>`:
  it hashes with Frigate's own `hash_password()` inside each container and writes
  `/config/frigate.db` directly, then verifies real logins on port 8971.
  No restart needed — Frigate reads the user table on every login.
- **Login fails / "wrong username or password"**: run `scripts/diag-portal-login.sh <user> <pass>`
  on the server. It shows the users in each `frigate.db`, the `/api/login` status
  per instance from the host **and** from inside `portal-metrics` (the path login
  really uses), and the portal endpoint's answer. Every attempt is also traced in
  `docker compose logs portal-metrics | grep '\[login\]'`, e.g.
  `[login] user=ceo result=unauthorized cafe=401 sahel=timeout ...`.
- A 401 from the portal means *some* instance rejected the password and none
  accepted. If instances were unreachable the answer is only partial — the
  response carries `unreachable` and the UI says so instead of blaming the user.
- Standard viewer user: `ceo` / role `viewer` (password set by operator, not committed).

## Deploy workflow

1. Edit `config/<instance>/config.yml` locally.
2. Upload to server `/home/rootuser/cctv_izadshahr/`.
3. `sudo docker compose restart frigate-<instance>`.
4. Verify: `docker compose ps` and `docker compose logs --tail=30 frigate-<instance>`.

Server SSH: `rootuser@192.168.10.18`, project path `/home/rootuser/cctv_izadshahr`. Docker commands need `sudo`.
