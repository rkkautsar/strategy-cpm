# CF Workers cron trigger

## Why this exists

GitHub Actions scheduled workflows are **automatically disabled after 60
days of repo inactivity**. Since this strategy only commits via its own
monthly run, the cron breaks after ~2 months without manual intervention.

This Worker is the durable clock. It does one thing: fire a webhook to
GitHub once a month to trigger the actual workflow. CF Workers cron
triggers have no inactivity penalty.

## Architecture

```
CF Workers cron (monthly, 30 16 1-3 * *)
  └─ POST https://api.github.com/repos/<owner>/<repo>/dispatches
       event_type: "monthly-signal"

GitHub Actions (workflow: monthly-signal.yml)
  on: repository_dispatch [monthly-signal]
  └─ Build Python, deploy to CF Pages, notify Telegram
```

Total moving parts: 1 Worker (15 lines of JS), 1 GH Actions workflow.

## Setup

### 1. Create GitHub PAT (Personal Access Token)

Fine-grained token: https://github.com/settings/tokens?type=beta

- Token name: `cpm-bull-cron`
- Expiration: 1 year (set reminder to rotate)
- Repository access: **Only select repositories** → your strategy repo
- Permissions: **Actions** → **Read and Write**

Copy the token (shown once).

### 2. Configure wrangler.toml

Edit `wrangler.toml`:
```toml
[vars]
GH_OWNER = "your-github-username"
GH_REPO  = "your-repo-name"
```

### 3. Deploy the Worker

```bash
cd deploy/cf-cron
npm install -g wrangler
wrangler login          # opens browser

# Set the GH token as a secret
wrangler secret put GH_TOKEN
# Paste the PAT from step 1, press Enter

# Optional: set a manual trigger token (random string)
wrangler secret put TRIGGER_TOKEN
# Paste any random string (used for HTTP manual triggers)

# Deploy
wrangler deploy
```

You should see:
```
Total Upload: 1.5 KiB / gzip: 0.6 KiB
Uploaded cpm-bull-cron (1.2 sec)
Published cpm-bull-cron (2.3 sec)
  https://cpm-bull-cron.<account>.workers.dev
Cron Trigger: 30 16 1-3 * *
```

### 4. Test it

#### Manual trigger via HTTP

```bash
curl -X POST https://cpm-bull-cron.<account>.workers.dev/ \
  -H "X-Trigger-Token: <TRIGGER_TOKEN you set>"
```

Should respond `Dispatched` and you should see the GH Actions workflow
start running immediately.

#### Manual trigger via Cloudflare dashboard

CF Dashboard → Workers → `cpm-bull-cron` → **Triggers** → Cron triggers
→ click **Run** next to the cron schedule.

#### Wait for scheduled fire

Next scheduled run: check `wrangler cron status` or CF dashboard.

### 5. Verify GH Actions runs on dispatch

After the Worker fires, check:
```bash
gh run list --workflow=monthly-signal.yml --limit 5
```

Should show the latest run with event `repository_dispatch`.

## Monitoring

CF Workers dashboard shows:
- Cron execution history
- Success/failure counts
- Real-time logs (`wrangler tail cpm-bull-cron`)

If the Worker fails (e.g., GH token expires), CF will email you.

## Cost

- CF Workers free tier: 100,000 requests/day. Monthly cron = ~3 requests/month.
- CF Workers paid tier: $5/month, not needed for this use case.
- Total: **$0**

## Failure modes

| What breaks | How to detect | How to fix |
|---|---|---|
| GH PAT expires | CF Worker errors, no GH Actions run | Rotate PAT, `wrangler secret put GH_TOKEN` |
| CF Worker disabled | No execution in CF dashboard | Redeploy: `wrangler deploy` |
| GH Actions disabled | Workflow doesn't run on dispatch | `gh workflow enable monthly-signal.yml` |
| Repo renamed | 404 from GH API | Update `GH_OWNER`/`GH_REPO` in wrangler.toml |

## Why not just put strategy in CF Workers Python?

Considered. Rejected because:
- Bundle size limit (10MB compressed) is tight with pandas+numpy+yfinance
- yfinance uses sync `requests`, would need refactor to async httpx
- 30s CPU limit is borderline for full backtest
- CSV stitch files need to move to R2

This Worker-as-clock pattern keeps the Python compute on a real Python
runtime (GH Actions runner has full pip, no constraints) while using CF
Workers only for the durable scheduling primitive it does well.
