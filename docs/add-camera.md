# Adding a camera

Cameras live in `inventory/cameras/<instance>.yml`. That file has two sections:

- **`sources`** — credential + host groups. Cameras sharing a device (e.g. a
  DVR with many channels, or one IP camera) reference the same source, so the
  secret host/user/password are declared once.
- **`cameras`** — each camera references a source and adds only the non-secret
  URL path.

## Rules

- **Never** put an IP address, username, or password in the inventory.
- A source `foo` under instance `bar` maps to exactly three runtime variables:
  `FRIGATE_BAR_FOO_USER`, `FRIGATE_BAR_FOO_PASSWORD`, `FRIGATE_BAR_FOO_HOST`.
  These live only in `/srv/frigate/secrets/.env`.
- The rendered URL is
  `scheme://{USER}:{PASSWORD}@{HOST}:port<path>` — Frigate substitutes the
  `{FRIGATE_*}` placeholders at container start.

## Add a camera on an existing source

If the device already exists as a source, just add the camera:

```yaml
cameras:
  dvr_cafe_ch11:
    enabled: true
    source: dvr                 # reuses FRIGATE_CAFE_DVR_{USER,PASSWORD,HOST}
    path: "/cam/realmonitor?channel=11&subtype=0"
```

No new secrets are needed.

## Add a camera on a brand-new device

Add a source, then the camera:

```yaml
sources:
  # ... existing ...
  lobby_50:
    scheme: rtsp
    rtsp_port: 554

cameras:
  ipcam_lobby_50:
    enabled: true
    source: lobby_50
    path: "/Streaming/Channels/101"
```

Then add the three new variables to `.env.example` (names only) and to the
server's real `.env`:

```
FRIGATE_CAFE_LOBBY_50_USER=
FRIGATE_CAFE_LOBBY_50_PASSWORD=
FRIGATE_CAFE_LOBBY_50_HOST=
```

## Per-camera fields

| Field     | Required | Notes                                                        |
|-----------|----------|--------------------------------------------------------------|
| `source`  | yes      | Must match a key under `sources`.                            |
| `path`    | yes      | URL path after the host, e.g. `/Streaming/Channels/101`.     |
| `enabled` | no       | Defaults to `true`. Set `false` to render but disable it.    |
| `scheme`  | no       | Overrides the source scheme (default `rtsp`).                |
| `rtsp_port` | no     | Overrides the source port (default `554`).                   |

## Validate and deploy

```bash
python3 scripts/render.py          # confirm required-env.txt looks right
bash scripts/validate.sh           # render + compose validation
```

Commit and push to `main`; the deploy updates only the affected instance's
`config.yml` and reloads its container. Because detection and recording are
disabled, cameras appear as live-only streams via go2rtc.
