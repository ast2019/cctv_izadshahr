# Adding a new instance

The design is fully data-driven: a new instance requires **only** an inventory
entry plus a camera file. No template, script, or workflow changes.

## Steps

1. **Pick unique host ports.** They must not collide with any existing instance
   or anything else on the server. Example for a new instance `center33`:

   | Purpose   | Host port |
   |-----------|-----------|
   | Web UI    | `8975`    |
   | RTSP      | `8562`    |
   | WebRTC    | `8563`    |

2. **Add the instance** to `inventory/instances.yml`:

   ```yaml
   instances:
     # ... existing instances ...
     - name: center33
       ui_port: 8975
       rtsp_port: 8562
       webrtc_port: 8563
   ```

3. **Create `inventory/cameras/center33.yml`** (see
   [add-camera.md](add-camera.md) for the schema):

   ```yaml
   sources:
     dvr:
       scheme: rtsp
       rtsp_port: 554

   cameras:
     dvr_center33_ch1:
       enabled: true
       source: dvr
       path: "/cam/realmonitor?channel=1&subtype=0"
   ```

4. **Sync env variable names automatically** into `.env.example`, then fill the
   real `/home/rootuser/frigate_new/secrets/.env` on the server:

   ```bash
   python3 scripts/render.py
   python3 scripts/sync-env-example.py --write
   cat generated/required-env.txt
   ```

5. **Validate locally:**

   ```bash
   bash scripts/validate.sh
   ```

6. **Commit and push to `main`.** CI validates, then the deploy job creates the
   `frigate-center33` container and health-checks it — existing instances keep
   running (deployment is sequential and per-service).

## What you get automatically

- Container `frigate-center33` on image `ghcr.io/blakeblackshear/frigate:0.17.2`
- Independent config dir `runtime-config/center33` and media dir `media/center33`
- Unique MQTT `topic_prefix`/`client_id` = `frigate_center33`
- tmpfs `/tmp/cache`, JSON log rotation, no detection/recording/Birdseye/GPU
