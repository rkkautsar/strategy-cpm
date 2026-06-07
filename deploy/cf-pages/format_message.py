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

from config import CPM_WEIGHT, NDX_WEIGHT, VAL_WEIGHT, RPV_WEIGHT


def fmt_alloc(weights: dict, label: str, sleeve_weight: float = 1.0) -> str:
    items = sorted(weights.items(), key=lambda x: -x[1])
    lines = [f"*{label}*"]
    for ticker, w in items:
        if w > 0.001:
            lines.append(f"`  {ticker:<6}` {w*100*sleeve_weight:>5.1f}%")
    return "\n".join(lines)


def main() -> None:
    panel = load_panel(live=True)
    ndx_panel = load_ndx_panel()
    # Use last completed month-end as signal date
    today = pd.Timestamp.today().normalize()
    prior_me = (today.replace(day=1) - pd.Timedelta(days=1))
    candidates = panel.index[panel.index <= prior_me]
    sig_d = candidates[-1] if len(candidates) > 0 else today

    from sleeves import compute_live_blend
    combined, res = compute_live_blend(panel, ndx_panel, sig_d)
    cpm_w, cpm_regime = res["cpm"].weights, res["cpm"].regime
    ndx_w, ndx_regime = res["ndx"].weights, res["ndx"].regime
    rpv_w, rpv_regime = res["rpv"].weights, res["rpv"].regime
    val_w, val_regime, val_picks = res["val"].weights, res["val"].regime, res["val"].picks

    parts = []
    parts.append(f"📈 *CPM-NDX-VAL-RPV Monthly Signal*")
    parts.append(f"Signal date: `{sig_d.date()}` · Trade T+1 OPEN (MOO)")
    parts.append("")
    parts.append(f"CPM: {cpm_regime} · NDX: {ndx_regime} · VAL: {val_regime} · RPV: {rpv_regime}")
    if val_picks:
        parts.append(f"_VAL picks: {', '.join(val_picks)}_")
    parts.append("")
    parts.append(fmt_alloc(cpm_w, "CPM sleeve (60%)", CPM_WEIGHT))
    parts.append("")
    parts.append(fmt_alloc(ndx_w, "NDX sleeve (15%)", NDX_WEIGHT))
    parts.append("")
    parts.append(fmt_alloc(val_w, "VAL sleeve (15%)", VAL_WEIGHT))
    parts.append("")
    parts.append(fmt_alloc(rpv_w, "RPV sleeve (10%)", RPV_WEIGHT))
    parts.append("")
    parts.append(fmt_alloc(combined, "Combined portfolio (100%)"))
    parts.append("")
    parts.append("⚠️ Backtest only · see dashboard caveats before trading")

    print("\n".join(parts))


if __name__ == "__main__":
    main()
