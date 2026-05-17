"""AWS Lambda entrypoint: compute monthly CPM-BULL signal and send to Telegram.

Triggered by EventBridge cron on the 1st of each month at 14:00 UTC.
Reads ETF prices via yfinance, computes target allocation, sends formatted
message to Telegram chat.

Environment variables (set in Lambda config):
  TELEGRAM_BOT_TOKEN   -- from @BotFather
  TELEGRAM_CHAT_ID     -- your personal chat ID (number)
  DRY_RUN              -- optional, "true" to log without sending
"""
from __future__ import annotations

import io
import os
import sys
import json
import logging
import traceback
from contextlib import redirect_stdout
from datetime import datetime, timezone

import requests

# Ensure strategy modules are importable (bundled in /var/task by container,
# or use repo root when running locally for dry-run).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for p in ("/var/task", "/var/task/strategy", _REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.path.insert(0, "/var/task/strategy")

logger = logging.getLogger()
logger.setLevel(logging.INFO)
# Local-run: also surface logger to stdout (Lambda's logger already handles
# CloudWatch routing).
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def refresh_live_data(panel, today):
    """Fetch fresh yfinance tails for canary/signal-critical assets and
    extend the stitched panel forward to today. Avoids stale signals from
    bundled CSVs that were frozen at container build time."""
    import pandas as pd
    import yfinance as yf

    # Assets where freshness is critical for the monthly signal
    # (signals computed: 13612U, 12-1 mom, Faber 10mo SMA, 756d covariance)
    LIVE_CRITICAL = [
        # Canary (both sleeves)
        "HYG", "LQD", "TIP", "GLD",
        # BULL bull asset + substitute
        "QQQ", "XLP",
        # CPM universe (need fresh for momentum ranking)
        "IGM", "XLE", "VBR", "SPHQ", "XMHQ", "XLV", "VEA", "VWO", "TLT",
        # Cash + reference
        "SHV", "SPY",
    ]
    # Pull last 3 years of data (need 756d covariance lookback + buffer)
    pull_start = (today - pd.DateOffset(years=4)).strftime("%Y-%m-%d")
    pull_end = (today + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Refreshing live data for {len(LIVE_CRITICAL)} assets from yfinance...")
    fresh = yf.download(
        LIVE_CRITICAL,
        start=pull_start, end=pull_end,
        auto_adjust=True, progress=False, threads=True,
    )
    if isinstance(fresh.columns, pd.MultiIndex):
        fresh = fresh["Close"]
    fresh = fresh.dropna(how="all")
    print(f"  Fetched {len(fresh)} days, latest = {fresh.index[-1].date()}")

    # Overlay fresh data onto stitched panel.
    # For stitched assets (HYG_stitched), merge the live HYG tail into
    # the stitched series past the CSV's last date.
    if "HYG" in fresh.columns and "HYG_stitched" in panel.columns:
        live_hyg = fresh["HYG"].dropna()
        stitched = panel["HYG_stitched"].dropna()
        last_stitched = stitched.index.max()
        new_tail = live_hyg[live_hyg.index > last_stitched]
        if len(new_tail) > 0:
            print(f"  Extending HYG_stitched: +{len(new_tail)} days past {last_stitched.date()}")
            panel.loc[new_tail.index, "HYG_stitched"] = new_tail.values

    # For non-stitched assets, overlay live data wholesale (latest wins)
    for asset in LIVE_CRITICAL:
        if asset not in fresh.columns:
            continue
        live_series = fresh[asset].dropna()
        if asset in panel.columns:
            # Extend existing column with newer data
            existing = panel[asset].dropna()
            new_tail = live_series[live_series.index > existing.index.max()] if len(existing) else live_series
            if len(new_tail) > 0:
                panel.loc[new_tail.index, asset] = new_tail.values
        else:
            # Asset not in panel -- add it
            panel = panel.join(live_series.rename(asset), how="outer")

    return panel.sort_index()


def compute_signal() -> str:
    """Run BULL-QQQ + CPM allocate commands and capture stdout."""
    import pandas as pd
    import bull_qqq_live as bql
    import cpm_live as fcp_mod
    from cpm_live import load_panel, compute_target_weights, SAFE_POOL

    # Clear yfinance disk cache to force fresh fetch (Lambda /tmp persists
    # across warm invocations; monthly cron cold-starts but safest to clear).
    import shutil
    shutil.rmtree("/tmp/cpm_cache", ignore_errors=True)

    # Load panel up to most recent month-end
    today = pd.Timestamp.today().normalize()
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=today)
    # CRITICAL: extend stitched CSVs (HYG_stitched etc.) and refresh live
    # ETF tails so signal uses TODAY's data, not container build-time data.
    panel = refresh_live_data(panel, today)
    monthly = panel.resample("ME").last()
    # Use last complete month-end as signal date
    sig_d = monthly.index[-1]
    if sig_d > today:
        sig_d = monthly.index[-2]

    # === BULL-QQQ sleeve ===
    bull_buf = io.StringIO()
    with redirect_stdout(bull_buf):
        weights_bull, regime_bull, diag_bull = bql.compute_bull_qqq_weights(
            panel, sig_d
        )
    bull_text = bull_buf.getvalue()

    # === CPM sleeve ===
    weights_fcp, pair, regime_fcp, safe = compute_target_weights(panel, sig_d)

    # === Combined portfolio ===
    PROD_BULL_W = bql.PROD_BULL_WEIGHT
    PROD_FCP_W = 1 - PROD_BULL_W
    combined = {}
    for t, w in weights_fcp.items():
        combined[t] = combined.get(t, 0) + PROD_FCP_W * w
    for t, w in weights_bull.items():
        combined[t] = combined.get(t, 0) + PROD_BULL_W * w
    # Filter out near-zero weights
    combined = {t: w for t, w in combined.items() if w > 0.001}

    # === Format message ===
    lines = []
    lines.append(f"📊 CPM-BULL Monthly Signal")
    lines.append(f"Signal date: {sig_d.date()}")
    lines.append(f"Trade at next MOC (T+1)")
    lines.append("")
    lines.append(f"━━━ CPM sleeve ({int(PROD_FCP_W*100)}%) ━━━")
    lines.append(f"Regime: {regime_fcp}")
    for t, w in sorted(weights_fcp.items(), key=lambda x: -x[1]):
        lines.append(f"  {t:6s}  {w*100:5.1f}%")
    lines.append("")
    lines.append(f"━━━ BULL-QQQ sleeve ({int(PROD_BULL_W*100)}%) ━━━")
    lines.append(f"Regime: {regime_bull}")
    for t, w in sorted(weights_bull.items(), key=lambda x: -x[1]):
        lines.append(f"  {t:6s}  {w*100:5.1f}%")
    lines.append("")
    lines.append(f"━━━ Combined portfolio (100%) ━━━")
    for t, w in sorted(combined.items(), key=lambda x: -x[1]):
        lines.append(f"  {t:6s}  {w*100:5.1f}%")
    lines.append("")
    lines.append(f"⚠️  Use only in tax-advantaged accounts (IRA/401k/Roth)")
    lines.append(f"⚠️  Forward Sharpe expectation 0.90-1.20 (not 1.54 backtest)")

    return "\n".join(lines)


def send_telegram(message: str) -> dict:
    """POST to Telegram Bot API."""
    if not TG_TOKEN or not TG_CHAT:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(
        url,
        json={
            "chat_id": TG_CHAT,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def lambda_handler(event, context):
    """Entrypoint. EventBridge cron triggers this."""
    logger.info(f"Triggered at {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Event: {json.dumps(event) if event else 'manual'}")

    try:
        message = compute_signal()
        logger.info(f"Signal computed ({len(message)} chars)")
        logger.info(f"---\n{message}\n---")

        if DRY_RUN:
            print("\n" + "=" * 60)
            print("DRY RUN -- would send the following to Telegram:")
            print("=" * 60)
            print(message)
            print("=" * 60 + "\n")
            return {"statusCode": 200, "body": "DRY_RUN — signal printed above, not sent"}

        result = send_telegram(message)
        logger.info(f"Telegram OK: message_id={result.get('result', {}).get('message_id')}")
        return {
            "statusCode": 200,
            "body": json.dumps({"sent": True, "msg_id": result.get("result", {}).get("message_id")}),
        }

    except Exception as e:
        err_msg = f"❌ CPM-BULL signal FAILED\n{type(e).__name__}: {e}\n\n{traceback.format_exc()[:1500]}"
        logger.error(err_msg)
        # Try to send error to Telegram so you know it failed
        try:
            if not DRY_RUN and TG_TOKEN and TG_CHAT:
                send_telegram(err_msg)
        except Exception:
            pass
        return {"statusCode": 500, "body": str(e)}


if __name__ == "__main__":
    # Local test: python handler.py
    os.environ.setdefault("DRY_RUN", "true")
    print(lambda_handler({}, None))
