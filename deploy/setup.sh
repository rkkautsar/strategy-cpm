#!/usr/bin/env bash
# One-shot setup for CF Pages + CF Workers cron + GH Actions deployment.
#
# Prerequisites:
#   - Cloudflare account (free)
#   - GitHub account
#   - gh CLI (`brew install gh`)
#   - wrangler CLI (`npm install -g wrangler`)
#   - This repo pushed to GitHub
#
# Run this script from the repo root: bash deploy/setup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "================================================================"
echo "CPM-NDX-VAL-RPV deployment setup"
echo "================================================================"
echo

# ---------- Preflight ----------
command -v gh       >/dev/null || { echo "ERR: install gh CLI: brew install gh"; exit 1; }
command -v wrangler >/dev/null || { echo "ERR: install wrangler: npm install -g wrangler"; exit 1; }
command -v uv       >/dev/null || { echo "ERR: install uv: https://astral.sh/uv"; exit 1; }

# ---------- GitHub remote check ----------
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "ERR: no git remote 'origin' configured."
  echo "Push this repo to GitHub first, e.g.:"
  echo "  gh repo create strategy-cpm --private --source=. --remote=origin --push"
  exit 1
fi

REMOTE_URL=$(git remote get-url origin)
# Parse owner/repo from URL (handles both git@ and https://)
if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
  GH_OWNER="${BASH_REMATCH[1]}"
  GH_REPO="${BASH_REMATCH[2]}"
  echo "GitHub repo: $GH_OWNER/$GH_REPO"
else
  echo "ERR: could not parse owner/repo from remote URL: $REMOTE_URL"
  exit 1
fi
echo

# ---------- Update wrangler.toml ----------
WRANGLER="$REPO_ROOT/deploy/cf-cron/wrangler.toml"
if grep -q 'GH_OWNER = "your-github-username"' "$WRANGLER"; then
  echo "Updating wrangler.toml with detected GH_OWNER/GH_REPO..."
  sed -i.bak "s|GH_OWNER = \"your-github-username\"|GH_OWNER = \ER\"|" "$WRANGLER"
  sed -i.bak "s|GH_REPO  = \"strategy-cpm\"|GH_REPO  = \"$GH_REPO\"|" "$WRANGLER"
  rm "$WRANGLER.bak"
  echo "  OK"
fi
echo

# ---------- CF login + project ----------
if ! wrangler whoami 2>/dev/null | grep -q "logged in"; then
  echo "Logging in to Cloudflare (opens browser)..."
  wrangler login
fi

CF_ACCOUNT_ID=$(wrangler whoami 2>/dev/null | grep -oE '[0-9a-f]{32}' | head -1)
echo "CF Account ID: $CF_ACCOUNT_ID"

# Create CF Pages project (idempotent)
echo "Creating CF Pages project 'cpm-bull-dashboard' (idempotent)..."
wrangler pages project create cpm-bull-dashboard \
  --production-branch=main 2>&1 | grep -v "already exists" || true
echo

# ---------- Prompt for secrets ----------
echo "================================================================"
echo "Need to set the following secrets. You'll be prompted for each."
echo "================================================================"
echo

# CF API Token
echo "[1/4] Cloudflare API token"
echo "  Create at: https://dash.cloudflare.com/profile/api-tokens"
echo "  Template: Custom token"
echo "  Permissions: Account > Cloudflare Pages > Edit"
echo
read -r -s -p "  Paste CLOUDFLARE_API_TOKEN: " CF_API_TOKEN
echo

# GitHub PAT for Workers
echo
echo "[2/4] GitHub fine-grained PAT (for CF Workers to trigger GH Actions)"
echo "  Create at: https://github.com/settings/tokens?type=beta"
echo "  Repository access: Only select repositories > $GH_OWNER/$GH_REPO"
echo "  Permissions: Actions > Read and Write"
echo
read -r -s -p "  Paste GH_TOKEN (for CF Worker): " GH_PAT
echo

# Random trigger token
TRIGGER_TOKEN=$(openssl rand -hex 16)
echo
echo "[3/4] Generated TRIGGER_TOKEN (for manual HTTP triggers):"
echo "  $TRIGGER_TOKEN"
echo "  (save this if you want to manually trigger via curl)"
echo

# Telegram (optional)
echo
echo "[4/5] Telegram bot (OPTIONAL, press Enter to skip)"
read -r -p "  TELEGRAM_TOKEN (or empty): " TG_TOKEN || true
TG_CHAT=""
if [[ -n "$TG_TOKEN" ]]; then
  read -r -p "  TELEGRAM_CHAT_ID: " TG_CHAT
fi
echo

# Resend email (optional)
echo
echo "[5/5] Resend email (OPTIONAL, press Enter to skip)"
if [[ -n "${RESEND_API_KEY:-}" ]]; then
  echo "  Found RESEND_API_KEY in environment ($(echo "$RESEND_API_KEY" | sed 's/\(re_\{0,1\}.\{4\}\).*/\1.../'))"
  read -r -p "  Use this key? [Y/n]: " USE_ENV_KEY
  if [[ "${USE_ENV_KEY:-Y}" =~ ^[Yy]?$ ]]; then
    RESEND_KEY="$RESEND_API_KEY"
  else
    read -r -s -p "  Paste RESEND_API_KEY (or empty): " RESEND_KEY || true
    echo
  fi
else
  read -r -s -p "  Paste RESEND_API_KEY (or empty): " RESEND_KEY || true
  echo
fi

RESEND_TO=""
RESEND_FROM=""
if [[ -n "$RESEND_KEY" ]]; then
  read -r -p "  Recipient email (RESEND_TO): " RESEND_TO
  echo
  echo "  Sender (RESEND_FROM):"
  echo "    Default 'onboarding@resend.dev' works ONLY for sending to your verified Resend"
  echo "    account email. To send to other addresses or use a custom from, verify a domain"
  echo "    at https://resend.com/domains first."
  read -r -p "  RESEND_FROM (or Enter for default): " RESEND_FROM
  RESEND_FROM="${RESEND_FROM:-CPM-NDX-VAL-RPV <onboarding@resend.dev>}"
fi
echo

# ---------- Deploy CF Worker ----------
echo "================================================================"
echo "Deploying CF Worker (cron clock)..."
echo "================================================================"
cd "$REPO_ROOT/deploy/cf-cron"
echo "$GH_PAT" | wrangler secret put GH_TOKEN
echo "$TRIGGER_TOKEN" | wrangler secret put TRIGGER_TOKEN
wrangler deploy
cd "$REPO_ROOT"
echo

# ---------- Set GH secrets ----------
echo "================================================================"
echo "Setting GitHub repo secrets..."
echo "================================================================"
echo "$CF_API_TOKEN" | gh secret set CLOUDFLARE_API_TOKEN
echo "$CF_ACCOUNT_ID" | gh secret set CLOUDFLARE_ACCOUNT_ID
if [[ -n "$TG_TOKEN" ]]; then
  echo "$TG_TOKEN" | gh secret set TELEGRAM_TOKEN
  echo "$TG_CHAT" | gh secret set TELEGRAM_CHAT_ID
fi
if [[ -n "$RESEND_KEY" ]]; then
  echo "$RESEND_KEY" | gh secret set RESEND_API_KEY
  echo "$RESEND_TO"  | gh secret set RESEND_TO
  # RESEND_FROM is non-secret -> store as repo variable so it shows in workflow logs
  gh variable set RESEND_FROM --body "$RESEND_FROM" 2>/dev/null || \
    echo "$RESEND_FROM" | gh secret set RESEND_FROM  # fallback if vars not supported
fi
echo

# ---------- Smoke test ----------
echo "================================================================"
echo "Setup complete! Smoke test:"
echo "================================================================"
echo
echo "1) Trigger GH Actions workflow manually:"
echo "     gh workflow run monthly-signal.yml"
echo "     gh run watch"
echo
echo "2) After it succeeds, dashboard will be at:"
echo "     https://cpm-bull-dashboard.pages.dev/"
echo
echo "3) Test CF Worker manual trigger (HTTP):"
echo "     curl -X POST https://cpm-bull-cron.$(wrangler whoami 2>/dev/null | grep -oE '[a-z0-9-]+\.workers\.dev' | head -1 | sed 's/\.workers\.dev$//').workers.dev/ \\"
echo "       -H 'X-Trigger-Token: $TRIGGER_TOKEN'"
echo
echo "4) Cron will auto-fire next: 16:30 UTC on 1st-3rd of next month."
echo
echo "All secrets:"
echo "  CF Pages project: cpm-bull-dashboard"
echo "  CF Worker:        cpm-bull-cron (cron: 30 16 1-3 * *)"
echo "  GH secrets set:   CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID$([ -n "$TG_TOKEN" ] && echo ', TELEGRAM_TOKEN, TELEGRAM_CHAT_ID')$([ -n "$RESEND_KEY" ] && echo ', RESEND_API_KEY, RESEND_TO')"
  GH variables set: $([ -n "$RESEND_KEY" ] && echo 'RESEND_FROM' || echo '(none)')"

echo "  TRIGGER_TOKEN:    $TRIGGER_TOKEN  (save this)"
