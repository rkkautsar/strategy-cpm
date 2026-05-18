# Cloudflare Pages monthly build setup

This deploys `cpm_dashboard.html` to a public Cloudflare Pages URL,
refreshed monthly via GitHub Actions cron.

## Architecture

```
GH Actions cron (1st-3rd of month, 16:30 UTC)
  ├─ uv sync (install deps)
  ├─ uv run cpm_live.py allocate    → signal computed (fresh data via yfinance)
  ├─ uv run build_dashboard.py      → cpm_dashboard.html regenerated
  ├─ Copy to dist/index.html
  ├─ wrangler pages deploy dist     → push to CF Pages
  └─ curl Telegram API              → notification with dashboard URL
```

Result: every month, a fresh dashboard at
`https://cpm-bull-dashboard.pages.dev/` (and a custom domain if you set one up).

Cost: $0. GH Actions free tier covers monthly jobs. CF Pages free tier
includes unlimited static hosting + 500 builds/month.

## One-time setup

### 1. Cloudflare side

```bash
# Install wrangler if you don't have it
npm install -g wrangler

# Login (opens browser)
wrangler login

# Create the Pages project (one-time)
wrangler pages project create cpm-bull-dashboard \
  --production-branch=main

# Get your Account ID
wrangler whoami
# Copy the Account ID
```

Get an API token for GH Actions:

1. https://dash.cloudflare.com/profile/api-tokens
2. **Create Token** → **Custom token**
3. Permissions:
   - `Account` → `Cloudflare Pages` → `Edit`
4. Account Resources: include your specific account
5. Copy the token (shown once)

### 2. GitHub secrets

In your repo: `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

| Secret name | Value |
|---|---|
| `CLOUDFLARE_API_TOKEN` | the token from step 1 |
| `CLOUDFLARE_ACCOUNT_ID` | your CF account ID |
| `TELEGRAM_TOKEN` | (optional) bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | (optional) chat ID to send to |

### 3. Test the workflow

```bash
# Push the workflow to GitHub
git add .github/workflows/monthly-signal.yml deploy/cf-pages/
git commit -m "Add CF Pages monthly build workflow"
git push

# Trigger manually (don't wait for cron)
gh workflow run monthly-signal.yml

# Watch it run
gh run watch
```

Expected output:
- Dashboard published at `https://cpm-bull-dashboard.pages.dev/`
- Telegram message with signal + dashboard URL
- Artifact uploaded (signal_raw.txt, signal_message.txt, dist/index.html)

## Custom domain (optional)

1. CF Pages dashboard → your project → **Custom domains** → **Set up a custom domain**
2. Add e.g. `cpm.yourdomain.com`
3. CF auto-creates DNS record if your domain is on CF, otherwise add the CNAME yourself
4. Free SSL via CF

## Schedule details

Default cron: `30 16 1-3 * *` (16:30 UTC on 1st-3rd of month).

Why 1st-3rd: catches the case when the 1st is a weekend/holiday. The signal
itself uses last completed month-end, so running on the 1st or 3rd produces
the same result. Idempotent.

Adjust in `.github/workflows/monthly-signal.yml` to your timezone preference.

Manual trigger anytime: `gh workflow run monthly-signal.yml`

## Why CF Pages over alternatives

| Option | Cost | Custom domain | Setup |
|---|---:|---|---|
| **CF Pages** ⭐ | $0 | free | wrangler CLI |
| GH Pages | $0 | free | git push to gh-pages branch |
| Vercel | $0 | free | connect repo |
| S3+CloudFront | $0 (free tier) | $0.50/mo CloudFront | AWS console |
| Self-host VPS | $5+/mo | DIY | overkill |

CF Pages chosen for: free + edge CDN globally + atomic deploys + good DX.
GH Pages also fine if you want even simpler (no CF account).

## Files in this directory

- `format_message.py` — formats the signal as Markdown for Telegram/Discord/email
- `README.md` — this file

The workflow itself lives at `.github/workflows/monthly-signal.yml`.

## Lambda comparison

This replaces the AWS Lambda setup in `deploy/lambda/` if you want.

| | Lambda | CF Pages + GH Actions |
|---|---|---|
| Compute | Lambda (Python native) | GH Actions runner (Python native) |
| Dashboard hosting | manual | included (CF Pages) |
| Cost | ~$0 | $0 |
| Cold start | 1-3s | n/a (cron, not request-driven) |
| Setup files | 5+ (Dockerfile, deploy.sh, handler.py, etc.) | 2 (workflow.yml, format_message.py) |
| AWS account needed | yes | no |
| Cloudflare account needed | no | yes |

Pick whichever ecosystem you prefer. Both work.

Lambda can stay deployed in parallel for redundancy; the two notifications
will be duplicates but harmless.

## Disabling Lambda after migration

If you want to fully migrate:

```bash
# Tear down Lambda + EventBridge
./deploy/lambda/teardown.sh

# Remove Lambda directory
git rm -r deploy/lambda/
git commit -m "Migrate from Lambda to CF Pages + GH Actions"
```
