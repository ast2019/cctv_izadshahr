# Deployment

This repository is a **GitOps source of truth** for several Frigate 0.17.2
instances. You never edit Frigate config or docker-compose by hand — you edit
the inventory, and the pipeline renders and deploys everything.

## Pipeline overview

```
inventory/ ──(scripts/render.py)──► generated/ ──(docker compose)──► containers
   ▲                                                                     ▲
   │  edit here                                     health-checked here ─┘
```

- **`inventory/instances.yml`** — global settings + the list of instances.
- **`inventory/cameras/<instance>.yml`** — cameras and credential/host sources.
- **`templates/`** — Jinja2 templates for the Frigate config and compose service.
- **`scripts/render.py`** — renders everything into `generated/` (git-ignored).
- **GitHub Actions** — `validate.yml` on every push/PR, `deploy.yml` on `main`.

## Runtime layout on the server

```
/home/rootuser/frigate_new/
├── repo/                         # this git repository (checked out on server)
├── secrets/.env                  # real credentials (NEVER in git)
├── media/<instance>/             # per-instance media (NEVER in git)
├── runtime-config/<instance>/    # per-instance config.yml + frigate.db
└── backups/<timestamp>/          # config.yml + frigate.db backups
```

Each container gets:
- an **independent** `/config` (→ `runtime-config/<instance>`) and
  `/media/frigate` (→ `media/<instance>`),
- a **tmpfs** at `/tmp/cache`,
- **JSON logging** with rotation (`max-size: 10m`, `max-file: 3`),
- a **unique MQTT** `topic_prefix`/`client_id`,
- **no** detection, recording, snapshots, Birdseye, GPU, NVIDIA, Coral, or any
  hardware accelerator.

## First-time server bootstrap

```bash
# As a sudo-capable user on the Ubuntu server:
sudo mkdir -p /home/rootuser/frigate_new/{secrets,media,runtime-config,backups}
sudo git clone https://github.com/ast2019/cctv_izadshahr.git /home/rootuser/frigate_new/repo

# Create the secrets file from the template and fill in real values.
sudo cp /home/rootuser/frigate_new/repo/.env.example /home/rootuser/frigate_new/secrets/.env
sudo chmod 600 /home/rootuser/frigate_new/secrets/.env
sudo "${EDITOR:-nano}" /home/rootuser/frigate_new/secrets/.env
```

Confirm every variable listed by `python3 scripts/render.py && cat
generated/required-env.txt` has a value in `/home/rootuser/frigate_new/secrets/.env`.
When inventory changes, refresh `.env.example` with:
`python3 scripts/sync-env-example.py --write`.

## Automatic deployment (recommended)

Configure these **GitHub repository secrets** (Settings → Secrets and variables
→ Actions):

| Secret            | Description                                            |
|-------------------|--------------------------------------------------------|
| `SSH_HOST`        | Server hostname or IP                                  |
| `SSH_USER`        | SSH user (member of the `docker` group)                |
| `SSH_PORT`        | SSH port (optional, defaults to `22`)                  |
| `SSH_PRIVATE_KEY` | Private key authorised on the server                   |
| `SSH_KNOWN_HOSTS` | Output of `ssh-keyscan -p <port> <host>`               |

Every push to `main`:
1. `validate` job renders configs and runs
   `docker compose -f generated/compose.generated.yaml config -q`.
2. `deploy` job SSHes in, `git reset --hard origin/main`, and runs
   `scripts/deploy.sh`.

## Manual deployment (from the server)

```bash
cd /home/rootuser/frigate_new/repo
git pull origin main
bash scripts/deploy.sh
```

`scripts/deploy.sh` will, in order:
1. render configs from the inventory,
2. back up **all** current `config.yml` and `frigate.db` files into
   `/home/rootuser/frigate_new/backups/<timestamp>/`,
3. validate the generated compose file,
4. for each instance sequentially: update **only** `config.yml`, recreate the
   container, and health-check its UI port before continuing.

It never deletes or overwrites `frigate.db` and never touches media.

## Local development

```bash
pip install jinja2 pyyaml
python3 scripts/sync-env-example.py --write
bash scripts/validate.sh     # render + validate, no server or secrets needed
```

Inspect the output under `generated/` (git-ignored).

## Future architecture (explicitly out of scope here)

The following are intentionally **not** implemented in this repository and are
noted only as future direction: a React dashboard, Home Assistant integration,
Authentik/Authelia, a reverse proxy, and SSO. They should be added as separate,
layered components without changing the inventory-driven model above.
