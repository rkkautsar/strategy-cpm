#!/usr/bin/env python
"""Format the monthly signal as a clean Markdown message for Telegram/Discord/email.

Reads from cpm_live.py allocate output and produces a compact, mobile-friendly
formatted message.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import cpm_live as cpm
from cpm_live import load_panel, compute_live_weights
from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel
from rpv_live import compute_rpv_weights
from core import cached_value_backtest



def fmt_alloc(weights: dict, label: str, sleeve_weight: float = 1.0) -> str:
    items = sorted(weights.items(), key=lambda x: -x[1])
    lines = [f"*{label}*"]
    for ticker, w in items:
        if w > 0.001:
            lines.append(f"`  {ticker:<6}` {w*100*sleeve_weight:>5.1f}%")
    return "\n".join(lines)


def _fmt_weight_pct(weight: float) -> str:
    pct = weight * 100.0
    return f"{pct:.1f}".rstrip("0").rstrip(".")


def main() -> None:
    panel = load_panel(live=True)
    ndx_panel = load_ndx_panel()
    # Use last completed month-end as signal date
    today = pd.Timestamp.today().normalize()
    prior_me = (today.replace(day=1) - pd.Timedelta(days=1))
    candidates = panel.index[panel.index <= prior_me]
    sig_d = candidates[-1] if len(candidates) > 0 else today
    # Prior month's signal = last panel date on/before the prior calendar month-end
    prior_month_end = sig_d.replace(day=1) - pd.Timedelta(days=1)
    prior_cands = panel.index[panel.index <= prior_month_end]
    prior_sig_d = prior_cands[-1] if len(prior_cands) > 0 else None

    from sleeves import compute_live_blend, get_blend_weights
    blend_weights = get_blend_weights(sig_d)
    combined, res = compute_live_blend(panel, ndx_panel, sig_d)
    cpm_w, cpm_regime = res["cpm"].weights, res["cpm"].regime
    ndx_w, ndx_regime = res["ndx"].weights, res["ndx"].regime
    rpv_w, rpv_regime = res["rpv"].weights, res["rpv"].regime
    val_w, val_regime = res["val"].weights, res["val"].regime

    parts = []
    parts.append(f"📈 *CPM-NDX-VAL-RPV Monthly Signal*")
    parts.append(f"Signal date: `{sig_d.date()}` · Trade T+1 OPEN (MOO)")
    parts.append("")
    parts.append(f"CPM: {cpm_regime} · NDX: {ndx_regime} · VAL: {val_regime} · RPV: {rpv_regime}")

    if prior_sig_d is None:
        parts.append("Trades: first signal (no prior month)")
    else:
        combined_prior, _ = compute_live_blend(panel, ndx_panel, prior_sig_d)
        trades = []
        trade_threshold = 0.001
        for ticker in set(combined) | set(combined_prior):
            now_w = combined.get(ticker, 0.0)
            prior_w = combined_prior.get(ticker, 0.0)
            delta = now_w - prior_w
            if abs(delta) <= trade_threshold:
                continue
            if prior_w <= trade_threshold and now_w > trade_threshold:
                action = "BUY"
            elif prior_w > trade_threshold and now_w <= trade_threshold:
                action = "SELL"
            elif delta > 0:
                action = "ADD"
            else:
                action = "TRIM"
            trades.append((action, ticker, delta))

        if not trades:
            parts.append(f"*Trades vs {prior_sig_d.date()}*: no change from last month")
        else:
            action_order = {"SELL": 0, "BUY": 1, "TRIM": 2, "ADD": 3}
            trades.sort(key=lambda x: (action_order[x[0]], -abs(x[2]), x[1]))
            parts.append(f"*Trades vs {prior_sig_d.date()}*")
            for action, ticker, delta in trades:
                parts.append(f"`  {action:<4} {ticker:<6}` {delta*100:+5.1f}%")

    parts.append("")
    parts.append(fmt_alloc(cpm_w, f"CPM sleeve ({_fmt_weight_pct(blend_weights['cpm'])}%)", blend_weights["cpm"]))
    parts.append("")
    parts.append(fmt_alloc(ndx_w, f"NDX sleeve ({_fmt_weight_pct(blend_weights['ndx'])}%)", blend_weights["ndx"]))
    parts.append("")
    parts.append(fmt_alloc(val_w, f"VAL sleeve ({_fmt_weight_pct(blend_weights['val'])}%)", blend_weights["val"]))
    parts.append("")
    parts.append(fmt_alloc(rpv_w, f"RPV sleeve ({_fmt_weight_pct(blend_weights['rpv'])}%)", blend_weights["rpv"]))
    parts.append("")
    parts.append(fmt_alloc(combined, "Combined portfolio (100%)"))
    parts.append("")
    parts.append("⚠️ Backtest only · see dashboard caveats before trading")

    print("\n".join(parts))


if __name__ == "__main__":
    main()
