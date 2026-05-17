"""AWS Lambda entrypoint: compute monthly FCP+BULL signal and send to Telegram.

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

# Ensure strategy modules are importable (bundled in /var/task by container)
sys.path.insert(0, "/var/task")
sys.path.insert(0, "/var/task/strategy")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


def compute_signal() -> str:
    """Run BULL-QQQ + FCP allocate commands and capture stdout."""
    import pandas as pd
    import bull_qqq_live as bql
    import fcp_live as fcp_mod
    from fcp_live import load_panel, compute_target_weights, SAFE_POOL

    # Load panel up to most recent month-end
    today = pd.Timestamp.today().normalize()
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=today)
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

    # === FCP sleeve ===
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
    lines.append(f"📊 FCP+BULL Monthly Signal")
    lines.append(f"Signal date: {sig_d.date()}")
    lines.append(f"Trade at next MOC (T+1)")
    lines.append("")
    lines.append(f"━━━ FCP sleeve ({int(PROD_FCP_W*100)}%) ━━━")
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
    lines.append(f"⚠️  Forward Sharpe expectation 0.90-1.20 (not 1.56 backtest)")

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
            return {"statusCode": 200, "body": "DRY_RUN — signal logged, not sent"}

        result = send_telegram(message)
        logger.info(f"Telegram OK: message_id={result.get('result', {}).get('message_id')}")
        return {
            "statusCode": 200,
            "body": json.dumps({"sent": True, "msg_id": result.get("result", {}).get("message_id")}),
        }

    except Exception as e:
        err_msg = f"❌ FCP+BULL signal FAILED\n{type(e).__name__}: {e}\n\n{traceback.format_exc()[:1500]}"
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
