"""Daily LQD/IEF credit-spread circuit check for NDX sleeve -- STATELESS.

Computes today's and yesterday's LQD/IEF circuit state on the fly; alerts
on day-over-day state change via Telegram. No persisted state.

Trigger: LQD/IEF ratio < its 50-day EMA (credit-spread widening).
Recovery: ratio >= EMA OR next monthly signal date (latch resets).

Run by GH Actions workflow circuit-check.yml (triggered daily by CF Worker cron).
"""
from __future__ import annotations

import os
import sys
from datetime import timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cpm_live import load_panel  # noqa: E402
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest  # noqa: E402
from circuit_breaker import (  # noqa: E402
    compute_lqd_ief_circuit_scale,
    current_circuit_state,
    LQD_IEF_EMA_SPAN,
)


def send_telegram_alert(prior_scale: float, new_scale: float,
                          ratio: float, ema: float, distance_pct: float,
                          date: pd.Timestamp,
                          dashboard_url: str | None = None) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print(f"[circuit-check] TELEGRAM creds missing, skipping alert")
        return
    if new_scale < 1.0:
        order = (f"SELL NDX sleeve to cash (LQD/IEF circuit triggered, "
                  f"ratio {ratio:.4f} < EMA50 {ema:.4f}, {distance_pct:+.2f}% below).")
    else:
        order = f"BUY back NDX sleeve to active weight per current monthly signal."
    msg = (
        f"\u26a0 *NDX LQD/IEF circuit state change*\n"
        f"Date: {date.date()}\n"
        f"Scale: {prior_scale:.2f} -> {new_scale:.2f}\n"
        f"LQD/IEF ratio: {ratio:.4f}\n"
        f"EMA{LQD_IEF_EMA_SPAN}: {ema:.4f} ({distance_pct:+.2f}%)\n\n"
        f"{order}\n\n"
        f"Latched until next monthly rebalance (or until ratio recovers above EMA)."
    )
    if dashboard_url:
        msg += f"\n\n\ud83d\udcca Dashboard: {dashboard_url}"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": msg, "parse_mode": "Markdown"},
            timeout=15,
        )
        print(f"[circuit-check] Telegram: {r.status_code}")
    except Exception as exc:
        print(f"[circuit-check] Telegram error: {exc}")


def check_ndx_circuit(panel: pd.DataFrame, ndx_returns: pd.Series,
                       sig_dates: list,
                       dashboard_url: str | None = None) -> int:
    """Check NDX LQD/IEF circuit for state change. Returns 0 normal, 1 alerted."""
    if len(ndx_returns) < 60:
        print(f"[circuit-check] insufficient history ({len(ndx_returns)} bars)")
        return 0
    common = ndx_returns.index
    scale = compute_lqd_ief_circuit_scale(panel["LQD"], panel["IEF"],
                                              common, sig_dates)
    if len(scale) < 2:
        print(f"[circuit-check] insufficient scale series")
        return 0
    today_scale = float(scale.iloc[-1])
    today_date = scale.index[-1]
    prior_scale = float(scale.iloc[-2])
    state = current_circuit_state(panel["LQD"], panel["IEF"])
    state_changed = abs(today_scale - prior_scale) > 0.01
    if state_changed:
        print(f"[circuit-check] NDX: \u26a0 STATE CHANGE scale {prior_scale:.2f} "
              f"-> {today_scale:.2f}, ratio {state['ratio']:.4f} "
              f"({state['distance_pct']:+.2f}% vs EMA)")
        send_telegram_alert(prior_scale, today_scale,
                              state["ratio"], state["ema"], state["distance_pct"],
                              today_date, dashboard_url)
        return 1
    else:
        status = "TRIGGERED" if today_scale < 1.0 else "normal"
        print(f"[circuit-check] NDX: no change, scale={today_scale:.2f} "
              f"({status}), ratio {state['ratio']:.4f} "
              f"({state['distance_pct']:+.2f}% vs EMA)")
        return 0


def main() -> int:
    end = pd.Timestamp.now(tz=timezone.utc).tz_localize(None).normalize()
    print(f"[circuit-check] loading panel + NDX sleeve returns up to {end.date()} ...")
    panel = load_panel(start=pd.Timestamp("1996-01-01"),
                       end=end + pd.Timedelta(days=2))
    ndx_panel = load_ndx_panel()
    ndx_r, _ = run_ndx_backtest(panel, ndx_panel, pd.Timestamp("2006-01-01"), end)
    if len(ndx_r) < 30:
        print(f"[circuit-check] insufficient sleeve history")
        return 1
    sig_dates_ndx = (pd.DataFrame({"x": 1}, index=ndx_r.index)
                      .groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    dash_url = os.environ.get("DASHBOARD_URL")
    n_alerts = check_ndx_circuit(panel, ndx_r, sig_dates_ndx, dash_url)
    print(f"[circuit-check] {n_alerts} alerts sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
