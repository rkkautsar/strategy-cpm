"""Daily vol-cap check.

Computes the current latched vol-cap scale, compares to prior persisted state,
and sends a Telegram alert on state change. Updates vol_cap_state.json.

Run by GH Actions workflow vol-check.yml (triggered daily by CF Worker cron).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cpm_live import load_panel, run_cpm_backtest  # noqa: E402
from bull_qqq_live import run_bull_qqq_backtest  # noqa: E402
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest  # noqa: E402
from vol_cap import (  # noqa: E402
    compute_latched_scale,
    current_threshold,
    VOL_CAP_ABS_FLOOR,
    VOL_CAP_LB_SHORT,
    VOL_CAP_LB_LONG,
)

STATE_FILE = ROOT / "vol_cap_state.json"
HISTORY_DAYS = 700  # >2y context: 252d long-avg + 21d short-vol + monthly latch + margin


def send_telegram_alert(prior_scale: float, new_scale: float,
                          realized_vol: float, threshold: float,
                          date: pd.Timestamp,
                          dashboard_url: str | None = None) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[vol-check] TELEGRAM creds missing, skipping alert")
        return
    try:
        import requests
    except ImportError:
        os.system(f"{sys.executable} -m pip install requests --quiet")
        import requests  # type: ignore

    if new_scale < prior_scale:
        action_line = "🚨 *DEFENSIVE TRIGGER: scale down to 50%*"
        order = (f"SELL {(prior_scale - new_scale) * 100:.0f}% of portfolio to cash. "
                 "Distribute across all current holdings proportionally.")
    else:
        action_line = "✅ *RECOVERY: scale back to 100%*"
        order = (f"BUY {(new_scale - prior_scale) * 100:.0f}% of portfolio back from cash, "
                 "rebalance to current sleeve targets.")
    msg = (
        f"{action_line}\n\n"
        f"As of: {date.date()}\n"
        f"21d realized vol: {realized_vol:.1f}%  (current threshold {threshold:.1f}%; "
        f"abs floor {VOL_CAP_ABS_FLOOR * 100:.0f}%)\n"
        f"Scale: {prior_scale:.2f} → {new_scale:.2f}\n\n"
        f"{order}\n\n"
        f"Latched until next monthly rebalance (or until vol re-evaluates at signal date)."
    )
    if dashboard_url:
        msg += f"\n\n📊 Dashboard: {dashboard_url}"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
            timeout=15,
        )
        print(f"[vol-check] Telegram: {r.status_code}")
    except Exception as exc:
        print(f"[vol-check] Telegram error: {exc}")


def main() -> int:
    end = pd.Timestamp.now(tz=timezone.utc).tz_localize(None).normalize()
    start = end - pd.Timedelta(days=HISTORY_DAYS)
    print(f"[vol-check] loading panels {start.date()} -> {end.date()} ...")
    panel = load_panel(start=start - pd.Timedelta(days=365),
                       end=end + pd.Timedelta(days=2))
    ndx_panel = load_ndx_panel()

    cpm_r, _ = run_cpm_backtest(panel, start, end)
    bull_r = run_bull_qqq_backtest(panel, start, end)
    ndx_r, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = cpm_r.index.intersection(bull_r.index).intersection(ndx_r.index)
    if len(common) < VOL_CAP_LB_LONG + 30:
        print(f"[vol-check] insufficient history: {len(common)} bars")
        return 1
    c = cpm_r.reindex(common).fillna(0.0)
    b = bull_r.reindex(common).fillna(0.0)
    n = ndx_r.reindex(common).fillna(0.0)
    blend = 0.60 * c + 0.20 * b + 0.20 * n

    sig_dates = (pd.date_range(common[0], common[-1], freq="ME")
                 .intersection(common).tolist())
    scale, events = compute_latched_scale(blend, sig_dates)

    today_scale = float(scale.iloc[-1])
    today_date = scale.index[-1]
    breakdown = current_threshold(blend)
    realized_vol = breakdown["realized_vol_21d"] * 100 if pd.notna(breakdown["realized_vol_21d"]) else float("nan")
    long_avg = breakdown["long_avg_252d"] * 100 if pd.notna(breakdown["long_avg_252d"]) else float("nan")
    current_thresh = breakdown["threshold"] * 100

    # Load prior state
    if STATE_FILE.exists():
        try:
            prior = json.loads(STATE_FILE.read_text())
        except Exception:
            prior = None
    else:
        prior = None
    prior_scale = float(prior.get("scale", 1.0)) if prior else 1.0

    state_changed = abs(today_scale - prior_scale) > 0.01

    new_state = {
        "scale": today_scale,
        "regime": "CAP_ENGAGED" if today_scale < 1.0 else "NORMAL",
        "as_of_date": str(today_date.date()),
        "realized_vol_21d_pct": round(realized_vol, 2),
        "long_avg_252d_pct": round(long_avg, 2) if pd.notna(long_avg) else None,
        "current_threshold_pct": round(current_thresh, 2),
        "abs_floor_pct": VOL_CAP_ABS_FLOOR * 100,
        "lb_short_days": VOL_CAP_LB_SHORT,
        "lb_long_days": VOL_CAP_LB_LONG,
        "last_check_utc": datetime.now(timezone.utc).isoformat(),
        "last_change_event": (
            {
                "from_scale": prior_scale,
                "to_scale": today_scale,
                "at_date": str(today_date.date()),
                "realized_vol_at_change": round(realized_vol, 2),
                "threshold_at_change": round(current_thresh, 2),
                "kind": "trigger" if today_scale < prior_scale else "lift",
            }
            if state_changed
            else (prior.get("last_change_event") if prior else None)
        ),
        "lifetime_events": (
            (prior.get("lifetime_events", 0) if prior else 0)
            + (1 if state_changed else 0)
        ),
    }
    STATE_FILE.write_text(json.dumps(new_state, indent=2) + "\n")

    if state_changed:
        print(f"[vol-check] ⚠ STATE CHANGED: {prior_scale:.2f} -> {today_scale:.2f}  "
              f"realized_vol={realized_vol:.2f}%  threshold={current_thresh:.2f}%")
        dash_url = os.environ.get("DASHBOARD_URL")
        send_telegram_alert(prior_scale, today_scale, realized_vol,
                              current_thresh, today_date, dash_url)
    else:
        print(f"[vol-check] no change: scale={today_scale:.2f}  "
              f"realized_vol={realized_vol:.2f}%  "
              f"threshold={current_thresh:.2f}% "
              f"(= max(long_avg {long_avg:.2f}%, abs_floor {VOL_CAP_ABS_FLOOR*100:.0f}%))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
