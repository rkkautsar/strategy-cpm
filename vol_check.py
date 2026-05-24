"""Daily vol-cap check (VIX-based) -- STATELESS.

Computes today's and yesterday's latched vol-cap scale on-the-fly from full
history; alerts on state change. No persisted state file.

Trigger: VIX > rolling 5y P95 of VIX (latched 50% binary until next monthly
signal). The latched scale is fully reconstructible from VIX + signal dates,
so day-over-day comparison is sufficient for change detection.

Run by GH Actions workflow vol-check.yml (triggered daily by CF Worker cron).
"""
from __future__ import annotations

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
    load_vix,
    VIX_PCT,
    VIX_LB_YEARS,
    VIX_SANE_MIN,
    VIX_SANE_MAX,
)

HISTORY_DAYS = 90  # only need recent blend returns; VIX has its own history


def send_telegram_alert(prior_scale: float, new_scale: float,
                          vix: float, threshold: float,
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
        action_line = "\u26a0\ufe0f *DEFENSIVE TRIGGER: scale down to 50%*"
        order = (f"SELL {(prior_scale - new_scale) * 100:.0f}% of portfolio to cash. "
                 "Distribute across all current holdings proportionally.")
    else:
        action_line = "\u2705 *RECOVERY: scale back to 100%*"
        order = (f"BUY {(new_scale - prior_scale) * 100:.0f}% of portfolio back from cash, "
                 "rebalance to current sleeve targets.")
    msg = (
        f"{action_line}\n\n"
        f"As of: {date.date()}\n"
        f"VIX: {vix:.2f}  (threshold {threshold:.2f} = "
        f"P{int(VIX_PCT * 100)} of rolling {VIX_LB_YEARS}y VIX)\n"
        f"Scale: {prior_scale:.2f} \u2192 {new_scale:.2f}\n\n"
        f"{order}\n\n"
        f"Latched until next monthly rebalance (or until VIX re-evaluates at signal date)."
    )
    if dashboard_url:
        msg += f"\n\n\ud83d\udcca Dashboard: {dashboard_url}"
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
    print(f"[vol-check] loading recent panel + VIX up to {end.date()} ...")
    panel = load_panel(start=start - pd.Timedelta(days=365),
                       end=end + pd.Timedelta(days=2))
    ndx_panel = load_ndx_panel()
    vix = load_vix(end=end + pd.Timedelta(days=2))

    cpm_r, _ = run_cpm_backtest(panel, start, end)
    bull_r = run_bull_qqq_backtest(panel, start, end)
    ndx_r, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = cpm_r.index.intersection(bull_r.index).intersection(ndx_r.index)
    if len(common) < 30:
        print(f"[vol-check] insufficient recent blend history: {len(common)} bars")
        return 1
    c = cpm_r.reindex(common).fillna(0.0)
    b = bull_r.reindex(common).fillna(0.0)
    n = ndx_r.reindex(common).fillna(0.0)
    blend = 0.60 * c + 0.20 * b + 0.20 * n

    sig_dates = (pd.date_range(common[0], common[-1], freq="ME")
                 .intersection(common).tolist())
    scale, _events = compute_latched_scale(blend, sig_dates, vix=vix)

    if len(scale) < 2:
        print(f"[vol-check] insufficient scale history: {len(scale)} bars")
        return 1

    today_scale = float(scale.iloc[-1])
    today_date = scale.index[-1]
    prior_scale = float(scale.iloc[-2])
    breakdown = current_threshold(vix)
    today_vix = breakdown["vix"]
    today_thresh = breakdown["threshold"]

    # Sanity-bound check on today's VIX print
    if pd.notna(today_vix) and (today_vix < VIX_SANE_MIN or today_vix > VIX_SANE_MAX):
        print(f"[vol-check] ERROR: today's VIX {today_vix:.2f} outside sane "
              f"range [{VIX_SANE_MIN}, {VIX_SANE_MAX}] - likely data error, "
              f"skipping alert")
        return 2

    state_changed = abs(today_scale - prior_scale) > 0.01

    if state_changed:
        print(f"[vol-check] \u26a0 STATE CHANGED: scale {prior_scale:.2f} -> "
              f"{today_scale:.2f}  VIX={today_vix:.2f}  "
              f"threshold={today_thresh:.2f}")
        dash_url = os.environ.get("DASHBOARD_URL")
        send_telegram_alert(prior_scale, today_scale, today_vix, today_thresh,
                              today_date, dash_url)
    else:
        cmp = ">" if today_vix > today_thresh else "<"
        print(f"[vol-check] no change: scale={today_scale:.2f}  "
              f"VIX={today_vix:.2f} {cmp} threshold={today_thresh:.2f} "
              f"(P{int(VIX_PCT * 100)} of {VIX_LB_YEARS}y VIX)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
