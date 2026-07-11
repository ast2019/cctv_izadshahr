# Rollback & disaster recovery

Two independent things can be rolled back:

1. **The desired state** (inventory → generated config) — via git.
2. **The runtime config on the server** — via the timestamped backups that
   `scripts/deploy.sh` creates before every deployment.

`frigate.db` is **never** deleted or overwritten by deployment, so instance
state (users, config metadata) survives config rollbacks.

## 1. Roll back the desired state (git)

If a bad change was pushed to `main`:

```bash
# Find the last good commit
git log --oneline

# Option A: revert the offending commit (keeps history, re-triggers deploy)
git revert <bad_commit_sha>
git push origin main

# Option B: reset main to a known-good commit (force-push; use with care)
git reset --hard <good_commit_sha>
git push --force-with-lease origin main
```

The push to `main` re-runs validate + deploy and converges the server to the
restored state.

## 2. Restore a config.yml from a server backup

Every deployment writes to `/home/rootuser/frigate_new/backups/<timestamp>/` before changing
anything. To restore one instance's config:

```bash
cd /home/rootuser/frigate_new

# List available backups (newest last)
ls -1 backups/

# Inspect what a backup holds
ls -R backups/20260711-140302/

# Restore ONE instance's config.yml (example: cafe)
cp backups/20260711-140302/cafe/config.yml runtime-config/cafe/config.yml

# Recreate just that container
docker compose -f repo/generated/compose.generated.yaml up -d --no-deps frigate-cafe
```

> Restore `config.yml` only. Do **not** copy `frigate.db` back unless you are
> deliberately recovering a corrupted database — the live one is authoritative.

## 3. Disaster recovery (rebuild a lost server)

The repo + the secrets file are all you need; media and the database are
runtime data.

```bash
# 1. Recreate the layout
sudo mkdir -p /home/rootuser/frigate_new/{secrets,media,runtime-config,backups}

# 2. Clone the repo
sudo git clone https://github.com/ast2019/cctv_izadshahr.git /home/rootuser/frigate_new/repo

# 3. Restore secrets (from your password manager / secure backup)
sudo cp /path/to/backup/.env /home/rootuser/frigate_new/secrets/.env
sudo chmod 600 /home/rootuser/frigate_new/secrets/.env

# 4. (Optional) restore config.yml/frigate.db from an off-server backup copy
#    into /home/rootuser/frigate_new/runtime-config/<instance>/ if you have one.

# 5. Deploy — missing runtime-config/frigate.db is recreated by Frigate on start
cd /home/rootuser/frigate_new/repo
bash scripts/deploy.sh
```

Because config is regenerated from the inventory, a fresh server converges to
the exact desired state as soon as `scripts/deploy.sh` completes and every
instance passes its health check.

## Health check reference

`scripts/deploy.sh` polls `http://127.0.0.1:<ui_port>/api/version` for up to
60 seconds per instance and treats any HTTP response (including `401`) as
"up". A hard failure aborts the deployment and dumps the last 50 log lines of
the failing container.
