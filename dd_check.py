"""Daily DD circuit breaker check (per-sleeve) -- STATELESS.

Computes today's and yesterday's DD circuit state for BULL and NDX sleeves
on-the-fly from full history; alerts on state change. No persisted state.

Trigger: per-sleeve cumulative DD from peak < -15% (DD_CIRCUIT_THRESHOLD).
Symmetric design with vol_check.py (VIX cap).

Run by GH Actions workflow dd-check.yml (triggered daily by CF Worker cron).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cpm_live import load_panel  # noqa: E402
from bull_qqq_live import run_bull_qqq_backtest  # noqa: E402
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest  # noqa: E402
from vol_cap import (  # noqa: E402
    compute_dd_circuit_scale,
    DD_CIRCUIT_THRESHOLD,
    DD_CIRCUIT_SCALE,
)


def send_telegram_alert(sleeve: str, prior_scale: float, new_scale: float,
                          current_dd: float, threshold: float,
                          date: pd.Timestamp,
                          dashboard_url: str | None = None) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print(f"[dd-check] TELEGRAM creds missing, skipping alert ({sleeve})")
        return
    try:
        import requests
    except ImportError:
        os.system(f"{sys.executable} -m pip install requests --quiet")
        import requests  # type: ignore

    if new_scale < prior_scale:
        action_line = f"\u26a0\ufe0f *{sleeve} DD CIRCUIT TRIGGERED: scale to cash*"
        order = (f"SELL {sleeve} sleeve to cash (DD {current_dd*100:.2f}% breached "
                 f"{threshold*100:.0f}% threshold). Sleeve weight redistributes to safe.")
    else:
        action_line = f"\u2705 *{sleeve} DD CIRCUIT LIFTED: back to active*"
        order = (f"BUY back {sleeve} sleeve to active weight per current monthly signal.")
    msg = (
        f"{action_line}\n\n"
        f"As of: {date.date()}\n"
        f"{sleeve} cumulative DD: {current_dd*100:+.2f}%\n"
        f"Threshold: {threshold*100:.0f}%\n"
        f"Scale: {prior_scale:.2f} \u2192 {new_scale:.2f}\n\n"
        f"{order}\n\n"
        f"Latched until next monthly rebalance (or until DD recovers above threshold)."
    )
    if dashboard_url:
        msg += f"\n\n\ud83d\udcca Dashboard: {dashboard_url}"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
            timeout=15,
        )
        print(f"[dd-check] Telegram ({sleeve}): {r.status_code}")
    except Exception as exc:
        print(f"[dd-check] Telegram error ({sleeve}): {exc}")


def check_sleeve(name: str, sleeve_returns: pd.Series, sig_dates: list,
                   threshold: float, recovery_scale: float,
                   dashboard_url: str | None = None) -> int:
    """Check single sleeve for DD state change. Returns 0 normal, 1 alerted."""
    if len(sleeve_returns) < 30:
        print(f"[dd-check] {name}: insufficient history ({len(sleeve_returns)} bars)")
        return 0
    scale = compute_dd_circuit_scale(sleeve_returns, sig_dates,
                                        threshold=threshold,
                                        recovery_scale=recovery_scale)
    if len(scale) < 2:
        print(f"[dd-check] {name}: insufficient scale series")
        return 0
    today_scale = float(scale.iloc[-1])
    today_date = scale.index[-1]
    prior_scale = float(scale.iloc[-2])
    eq = (1.0 + sleeve_returns).cumprod()
    current_dd = float((eq / eq.cummax() - 1.0).iloc[-1])
    state_changed = abs(today_scale - prior_scale) > 0.01
    if state_changed:
        print(f"[dd-check] {name}: \u26a0 STATE CHANGE scale {prior_scale:.2f} "
              f"-> {today_scale:.2f}, DD {current_dd*100:+.2f}%")
        send_telegram_alert(name, prior_scale, today_scale, current_dd,
                              threshold, today_date, dashboard_url)
        return 1
    else:
        status = "TRIGGERED" if today_scale < 1.0 else "normal"
        print(f"[dd-check] {name}: no change, scale={today_scale:.2f} "
              f"({status}), DD {current_dd*100:+.2f}%")
        return 0


def main() -> int:
    end = pd.Timestamp.now(tz=timezone.utc).tz_localize(None).normalize()
    print(f"[dd-check] loading panel + sleeve returns up to {end.date()} ...")
    panel = load_panel(start=pd.Timestamp("1996-01-01"),
                       end=end + pd.Timedelta(days=2))
    ndx_panel = load_ndx_panel()
    bull_r = run_bull_qqq_backtest(panel, pd.Timestamp("1996-01-04"), end)
    ndx_r, _ = run_ndx_backtest(panel, ndx_panel, pd.Timestamp("2006-01-01"), end)
    if len(bull_r) < 30 or len(ndx_r) < 30:
        print(f"[dd-check] insufficient sleeve history")
        return 1

    sig_dates = (pd.date_range(bull_r.index[0], bull_r.index[-1], freq="ME")
                 .intersection(bull_r.index).tolist())
    sig_dates_ndx = (pd.date_range(ndx_r.index[0], ndx_r.index[-1], freq="ME")
                      .intersection(ndx_r.index).tolist())

    dash_url = os.environ.get("DASHBOARD_URL")
    n_alerts = 0
    n_alerts += check_sleeve("BULL", bull_r, sig_dates,
                                DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE, dash_url)
    n_alerts += check_sleeve("NDX", ndx_r, sig_dates_ndx,
                                DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE, dash_url)
    print(f"[dd-check] {n_alerts} alerts sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
